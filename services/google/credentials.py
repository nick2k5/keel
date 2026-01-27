"""Google Cloud credentials management."""
import json
import logging
from typing import Optional

from google.oauth2 import service_account
from google.auth import default
from google.cloud import secretmanager

from config import config

logger = logging.getLogger(__name__)


def get_credentials(include_gmail: bool = False):
    """Get Google Cloud credentials with required scopes.

    Args:
        include_gmail: Whether to include Gmail API scope (requires domain-wide delegation)

    Returns:
        Google Cloud credentials object
    """
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/documents'
    ]

    if include_gmail:
        scopes.append('https://www.googleapis.com/auth/gmail.readonly')

    credentials, project = default(scopes=scopes)
    return credentials


def get_gmail_credentials(user_email: str):
    """Get Gmail credentials with domain-wide delegation.

    This loads a dedicated service account from Secret Manager that has
    domain-wide delegation enabled for Gmail API access.

    Args:
        user_email: Email address to impersonate via delegation

    Returns:
        Credentials with delegation to the specified user
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{config.project_id}/secrets/keel-gmail-credentials/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        key_data = json.loads(response.payload.data.decode('UTF-8'))

        scopes = ['https://www.googleapis.com/auth/gmail.readonly']
        credentials = service_account.Credentials.from_service_account_info(
            key_data,
            scopes=scopes,
            subject=user_email
        )

        logger.info(f"Loaded Gmail credentials with delegation to {user_email}")
        return credentials

    except Exception as e:
        logger.error(f"Error loading Gmail credentials: {e}", exc_info=True)
        raise


class ServiceFactory:
    """Factory for creating pre-configured service instances."""

    def __init__(self, credentials=None, gmail_credentials=None):
        self._credentials = credentials
        self._gmail_credentials = gmail_credentials

    @classmethod
    def create(cls, include_gmail: bool = False, gmail_user: Optional[str] = None) -> 'ServiceFactory':
        """Create a ServiceFactory with appropriate credentials.

        Args:
            include_gmail: Whether to include Gmail service
            gmail_user: Email address for Gmail delegation (required if include_gmail=True)

        Returns:
            ServiceFactory instance
        """
        credentials = get_credentials(include_gmail=False)
        gmail_credentials = None

        if include_gmail and gmail_user:
            gmail_credentials = get_gmail_credentials(gmail_user)

        return cls(credentials=credentials, gmail_credentials=gmail_credentials)

    def create_all(self, gmail_user: Optional[str] = None) -> dict:
        """Create all services as a dict.

        Args:
            gmail_user: Email for Gmail service (optional)

        Returns:
            Dict of service name to service instance
        """
        from services.google.sheets import SheetsService
        from services.google.drive import DriveService
        from services.google.docs import DocsService
        from services.google.firestore import FirestoreService
        from services.google.gemini import GeminiService
        from services.google.gmail import GmailService

        services = {
            'sheets': SheetsService(self._credentials),
            'drive': DriveService(self._credentials),
            'docs': DocsService(self._credentials),
            'firestore': FirestoreService(),
            'gemini': GeminiService(),
        }

        if self._gmail_credentials and gmail_user:
            services['gmail'] = GmailService(
                credentials=self._gmail_credentials,
                user_email=gmail_user
            )

        return services

    @property
    def sheets(self):
        from services.google.sheets import SheetsService
        return SheetsService(self._credentials)

    @property
    def drive(self):
        from services.google.drive import DriveService
        return DriveService(self._credentials)

    @property
    def docs(self):
        from services.google.docs import DocsService
        return DocsService(self._credentials)

    @property
    def firestore(self):
        from services.google.firestore import FirestoreService
        return FirestoreService()

    @property
    def gemini(self):
        from services.google.gemini import GeminiService
        return GeminiService()
