"""
RPC Functions for Reports Management
Handles Safaricom dealer portal XLS report uploads and analysis
"""
from ssm.models.base_models import User, Team, LotMetadata, BatchMetadata, SimCard
import pandas as pd
from io import BytesIO


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
    Optimized for large files (100k+ rows) using vectorized pandas operations

    Args:
        user: Authenticated user
        file_base64: Base64 encoded Excel file content

    Returns parsed data with metrics
    """
    try:
        import base64
        import numpy as np

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
            'TM Date', 'ID Date', 'Sim Serial Number', 'Top Up Amount',
            'Cumulative Usage', 'Quality'
        ]

        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise Exception(f'Missing required columns: {", ".join(missing_columns)}')

        # Clean and process data - VECTORIZED OPERATIONS
        df = df.fillna({
            'Top Up Amount': 0,
            'Cumulative Usage': 0,
            'Quality': 'N',
            'BA': '-',
            'Region': '-',
            'Territory': '-',
            'Cluster': '-',
            'Role': '-',
            'Fraud Flagged': 'N',
            'Top Up Date': '',
            'Agent MSISDN': '',
            'Fraud Reason': ''
        })

        # Convert data types - VECTORIZED
        df['Top Up Amount'] = pd.to_numeric(df['Top Up Amount'], errors='coerce').fillna(0)
        df['Cumulative Usage'] = pd.to_numeric(df['Cumulative Usage'], errors='coerce').fillna(0)

        # OPTIMIZATION 1: Format dates using vectorized string operations
        # Format TM Date: '2025-04-21T00:00' -> '2025-04-21'
        df['tm_date'] = df['TM Date'].astype(str).str.split('T').str[0]

        # Format ID Date: '20250421' -> '2025-04-21' - VECTORIZED
        def format_id_date(date_str):
            date_str = str(date_str).strip()
            if date_str and len(date_str) == 8 and date_str.isdigit():
                return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
            return date_str

        df['id_date'] = df['ID Date'].apply(format_id_date)

        # Format Top Up Date
        df['top_up_date'] = df['Top Up Date'].astype(str).str.split('T').str[0]

        # OPTIMIZATION 2: Strip and convert serial numbers - VECTORIZED
        df['serial_number'] = df['Sim Serial Number'].astype(str).str.strip()

        # OPTIMIZATION 3: Convert remaining columns to strings efficiently
        df['agent_msisdn'] = df['Agent MSISDN'].astype(str)
        df['ba'] = df['BA'].astype(str)
        df['region'] = df['Region'].astype(str)
        df['territory'] = df['Territory'].astype(str)
        df['cluster'] = df['Cluster'].astype(str)
        df['fraud_flagged'] = df['Fraud Flagged'].astype(str)
        df['fraud_reason'] = df['Fraud Reason'].astype(str)
        df['role'] = df['Role'].astype(str)
        df['quality'] = df['Quality'].astype(str)

        # OPTIMIZATION 4: Create records dict using to_dict('records') - MUCH FASTER
        records = df[[
            'tm_date', 'id_date', 'serial_number', 'top_up_date', 'Top Up Amount',
            'agent_msisdn', 'ba', 'region', 'territory', 'cluster', 'Cumulative Usage',
            'fraud_flagged', 'fraud_reason', 'role', 'quality'
        ]].rename(columns={
            'Top Up Amount': 'top_up_amount',
            'Cumulative Usage': 'cumulative_usage'
        }).to_dict('records')

        # OPTIMIZATION 5: Calculate metrics using pandas vectorized operations
        total_records = len(df)
        quality_count = (df['quality'] == 'Y').sum()
        non_quality_count = total_records - quality_count

        # Non-quality breakdown - VECTORIZED
        non_quality_mask = df['quality'] != 'Y'
        low_topup_count = ((df['Top Up Amount'] > 0) & (df['Top Up Amount'] < 50) & non_quality_mask).sum()
        zero_usage_count = ((df['Cumulative Usage'] == 0) & non_quality_mask).sum()
        no_topup_count = ((df['Top Up Amount'] == 0) & non_quality_mask).sum()

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
                'quality_count': int(quality_count),
                'non_quality_count': int(non_quality_count),
                'quality_percentage': quality_percentage,
                'non_quality_percentage': non_quality_percentage,
                'non_quality_breakdown': {
                    'low_topup': int(low_topup_count),
                    'zero_usage': int(zero_usage_count),
                    'no_topup': int(no_topup_count),
                    'low_topup_percentage': low_topup_percentage,
                    'zero_usage_percentage': zero_usage_percentage,
                    'no_topup_percentage': no_topup_percentage
                }
            }
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Failed to parse Safaricom report: {str(e)}')
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
        default_team_name = f"{user.full_name} - Default"

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
    Processes chunks of 1000-20,000+ records sent from frontend
    Optimized for bulk operations with minimal database queries

    Args:
        user: Admin user
        records: List of {serial_number, team_id, activation_date, usage, top_up_amount, quality} objects
        chunk_index: Index of this chunk (for tracking)

    Returns:
        {
            'success': True,
            'processed': int,
            'created': int,
            'updated': int,
            'chunk_index': int
        }
    """
    try:
        from django.utils import timezone
        from django.db import transaction
        from ssm.utilities import ensure_timezone_aware

        # Separate extras from regular records
        extras_records = [r for r in records if r.get('team_id') is None]
        regular_records = [r for r in records if r.get('team_id') is not None]

        created_count = 0
        updated_count = 0

        # Process extras (create SIM cards with default team)
        if extras_records:
            default_team = get_or_create_default_team(user)

            # Get or create batch and lot for extras
            batch_id = f"REPORT_EXTRAS_{timezone.now().strftime('%Y%m%d')}"

            # Try to get existing batch for today, or create new one
            batch, batch_created = BatchMetadata.objects.get_or_create(
                batch_id=batch_id,
                admin=user,
                defaults={
                    'order_number': f"AUTO_{batch_id}",
                    'company_name': "Auto-generated from Report",
                    'date_created': timezone.now().isoformat(),
                    'quantity': 0,
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

            # OPTIMIZATION 1: Fetch existing SIM cards in one query
            serial_numbers = [r['serial_number'] for r in extras_records]
            existing_sim_cards = set(
                SimCard.objects.filter(
                    serial_number__in=serial_numbers,
                    admin=user
                ).values_list('serial_number', flat=True)
            )

            # OPTIMIZATION 2: Separate new vs existing records
            new_records = [r for r in extras_records if r['serial_number'] not in existing_sim_cards]
            existing_records = [r for r in extras_records if r['serial_number'] in existing_sim_cards]

            # OPTIMIZATION 3: Bulk create new SIM cards
            if new_records:
                new_sim_cards = []
                new_serials = []

                for record in new_records:
                    new_sim_cards.append(SimCard(
                        serial_number=record['serial_number'],
                        admin=user,
                        team=default_team,
                        batch=batch,
                        lot=lot.lot_number,
                        activation_date=ensure_timezone_aware(record.get('activation_date')),
                        usage=record.get('usage', 0),
                        top_up_amount=record.get('top_up_amount', 0),
                        quality=record.get('quality', 'N'),
                    ))
                    new_serials.append(record['serial_number'])

                # Bulk create - single query instead of N queries
                with transaction.atomic():
                    SimCard.objects.bulk_create(new_sim_cards, batch_size=1000, ignore_conflicts=True)
                    created_count = len(new_sim_cards)

                    # OPTIMIZATION 4: Update lot serial numbers once
                    current_serials = lot.serial_numbers if lot.serial_numbers else []
                    lot.serial_numbers = list(set(current_serials + new_serials))  # Use set to avoid duplicates
                    lot.total_sims = len(lot.serial_numbers)
                    lot.save(update_fields=['serial_numbers', 'total_sims'])

                    # Update batch quantity
                    batch.quantity = lot.total_sims
                    batch.save(update_fields=['quantity'])

            # OPTIMIZATION 5: Bulk update existing SIM cards if needed
            if existing_records:
                # Build update list
                sim_cards_to_update = []
                serial_numbers_to_update = [r['serial_number'] for r in existing_records]

                existing_sims = SimCard.objects.filter(
                    serial_number__in=serial_numbers_to_update,
                    admin=user
                )

                for sim_card in existing_sims:
                    # Find matching record
                    record = next((r for r in existing_records if r['serial_number'] == sim_card.serial_number), None)
                    if record:
                        # Update fields
                        sim_card.activation_date = ensure_timezone_aware(record.get('activation_date'))
                        sim_card.usage = record.get('usage', 0)
                        sim_card.top_up_amount = record.get('top_up_amount', 0)
                        sim_card.quality = record.get('quality', 'N')
                        sim_cards_to_update.append(sim_card)

                # Bulk update - single query
                if sim_cards_to_update:
                    SimCard.objects.bulk_update(
                        sim_cards_to_update,
                        ['activation_date', 'usage', 'top_up_amount', 'quality'],
                        batch_size=1000
                    )
                    updated_count = len(sim_cards_to_update)

        # Process regular records (these already exist in the system)
        if regular_records:
            # OPTIMIZATION 6: Bulk update regular records if needed
            serial_numbers_regular = [r['serial_number'] for r in regular_records]

            existing_regulars = SimCard.objects.filter(
                serial_number__in=serial_numbers_regular,
                admin=user
            )

            regulars_to_update = []
            for sim_card in existing_regulars:
                record = next((r for r in regular_records if r['serial_number'] == sim_card.serial_number), None)
                if record:
                    sim_card.activation_date = ensure_timezone_aware(record.get('activation_date'))
                    sim_card.usage = record.get('usage', 0)
                    sim_card.top_up_amount = record.get('top_up_amount', 0)
                    sim_card.quality = record.get('quality', 'N')
                    regulars_to_update.append(sim_card)

            if regulars_to_update:
                SimCard.objects.bulk_update(
                    regulars_to_update,
                    ['activation_date', 'usage', 'top_up_amount', 'quality'],
                    batch_size=1000
                )
                updated_count += len(regulars_to_update)

        return {
            'success': True,
            'processed': len(records),
            'created': created_count,
            'updated': updated_count,
            'chunk_index': chunk_index
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Failed to process chunk {chunk_index}: {str(e)}')
        raise Exception(f'Failed to process chunk {chunk_index}: {str(e)}')


functions = {
    'get_teams_with_lots_mapping': get_teams_with_lots_mapping,
    'parse_safaricom_report': parse_safaricom_report,
    'save_report_data_chunk': save_report_data_chunk,
}
