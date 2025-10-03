from ssm.models.base_models import Team
import csv
import io
from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


def get_all_teams(user, **kwargs):
    """Get all Team records"""
    teams = Team.objects.all().values(
        'id', 'name', 'leader_id', 'region', 'territory',
        'van_number_plate', 'van_location', 'is_active', 'is_default',
        'admin_id', 'created_at'
    )
    return list(teams)


def get_team(user, **kwargs):
    """Get a single Team by ID"""
    team_id = kwargs.get('team_id')
    if not team_id:
        raise ValueError("team_id is required")

    team = Team.objects.filter(id=team_id).values(
        'id', 'name', 'leader_id', 'region', 'territory',
        'van_number_plate', 'van_location', 'is_active', 'is_default',
        'admin_id', 'created_at'
    ).first()

    if not team:
        raise ValueError(f"Team with id {team_id} not found")

    return team


def create_team(user, **kwargs):
    """Create a new Team"""
    pass


def update_team(user, **kwargs):
    """Update an existing Team"""
    pass


def delete_team(user, **kwargs):
    """Delete a Team"""
    team_id = kwargs.get('team_id')
    if not team_id:
        raise ValueError("team_id is required")

    team = Team.objects.filter(id=team_id).first()
    if not team:
        raise ValueError(f"Team with id {team_id} not found")

    team.delete()

    return {
        'id': str(team_id),
        'deleted': True
    }


def toggle_team_status(user, **kwargs):
    """Toggle a team's active status"""
    team_id = kwargs.get('team_id')
    if not team_id:
        raise ValueError("team_id is required")

    team = Team.objects.filter(id=team_id).first()
    if not team:
        raise ValueError(f"Team with id {team_id} not found")

    # Toggle the is_active status
    team.is_active = not team.is_active
    team.save()

    return {
        'id': str(team.id),
        'name': team.name,
        'is_active': team.is_active
    }


def bulk_import_teams(user, **kwargs):
    """Bulk import teams from CSV, filtering by admin_id and replacing with new admin"""
    csv_data = kwargs.get('csv_data')
    new_admin_id = kwargs.get('new_admin_id')
    filter_admin_id = kwargs.get('filter_admin_id')

    if not csv_data or not new_admin_id or not filter_admin_id:
        raise ValueError("csv_data, new_admin_id, and filter_admin_id are required")

    # Parse CSV
    csv_file = io.StringIO(csv_data)
    reader = csv.DictReader(csv_file)

    teams_to_create = []
    for row in reader:
        # Filter by admin_id
        if row.get('admin_id') == filter_admin_id:
            # Parse created_at from CSV or use current time
            created_at_str = row.get('created_at', '').strip()
            if created_at_str:
                from dateutil import parser
                created_at = parser.parse(created_at_str)
            else:
                created_at = timezone.now()

            # Prepare team data
            team_data = {
                'id': row.get('id'),
                'name': row.get('name'),
                'leader_id': None,  # Set leader_id to null
                'region': row.get('region', ''),
                'territory': row.get('territory', ''),
                'van_number_plate': row.get('van_number_plate', ''),
                'van_location': row.get('van_location', ''),
                'is_active': row.get('is_active', 'true').lower() == 'true',
                'is_default': False,
                'admin_id': new_admin_id,  # Replace with new admin_id
                'created_at': created_at
            }
            teams_to_create.append(team_data)

    # Bulk create/update teams with transaction and logging
    try:
        with transaction.atomic():
            logger.info(f"Starting bulk import of {len(teams_to_create)} teams")

            created_count = 0
            updated_count = 0

            if teams_to_create:
                for team_data in teams_to_create:
                    team_id = team_data.pop('id')

                    # Try to update existing team or create new one
                    team, created = Team.objects.update_or_create(
                        id=team_id,
                        defaults=team_data
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                logger.info(f"Import completed: {created_count} teams created, {updated_count} teams updated")

            return {
                'imported_count': len(teams_to_create),
                'created_count': created_count,
                'updated_count': updated_count,
                'message': f'Successfully imported {len(teams_to_create)} teams ({created_count} created, {updated_count} updated)'
            }
    except Exception as e:
        logger.error(f"Error during bulk import: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to import teams: {str(e)}")


functions = {
    "admin_get_all_teams": get_all_teams,
    "admin_get_team": get_team,
    "admin_create_team": create_team,
    "admin_update_team": update_team,
    "admin_delete_team": delete_team,
    "admin_toggle_team_status": toggle_team_status,
    "admin_bulk_import_teams": bulk_import_teams
}
