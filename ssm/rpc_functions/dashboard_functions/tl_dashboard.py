from django.db.models import Q


def tl_get_dash_start(user, ):
    """Get team leader dashboard metrics and statistics"""
    from ssm.models import User, SimCard, LotMetadata

    try:
        ssm_user = user

        # Ensure user is a team leader
        if ssm_user.role != 'team_leader' or not ssm_user.admin:
            raise PermissionError("Only team leaders can access this dashboard")

        # Get the team leader's team
        team = ssm_user.team
        if not team:
            raise ValueError("Team leader must be assigned to a team")

        # Check if user is actually the leader of this team
        is_team_leader = team.leader_id == ssm_user.id

        # Get team member count (excluding the team leader)
        member_count = User.objects.filter(
            team=team,
            status="ACTIVE",
            deleted=False
        ).exclude(role='team_leader').count()

        # Get lot numbers assigned to this team
        team_lots = LotMetadata.objects.filter(
            assigned_team=team,
            admin=ssm_user.admin
        ).values_list('lot_number', flat=True)

        # Get SIM card statistics for the team based on lot assignments
        team_sim_cards = SimCard.objects.filter(
            lot__in=team_lots,
            admin=ssm_user.admin
        )
        total_sim_cards = team_sim_cards.count()

        # Active SIM cards (registered and not fraud-flagged)
        assigned_sim_cards = team_sim_cards.filter(
            assigned_to_user__isnull=False
        ).count()
        unassigned_sim_cards = team_sim_cards.filter(
            assigned_to_user__isnull=True
        ).count()

        return {
            'team': {
                'name': team.name,
                'member_count': member_count,
                'total_sim_cards': total_sim_cards,
                'assigned_sim_cards': assigned_sim_cards,
                'unassigned_sim_cards': unassigned_sim_cards,
            },
            'is_team_leader': is_team_leader
        }

    except PermissionError as e:
        raise e
    except ValueError as e:
        raise e
    except Exception as e:
        raise Exception(f"Error fetching team leader dashboard data: {str(e)}")


def tl_get_dashboard_stats(user, ):
    """Get team leader dashboard statistics including today's registration, quality metrics"""
    from ssm.models import SimCard, LotMetadata
    from django.utils import timezone
    from datetime import timedelta

    try:
        ssm_user = user

        # Ensure user is a team leader
        if ssm_user.role != 'team_leader' or not ssm_user.admin:
            raise PermissionError("Only team leaders can access this dashboard")

        # Get the team leader's team
        team = ssm_user.team
        if not team:
            raise ValueError("Team leader must be assigned to a team")

        # Get lot numbers assigned to this team
        team_lots = LotMetadata.objects.filter(
            assigned_team=team,
            admin=ssm_user.admin
        ).values_list('lot_number', flat=True)

        # Base queryset for team's SIM cards
        team_sim_cards = SimCard.objects.filter(
            lot__in=team_lots,
            admin=ssm_user.admin
        )

        # Get today's date range
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Get yesterday's date range
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start

        # Today's registrations using custom QuerySet
        todays_registration = team_sim_cards.registered_today().count()
        # Yesterday's registrations for comparison (from 00:00:00 yesterday to 00:00:00 today, exclusive)
        yesterdays_registration = team_sim_cards.registered_yesterday().count()

        # Calculate percentage change
        if yesterdays_registration > 0:
            registration_change_percent = round(
                ((todays_registration - yesterdays_registration) / yesterdays_registration) * 100, 1
            )
        else:
            registration_change_percent = 100 if todays_registration > 0 else 0

        # Get current month's date range
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get last month's date range (same time period)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)
        current_day_of_month = now.day
        last_month_same_day = last_month_start + timedelta(days=current_day_of_month - 1)

        # Month-to-date quality SIM cards

        quality_mtd = team_sim_cards.filter(
            Q(quality='Y') | Q(quality='QUALITY'),
            activation_date__gte=month_start,
            activation_date__lte=now,

        ).count()

        # Month-to-date non-quality SIM cards
        non_quality_mtd = team_sim_cards.filter(
            Q(quality='N') | Q(quality='NON_QUALITY'),
            activation_date__gte=month_start,
            activation_date__lte=now,
        ).count()

        # Last month's quality for same time period
        last_month_quality = team_sim_cards.filter(
            Q(quality='Y') | Q(quality='QUALITY'),
            activation_date__gte=last_month_start,
            activation_date__lte=last_month_same_day,
        ).count()

        # Last month's non-quality for same time period
        last_month_non_quality = team_sim_cards.filter(
            Q(quality='N') | Q(quality='NON_QUALITY'),
            activation_date__gte=last_month_start,
            activation_date__lte=last_month_same_day,
        ).count()

        return {
            'todays_registration': todays_registration,
            'yesterdays_registration': yesterdays_registration,
            'registration_change_percent': registration_change_percent,
            'registration_trend': 'up' if registration_change_percent > 0 else 'down',
            'quality': {
                'month_to_date': quality_mtd,
                'last_month_same_period': last_month_quality,
            },
            'non_quality': {
                'month_to_date': non_quality_mtd,
                'last_month_same_period': last_month_non_quality,
            }
        }

    except PermissionError as e:
        raise e
    except ValueError as e:
        raise e
    except Exception as e:
        raise Exception(f"Error fetching team leader dashboard statistics: {str(e)}")


functions = {
    "tl_get_dash_start": tl_get_dash_start,
    "tl_get_dashboard_stats": tl_get_dashboard_stats
}
