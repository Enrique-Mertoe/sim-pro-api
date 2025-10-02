"""
RPC Functions for Reports Management
Handles Safaricom dealer portal XLS report uploads and analysis
"""
from ssm.models.base_models import User, Team, LotMetadata, BatchMetadata, SimCard
import pandas as pd
from io import BytesIO
from decimal import Decimal
from datetime import datetime
from django.db import transaction


def get_teams_with_lots_mapping(user):
    """
    Fetch all teams with their lots and serial numbers for efficient mapping
    Used to map XLS report serial numbers to teams on the UI side

    Returns:
    {
        "success": true,
        "teams": [
            {
                "team_id": "uuid",
                "team_name": "Team Name",
                "lots": [
                    {
                        "lot_number": "LOT123",
                        "serial_numbers": ["89254...", "89254..."],
                        "total_sims": 1000
                    }
                ]
            }
        ],
        "total_teams": 10
    }
    """
    try:
        # Get all active teams for this admin
        teams = Team.objects.filter(
            admin=user,
            is_active=True
        ).order_by('name')

        teams_data = []

        for team in teams:
            # Get all lots assigned to this team
            lots = LotMetadata.objects.filter(
                admin=user,
                assigned_team=team
            ).values('lot_number', 'serial_numbers', 'total_sims')

            lots_list = []
            for lot in lots:
                lots_list.append({
                    'lot_number': lot['lot_number'],
                    'serial_numbers': lot['serial_numbers'],
                    'total_sims': lot['total_sims']
                })

            teams_data.append({
                'team_id': str(team.id),
                'team_name': team.name,
                'lots': lots_list
            })

        return {
            'success': True,
            'teams': teams_data,
            'total_teams': len(teams_data)
        }

    except Exception as e:
        raise Exception(str(e))


def parse_safaricom_report(user, file_base64: str):
    """
    Parse uploaded Safaricom dealer portal XLS report from base64 encoded file

    Args:
        user: Authenticated user
        file_base64: Base64 encoded Excel file content

    Returns parsed data with metrics
    """
    try:
        import base64

        # Decode base64 file
        try:
            file_content = base64.b64decode(file_base64)
        except Exception as e:
            raise Exception(f'Failed to decode file: {str(e)}')

        # Read Excel file
        try:
            df = pd.read_excel(BytesIO(file_content))
        except Exception as e:
            raise Exception(f'Failed to read Excel file: {str(e)}')

        # Validate required columns
        required_columns = [
            'TM Date', 'Sim Serial Number', 'Top Up Amount',
            'Cumulative Usage', 'Quality'
        ]
        print("cols",df.columns)

        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise Exception(f'Missing required columns: {", ".join(missing_columns)}')

        # Clean and process data
        df = df.fillna({
            'Top Up Amount': 0,
            'Cumulative Usage': 0,
            'Quality': 'N',
            'BA': '-',
            'Region': '-',
            'Territory': '-',
            'Cluster': '-',
            'Role': '-',
            'Fraud Flagged': 'N'
        })

        # Convert data types
        df['Top Up Amount'] = pd.to_numeric(df['Top Up Amount'], errors='coerce').fillna(0)
        df['Cumulative Usage'] = pd.to_numeric(df['Cumulative Usage'], errors='coerce').fillna(0)

        # Parse data into records
        records = []
        for _, row in df.iterrows():
            record = {
                'tm_date': str(row.get('TM Date', '')),
                'serial_number': str(row.get('Sim Serial Number', '')).strip(),
                'top_up_date': str(row.get('Top Up Date', '')),
                'top_up_amount': float(row.get('Top Up Amount', 0)),
                'agent_msisdn': str(row.get('Agent MSISDN', '')),
                'ba': str(row.get('BA', '-')),
                'region': str(row.get('Region', '-')),
                'territory': str(row.get('Territory', '-')),
                'cluster': str(row.get('Cluster', '-')),
                'cumulative_usage': float(row.get('Cumulative Usage', 0)),
                'fraud_flagged': str(row.get('Fraud Flagged', 'N')),
                'fraud_reason': str(row.get('Fraud Reason', '')),
                'role': str(row.get('Role', '-')),
                'quality': str(row.get('Quality', 'N'))
            }
            records.append(record)

        # Calculate overall metrics
        total_records = len(records)
        quality_count = len([r for r in records if r['quality'] == 'Y'])
        non_quality_count = total_records - quality_count

        # Non-quality breakdown
        non_quality_records = [r for r in records if r['quality'] != 'Y']
        low_topup_count = len([r for r in non_quality_records if 0 < r['top_up_amount'] < 50])
        zero_usage_count = len([r for r in non_quality_records if r['cumulative_usage'] == 0])
        no_topup_count = len([r for r in non_quality_records if r['top_up_amount'] == 0])

        # Calculate percentages
        quality_percentage = round((quality_count / total_records * 100), 2) if total_records > 0 else 0
        non_quality_percentage = round((non_quality_count / total_records * 100), 2) if total_records > 0 else 0

        # Non-quality breakdown percentages
        low_topup_percentage = round((low_topup_count / non_quality_count * 100), 2) if non_quality_count > 0 else 0
        zero_usage_percentage = round((zero_usage_count / non_quality_count * 100), 2) if non_quality_count > 0 else 0
        no_topup_percentage = round((no_topup_count / non_quality_count * 100), 2) if non_quality_count > 0 else 0

        return {
            'success': True,
            'records': records,
            'total_records': total_records,
            'metrics': {
                'quality_count': quality_count,
                'non_quality_count': non_quality_count,
                'quality_percentage': quality_percentage,
                'non_quality_percentage': non_quality_percentage,
                'non_quality_breakdown': {
                    'low_topup': low_topup_count,
                    'zero_usage': zero_usage_count,
                    'no_topup': no_topup_count,
                    'low_topup_percentage': low_topup_percentage,
                    'zero_usage_percentage': zero_usage_percentage,
                    'no_topup_percentage': no_topup_percentage
                }
            }
        }

    except Exception as e:
        raise Exception(str(e))


def get_or_create_default_team(user):
    """
    Get or create default team for admin user
    Default team is used for SIM cards that don't belong to any team (extras from reports)

    Returns:
        Team object
    """
    try:
        # Try to get existing default team
        default_team = Team.objects.filter(
            admin=user,
            is_default=True,
            is_active=True
        ).first()

        if default_team:
            return default_team

        # Create new default team
        default_team_name = f"{user.username} - Default"

        default_team = Team.objects.create(
            name=default_team_name,
            admin=user,
            region='Default',
            is_default=True,
            is_active=True
        )

        return default_team

    except Exception as e:
        raise Exception(f'Failed to get or create default team: {str(e)}')


def create_batch_and_lot_for_extras(user, serial_numbers, default_team):
    """
    Create batch and lot for extra SIM cards (no team)

    Args:
        user: Admin user
        serial_numbers: List of serial numbers
        default_team: Default team to assign the lot to

    Returns:
        tuple: (batch, lot)
    """
    try:
        from django.utils import timezone

        # Create batch for extras
        batch_id = f"REPORT_EXTRAS_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

        batch = BatchMetadata.objects.create(
            batch_id=batch_id,
            order_number=f"AUTO_{batch_id}",
            company_name="Auto-generated from Report",
            date_created=timezone.now().isoformat(),
            quantity=len(serial_numbers),
            created_by_user=user,
            admin=user,
            lot_numbers=[f"{batch_id}_LOT1"]
        )

        # Create lot for the batch
        lot = LotMetadata.objects.create(
            batch=batch,
            lot_number=f"{batch_id}_LOT1",
            serial_numbers=serial_numbers,
            assigned_team=default_team,
            assigned_on=timezone.now(),
            status='ASSIGNED',
            total_sims=len(serial_numbers),
            admin=user
        )

        return batch, lot

    except Exception as e:
        raise Exception(f'Failed to create batch and lot: {str(e)}')


def save_report_data_chunk(user, records: list, chunk_index: int = 0):
    """
    Save report data chunk to database synchronously
    Processes chunks of 1000 records sent from frontend

    Args:
        user: Admin user
        records: List of {serial_number, team_id} objects
        chunk_index: Index of this chunk (for tracking)

    Returns:
        {
            'success': True,
            'processed': int,
            'created': int,
            'chunk_index': int
        }
    """
    try:
        from django.utils import timezone

        # Separate extras from regular records
        extras_records = [r for r in records if r['team_id'] is None]
        regular_records = [r for r in records if r['team_id'] is not None]

        created_count = 0
        updated_count = 0

        # Process extras (create SIM cards with default team)
        if extras_records:
            default_team = get_or_create_default_team(user)

            # Get or create batch and lot for extras
            # Use a consistent batch_id based on today's date
            batch_id = f"REPORT_EXTRAS_{timezone.now().strftime('%Y%m%d')}"

            # Try to get existing batch for today, or create new one
            batch, batch_created = BatchMetadata.objects.get_or_create(
                batch_id=batch_id,
                admin=user,
                defaults={
                    'order_number': f"AUTO_{batch_id}",
                    'company_name': "Auto-generated from Report",
                    'date_created': timezone.now().isoformat(),
                    'quantity': 0,  # Will be updated
                    'created_by_user': user,
                    'lot_numbers': [f"{batch_id}_LOT1"]
                }
            )

            # Get or create lot
            lot, lot_created = LotMetadata.objects.get_or_create(
                batch=batch,
                lot_number=f"{batch_id}_LOT1",
                defaults={
                    'serial_numbers': [],
                    'assigned_team': default_team,
                    'assigned_on': timezone.now(),
                    'status': 'ASSIGNED',
                    'total_sims': 0,
                    'admin': user
                }
            )

            # Create SIM cards for extras
            extras_serials = []
            for record in extras_records:
                sim_card, created = SimCard.objects.get_or_create(
                    serial_number=record['serial_number'],
                    admin=user,
                    defaults={
                        'team': default_team,
                        'batch': batch,
                        'lot': lot.lot_number,
                        'registered_by_user': user
                    }
                )

                if created:
                    created_count += 1
                    extras_serials.append(record['serial_number'])
                else:
                    updated_count += 1

            # Update lot's serial numbers if we created any
            if extras_serials:
                current_serials = lot.serial_numbers if lot.serial_numbers else []
                lot.serial_numbers = current_serials + extras_serials
                lot.total_sims = len(lot.serial_numbers)
                lot.save()

                # Update batch quantity
                batch.quantity = lot.total_sims
                batch.save()

        # Process regular records (these already exist in the system)
        if regular_records:
            # Just count them for now - they're already in the system from batch assignment
            updated_count += len(regular_records)

        return {
            'success': True,
            'processed': len(records),
            'created': created_count,
            'updated': updated_count,
            'chunk_index': chunk_index
        }

    except Exception as e:
        raise Exception(f'Failed to process chunk {chunk_index}: {str(e)}')




functions = {
    'get_teams_with_lots_mapping': get_teams_with_lots_mapping,
    'parse_safaricom_report': parse_safaricom_report,
    'save_report_data_chunk': save_report_data_chunk,
}
