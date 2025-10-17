"""
RPC functions for picklist processing.
"""
import base64
from typing import Dict, Any

from ..picklist_utils import PDFProcessor, PicklistParser


def parse_picklist_pdf(user, file_base64: str) -> Dict[str, Any]:
    """
    Parse uploaded picklist PDF from base64 encoded file and extract metadata and serial numbers.

    Args:
        user: Authenticated user
        file_base64: Base64 encoded PDF file content

    Returns:
        Dictionary with parsed data including metadata, lots, and serial numbers
    """
    try:
        # Decode base64 file
        try:
            file_content = base64.b64decode(file_base64)
        except Exception as e:
            raise Exception(f'Failed to decode file: {str(e)}')

        # Extract text from PDF
        try:
            text, num_pages = PDFProcessor.extract_text_from_pdf(file_content)
        except Exception as e:
            raise Exception(f'Failed to extract text from PDF: {str(e)}')

        if not text.strip():
            raise Exception('No text found in PDF. The file may be empty or contain only images.')

        # Process the extracted text
        try:
            result = process_picklist_text(user, text, num_pages)
            return result
        except Exception as e:
            raise Exception(f'Failed to process picklist data: {str(e)}')

    except Exception as e:
        raise Exception(str(e))


def process_picklist_text(user, text: str, page_count: int = 0) -> Dict[str, Any]:
    """
    Process picklist text and extract metadata and serial numbers.

    Args:
        user: Authenticated user
        text: The extracted text from picklist
        page_count: Number of pages in the PDF (if applicable)

    Returns:
        Dictionary with parsed data including metadata, lots, and serial numbers
    """
    try:
        parser = PicklistParser()

        # Check if the text is a valid picklist
        is_picklist = parser.is_picklist(text)

        if is_picklist:
            # Extract serials with their lots from picklist
            serials_with_lots, total_serial = parser.extract_serials_with_lots(text)

            # Parse metadata
            metadata = parser.parse_picklist_metadata(text, str(user.id))

            return {
                'success': True,
                'is_picklist': True,
                'metadata': metadata,
                'lots': serials_with_lots,
                'total_serial_numbers': total_serial,
                'page_count': page_count
            }
        else:
            # If not a picklist, just extract serial numbers without lot organization
            import re
            # Extract all 16+ digit numbers
            serial_numbers = re.findall(r'\b\d{16,}\b', text)

            return {
                'success': True,
                'is_picklist': False,
                'metadata': None,
                'lots': [{
                    'lotNumber': 'UNKNOWN',
                    'serialNumbers': serial_numbers
                }],
                'total_serial_numbers': len(serial_numbers),
                'page_count': page_count
            }

    except Exception as e:
        raise Exception(f'Error processing picklist text: {str(e)}')


def save_picklist_data(user, **kwargs):
    """
    Save picklist data by creating batch metadata, lots, and SIM cards in bulk.
    Bypasses triggers for performance - creates all SIM cards directly in a single bulk operation.

    Args:
        user: Authenticated user
        **kwargs: Expected keys:
            - metadata: Dict containing batch metadata
            - lots: List of dicts containing lot information with serial numbers
            - assignments: List of team assignments for lots

    Returns:
        Dictionary with success status, batch_id, and created lot information
    """

    if user.role not in ["admin"]:
        raise PermissionError("Not authorised for this task!")

    from django.db import transaction
    from django.utils import timezone
    from ssm.models import BatchMetadata, LotMetadata, Team, SimCard

    try:
        metadata = kwargs.get('metadata', {})
        lots = kwargs.get('lots', [])
        assignments = kwargs.get('assignments', [])

        if not metadata:
            raise Exception("Metadata is required")

        if not lots:
            raise Exception("At least one lot is required")

        with transaction.atomic():
            # Helper function to group assignments by team (same as frontend)
            def group_assignments_by_team(assignments_list):
                team_map = {}
                for assignment in assignments_list:
                    if not assignment.get('teamId'):
                        continue

                    team_id = str(assignment['teamId'])
                    if team_id in team_map:
                        team_map[team_id]['lotNumbers'].append(assignment['lotNumber'])
                    else:
                        team_map[team_id] = {
                            'teamId': team_id,
                            'teamName': assignment.get('teamName', ''),
                            'lotNumbers': [assignment['lotNumber']]
                        }

                return list(team_map.values())

            # 1. Create BatchMetadata
            batch_id = metadata.get('orderNo') or metadata.get('moveOrderNumber', '')
            teams_data = group_assignments_by_team(assignments)

            batch = BatchMetadata.objects.create(
                batch_id=batch_id,
                order_number=metadata.get('orderNo', ''),
                requisition_number=metadata.get('requisitionNo', ''),
                company_name=metadata.get('company', ''),
                collection_point=metadata.get('collectionPoint', ''),
                move_order_number=metadata.get('moveOrderNumber', ''),
                date_created=metadata.get('dateCreated', ''),
                item_description=metadata.get('itemDescription', ''),
                quantity=metadata.get('quantity', 0),
                created_by_user=user,
                admin=user,
                lot_numbers=[lot['lotNumber'] for lot in lots],
                teams=teams_data
            )

            # 2. Create assignment lookup map
            assignment_map = {a['lotNumber']: a for a in assignments}

            # 3. Bulk create LotMetadata records (without triggering signals)
            lot_metadata_to_create = []
            lot_metadata_map = {}  # Map lot_number to lot metadata for SIM card creation

            for lot_data in lots:
                lot_number = lot_data['lotNumber']
                assignment = assignment_map.get(lot_number)

                # Get assigned team if exists
                assigned_team = None
                assigned_on = None
                status = 'PENDING'

                if assignment and assignment.get('teamId'):
                    try:
                        assigned_team = Team.objects.get(id=assignment['teamId'])
                        assigned_on = timezone.now()
                        status = 'ASSIGNED'
                    except Team.DoesNotExist:
                        pass  # Keep as PENDING if team not found

                lot_metadata = LotMetadata(
                    batch=batch,
                    lot_number=lot_number,
                    serial_numbers=lot_data['serialNumbers'],
                    assigned_team=assigned_team,
                    assigned_on=assigned_on,
                    total_sims=len(lot_data['serialNumbers']),
                    admin=user,
                    status=status,
                    quality_count=0,
                    nonquality_count=len(lot_data['serialNumbers'])
                )
                lot_metadata_to_create.append(lot_metadata)
                lot_metadata_map[lot_number] = {
                    'metadata': lot_metadata,
                    'serial_numbers': lot_data['serialNumbers'],
                    'assigned_team': assigned_team
                }

            # Bulk create all lots at once
            created_lots = LotMetadata.objects.bulk_create(lot_metadata_to_create, batch_size=100)

            # 4. Bulk create all SIM cards in a single operation
            sim_cards_to_create = []

            for lot in created_lots:
                lot_data = lot_metadata_map.get(lot.lot_number)
                if not lot_data:
                    continue

                serial_numbers = lot_data['serial_numbers']
                assigned_team = lot_data['assigned_team']

                for serial_number in serial_numbers:
                    sim_card = SimCard(
                        serial_number=serial_number,
                        batch=batch,
                        lot=lot,
                        team=assigned_team,
                        admin=user,
                        status='PENDING',
                        quality='NON_QUALITY',
                        match=False
                    )
                    sim_cards_to_create.append(sim_card)

            # Bulk create all SIM cards at once (much faster than individual creates)
            SimCard.objects.bulk_create(sim_cards_to_create, batch_size=1000, ignore_conflicts=True)

            return {
                'success': True,
                'message': f'Successfully created batch {batch.batch_id} with {len(created_lots)} lots and {len(sim_cards_to_create)} SIM cards',
                'data': {
                    'batch_id': str(batch.id),
                    'batch_number': batch.batch_id,
                    'lots_created': len(created_lots),
                    'lots_assigned': sum(1 for lot in created_lots if lot.assigned_team),
                    'total_serial_numbers': len(sim_cards_to_create),
                    'lot_numbers': [lot.lot_number for lot in created_lots],
                    'teams_assigned': len(teams_data)
                }
            }

    except Exception as e:
        import traceback
        return {
            'success': False,
            'message': f'Failed to save picklist data: {str(e)}',
            'error': str(e),
            'traceback': traceback.format_exc()
        }


functions = {
    "parse_picklist_pdf": parse_picklist_pdf,
    "save_picklist_data": save_picklist_data,
}
