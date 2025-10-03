from ssm.models.base_models import Team
import csv
import io
from django.utils import timezone


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
                'created_at': timezone.now()
            }
            teams_to_create.append(team_data)

    # Bulk create teams
    if teams_to_create:
        Team.objects.bulk_create([
            Team(**team_data) for team_data in teams_to_create
        ], ignore_conflicts=True)

    return {
        'imported_count': len(teams_to_create),
        'message': f'Successfully imported {len(teams_to_create)} teams'
    }


functions = {
    "admin_get_all_teams": get_all_teams,
    "admin_get_team": get_team,
    "admin_create_team": create_team,
    "admin_update_team": update_team,
    "admin_delete_team": delete_team,
    "admin_toggle_team_status": toggle_team_status,
    "admin_bulk_import_teams": bulk_import_teams
}
