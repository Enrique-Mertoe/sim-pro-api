def ba_get_dashboard_stats(user, ):
    """Get Brand Ambassador dashboard statistics"""
    from ssm.models import SimCard, ActivityLog
    from django.utils import timezone
    from datetime import timedelta

    try:
        ssm_user = user

        # Ensure user is a staff member (BA)
        if ssm_user.role != 'van_staff' or not ssm_user.admin:
            raise PermissionError("Only staff members can access this dashboard")

        # Get today's date range
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Get all SIM cards assigned to this BA
        assigned_sim_cards = SimCard.objects.filter(
            assigned_to_user=ssm_user,
            admin=ssm_user.admin
        )

        # Total assigned SIM cards
        total_assigned = assigned_sim_cards.count()

        # Unassigned SIM cards from their team's lot (cards not assigned to anyone yet)
        if ssm_user.team:
            from ssm.models import LotMetadata
            team_lots = LotMetadata.objects.filter(
                assigned_team=ssm_user.team,
                admin=ssm_user.admin
            ).values_list('lot_number', flat=True)

            unregistered = SimCard.objects.filter(
                lot__in=team_lots,
                admin=ssm_user.admin,
                assigned_to_user=ssm_user,
                registered_on__isnull=True
            ).count()
        else:
            unregistered = 0

        # Today's registrations by this BA
        todays_registration = assigned_sim_cards.filter(
            registered_on__gte=today_start,
            registered_on__lt=today_end
        ).count()

        # Recent activities (last 10 activities by this user)
        recent_activities = ActivityLog.objects.filter(
            user=ssm_user
        ).order_by('-created_at')[:10]

        activities_list = []
        for activity in recent_activities:
            activities_list.append({
                'id': str(activity.id),
                'action_type': activity.action_type,
                'details': activity.details,
                'created_at': activity.created_at.isoformat(),
                'is_offline_action': activity.is_offline_action
            })

        return {
            'stats': {
                'todays_registration': todays_registration,
                'total_assigned': total_assigned,
                'unregistered': unregistered,
            },
            'recent_activities': activities_list,
            'user_info': {
                'full_name': ssm_user.full_name,
                'team_name': ssm_user.team.name if ssm_user.team else None,
                'role': ssm_user.role
            }
        }

    except PermissionError as e:
        raise e
    except Exception as e:
        raise Exception(f"Error fetching BA dashboard data: {str(e)}")


functions = {
    "ba_get_dashboard_stats": ba_get_dashboard_stats
}
