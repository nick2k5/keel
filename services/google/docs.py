"""Google Docs service for document operations."""
import logging
import re

from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class DocsService:
    """Service for Google Docs operations."""

    def __init__(self, credentials):
        self.service = build('docs', 'v1', credentials=credentials)

    def insert_text(self, doc_id: str, content: str):
        """Insert markdown content into a Google Doc with proper formatting.

        Clears existing content before inserting new content.
        """
        try:
            # First, clear existing content from the document
            doc = self.service.documents().get(documentId=doc_id).execute()
            doc_content = doc.get('body', {}).get('content', [])

            # Find the end index of existing content
            end_index = 1
            for element in doc_content:
                if 'endIndex' in element:
                    end_index = max(end_index, element['endIndex'])

            # Delete existing content if there is any (leave index 1 which is required)
            if end_index > 2:
                delete_request = [{
                    'deleteContentRange': {
                        'range': {
                            'startIndex': 1,
                            'endIndex': end_index - 1
                        }
                    }
                }]
                self.service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': delete_request}
                ).execute()
                logger.info(f"Cleared existing content from document {doc_id}")

            # Parse markdown and convert to Google Docs format
            lines = content.split('\n')
            requests = []
            current_index = 1  # Google Docs index starts at 1

            # Track ranges for formatting
            heading_ranges = []  # (start, end, level)
            bold_ranges = []     # (start, end)

            # First pass: build plain text and track formatting ranges
            plain_lines = []
            for line in lines:
                original_line = line

                # Detect heading level
                heading_level = 0
                if line.startswith('# '):
                    heading_level = 1
                    line = line[2:]
                elif line.startswith('## '):
                    heading_level = 2
                    line = line[3:]
                elif line.startswith('### '):
                    heading_level = 3
                    line = line[4:]

                # Track heading range
                if heading_level > 0:
                    start = current_index
                    end = current_index + len(line)
                    heading_ranges.append((start, end, heading_level))

                # Track bold ranges (simple **text** pattern)
                line_with_bold = line
                bold_offset = 0
                for match in re.finditer(r'\*\*(.+?)\*\*', line):
                    # Adjust for removed ** markers
                    actual_start = current_index + match.start() - bold_offset
                    actual_end = actual_start + len(match.group(1))
                    bold_ranges.append((actual_start, actual_end))
                    bold_offset += 4  # Remove 4 chars (two ** on each side)

                # Remove markdown bold markers from text
                line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)

                plain_lines.append(line)
                current_index += len(line) + 1  # +1 for newline

            plain_text = '\n'.join(plain_lines)

            # Insert all text first
            requests.append({
                'insertText': {
                    'location': {'index': 1},
                    'text': plain_text
                }
            })

            # Apply heading styles (must be done after text insertion)
            for start, end, level in heading_ranges:
                heading_style = 'HEADING_1' if level == 1 else 'HEADING_2' if level == 2 else 'HEADING_3'
                requests.append({
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': start,
                            'endIndex': end
                        },
                        'paragraphStyle': {
                            'namedStyleType': heading_style
                        },
                        'fields': 'namedStyleType'
                    }
                })

            # Apply bold formatting
            for start, end in bold_ranges:
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': start,
                            'endIndex': end
                        },
                        'textStyle': {
                            'bold': True
                        },
                        'fields': 'bold'
                    }
                })

            self.service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Inserted formatted content into document {doc_id}")

        except Exception as e:
            logger.error(f"Error inserting text into document {doc_id}: {e}", exc_info=True)
            raise
