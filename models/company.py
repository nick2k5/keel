"""Company model."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Company:
    """Represents a company in the deal flow pipeline."""
    name: str
    domain: Optional[str] = None
    source: Optional[str] = None  # e.g., 'W26' for YC batch
    row_number: Optional[int] = None
    status: Optional[str] = None

    @property
    def is_yc(self) -> bool:
        """Check if company is from Y Combinator."""
        if not self.source:
            return False
        return self.source.upper().startswith(('W', 'S'))

    @property
    def firestore_key(self) -> str:
        """Get the key used for Firestore lookups."""
        if self.domain:
            return self.domain.lower().strip()
        return self.name.lower().replace(' ', '-')

    @classmethod
    def from_sheet_row(cls, row: dict) -> 'Company':
        """Create Company from spreadsheet row dict."""
        return cls(
            name=row.get('company', ''),
            domain=row.get('domain'),
            source=row.get('source'),
            row_number=row.get('row_number'),
            status=row.get('status')
        )
