"""Firestore service for idempotency tracking."""
import logging
from typing import Dict, Optional, Any

from google.cloud import firestore as firestore_module
from config import config

logger = logging.getLogger(__name__)


class FirestoreService:
    """Service for Firestore idempotency tracking."""

    def __init__(self):
        self.db = firestore_module.Client(project=config.project_id)
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
            'processed_at': firestore_module.SERVER_TIMESTAMP
        })

        logger.info(f"Marked {domain} as processed in Firestore")

    def get_processed(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get processed record for a domain."""
        normalized = self.normalize_domain(domain)
        doc_ref = self.db.collection(self.collection).document(normalized)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def clear_processed(self, domain: str) -> bool:
        """Clear the processed record for a domain to allow reprocessing."""
        normalized = self.normalize_domain(domain)
        doc_ref = self.db.collection(self.collection).document(normalized)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.delete()
            logger.info(f"Cleared processed record for {domain}")
            return True
        logger.info(f"No processed record found for {domain}")
        return False

    def get_yc_company_data(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Get stored YC company data (posts, founders) for a company."""
        company_key = company_name.lower().replace(' ', '-')
        doc_ref = self.db.collection('yc_companies').document(company_key)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def get_relationship_data(self, domain: str = None, company_name: str = None) -> Optional[Dict[str, Any]]:
        """Get relationship data (emails, timeline, contacts) for a company.

        Args:
            domain: Company domain to look up
            company_name: Company name to look up (fallback if no domain)
        """
        # Try by domain first
        if domain:
            normalized = domain.lower().strip()
            doc_ref = self.db.collection('relationships').document(normalized)
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()

        # Try by company name as key
        if company_name:
            company_key = company_name.lower().replace(' ', '-')
            doc_ref = self.db.collection('relationships').document(company_key)
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()

        return None
