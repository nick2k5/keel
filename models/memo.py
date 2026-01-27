"""Memo model."""
from dataclasses import dataclass
from typing import Optional
from models.company import Company


@dataclass
class Memo:
    """Represents an investment memo document."""
    company: Company
    doc_id: str
    folder_id: str
    content: Optional[str] = None

    @property
    def doc_url(self) -> str:
        """Get the Google Docs URL for this memo."""
        return f"https://docs.google.com/document/d/{self.doc_id}/edit"
