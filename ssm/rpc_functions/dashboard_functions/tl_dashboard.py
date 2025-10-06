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
            is_active=True,
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
        active_sim_cards = team_sim_cards.filter(
            activation_date__isnull=False
        ).count()

        return {
            'team': {
                'name': team.name,
                'member_count': member_count,
                'total_sim_cards': total_sim_cards,
                'active_sim_cards': active_sim_cards,
            },
            'is_team_leader': is_team_leader
        }

    except PermissionError as e:
        raise e
    except ValueError as e:
        raise e
    except Exception as e:
        raise Exception(f"Error fetching team leader dashboard data: {str(e)}")


functions = {
    "tl_get_dash_start": tl_get_dash_start
}
