def create_team_group(user, data):
    """
    Create a team group with members using TeamGroupMembership
    Expected data: {'team_id': str, 'name': str, 'description': str, 'location': str, 'is_active': bool, 'member_ids': list}
    """
    from django.db import transaction
    from ..models import TeamGroup, TeamGroupMembership, User, Team
    
    # Check permissions
    if user.role not in ['admin', 'team_leader']:
        raise PermissionError("Only admins and team leaders can create team groups")
    
    # Validate required fields
    required_fields = ['team_id', 'name', 'location', 'member_ids']
    for field in required_fields:
        if field not in data or not data[field]:
            raise ValueError(f"Missing required field: {field}")
    
    if not isinstance(data['member_ids'], list) or len(data['member_ids']) == 0:
        raise ValueError("At least one member is required")
    
    try:
        with transaction.atomic():
            # Verify team exists and user has access
            try:
                team = Team.objects.get(id=data['team_id'])
                if user.role == 'team_leader' and user.team != team:
                    raise PermissionError("Team leaders can only create groups in their own team")
            except Team.DoesNotExist:
                raise ValueError(f"Team with ID {data['team_id']} not found")
            
            # Create the team group
            team_group = TeamGroup.objects.create(
                team=team,
                name=data['name'].strip(),
                description=data.get('description', '').strip() or None,
                location=data['location'],
                is_active=data.get('is_active', True),
                admin=user
            )
            
            # Verify members exist and belong to the team
            members = User.objects.filter(
                id__in=data['member_ids'],
                team=team
            )

            if members.count() != len(data['member_ids']):
                raise ValueError(f"Could only find {members.count()} of {len(data['member_ids'])} members. Check member IDs and team membership.")

            # Remove members from any existing groups (a user can only be in one group at a time)
            existing_memberships = TeamGroupMembership.objects.filter(
                user__in=members
            ).select_related('group')

            # Track which members were moved from other groups
            moved_members = []
            for membership in existing_memberships:
                moved_members.append({
                    'user_id': str(membership.user.id),
                    'user_name': membership.user.full_name,
                    'old_group_id': str(membership.group.id),
                    'old_group_name': membership.group.name
                })

            # Delete existing memberships
            if existing_memberships.exists():
                existing_memberships.delete()

            # Create new memberships
            memberships = [
                TeamGroupMembership(group=team_group, user=member)
                for member in members
            ]
            TeamGroupMembership.objects.bulk_create(memberships)
            
            return {
                'success': True,
                'group': {
                    'id': str(team_group.id),
                    'name': team_group.name,
                    'description': team_group.description,
                    'location': team_group.location,
                    'is_active': team_group.is_active,
                    'team_id': str(team.id),
                    'team_name': team.name,
                    'member_count': len(memberships),
                    'created_at': team_group.created_at.isoformat()
                },
                'members': [{
                    'id': str(member.id),
                    'full_name': member.full_name,
                    'email': member.email,
                    'phone_number': member.phone_number
                } for member in members],
                'moved_members': moved_members,
                'moved_count': len(moved_members)
            }
            
    except Exception as e:
        raise ValueError(f"Failed to create team group: {str(e)}")


def get_group_members(user, group_id):
    """
    Get all members of a team group
    Expected params: group_id (str)
    """
    from ..models import TeamGroup, TeamGroupMembership

    # Check permissions
    if user.role not in ['admin', 'team_leader', 'staff']:
        raise PermissionError("Unauthorized to view group members")

    if not group_id:
        raise ValueError("group_id is required")

    try:
        # Get the team group
        try:
            team_group = TeamGroup.objects.select_related('team').get(id=group_id)
        except TeamGroup.DoesNotExist:
            raise ValueError(f"Team group with ID {group_id} not found")

        # Check if user has access to this group
        if user.role == 'team_leader' and user.team != team_group.team:
            raise PermissionError("Team leaders can only view groups in their own team")
        elif user.role == 'staff' and user.team != team_group.team:
            raise PermissionError("You can only view groups in your own team")

        # Get all members of the group
        memberships = TeamGroupMembership.objects.filter(
            group=team_group
        ).select_related('user', 'user__auth_user')

        members = []
        for membership in memberships:
            member = membership.user
            members.append({
                'id': str(member.id),
                'full_name': member.full_name,
                'email': member.email,
                'phone_number': member.phone_number,
                'role': member.role,
                'is_active': member.is_active,
                'joined_group_at': membership.joined_at.isoformat()
            })

        return {
            'success': True,
            'group': {
                'id': str(team_group.id),
                'name': team_group.name,
                'description': team_group.description,
                'location': team_group.location
            },
            'members': members,
            'count': len(members)
        }

    except Exception as e:
        raise ValueError(f"Failed to get group members: {str(e)}")


def add_members_to_group(user, data):
    """
    Add members to a team group
    Expected data: {'group_id': str, 'member_ids': list}
    """
    from django.db import transaction
    from ..models import TeamGroup, TeamGroupMembership, User

    # Check permissions
    if user.role not in ['admin', 'team_leader']:
        raise PermissionError("Only admins and team leaders can add members to groups")

    # Validate required fields
    if 'group_id' not in data or not data['group_id']:
        raise ValueError("group_id is required")

    if 'member_ids' not in data or not isinstance(data['member_ids'], list) or len(data['member_ids']) == 0:
        raise ValueError("At least one member_id is required")

    try:
        with transaction.atomic():
            # Get the team group
            try:
                team_group = TeamGroup.objects.select_related('team').get(id=data['group_id'])
            except TeamGroup.DoesNotExist:
                raise ValueError(f"Team group with ID {data['group_id']} not found")

            # Check permissions
            if user.role == 'team_leader' and user.team != team_group.team:
                raise PermissionError("Team leaders can only manage groups in their own team")

            # Verify members exist and belong to the team
            members = User.objects.filter(
                id__in=data['member_ids'],
                team=team_group.team
            ).exclude(role__in=['admin', 'team_leader'])

            if members.count() != len(data['member_ids']):
                raise ValueError(f"Could only find {members.count()} of {len(data['member_ids'])} members in the team")

            # Get existing memberships in THIS group to avoid duplicates
            existing_member_ids = set(
                TeamGroupMembership.objects.filter(
                    group=team_group,
                    user__in=members
                ).values_list('user_id', flat=True)
            )

            # Get members not already in this group
            members_to_add = [m for m in members if m.id not in existing_member_ids]

            # Remove these members from any OTHER groups (a user can only be in one group)
            moved_members = []
            if members_to_add:
                existing_other_memberships = TeamGroupMembership.objects.filter(
                    user__in=members_to_add
                ).exclude(group=team_group).select_related('group', 'user')

                for membership in existing_other_memberships:
                    moved_members.append({
                        'user_id': str(membership.user.id),
                        'user_name': membership.user.full_name,
                        'old_group_id': str(membership.group.id),
                        'old_group_name': membership.group.name
                    })

                # Delete memberships in other groups
                if existing_other_memberships.exists():
                    existing_other_memberships.delete()

            # Create new memberships for members not already in the group
            new_memberships = [
                TeamGroupMembership(group=team_group, user=member)
                for member in members_to_add
            ]

            if new_memberships:
                TeamGroupMembership.objects.bulk_create(new_memberships)

            return {
                'success': True,
                'added_count': len(new_memberships),
                'already_members': len(existing_member_ids & set(m.id for m in members)),
                'moved_members': moved_members,
                'moved_count': len(moved_members),
                'message': f'Successfully added {len(new_memberships)} member(s) to {team_group.name}'
            }

    except Exception as e:
        raise ValueError(f"Failed to add members to group: {str(e)}")


def remove_member_from_group(user, data):
    """
    Remove a member from a team group
    Expected data: {'group_id': str, 'member_id': str}
    """
    from django.db import transaction
    from ..models import TeamGroup, TeamGroupMembership

    # Check permissions
    if user.role not in ['admin', 'team_leader']:
        raise PermissionError("Only admins and team leaders can remove members from groups")

    # Validate required fields
    if 'group_id' not in data or not data['group_id']:
        raise ValueError("group_id is required")

    if 'member_id' not in data or not data['member_id']:
        raise ValueError("member_id is required")

    try:
        with transaction.atomic():
            # Get the team group
            try:
                team_group = TeamGroup.objects.select_related('team').get(id=data['group_id'])
            except TeamGroup.DoesNotExist:
                raise ValueError(f"Team group with ID {data['group_id']} not found")

            # Check permissions
            if user.role == 'team_leader' and user.team != team_group.team:
                raise PermissionError("Team leaders can only manage groups in their own team")

            # Remove the membership
            deleted_count, _ = TeamGroupMembership.objects.filter(
                group=team_group,
                user_id=data['member_id']
            ).delete()

            if deleted_count == 0:
                raise ValueError(f"Member {data['member_id']} is not in this group")

            return {
                'success': True,
                'message': f'Successfully removed member from {team_group.name}'
            }

    except Exception as e:
        raise ValueError(f"Failed to remove member from group: {str(e)}")


def get_available_members(user, data):
    """
    Get available members who can be added to a team group
    Expected data: {'team_id': str, 'exclude_group_id': str (optional)}
    """
    from ..models import User, TeamGroupMembership, Team
    from django.db.models import Q

    # Check permissions
    if user.role not in ['admin', 'team_leader']:
        raise PermissionError("Only admins and team leaders can view available members")

    # Validate required fields
    if 'team_id' not in data or not data['team_id']:
        raise ValueError("team_id is required")

    try:
        # Get the team
        try:
            team = Team.objects.get(id=data['team_id'])
        except Team.DoesNotExist:
            raise ValueError(f"Team with ID {data['team_id']} not found")

        # Check permissions
        if user.role == 'team_leader' and user.team != team:
            raise PermissionError("Team leaders can only view members from their own team")

        # Start with all van_staff members in the team
        available_members = User.objects.filter(
            team=team,
            staff_type='van_staff',
            is_active=True
        ).select_related('auth_user')

        # If excluding a specific group, filter out its members
        if data.get('exclude_group_id'):
            # Get member IDs already in the specified group
            group_member_ids = TeamGroupMembership.objects.filter(
                group_id=data['exclude_group_id']
            ).values_list('user_id', flat=True)

            available_members = available_members.exclude(id__in=group_member_ids)

        members = []
        for member in available_members:
            # Check if member is in any group
            current_group = TeamGroupMembership.objects.filter(
                user=member
            ).select_related('group').first()

            members.append({
                'id': str(member.id),
                'full_name': member.full_name,
                'email': member.email,
                'phone_number': member.phone_number,
                'role': member.role,
                'is_active': member.is_active,
                'team_group': str(current_group.group.id) if current_group else None,
                'team_group_name': current_group.group.name if current_group else None
            })

        return {
            'success': True,
            'members': members,
            'count': len(members),
            'team_id': str(team.id),
            'team_name': team.name
        }

    except Exception as e:
        raise ValueError(f"Failed to get available members: {str(e)}")


def get_team_groups_with_members(user, data):
    """
    Get all team groups with their members for a specific team
    Expected data: {'team_id': str}
    """
    from ..models import TeamGroup, TeamGroupMembership, Team

    # Check permissions
    if user.role not in ['admin', 'team_leader']:
        raise PermissionError("Only admins and team leaders can view team groups")

    # Validate required fields
    if 'team_id' not in data or not data['team_id']:
        raise ValueError("team_id is required")

    try:
        # Get the team
        try:
            team = Team.objects.get(id=data['team_id'])
        except Team.DoesNotExist:
            raise ValueError(f"Team with ID {data['team_id']} not found")

        # Check permissions
        if user.role == 'team_leader' and user.team != team:
            raise PermissionError("Team leaders can only view their own team's groups")

        # Get all groups for the team
        team_groups = TeamGroup.objects.filter(
            team=team
        ).select_related('team', 'admin').order_by('-created_at')

        groups = []
        for group in team_groups:
            # Get members for this group
            memberships = TeamGroupMembership.objects.filter(
                group=group
            ).select_related('user')

            members = []
            for membership in memberships:
                member = membership.user
                members.append({
                    'id': str(member.id),
                    'full_name': member.full_name,
                    'email': member.email,
                    'phone_number': member.phone_number,
                    'role': member.role,
                    'is_active': member.is_active,
                    'joined_group_at': membership.joined_at.isoformat()
                })

            groups.append({
                'id': str(group.id),
                'name': group.name,
                'description': group.description,
                'location': group.location,
                'is_active': group.is_active,
                'team_id': str(group.team.id),
                'team_name': group.team.name,
                'admin_id': str(group.admin.id) if group.admin else None,
                'admin_name': group.admin.full_name if group.admin else None,
                'created_at': group.created_at.isoformat(),
                'updated_at': group.updated_at.isoformat(),
                'members': members,
                'member_count': len(members)
            })

        return {
            'success': True,
            'groups': groups,
            'count': len(groups),
            'team_id': str(team.id),
            'team_name': team.name,
            'statistics': {
                'total_groups': len(groups),
                'active_groups': len([g for g in groups if g['is_active']]),
                'total_members': sum(g['member_count'] for g in groups)
            }
        }

    except Exception as e:
        raise ValueError(f"Failed to get team groups: {str(e)}")


def get_team_members_with_groups(user, data):
    """
    Get all team members with their group information for assignment
    Expected data: {'team_id': str, 'exclude_group_id': str (optional)}
    """
    from ..models import User, TeamGroupMembership, Team

    # Check permissions
    if user.role not in ['admin', 'team_leader']:
        raise PermissionError("Only admins and team leaders can view team members")

    # Validate required fields
    if 'team_id' not in data or not data['team_id']:
        raise ValueError("team_id is required")

    try:
        # Get the team
        try:
            team = Team.objects.get(id=data['team_id'])
        except Team.DoesNotExist:
            raise ValueError(f"Team with ID {data['team_id']} not found")

        # Check permissions
        if user.role == 'team_leader' and user.team != team:
            raise PermissionError("Team leaders can only view members from their own team")

        # Get all active van_staff members in the team
        team_members = User.objects.filter(
            team=team,
            staff_type='van_staff',
            is_active=True
        ).select_related('auth_user')

        # If excluding a specific group, filter out its members
        if data.get('exclude_group_id'):
            # Get member IDs already in the specified group
            excluded_member_ids = TeamGroupMembership.objects.filter(
                group_id=data['exclude_group_id']
            ).values_list('user_id', flat=True)

            team_members = team_members.exclude(id__in=excluded_member_ids)

        members = []
        for member in team_members:
            # Check if member is in any group
            current_membership = TeamGroupMembership.objects.filter(
                user=member
            ).select_related('group').first()

            members.append({
                'id': str(member.id),
                'full_name': member.full_name,
                'email': member.email,
                'phone_number': member.phone_number,
                'role': member.role,
                'staff_type': member.staff_type,
                'is_active': member.is_active,
                'team_group': str(current_membership.group.id) if current_membership else None,
                'team_group_name': current_membership.group.name if current_membership else None
            })

        return {
            'success': True,
            'members': members,
            'count': len(members),
            'team_id': str(team.id),
            'team_name': team.name
        }

    except Exception as e:
        raise ValueError(f"Failed to get team members: {str(e)}")


functions = {
    'create_team_group': create_team_group,
    'get_group_members': get_group_members,
    'add_members_to_group': add_members_to_group,
    'remove_member_from_group': remove_member_from_group,
    'get_available_members': get_available_members,
    'get_team_groups_with_members': get_team_groups_with_members,
    'get_team_members_with_groups': get_team_members_with_groups,
}
