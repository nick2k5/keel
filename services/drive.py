"""Google Drive service for file and folder operations."""
import logging
from typing import Optional

from googleapiclient.discovery import build
from config import config

logger = logging.getLogger(__name__)


class DriveService:
    """Service for Google Drive operations."""

    def __init__(self, credentials):
        self.service = build('drive', 'v3', credentials=credentials)
        self.parent_folder_id = config.drive_parent_folder_id

    def find_existing_folder(self, company: str, domain: str) -> Optional[str]:
        """Find an existing folder for the company in the parent folder."""
        folder_name = f"{company} ({domain})"

        try:
            # Search for folder with exact name in parent folder
            query = (
                f"name = '{folder_name}' and "
                f"'{self.parent_folder_id}' in parents and "
                f"mimeType = 'application/vnd.google-apps.folder' and "
                f"trashed = false"
            )

            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora='allDrives'
            ).execute()

            files = results.get('files', [])
            if files:
                folder_id = files[0]['id']
                logger.info(f"Found existing folder '{folder_name}' with ID: {folder_id}")
                return folder_id

            return None

        except Exception as e:
            logger.error(f"Error searching for folder: {e}", exc_info=True)
            return None

    def create_folder(self, company: str, domain: str) -> str:
        """Create a folder in the parent folder, or return existing one."""
        folder_name = f"{company} ({domain})"

        # Check for existing folder first
        existing_folder_id = self.find_existing_folder(company, domain)
        if existing_folder_id:
            return existing_folder_id

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

    def find_document_in_folder(self, folder_id: str, doc_name: str) -> Optional[str]:
        """Find a document by name in a folder."""
        try:
            query = f"name = '{doc_name}' and '{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false"
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()

            files = results.get('files', [])
            if files:
                doc_id = files[0]['id']
                logger.info(f"Found existing document '{doc_name}' with ID: {doc_id}")
                return doc_id
            return None

        except Exception as e:
            logger.warning(f"Error searching for document: {e}")
            return None

    def create_document(self, folder_id: str, company: str) -> str:
        """Get or create the 'Initial Brief' document in the specified folder."""
        doc_name = "Initial Brief"

        # Check for existing Initial Brief document
        existing_doc_id = self.find_document_in_folder(folder_id, doc_name)
        if existing_doc_id:
            return existing_doc_id

        try:
            file_metadata = {
                'name': doc_name,
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [folder_id]
            }

            doc = self.service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()

            doc_id = doc.get('id')
            logger.info(f"Created document '{doc_name}' with ID: {doc_id}")
            return doc_id

        except Exception as e:
            logger.error(f"Error creating document for {company}: {e}", exc_info=True)
            raise
