"""
Analytics-related RPC functions
"""
from django.db.models import Q, Count, Sum, Case, When, IntegerField, DecimalField, Value
from django.utils import timezone
from datetime import datetime
from ..models import SimCard, User


def get_connections_analytics(user, start_date=None, end_date=None, **kwargs):
    """
    Get comprehensive analytics for connections (activated SIM cards)
    Filters by activation_date range and only includes cards with activation_date not null
    """
    try:
        # Base queryset - only activated sim cards whose batches belong to this admin
        base_query = SimCard.objects.filter(
            batch__admin=user,
            activation_date__isnull=False
        )
        user_id = kwargs.get("user_id")
        # Filter by user's admin
        if user_id:
            base_query = base_query.filter(assigned_to_user_id=user_id)

        # Apply date filters if provided
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            base_query = base_query.filter(activation_date__gte=start_dt)

        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            base_query = base_query.filter(activation_date__lte=end_dt)

        # Total connections
        total_connections = base_query.count()

        # Quality vs Non-Quality
        quality_count = base_query.filter(Q(quality__in=['Y', 'QUALITY'])).count()
        non_quality_count = base_query.filter(Q(quality__in=['N', 'NON_QUALITY'])).count()

        # From Picklist (batch not null) vs Extra (batch null)
        from_picklist = base_query.filter(team__is_default=False).count()
        extra_connections = base_query.filter(team__is_default=True).count()

        # Non-quality breakdown
        non_quality_query = base_query.filter(Q(quality__in=['N', 'NON_QUALITY']))

        # Low top-up (< 50)
        low_topup = non_quality_query.filter(
            Q(top_up_amount__lt=50) & Q(top_up_amount__gt=0)
        ).count()

        # Zero usage
        zero_usage = non_quality_query.filter(
            Q(usage__lt=50) | Q(usage__isnull=True),
            top_up_amount__gte=50
        ).count()

        # No top-up amount
        no_topup = non_quality_query.filter(
            Q(top_up_amount__isnull=True) | Q(top_up_amount=0)
        ).count()

        return {
            'success': True,
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            },
            'overview': {
                'total_connections': total_connections,
                'quality_count': quality_count,
                'non_quality_count': non_quality_count,
                'quality_percentage': round((quality_count / total_connections * 100) if total_connections > 0 else 0,
                                            2),
                'non_quality_percentage': round(
                    (non_quality_count / total_connections * 100) if total_connections > 0 else 0, 2)
            },
            'source_breakdown': {
                'from_picklist': from_picklist,
                'extra_connections': extra_connections,
                'picklist_percentage': round((from_picklist / total_connections * 100) if total_connections > 0 else 0,
                                             2),
                'extra_percentage': round((extra_connections / total_connections * 100) if total_connections > 0 else 0,
                                          2)
            },
            'non_quality_breakdown': {
                'total': non_quality_count,
                'low_topup': low_topup,
                'zero_usage': zero_usage,
                'no_topup': no_topup,
                'low_topup_percentage': round((low_topup / non_quality_count * 100) if non_quality_count > 0 else 0, 2),
                'zero_usage_percentage': round((zero_usage / non_quality_count * 100) if non_quality_count > 0 else 0,
                                               2),
                'no_topup_percentage': round((no_topup / non_quality_count * 100) if non_quality_count > 0 else 0, 2)
            }
        }
    except Exception as e:
        raise ValueError(f"Error getting analytics: {str(e)}")


def get_team_analytics_breakdown(user, start_date=None, end_date=None, **kwargs):
    """
    Get team-wise breakdown of connections analytics with non-quality breakdown
    Optimized for large datasets (50K+ records) using single-query aggregation
    """
    try:
        from django.db.models import Value as V, CharField
        from django.db.models.functions import Coalesce

        # Base queryset - only activated sim cards whose batches belong to this admin
        base_query = SimCard.objects.filter(
            batch__admin=user,
            activation_date__isnull=False
        )

        # Filter by user_id if provided
        user_id = kwargs.get("user_id")
        if user_id:
            base_query = base_query.filter(assigned_to_user_id=user_id)

        # Default to current month if no dates provided
        if not start_date or not end_date:
            now = timezone.now()
            current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            if now.month == 12:
                next_month_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_month_start = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            
            if not start_date:
                start_date = current_month_start.isoformat()
            if not end_date:
                end_date = next_month_start.isoformat()

        # Apply date filters
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        base_query = base_query.filter(activation_date__gte=start_dt)

        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        base_query = base_query.filter(activation_date__lt=end_dt)

        # Single optimized query with all aggregations including non-quality breakdown
        # This eliminates N+1 queries by doing everything in one database call
        team_stats = base_query.values('team__name', 'team__id').annotate(
            # Basic counts
            total_connections=Count('id'),
            quality_count=Count(Case(When(Q(quality__in=['Y', 'QUALITY']), then=1), output_field=IntegerField())),
            non_quality_count=Count(
                Case(When(Q(quality__in=['N', 'NON_QUALITY']), then=1), output_field=IntegerField())),
            from_picklist=Count(Case(When(batch__isnull=False, then=1), output_field=IntegerField())),
            extra_connections=Count(Case(When(batch__isnull=True, then=1), output_field=IntegerField())),
            total_topup=Sum('top_up_amount'),
            total_usage=Sum('usage'),

            # Non-quality breakdown - all calculated in single query
            low_topup_count=Count(
                Case(
                    When(
                        Q(quality__in=['N', 'NON_QUALITY']) &
                        Q(top_up_amount__lt=50) &
                        Q(top_up_amount__gt=0),
                        then=1
                    ),
                    output_field=IntegerField()
                )
            ),
            zero_usage_count=Count(
                Case(
                    When(
                        Q(quality__in=['N', 'NON_QUALITY']) &
                        (Q(usage__lt=50) | Q(usage__isnull=True)) &
                        Q(top_up_amount__gte=50),
                        then=1
                    ),
                    output_field=IntegerField()
                )
            ),
            no_topup_count=Count(
                Case(
                    When(
                        Q(quality__in=['N', 'NON_QUALITY']) &
                        (Q(top_up_amount__isnull=True) | Q(top_up_amount=0)),
                        then=1
                    ),
                    output_field=IntegerField()
                )
            )
        ).order_by('-total_connections')

        # Format the results - single loop, no additional queries
        teams_breakdown = []
        for team in team_stats:
            total = team['total_connections']
            quality = team['quality_count']
            non_quality = team['non_quality_count']
            low_topup = team['low_topup_count']
            zero_usage = team['zero_usage_count']
            no_topup = team['no_topup_count']

            teams_breakdown.append({
                'team_id': str(team['team__id']) if team['team__id'] else None,
                'team_name': team['team__name'] or 'Unassigned',
                'total_connections': total,
                'quality_count': quality,
                'non_quality_count': non_quality,
                'quality_percentage': round((quality / total * 100) if total > 0 else 0, 2),
                'non_quality_percentage': round((non_quality / total * 100) if total > 0 else 0, 2),
                'from_picklist': team['from_picklist'],
                'extra_connections': team['extra_connections'],
                'total_topup': float(team['total_topup']) if team['total_topup'] else 0,
                'total_usage': float(team['total_usage']) if team['total_usage'] else 0,
                'non_quality_breakdown': {
                    'low_topup': low_topup,
                    'zero_usage': zero_usage,
                    'no_topup': no_topup,
                    'low_topup_percentage': round((low_topup / non_quality * 100) if non_quality > 0 else 0, 2),
                    'zero_usage_percentage': round((zero_usage / non_quality * 100) if non_quality > 0 else 0, 2),
                    'no_topup_percentage': round((no_topup / non_quality * 100) if non_quality > 0 else 0, 2)
                }
            })

        return {
            'success': True,
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            },
            'teams': teams_breakdown,
            'total_teams': len(teams_breakdown)
        }
    except Exception as e:
        raise ValueError(f"Error getting team analytics: {str(e)}")


def get_quality_trend(user, start_date=None, end_date=None, **kwargs):
    """
    Get quality vs non-quality trend over time (grouped by day)
    """
    try:
        # Base queryset - only activated sim cards whose batches belong to this admin
        base_query = SimCard.objects.filter(
            batch__admin=user,
            activation_date__isnull=False
        )

        # Filter by user_id if provided
        user_id = kwargs.get("user_id")
        if user_id:
            base_query = base_query.filter(assigned_to_user_id=user_id)

        # Apply date filters if provided
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            base_query = base_query.filter(activation_date__gte=start_dt)

        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            base_query = base_query.filter(activation_date__lte=end_dt)

        # Group by date and quality
        from django.db.models.functions import TruncDate

        trend_data = base_query.annotate(
            date=TruncDate('activation_date')
        ).values('date').annotate(
            quality_count=Count(Case(When(Q(quality__in=['Y', 'QUALITY']), then=1), output_field=IntegerField())),
            non_quality_count=Count(
                Case(When(Q(quality__in=['N', 'NON_QUALITY']), then=1), output_field=IntegerField())),
            total=Count('id')
        ).order_by('date')

        # Format the results
        trend = []
        for item in trend_data:
            trend.append({
                'date': item['date'].isoformat(),
                'quality_count': item['quality_count'],
                'non_quality_count': item['non_quality_count'],
                'total': item['total']
            })

        return {
            'success': True,
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            },
            'trend': trend
        }
    except Exception as e:
        raise ValueError(f"Error getting quality trend: {str(e)}")


def get_teams_list(user, start_date=None, end_date=None, **kwargs):
    """
    Get list of teams with basic info - optimized for initial load
    Queries Team model directly, then counts connections separately
    Much faster than querying through SimCard model
    """
    try:
        from ..models import Team

        # Get user_id filter if provided
        user_id = kwargs.get("user_id")

        # Get all teams for this admin - super fast query
        teams_queryset = Team.objects.filter(
            admin=user,
            is_active=True
        ).values('id', 'name').order_by('name')

        teams_list = []

        # For each team, count activated connections with date filters
        for team in teams_queryset:
            # Build connection count query - filter by batch admin
            connection_query = SimCard.objects.filter(
                batch__admin=user,
                team__id=team['id'],
                activation_date__isnull=False
            )

            # Filter by user_id if provided
            if user_id:
                connection_query = connection_query.filter(assigned_to_user_id=user_id)

            # Apply date filters if provided
            if start_date:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                connection_query = connection_query.filter(activation_date__gte=start_dt)

            if end_date:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                connection_query = connection_query.filter(activation_date__lte=end_dt)

            count = connection_query.count()

            teams_list.append({
                'team_id': str(team['id']),
                'team_name': team['name'],
                'total_connections': count
            })

        # Add unassigned connections - filter by batch admin
        unassigned_query = SimCard.objects.filter(
            batch__admin=user,
            team__isnull=True,
            activation_date__isnull=False
        )

        # Filter by user_id if provided
        if user_id:
            unassigned_query = unassigned_query.filter(assigned_to_user_id=user_id)

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            unassigned_query = unassigned_query.filter(activation_date__gte=start_dt)

        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            unassigned_query = unassigned_query.filter(activation_date__lte=end_dt)

        unassigned_count = unassigned_query.count()

        if unassigned_count > 0:
            teams_list.append({
                'team_id': None,
                'team_name': 'Unassigned',
                'total_connections': unassigned_count
            })

        # Sort by total connections descending
        teams_list.sort(key=lambda x: x['total_connections'], reverse=True)

        return {
            'success': True,
            'teams': teams_list,
            'total_teams': len(teams_list)
        }
    except Exception as e:
        raise ValueError(f"Error getting teams list: {str(e)}")


def get_team_metrics(user, team_id=None, start_date=None, end_date=None, **kwargs):
    """
    Get detailed metrics for a specific team
    Called after team list is loaded for progressive loading
    """
    try:
        # Base queryset - only activated sim cards whose batches belong to this admin
        base_query = SimCard.objects.filter(
            batch__admin=user,
            activation_date__isnull=False
        )

        # Filter by user_id if provided
        user_id = kwargs.get("user_id")
        if user_id:
            base_query = base_query.filter(assigned_to_user_id=user_id)

        # Apply date filters if provided
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            base_query = base_query.filter(activation_date__gte=start_dt)

        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            base_query = base_query.filter(activation_date__lte=end_dt)

        # Filter by team
        if team_id and team_id != 'null':
            base_query = base_query.filter(team__id=team_id)
        else:
            base_query = base_query.filter(team__isnull=True)

        # Get all metrics in one query
        metrics = base_query.aggregate(
            total_connections=Count('id'),
            quality_count=Count(Case(When(quality='Y', then=1), output_field=IntegerField())),
            non_quality_count=Count(Case(When(quality='N', then=1), output_field=IntegerField())),
            from_picklist=Count(Case(When(batch__isnull=False, then=1), output_field=IntegerField())),
            extra_connections=Count(Case(When(batch__isnull=True, then=1), output_field=IntegerField())),
            total_topup=Sum('top_up_amount'),
            total_usage=Sum('usage'),
            # Non-quality breakdown
            low_topup_count=Count(
                Case(
                    When(
                        Q(quality='N') &
                        Q(top_up_amount__lt=50) &
                        Q(top_up_amount__gt=0),
                        then=1
                    ),
                    output_field=IntegerField()
                )
            ),
            zero_usage_count=Count(
                Case(
                    When(
                        Q(quality='N') &
                        (Q(usage__lt=50) | Q(usage__isnull=True)) &
                        Q(top_up_amount__gte=50),
                        then=1
                    ),
                    output_field=IntegerField()
                )
            ),
            no_topup_count=Count(
                Case(
                    When(
                        Q(quality='N') &
                        (Q(top_up_amount__isnull=True) | Q(top_up_amount=0)),
                        then=1
                    ),
                    output_field=IntegerField()
                )
            )
        )

        total = metrics['total_connections']
        quality = metrics['quality_count']
        non_quality = metrics['non_quality_count']
        low_topup = metrics['low_topup_count']
        zero_usage = metrics['zero_usage_count']
        no_topup = metrics['no_topup_count']

        return {
            'success': True,
            'team_id': team_id,
            'metrics': {
                'total_connections': total,
                'quality_count': quality,
                'non_quality_count': non_quality,
                'quality_percentage': round((quality / total * 100) if total > 0 else 0, 2),
                'non_quality_percentage': round((non_quality / total * 100) if total > 0 else 0, 2),
                'from_picklist': metrics['from_picklist'],
                'extra_connections': metrics['extra_connections'],
                'total_topup': float(metrics['total_topup']) if metrics['total_topup'] else 0,
                'total_usage': float(metrics['total_usage']) if metrics['total_usage'] else 0,
                'non_quality_breakdown': {
                    'low_topup': low_topup,
                    'zero_usage': zero_usage,
                    'no_topup': no_topup,
                    'low_topup_percentage': round((low_topup / non_quality * 100) if non_quality > 0 else 0, 2),
                    'zero_usage_percentage': round((zero_usage / non_quality * 100) if non_quality > 0 else 0, 2),
                    'no_topup_percentage': round((no_topup / non_quality * 100) if non_quality > 0 else 0, 2)
                }
            }
        }
    except Exception as e:
        raise ValueError(f"Error getting team metrics: {str(e)}")


# Register functions
functions = {
    'get_connections_analytics': get_connections_analytics,
    'get_team_analytics_breakdown': get_team_analytics_breakdown,
    'get_teams_list': get_teams_list,
    'get_team_metrics': get_team_metrics,
    'get_quality_trend': get_quality_trend,
}
