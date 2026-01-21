"""Business logic services for processing companies."""
import logging
import json
from typing import Dict, List, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import firestore
import vertexai
from vertexai.preview.generative_models import GenerativeModel
from config import config

logger = logging.getLogger(__name__)


class SheetsService:
    """Service for interacting with Google Sheets."""

    def __init__(self, credentials):
        self.service = build('sheets', 'v4', credentials=credentials)
        self.spreadsheet_id = config.spreadsheet_id

    def get_rows_to_process(self) -> List[Dict]:
        """Get rows from Index tab that need processing."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Index!A:C'
            ).execute()

            values = result.get('values', [])
            if not values:
                logger.info("No data found in spreadsheet")
                return []

            # Skip header row
            headers = values[0] if values else []
            rows_to_process = []

            for idx, row in enumerate(values[1:], start=2):
                if len(row) < 2:  # Need at least Company and Domain
                    continue

                company = row[0].strip() if len(row) > 0 else ""
                domain = row[1].strip() if len(row) > 1 else ""
                status = row[2].strip() if len(row) > 2 else ""

                # Process if Status is empty or "New"
                if not status or status == "New":
                    if company and domain:
                        rows_to_process.append({
                            'row_number': idx,
                            'company': company,
                            'domain': domain,
                            'status': status
                        })

            logger.info(f"Found {len(rows_to_process)} rows to process")
            return rows_to_process

        except Exception as e:
            logger.error(f"Error reading spreadsheet: {e}", exc_info=True)
            raise

    def update_status(self, row_number: int, status: str):
        """Update the Status column for a specific row."""
        try:
            range_name = f'Index!C{row_number}'
            body = {'values': [[status]]}

            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()

            logger.info(f"Updated row {row_number} status to '{status}'")

        except Exception as e:
            logger.error(f"Error updating status for row {row_number}: {e}", exc_info=True)
            raise


class FirestoreService:
    """Service for Firestore idempotency tracking."""

    def __init__(self):
        self.db = firestore.Client(project=config.project_id)
        self.collection = config.firestore_collection

    @staticmethod
    def normalize_domain(domain: str) -> str:
        """Normalize domain for consistent keying."""
        return domain.lower().strip()

    def is_processed(self, domain: str) -> bool:
        """Check if a domain has already been processed."""
        normalized = self.normalize_domain(domain)
        doc_ref = self.db.collection(self.collection).document(normalized)
        doc = doc_ref.get()
        return doc.exists

    def mark_processed(self, domain: str, company: str, doc_id: str, folder_id: str):
        """Mark a domain as processed with metadata."""
        normalized = self.normalize_domain(domain)
        doc_ref = self.db.collection(self.collection).document(normalized)

        doc_ref.set({
            'domain': domain,
            'normalized_domain': normalized,
            'company': company,
            'doc_id': doc_id,
            'folder_id': folder_id,
            'processed_at': firestore.SERVER_TIMESTAMP
        })

        logger.info(f"Marked {domain} as processed in Firestore")


class DriveService:
    """Service for Google Drive operations."""

    def __init__(self, credentials):
        self.service = build('drive', 'v3', credentials=credentials)
        self.parent_folder_id = config.drive_parent_folder_id

    def create_folder(self, company: str, domain: str) -> str:
        """Create a folder in the parent folder."""
        folder_name = f"{company} ({domain})"

        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [self.parent_folder_id]
            }

            folder = self.service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()

            folder_id = folder.get('id')
            logger.info(f"Created folder '{folder_name}' with ID: {folder_id}")
            return folder_id

        except Exception as e:
            logger.error(f"Error creating folder for {company}: {e}", exc_info=True)
            raise

    def copy_template(self, folder_id: str, company: str) -> str:
        """Copy the template document into the specified folder."""
        try:
            file_metadata = {
                'name': f"{company} - Investment Memo",
                'parents': [folder_id]
            }

            copied_file = self.service.files().copy(
                fileId=config.template_doc_id,
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()

            doc_id = copied_file.get('id')
            logger.info(f"Copied template to doc ID: {doc_id}")
            return doc_id

        except Exception as e:
            logger.error(f"Error copying template: {e}", exc_info=True)
            raise


class GeminiService:
    """Service for Google Gemini via Vertex AI."""

    def __init__(self):
        # Initialize Vertex AI
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-1.5-flash")

    def generate_memo(self, company: str, domain: str) -> Dict[str, str]:
        """Generate investment memo content using Gemini."""
        prompt = f"""You are a venture capital analyst. Generate a concise investment memo for the following company:

Company: {company}
Domain: {domain}

Provide a JSON response with exactly these keys (no markdown, just JSON):
- EXEC_SUMMARY: 2-3 sentence executive summary
- TEAM: Assessment of the founding team (1-2 sentences)
- PRODUCT: Description of the product/service (2-3 sentences)
- MARKET: Market size and opportunity (2-3 sentences)
- TRACTION: Current traction and metrics (2-3 sentences)
- RISKS: Key risks and concerns (2-3 sentences)
- QUESTIONS: Important due diligence questions (2-3 bullet points)
- RECOMMENDATION: Investment recommendation (1-2 sentences)

Write in a crisp, professional VC memo style. Be specific and analytical."""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 2048,
                    "temperature": 0.7,
                }
            )

            # Extract text content
            content = response.text

            # Parse JSON response
            memo_data = json.loads(content)

            logger.info(f"Generated memo for {company}")
            return memo_data

        except Exception as e:
            logger.error(f"Error generating memo with Gemini: {e}", exc_info=True)
            raise


class DocsService:
    """Service for Google Docs operations."""

    def __init__(self, credentials):
        self.service = build('docs', 'v1', credentials=credentials)

    def update_document(self, doc_id: str, company: str, domain: str, memo_data: Dict[str, str]):
        """Update document with generated content using batchUpdate."""
        try:
            # Build replaceAllText requests for each placeholder
            requests = [
                {'replaceAllText': {
                    'containsText': {'text': '{{COMPANY}}', 'matchCase': True},
                    'replaceText': company
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{DOMAIN}}', 'matchCase': True},
                    'replaceText': domain
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{EXEC_SUMMARY}}', 'matchCase': True},
                    'replaceText': memo_data.get('EXEC_SUMMARY', '')
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{TEAM}}', 'matchCase': True},
                    'replaceText': memo_data.get('TEAM', '')
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{PRODUCT}}', 'matchCase': True},
                    'replaceText': memo_data.get('PRODUCT', '')
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{MARKET}}', 'matchCase': True},
                    'replaceText': memo_data.get('MARKET', '')
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{TRACTION}}', 'matchCase': True},
                    'replaceText': memo_data.get('TRACTION', '')
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{RISKS}}', 'matchCase': True},
                    'replaceText': memo_data.get('RISKS', '')
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{QUESTIONS}}', 'matchCase': True},
                    'replaceText': memo_data.get('QUESTIONS', '')
                }},
                {'replaceAllText': {
                    'containsText': {'text': '{{RECOMMENDATION}}', 'matchCase': True},
                    'replaceText': memo_data.get('RECOMMENDATION', '')
                }}
            ]

            self.service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Updated document {doc_id} with memo content")

        except Exception as e:
            logger.error(f"Error updating document {doc_id}: {e}", exc_info=True)
            raise
