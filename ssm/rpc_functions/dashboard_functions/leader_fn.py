"""
Dashboard RPC functions for Leader/Dealer role
"""


def get_inventory_stats(user):
    """
    Get inventory statistics for dealer dashboard
    Returns total sim cards, picklist cards, and extra cards

    Excludes sim cards activated in previous months.
    Only counts:
    - Sim cards not yet activated (activation_date is null)
    - Sim cards activated in the current month

    Args:
        user: Authenticated admin user

    Returns:
        {
            'success': True,
            'total': int,      # Total sim cards
            'picklist': int,   # Sim cards from picklist (team.is_default=False)
            'extra': int       # Extra sim cards (team.is_default=True)
        }
    """
    try:
        from ssm.models.base_models import SimCard
        from django.utils import timezone
        from django.db.models import Q

        # Get current month start and end dates
        now = timezone.now()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Calculate next month start (end of current month)
        if now.month == 12:
            next_month_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month_start = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

        # Base filter: exclude cards activated outside current month
        # Include: activation_date is null OR activation_date is in current month
        base_filter = Q(admin=user) & (
                Q(activation_date__isnull=True) |
                Q(activation_date__gte=current_month_start, activation_date__lt=next_month_start)
        )

        # Get all sim cards for this admin (not activated or activated this month)
        total_count = SimCard.objects.filter(base_filter).count()

        # Get picklist sim cards (team is not default)
        picklist_count = SimCard.objects.filter(
            base_filter & Q(team__is_default=False)
        ).count()

        # Get extra sim cards (team is default)
        extra_count = SimCard.objects.filter(
            base_filter & Q(team__is_default=True)
        ).count()

        return {
            'success': True,
            'total': total_count,
            'picklist': picklist_count,
            'extra': extra_count
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Failed to get inventory stats: {str(e)}')
        raise Exception(f'Failed to get inventory stats: {str(e)}')


def get_quality_metrics(user):
    """
    Get quality metrics for dealer dashboard
    Returns total quality sim cards, picklist quality, and extra quality

    Excludes sim cards activated in previous months.
    Only counts quality='Y' sim cards that are:
    - Not yet activated (activation_date is null)
    - Activated in the current month

    Args:
        user: Authenticated admin user

    Returns:
        {
            'success': True,
            'total': int,      # Total quality sim cards
            'picklist': int,   # Quality sim cards from picklist (team.is_default=False)
            'extra': int       # Quality sim cards that are extra (team.is_default=True)
        }
    """
    try:
        from ssm.models.base_models import SimCard
        from django.utils import timezone
        from django.db.models import Q

        # Get current month boundaries
        now = timezone.now()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if now.month == 12:
            next_month_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month_start = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

        # Base filter: quality='Y' AND (not activated OR activated this month)
        base_filter = Q(admin=user) & (Q(quality='Y') | Q(quality='QUALITY')) & (
                Q(activation_date__isnull=False) &
                Q(activation_date__gte=current_month_start, activation_date__lt=next_month_start)
        )

        # Get total quality sim cards
        total_count = SimCard.objects.filter(base_filter).count()

        # Get picklist quality sim cards
        picklist_count = SimCard.objects.filter(
            base_filter & Q(team__is_default=False)
        ).count()

        # Get extra quality sim cards
        extra_count = SimCard.objects.filter(
            base_filter & Q(team__is_default=True)
        ).count()

        return {
            'success': True,
            'total': total_count,
            'picklist': picklist_count,
            'extra': extra_count
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Failed to get quality metrics: {str(e)}')
        raise Exception(f'Failed to get quality metrics: {str(e)}')


def get_non_quality_metrics(user):
    """
    Get non-quality metrics for dealer dashboard
    Returns total non-quality sim cards, picklist non-quality, and extra non-quality

    Excludes sim cards activated in previous months.
    Only counts quality='N' sim cards that are:
    - Not yet activated (activation_date is null)
    - Activated in the current month

    Args:
        user: Authenticated admin user

    Returns:
        {
            'success': True,
            'total': int,      # Total non-quality sim cards
            'picklist': int,   # Non-quality sim cards from picklist (team.is_default=False)
            'extra': int       # Non-quality sim cards that are extra (team.is_default=True)
        }
    """
    try:
        from ssm.models.base_models import SimCard
        from django.utils import timezone
        from django.db.models import Q

        # Get current month boundaries
        now = timezone.now()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if now.month == 12:
            next_month_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month_start = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

        # Base filter: quality='N' AND (not activated OR activated this month)
        base_filter = Q(admin=user) & (Q(quality='N') | Q(quality='NON_QUALITY')) & (
                Q(activation_date__isnull=False) &
                Q(activation_date__gte=current_month_start, activation_date__lt=next_month_start)
        )

        # Get total non-quality sim cards
        total_count = SimCard.objects.filter(base_filter).count()

        # Get picklist non-quality sim cards
        picklist_count = SimCard.objects.filter(
            base_filter & Q(team__is_default=False)
        ).count()

        # Get extra non-quality sim cards
        extra_count = SimCard.objects.filter(
            base_filter & Q(team__is_default=True)
        ).count()

        return {
            'success': True,
            'total': total_count,
            'picklist': picklist_count,
            'extra': extra_count
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Failed to get non-quality metrics: {str(e)}')
        raise Exception(f'Failed to get non-quality metrics: {str(e)}')


functions = {
    'get_inventory_stats': get_inventory_stats,
    'get_quality_metrics': get_quality_metrics,
    'get_non_quality_metrics': get_non_quality_metrics,
}
