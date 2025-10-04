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


functions = {
    "parse_picklist_pdf": parse_picklist_pdf
}
