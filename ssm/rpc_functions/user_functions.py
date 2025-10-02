"""
User management RPC functions
"""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from ..exceptions import RequiredValueError
from ..models import User, SimCard, Subscription, OnboardingRequest

SSMAuthUser = get_user_model()


def get_users_with_sim_assignment(user, **args):
    """Get all users with their SIM card assignment counts (registered vs not registered)"""

    try:
        ssm_user = user
        if ssm_user.role not in ['admin', 'team_leader']:
            raise PermissionError("Only admins and team leaders can view user SIM assignments")

        # Filter users based on role
        if ssm_user.role == 'team_leader':
            # Team leaders can only see users in their team
            users_query = User.objects.filter(team=ssm_user.team).exclude(role='team_leader')
        else:
            # Admins can see all users
            users_query = User.objects.exclude(role='team_leader').all()

        users_with_assignments = []

        for ssm_user_item in users_query.select_related('auth_user', 'team'):
            # Get SIM card counts
            assigned_sim_cards = SimCard.objects.filter(assigned_to_user=ssm_user_item)

            total_assigned = assigned_sim_cards.count()
            registered_count = assigned_sim_cards.filter(registered_on__isnull=False).count()
            not_registered_count = assigned_sim_cards.filter(registered_on__isnull=True).count()

            users_with_assignments.append({
                'user_id': str(ssm_user_item.id),
                'name': f"{ssm_user_item.auth_user.first_name} {ssm_user_item.auth_user.last_name}".strip(),
                'email': ssm_user_item.auth_user.email,
                'username': ssm_user_item.auth_user.username,
                'role': ssm_user_item.role,
                'team_name': ssm_user_item.team.name if ssm_user_item.team else None,
                'is_active': ssm_user_item.is_active,
                'sim_assignment': {
                    'total_assigned': total_assigned,
                    'registered_count': registered_count,
                    'not_registered_count': not_registered_count,
                    'registration_rate': round((registered_count / total_assigned * 100) if total_assigned > 0 else 0,
                                               2)
                },
                'created_at': ssm_user_item.created_at.isoformat() if ssm_user_item.created_at else None,
            })

        # Sort by total assigned SIM cards (descending)
        users_with_assignments.sort(key=lambda x: x['sim_assignment']['total_assigned'], reverse=True)
        return {
            'users': users_with_assignments,
            'summary': {
                'total_users': len(users_with_assignments),
                'users_with_assignments': len(
                    [u for u in users_with_assignments if u['sim_assignment']['total_assigned'] > 0]),
                'total_sim_cards_assigned': sum(u['sim_assignment']['total_assigned'] for u in users_with_assignments),
                'total_registered': sum(u['sim_assignment']['registered_count'] for u in users_with_assignments),
                'total_not_registered': sum(
                    u['sim_assignment']['not_registered_count'] for u in users_with_assignments),
            }
        }

    except User.DoesNotExist:
        raise PermissionError("User profile not found")


def get_user_sim_details(user, target_user_id):
    """Get detailed SIM card information for a specific user"""
    try:
        ssm_user = user
        target_user = User.objects.get(id=target_user_id)
        # Check permissions
        if ssm_user.role == 'staff':
            if str(ssm_user.id) != target_user_id:
                raise PermissionError(" can only view their own data")
        elif ssm_user.role == 'team_leader':
            print("uis")
            if target_user.team != ssm_user.team:
                raise PermissionError("Team leaders can only view users in their team")
        # Admins can view any user

        # Get user's SIM cards with detailed information
        sim_cards = SimCard.objects.filter(assigned_to_user=target_user).select_related('batch')

        registered_sim_cards = []
        not_registered_sim_cards = []

        for sim_card in sim_cards:
            sim_data = {
                'id': str(sim_card.id),
                'serial_number': sim_card.serial_number,
                'phone_number': "sim_card.phone_number",
                'status': sim_card.status,
                'quality': sim_card.quality,
                'assigned_at': sim_card.assigned_on.isoformat() if sim_card.assigned_on else None,
                'activated_at': sim_card.activation_date.isoformat() if sim_card.activation_date else None,
                'registered_on': sim_card.registered_on.isoformat() if sim_card.registered_on else None,
                'batch_name': sim_card.batch.batch_id if sim_card.batch else None,
                'batch_id': str(sim_card.batch.id) if sim_card.batch else None,
                'notes': "sim_card.notes",
            }

            if sim_card.registered_on:
                registered_sim_cards.append(sim_data)
            else:
                not_registered_sim_cards.append(sim_data)

        # Calculate statistics
        total_assigned = len(sim_cards)
        registered_count = len(registered_sim_cards)
        not_registered_count = len(not_registered_sim_cards)
        registration_rate = round((registered_count / total_assigned * 100) if total_assigned > 0 else 0, 2)

        # Status breakdown
        status_breakdown = {}
        for sim_card in sim_cards:
            status = sim_card.status
            if status in status_breakdown:
                status_breakdown[status] += 1
            else:
                status_breakdown[status] = 1

        return {
            'user': {
                'id': str(target_user.id),
                'name': f"{target_user.auth_user.first_name} {target_user.auth_user.last_name}".strip(),
                'email': target_user.auth_user.email,
                'username': target_user.auth_user.username,
                'role': target_user.role,
                'team_name': target_user.team.name if target_user.team else None,
                'team_id': str(target_user.team.id) if target_user.team else None,
                'is_active': target_user.is_active,
                'created_at': target_user.created_at.isoformat() if target_user.created_at else None,
            },
            'statistics': {
                'total_assigned': total_assigned,
                'registered_count': registered_count,
                'not_registered_count': not_registered_count,
                'registration_rate': registration_rate,
                'status_breakdown': status_breakdown
            },
            'sim_cards': {
                'registered': registered_sim_cards,
                'not_registered': not_registered_sim_cards
            }
        }

    except User.DoesNotExist:
        if str(ssm_user.id) == target_user_id:
            raise PermissionError("User profile not found")
        else:
            raise PermissionError("Target user not found")


def get_auth_info(user):
    admin_user = user.admin if user.admin else user

    subscriptions = Subscription.objects.filter(
        user=admin_user,
        status='active',
        starts_at__lte=timezone.now(),
        expires_at__gt=timezone.now()
    ).select_related('user').order_by('-created_at')
    subscription_data = []
    for subscription in subscriptions:
        subscription_data.append({
            'id': str(subscription.id),
            'user_id': str(subscription.user.id),
            'plan_id': str(subscription.plan_id),
            'status': subscription.status,
            'starts_at': subscription.starts_at.isoformat(),
            'expires_at': subscription.expires_at.isoformat(),
            'payment_reference': subscription.payment_reference,
            'auto_renew': subscription.auto_renew,
            'cancellation_date': subscription.cancellation_date.isoformat() if subscription.cancellation_date else None,
            'cancellation_reason': subscription.cancellation_reason,
            'is_trial': subscription.is_trial,
            'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
            'trial_days': subscription.trial_days,
            'created_at': subscription.created_at.isoformat(),
            'updated_at': subscription.updated_at.isoformat(),
        })
    return {
        "user": {
            "id": user.id,
            "is_admin": user.admin is None,
            "super_account": True,
            "admin_user_id": str(admin_user.id),
        },
        "subscription": {
            'subscriptions': subscription_data,
            'has_active_subscription': len(subscription_data) > 0,
            'user_id': str(user.id)
        }
    }


def create_auth_user(user, data):
    """
    Create a new user with both SSMAuthUser (Django auth) and User (profile) records
    Expected data: {'email': str, 'full_name': str, 'phone_number': str, 'id_number': str, 'role': str, 'team_id': str}
    """
    from ..models import Team
    from django.contrib.auth.hashers import make_password
    from django.db import transaction
    import secrets
    import string
    if user.role not in ['admin']:
        raise PermissionError("Action denied")

    # Validate required fields
    required_fields = ['email', 'full_name', 'phone_number', 'id_number', 'role', 'team_id']
    for field in required_fields:
        if field not in data or not data[field]:
            raise ValueError(f"Missing required field: {field}")

    # Check if user already exists with this email or username
    if SSMAuthUser.objects.filter(email=data['email']).exists():
        raise ValueError(f"A user with email '{data['email']}' already exists")

    if SSMAuthUser.objects.filter(username=data['email']).exists():
        raise ValueError(f"A user with username '{data['email']}' already exists")

    # Also check if User profile exists with this email or id_number
    if User.objects.filter(email=data['email']).exists():
        raise ValueError(f"A user profile with email '{data['email']}' already exists")

    if User.objects.filter(id_number=data['id_number']).exists():
        raise ValueError(f"A user with ID number '{data['id_number']}' already exists")

    # Generate a secure temporary password
    def generate_temp_password(length=12):
        characters = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(characters) for _ in range(length))

    temp_password = generate_temp_password()

    try:
        with transaction.atomic():
            # Get the team
            try:
                team = Team.objects.get(id=data['team_id'])
            except Team.DoesNotExist:
                raise ValueError(f"Team with ID {data['team_id']} does not exist")
            except:
                raise RequiredValueError(f"A valid Team is required")

            # Create SSMAuthUser (Django auth user)
            auth_user = SSMAuthUser.objects.create_user(
                username=data['email'],
                email=data['email'],
                password=temp_password,
                first_name=data['full_name'].split()[0] if data['full_name'] else '',
                last_name=' '.join(data['full_name'].split()[1:]) if len(data['full_name'].split()) > 1 else '',
                is_active=True,
                email_confirmed=True,
                confirmed_at=timezone.now(),
                raw_user_meta_data={
                    'full_name': data['full_name'],
                    'role': data['role'],
                    'created_by_admin': True
                }
            )
            print("au", auth_user.id)
            # Create User profile record
            user_profile = User.objects.create(
                id=auth_user.id,
                email=data['email'],
                full_name=data['full_name'],
                phone_number=data['phone_number'],
                id_number=data['id_number'],
                role=data['role'],
                team=team,
                auth_user=auth_user,
                admin=user,  # Set the current user as admin
                status='ACTIVE',
                is_active=True,
                is_first_login=True,
                id_front_url='',  # Set empty as per the Next.js implementation
                id_back_url=''  # Set empty as per the Next.js implementation
            )

            return {
                'success': True,
                'user_id': str(user_profile.id),
                'auth_user_id': str(auth_user.id),
                'email': auth_user.email,
                'full_name': user_profile.full_name,
                'role': user_profile.role,
                'team_id': str(team.id),
                'team_name': team.name,
                'temp_password': temp_password,  # Include for admin to share with user
                'is_first_login': True,
                'created_at': user_profile.created_at.isoformat()
            }

    except Exception as e:
        raise ValueError(f"Failed to create user: {str(e)}")


def approve_onboarding_request(user, data):
    """
    Approve an onboarding request and create user account
    Expected data: {'id': str (request_id), 'reviewNotes': str (optional)}
    """
    from ..models import Team
    from django.db import transaction
    import secrets
    import string

    print("approve_onboarding_request", data)

    # Only admins and team leaders can approve requests
    if user.role not in ['admin', 'team_leader']:
        raise PermissionError("Only admins and team leaders can approve onboarding requests")

    # Validate required fields
    if 'id' not in data or not data['id']:
        raise ValueError("Missing required field: id (request_id)")

    request_id = data['id']
    review_notes = data.get('reviewNotes', 'Request approved and user created')

    try:
        with transaction.atomic():
            # Get the onboarding request
            try:
                request_obj = OnboardingRequest.objects.select_related(
                    'requested_by', 'requested_by__team', 'admin'
                ).get(id=request_id)
            except OnboardingRequest.DoesNotExist:
                raise ValueError(f"Onboarding request with ID {request_id} not found")

            # Check if request is still pending
            if request_obj.status != 'pending':
                raise ValueError(f"Request is already {request_obj.status}")

            # For team leaders, ensure they can only approve requests from their team
            if user.role == 'team_leader':
                if request_obj.requested_by.team != user.team:
                    raise PermissionError("Team leaders can only approve requests from their own team")

            # Extract user data from the request
            user_data = request_obj.user_data
            print("sss", user_data)

            # Validate required user data fields
            required_fields = ['full_name', 'id_number', 'role']

            # Append additional fields to check based on login method
            login_method = user_data.get('login_method', 'email')
            if login_method == 'email':
                required_fields.append('email')
            elif login_method == 'phone':
                required_fields.append('phone_number')  # Already in list but ensuring it's checked
            elif login_method == 'username':
                required_fields.append('username')
            elif login_method == 'both':
                # For 'both', require at least email, username, or phone
                if not (user_data.get('email') or user_data.get('username') or user_data.get('phone_number')):
                    raise ValueError(
                        "For login method 'both', at least one of email, username, or phone_number is required")

            for field in required_fields:
                if field not in user_data or not user_data[field]:
                    raise ValueError(f"Missing required user data field: {field}")

            # Check if user already exists - if so, automatically reject the request
            rejection_reason = None

            if user_data.get('email') and SSMAuthUser.objects.filter(email=user_data['email']).exists():
                rejection_reason = f"A user with email '{user_data['email']}' already exists"
            elif user_data.get('email') and User.objects.filter(email=user_data['email']).exists():
                rejection_reason = f"A user profile with email '{user_data['email']}' already exists"
            elif user_data.get('id_number') and User.objects.filter(id_number=user_data['id_number']).exists():
                rejection_reason = f"A user with ID number '{user_data['id_number']}' already exists"
            elif user_data.get('username') and SSMAuthUser.objects.filter(username=user_data['username']).exists():
                rejection_reason = f"A user with username '{user_data['username']}' already exists"
            elif user_data.get('phone_number') and User.objects.filter(phone_number=user_data['phone_number']).exists():
                rejection_reason = f"A user with phone number '{user_data['phone_number']}' already exists"

            # If user already exists, reject the request automatically
            if rejection_reason:
                request_obj.status = 'rejected'
                request_obj.review_notes = f"Auto-rejected: {rejection_reason}"
                request_obj.review_date = timezone.now()
                request_obj.reviewed_by = user
                request_obj.save()

                return {
                    'success': False,
                    'message': 'Request automatically rejected due to existing user',
                    'reason': rejection_reason,
                    'request': {
                        'request_id': str(request_obj.id),
                        'status': request_obj.status,
                        'review_date': request_obj.review_date.isoformat(),
                        'reviewed_by': user.full_name,
                        'review_notes': request_obj.review_notes
                    }
                }

            # Generate secure temporary password
            def generate_temp_password(length=12):
                characters = string.ascii_letters + string.digits + "!@#$%^&*"
                return ''.join(secrets.choice(characters) for _ in range(length))

            # Determine login credential and password based on login method
            login_method = user_data.get('login_method', 'email')

            if login_method == 'email':
                credential = user_data['email']
                temp_password = user_data['email']  # Use email as default password
            elif login_method == 'username':
                credential = user_data.get('username', user_data['email'])
                temp_password = credential
            elif login_method == 'phone':
                credential = user_data['phone_number']
                temp_password = credential
            elif login_method == 'both':
                credential = user_data['email'] or user_data.get('username') or user_data['phone_number']
                temp_password = credential
            else:
                # Default fallback
                credential = user_data['email']
                temp_password = generate_temp_password()

            # Get the team (use requested_by's team if team_id not specified)
            team_id = user_data.get('team_id') or str(request_obj.requested_by.team.id)
            try:
                team = Team.objects.get(id=team_id)
            except Team.DoesNotExist:
                raise ValueError(f"Team with ID {team_id} does not exist")

            # Create SSMAuthUser (Django auth user)
            auth_user = SSMAuthUser.objects.create_user(
                username=credential,
                email=user_data['email'],
                password=temp_password,
                first_name=user_data['full_name'].split()[0] if user_data['full_name'] else '',
                last_name=' '.join(user_data['full_name'].split()[1:]) if len(
                    user_data['full_name'].split()) > 1 else '',
                is_active=True,
                email_confirmed=True,
                confirmed_at=timezone.now(),
                raw_user_meta_data={
                    'full_name': user_data['full_name'],
                    'role': user_data['role'],
                    'approved_from_request': True,
                    'request_id': str(request_id),
                    'login_method': login_method
                }
            )

            # Create User profile record
            user_profile = User.objects.create(
                id=auth_user.id,  # Use same UUID as auth user
                email=user_data['email'],
                full_name=user_data['full_name'],
                phone_number=user_data.get('phone_number'),
                id_number=user_data['id_number'],
                username=user_data.get('username', ''),
                mobigo_number=user_data.get('mobigo_number', ''),
                role='staff',  # Set role as staff for approved onboarding requests
                team=team,
                auth_user=auth_user,
                admin=request_obj.admin,  # Use the admin from the request
                status='ACTIVE',
                is_active=True,
                is_first_login=True,
                staff_type=user_data.get('staff_type', ''),
                id_front_url=user_data.get('id_front_url', ''),
                id_back_url=user_data.get('id_back_url', '')
            )

            # Update the onboarding request status
            request_obj.status = 'approved'
            request_obj.review_notes = review_notes
            request_obj.review_date = timezone.now()
            request_obj.reviewed_by = user
            request_obj.save()

            return {
                'success': True,
                'message': 'User request approved and account created successfully',
                'user': {
                    'user_id': str(user_profile.id),
                    'auth_user_id': str(auth_user.id),
                    'email': auth_user.email,
                    'full_name': user_profile.full_name,
                    'role': user_profile.role,
                    'team_id': str(team.id),
                    'team_name': team.name,
                    'temp_password': temp_password,
                    'is_first_login': True,
                    'created_at': user_profile.created_at.isoformat()
                },
                'request': {
                    'request_id': str(request_obj.id),
                    'status': request_obj.status,
                    'review_date': request_obj.review_date.isoformat(),
                    'reviewed_by': user.full_name,
                    'review_notes': review_notes
                }
            }

    except Exception as e:
        raise ValueError(f"Failed to approve onboarding request: {str(e)}")


def check_user_before_request(user, data):
    """
    Check if a user exists before creating an onboarding request
    Expected data: {'login_method': str, 'credential': str}
    """
    from django.db.models import Q

    print("check_user_before_request", data)

    # Validate required fields
    if 'login_method' not in data or not data['login_method']:
        raise ValueError("Missing required field: login_method")

    if 'credential' not in data or not data['credential']:
        raise ValueError("Missing required field: credential")

    login_method = data['login_method']
    credential = data['credential']

    # Check if user exists in both SSMAuthUser and User models
    try:
        auth_user_exists = False
        profile_user_exists = False

        if login_method == 'email':
            # Check by email
            auth_user_exists = SSMAuthUser.objects.filter(
                Q(email=credential) | Q(username=credential)
            ).exists()
            profile_user_exists = User.objects.filter(email=credential).exists()

        elif login_method == 'username':
            # Check by username
            auth_user_exists = SSMAuthUser.objects.filter(username=credential).exists()
            profile_user_exists = User.objects.filter(username=credential).exists()

        elif login_method == 'phone':
            # Check by phone number
            auth_user_exists = SSMAuthUser.objects.filter(
                username=credential).exists()  # Phone might be used as username
            profile_user_exists = User.objects.filter(phone_number=credential).exists()

        elif login_method == 'both':
            # Check across email, username, and phone
            auth_user_exists = SSMAuthUser.objects.filter(
                Q(email=credential) | Q(username=credential)
            ).exists()
            profile_user_exists = User.objects.filter(
                Q(email=credential) | Q(username=credential) | Q(phone_number=credential)
            ).exists()

        user_exists = auth_user_exists or profile_user_exists

        return {
            'success': True,
            'user_exists': user_exists,
            'auth_user_exists': auth_user_exists,
            'profile_user_exists': profile_user_exists,
            'login_method': login_method,
            'credential': credential,
            'message': 'User check completed successfully'
        }

    except Exception as e:
        raise ValueError(f"Failed to check user: {str(e)}")


# Register functions
functions = {
    'get_users_with_sim_assignment': get_users_with_sim_assignment,
    'get_user_sim_details': get_user_sim_details,
    'get_auth_info': get_auth_info,
    'check_user_before_request': check_user_before_request,
    'approve_onboarding_request': approve_onboarding_request,
    'create_auth_user': create_auth_user,
}
