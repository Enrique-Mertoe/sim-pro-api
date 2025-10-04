"""
Utility functions for processing picklist PDFs and parsing picklist data.
This module handles PDF text extraction and parsing of picklist metadata and serial numbers.
"""
import re
from typing import Tuple, List, Dict, Any
from io import BytesIO
import pdfplumber


class PicklistParser:
    """
    Parser for extracting metadata and serial numbers from picklist text.
    """

    @staticmethod
    def is_picklist(text: str) -> bool:
        """
        Detects if the provided text is a picklist based on key indicators.

        Args:
            text: The text to check

        Returns:
            True if the text appears to be a picklist, False otherwise
        """
        indicators = [
            r'Order No\s*:?\s*\d+',
            r'Requisition No\s*:?\s*\d+',
            r'Collection Point',
            r'Move Order Number',
            r'Date Created',
            r'<<Lot>>',
            r'Serial Numbers'
        ]

        match_count = sum(1 for regex in indicators if re.search(regex, text, re.IGNORECASE))

        # If at least 3 indicators are present, consider it a picklist
        return match_count >= 3

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalizes whitespace while preserving paragraph breaks.
        - Collapses multiple spaces/tabs into a single space
        - Collapses multiple blank lines into a double newline
        - Trims leading/trailing whitespace
        """
        return (
            re.sub(r'\n\s*\n', '\n\n',  # collapse multiple blank lines into double newline
                   re.sub(r'\s+', ' ', text))  # collapse all whitespace into single space
            .strip()
        )

    @staticmethod
    def extract_serials_with_lots(text: str) -> Tuple[List[Dict[str, Any]], int]:
        """
        Extracts serial numbers organized by lot numbers from picklist text.

        Args:
            text: The picklist text

        Returns:
            Tuple of (list of lots with serial numbers, total serial count)
        """
        serials_with_lots = []
        sections = re.split(r'<<\s*(\d+\s*[-_][A-Z0-9\-]+)\s*>>', text, flags=re.IGNORECASE)
        count = 0

        # Process sections in pairs (lot number, content)
        for i in range(1, len(sections), 2):
            lot_number = sections[i].strip()

            content = sections[i + 1] if i + 1 < len(sections) else ''
            # Extract serial numbers from content
            # Split by whitespace, commas, or semicolons
            tokens = re.split(r'[\s,;]+', content)
            print("tokens",tokens)
            serial_numbers = []

            for token in tokens:
                if not token:
                    continue
                # Find all digit sequences and get the longest one
                matches = re.findall(r'\d+', token)
                if matches:
                    longest = max(matches, key=len)
                    # Only keep if 16+ digits (valid serial number length)
                    if len(longest) >= 16:
                        serial_numbers.append(longest)

            count += len(serial_numbers)
            print("count", len(serial_numbers))
            serials_with_lots.append({
                'lotNumber': lot_number,
                'serialNumbers': serial_numbers
            })

        return serials_with_lots, count

    @staticmethod
    def parse_picklist_metadata(text: str, user_id: str) -> Dict[str, Any]:
        """
        Extracts metadata from picklist text.

        Args:
            text: The picklist text to parse
            user_id: The user ID of the creator

        Returns:
            Dictionary with extracted metadata
        """
        # Clean up the text
        clean_text = text.replace('\r\n', '\n').replace('\n', ' ')
        clean_text = re.sub(r'\s+', ' ', clean_text)

        metadata = {
            'created_by_user_id': user_id,
            'lot_numbers': []
        }

        # Extract order number
        order_match = re.search(r'Order No\s*:?\s*(\d+)', clean_text, re.IGNORECASE)
        if order_match:
            metadata['order_number'] = order_match.group(1).strip()

        # Extract requisition number
        req_match = re.search(r'Requisition No\s*:?\s*(\d+)', clean_text, re.IGNORECASE)
        if req_match:
            metadata['requisition_number'] = req_match.group(1).strip()

        # Extract company name
        company_match = re.search(r'Requisition No\s*:?\s*\d+\s+([A-Z\s]+LIMITED)', clean_text, re.IGNORECASE)
        if company_match:
            metadata['company_name'] = company_match.group(1).strip()

        # Extract collection point
        collection_match = re.search(r'Collection Point\s*:?\s*([A-Z0-9\s]+)', clean_text, re.IGNORECASE)
        if collection_match:
            metadata['collection_point'] = collection_match.group(1).strip()

        # Extract move order number
        move_order_match = re.search(r'Move Order Number\s*:?\s*(\d+)', clean_text, re.IGNORECASE)
        if move_order_match:
            metadata['move_order_number'] = move_order_match.group(1).strip()

        # Extract date created
        date_match = re.search(r'Date Created\s*:?\s*(\d{2}-[A-Z]{3}-\d{2})', clean_text, re.IGNORECASE)
        if date_match:
            metadata['date_created'] = date_match.group(1).strip()

        # Extract lot numbers
        lot_matches = re.finditer(r'<<(\d+\s*_[A-Z0-9]+)>>', clean_text)
        for match in lot_matches:
            metadata['lot_numbers'].append(match.group(1).strip())

        # Extract item description
        desc_match = re.search(r'Description\s*:?\s*([A-Z0-9\s]+Safaricom[A-Z0-9\s]+)', clean_text, re.IGNORECASE)
        if desc_match:
            metadata['item_description'] = desc_match.group(1).strip()

        # Extract quantity
        quantity_match = re.search(r'Quantity\s*:?\s*(\d+\.?\d*)', clean_text, re.IGNORECASE)
        if quantity_match:
            metadata['quantity'] = float(quantity_match.group(1).strip())

        return metadata


class PDFProcessor:
    """
    Processor for extracting text from PDF files.
    """

    @staticmethod
    def extract_text_from_pdf(file_content: bytes) -> Tuple[str, int]:
        """
        Extracts text from a PDF file using pdfplumber for better text extraction quality.

        Args:
            file_content: The PDF file content as bytes

        Returns:
            Tuple of (extracted text, number of pages)
        """
        try:
            pdf_file = BytesIO(file_content)

            with pdfplumber.open(pdf_file) as pdf:
                num_pages = len(pdf.pages)
                full_text = ''

                for page in pdf.pages:
                    # Extract text from page
                    text = page.extract_text()
                    if text:
                        full_text += text + '\n\n'

            # Normalize the extracted text
            normalized_text = PicklistParser.normalize_text(full_text)

            return normalized_text, num_pages

        except Exception as e:
            raise Exception(f'Failed to extract text from PDF: {str(e)}')
