"""
Batch management RPC functions
"""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from ..models import User, BatchMetadata, SimCard, LotMetadata

SSMAuthUser = get_user_model()


def get_available_batches(user):
    """Get all batches with available SIM cards"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        if ssm_user.role not in ['admin', 'team_leader']:
            raise PermissionError("Only admins and team leaders can view batch information")

        batches = BatchMetadata.objects.annotate(
            total_sim_cards=Count('simcard'),
            available_sim_cards=Count('simcard', filter=Q(simcard__status='available')),
            assigned_sim_cards=Count('simcard', filter=Q(simcard__status='assigned')),
            active_sim_cards=Count('simcard', filter=Q(simcard__status='active'))
        ).order_by('-created_at')

        return [
            {
                'id': str(batch.id),
                'batch_name': batch.batch_name,
                'batch_number': batch.batch_number,
                'upload_date': batch.upload_date.isoformat() if batch.upload_date else None,
                'total_sim_cards': batch.total_sim_cards,
                'available_sim_cards': batch.available_sim_cards,
                'assigned_sim_cards': batch.assigned_sim_cards,
                'active_sim_cards': batch.active_sim_cards,
                'created_at': batch.created_at.isoformat() if batch.created_at else None,
            }
            for batch in batches if batch.available_sim_cards > 0  # Only show batches with available cards
        ]
    except User.DoesNotExist:
        raise PermissionError("User profile not found")


def get_batch_details(user, batch_id):
    """Get detailed information about a specific batch"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        if ssm_user.role not in ['admin', 'team_leader']:
            raise PermissionError("Only admins and team leaders can view batch details")

        batch = BatchMetadata.objects.get(id=batch_id)

        # Get SIM card statistics
        sim_cards = SimCard.objects.filter(batch_metadata=batch)
        total_count = sim_cards.count()
        available_count = sim_cards.filter(status='available').count()
        assigned_count = sim_cards.filter(status='assigned').count()
        active_count = sim_cards.filter(status='active').count()
        inactive_count = sim_cards.filter(status='inactive').count()

        # Get recent SIM cards from this batch
        recent_sim_cards = sim_cards.order_by('-created_at')[:10]
        sim_card_data = [
            {
                'id': str(sim.id),
                'serial_number': sim.serial_number,
                'phone_number': sim.phone_number,
                'status': sim.status,
                'quality': sim.quality,
                'assigned_to': {
                    'name': f"{sim.assigned_to.auth_user.first_name} {sim.assigned_to.auth_user.last_name}".strip(),
                    'email': sim.assigned_to.auth_user.email,
                } if sim.assigned_to else None,
                'assigned_at': sim.assigned_at.isoformat() if sim.assigned_at else None,
            }
            for sim in recent_sim_cards
        ]

        return {
            'batch': {
                'id': str(batch.id),
                'batch_name': batch.batch_name,
                'batch_number': batch.batch_number,
                'upload_date': batch.upload_date.isoformat() if batch.upload_date else None,
                'created_at': batch.created_at.isoformat() if batch.created_at else None,
            },
            'statistics': {
                'total_count': total_count,
                'available_count': available_count,
                'assigned_count': assigned_count,
                'active_count': active_count,
                'inactive_count': inactive_count,
                'utilization_rate': round((assigned_count + active_count) / total_count * 100) if total_count > 0 else 0
            },
            'recent_sim_cards': sim_card_data
        }

    except User.DoesNotExist:
        raise PermissionError("User profile not found")
    except BatchMetadata.DoesNotExist:
        return {'error': 'Batch not found'}


def get_batch_assignment_summary(user):
    """Get summary of SIM card assignments across all batches"""
    try:
        ssm_user = User.objects.get(auth_user=user)
        if ssm_user.role != 'admin':
            raise PermissionError("Only admins can view batch assignment summary")

        batches = BatchMetadata.objects.annotate(
            total_sim_cards=Count('simcard'),
            available_sim_cards=Count('simcard', filter=Q(simcard__status='available')),
            assigned_sim_cards=Count('simcard', filter=Q(simcard__status='assigned')),
            active_sim_cards=Count('simcard', filter=Q(simcard__status='active')),
            inactive_sim_cards=Count('simcard', filter=Q(simcard__status='inactive')),
        ).order_by('-upload_date')

        summary_data = []
        total_sim_cards_all = 0
        total_available_all = 0
        total_assigned_all = 0
        total_active_all = 0

        for batch in batches:
            total_sim_cards_all += batch.total_sim_cards
            total_available_all += batch.available_sim_cards
            total_assigned_all += batch.assigned_sim_cards
            total_active_all += batch.active_sim_cards

            utilization_rate = round(
                ((batch.assigned_sim_cards + batch.active_sim_cards) / batch.total_sim_cards * 100)
                if batch.total_sim_cards > 0 else 0
            )

            summary_data.append({
                'batch_id': str(batch.id),
                'batch_name': batch.batch_name,
                'batch_number': batch.batch_number,
                'upload_date': batch.upload_date.isoformat() if batch.upload_date else None,
                'total_sim_cards': batch.total_sim_cards,
                'available_sim_cards': batch.available_sim_cards,
                'assigned_sim_cards': batch.assigned_sim_cards,
                'active_sim_cards': batch.active_sim_cards,
                'inactive_sim_cards': batch.inactive_sim_cards,
                'utilization_rate': utilization_rate
            })

        return {
            'batches': summary_data,
            'overall_summary': {
                'total_sim_cards': total_sim_cards_all,
                'available_sim_cards': total_available_all,
                'assigned_sim_cards': total_assigned_all,
                'active_sim_cards': total_active_all,
                'overall_utilization_rate': round(
                    ((total_assigned_all + total_active_all) / total_sim_cards_all * 100)
                    if total_sim_cards_all > 0 else 0
                )
            }
        }

    except User.DoesNotExist:
        raise PermissionError("User profile not found")


# Register functions
functions = {
    'get_available_batches': get_available_batches,
    'get_batch_details': get_batch_details,
    'get_batch_assignment_summary': get_batch_assignment_summary,
}