"""Services package."""
# Google services (new location)
from services.google import (
    get_credentials,
    get_gmail_credentials,
    ServiceFactory,
    SheetsService,
    DriveService,
    DocsService,
    GmailService,
    InboxSyncService,
    FirestoreService,
    GeminiService,
)

# Other services
from services.bookface import BookfaceService
from services.email_agent import EmailAgentService
from services.question import QuestionService

# Legacy - keep old ResearchService for backward compatibility during migration
# TODO: Remove after migration complete
try:
    from services.research import ResearchService
except ImportError:
    ResearchService = None

__all__ = [
    # Credentials
    'get_credentials',
    'get_gmail_credentials',
    'ServiceFactory',
    # Google services
    'SheetsService',
    'FirestoreService',
    'DriveService',
    'DocsService',
    'GeminiService',
    'GmailService',
    'InboxSyncService',
    # Other services
    'BookfaceService',
    'EmailAgentService',
    'QuestionService',
    # Legacy
    'ResearchService',
]
