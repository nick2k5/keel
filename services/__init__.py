"""Services package - re-exports all classes for backward compatibility."""
from services.sheets import SheetsService
from services.firestore import FirestoreService
from services.drive import DriveService
from services.docs import DocsService
from services.gemini import GeminiService
from services.research import ResearchService
from services.bookface import BookfaceService
from services.email_agent import EmailAgentService

__all__ = [
    'SheetsService',
    'FirestoreService',
    'DriveService',
    'DocsService',
    'GeminiService',
    'ResearchService',
    'BookfaceService',
    'EmailAgentService',
]
