"""
SIM Card management RPC functions
"""
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from django.utils import timezone
from ..models import User, SimCard, BatchMetadata, SimCardTransfer

SSMAuthUser = get_user_model()


def get_available_sim_cards(user: 'SSMAuthUser', batch_id=None):
    """Get available SIM cards for assignment"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        if ssm_user.role not in ['admin', 'team_leader']:
            raise PermissionError("Only admins and team leaders can view available SIM cards")

        query = Q(status='available')
        if batch_id:
            query &= Q(batch_metadata_id=batch_id)

        sim_cards = SimCard.objects.filter(query).select_related('batch_metadata')

        return [
            {
                'id': str(sim.id),
                'serial_number': sim.serial_number,
                'phone_number': sim.phone_number,
                'batch_id': str(sim.batch_metadata.id) if sim.batch_metadata else None,
                'batch_name': sim.batch_metadata.batch_name if sim.batch_metadata else None,
                'quality': sim.quality,
                'created_at': sim.created_at.isoformat() if sim.created_at else None,
            }
            for sim in sim_cards
        ]
    except User.DoesNotExist:
        raise PermissionError("User profile not found")


def assign_sim_cards(user, sim_card_ids, assignee_id):
    """Assign multiple SIM cards to a Business Associate"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        if ssm_user.role not in ['admin', 'team_leader']:
            raise PermissionError("Only admins and team leaders can assign SIM cards")

        # Get assignee
        assignee = User.objects.get(id=assignee_id)
        if assignee.role != 'business_associate':
            raise ValueError("Can only assign SIM cards to Business Associates")

        # Check if team leader is trying to assign to someone outside their team
        if ssm_user.role == 'team_leader':
            if assignee.team != ssm_user.team:
                raise PermissionError("Team leaders can only assign to members of their own team")

        # Get SIM cards and check availability
        sim_cards = SimCard.objects.filter(id__in=sim_card_ids, status='available')
        if len(sim_cards) != len(sim_card_ids):
            return {'error': 'Some SIM cards are not available for assignment'}

        # Perform assignment
        assigned_count = 0
        for sim_card in sim_cards:
            sim_card.assigned_to = assignee
            sim_card.status = 'assigned'
            sim_card.assigned_at = timezone.now()
            sim_card.save()

            # Create transfer record
            SimCardTransfer.objects.create(
                sim_card=sim_card,
                from_user=None,
                to_user=assignee,
                transfer_type='assignment',
                transferred_by=ssm_user
            )
            assigned_count += 1

        return {
            'success': True,
            'assigned_count': assigned_count,
            'assignee': {
                'id': str(assignee.id),
                'name': f"{assignee.auth_user.first_name} {assignee.auth_user.last_name}".strip(),
                'email': assignee.auth_user.email,
            }
        }

    except User.DoesNotExist:
        return {'error': 'User not found'}
    except Exception as e:
        return {'error': str(e)}


def get_my_sim_cards(user):
    """Get SIM cards assigned to the current user"""
    try:
        ssm_user = User.objects.get(auth_user=user)

        sim_cards = SimCard.objects.filter(assigned_to=ssm_user).select_related('batch_metadata')

        return [
            {
                'id': str(sim.id),
                'serial_number': sim.serial_number,
                'phone_number': sim.phone_number,
                'status': sim.status,
                'quality': sim.quality,
                'assigned_at': sim.assigned_at.isoformat() if sim.assigned_at else None,
                'activated_at': sim.activated_at.isoformat() if sim.activated_at else None,
                'batch_name': sim.batch_metadata.batch_name if sim.batch_metadata else None,
            }
            for sim in sim_cards
        ]
    except User.DoesNotExist:
        return {'error': 'User profile not found'}


def update_sim_card_status(user, sim_card_id, new_status, notes=None):
    """Update SIM card status"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        sim_card = SimCard.objects.get(id=sim_card_id)

        # Check permissions
        if ssm_user.role == 'business_associate':
            if sim_card.assigned_to != ssm_user:
                raise PermissionError("You can only update your own SIM cards")
        elif ssm_user.role == 'team_leader':
            if sim_card.assigned_to.team != ssm_user.team:
                raise PermissionError("Team leaders can only update SIM cards within their team")

        # Validate status transition
        valid_statuses = ['available', 'assigned', 'active', 'inactive', 'damaged', 'lost']
        if new_status not in valid_statuses:
            return {'error': f'Invalid status. Must be one of: {valid_statuses}'}

        old_status = sim_card.status
        sim_card.status = new_status

        # Set timestamps based on status
        if new_status == 'active' and old_status != 'active':
            sim_card.activated_at = timezone.now()

        if notes:
            sim_card.notes = notes

        sim_card.save()

        return {
            'success': True,
            'sim_card_id': str(sim_card.id),
            'old_status': old_status,
            'new_status': new_status,
            'updated_at': timezone.now().isoformat()
        }

    except User.DoesNotExist:
        return {'error': 'User profile not found'}
    except SimCard.DoesNotExist:
        return {'error': 'SIM card not found'}


def get_sim_card_by_serial(user, serial_number):
    """Find SIM card by serial number"""
    try:
        ssm_user = User.objects.get(auth_user=user)

        sim_card = SimCard.objects.get(serial_number=serial_number)

        # Check permissions
        if ssm_user.role == 'business_associate':
            if sim_card.assigned_to != ssm_user:
                raise PermissionError("You can only view your own SIM cards")
        elif ssm_user.role == 'team_leader':
            if sim_card.assigned_to and sim_card.assigned_to.team != ssm_user.team:
                raise PermissionError("Team leaders can only view SIM cards within their team")

        return {
            'id': str(sim_card.id),
            'serial_number': sim_card.serial_number,
            'phone_number': sim_card.phone_number,
            'status': sim_card.status,
            'quality': sim_card.quality,
            'assigned_to': {
                'id': str(sim_card.assigned_to.id),
                'name': f"{sim_card.assigned_to.auth_user.first_name} {sim_card.assigned_to.auth_user.last_name}".strip(),
                'email': sim_card.assigned_to.auth_user.email,
            } if sim_card.assigned_to else None,
            'assigned_at': sim_card.assigned_at.isoformat() if sim_card.assigned_at else None,
            'activated_at': sim_card.activated_at.isoformat() if sim_card.activated_at else None,
            'batch_name': sim_card.batch_metadata.batch_name if sim_card.batch_metadata else None,
        }

    except User.DoesNotExist:
        return {'error': 'User profile not found'}
    except SimCard.DoesNotExist:
        return {'error': 'SIM card not found'}


# Register functions
functions = {
    'get_available_sim_cards': get_available_sim_cards,
    'assign_sim_cards': assign_sim_cards,
    'get_my_sim_cards': get_my_sim_cards,
    'update_sim_card_status': update_sim_card_status,
    'get_sim_card_by_serial': get_sim_card_by_serial,
}
