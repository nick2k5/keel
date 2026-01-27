"""Relationship model."""
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class Contact:
    """A contact person at a company."""
    name: str
    email: Optional[str] = None
    role: Optional[str] = None


@dataclass
class TimelineEvent:
    """An event in the relationship timeline."""
    date: str
    event: str


@dataclass
class Introducer:
    """Person who made an introduction."""
    name: str
    email: Optional[str] = None
    context: Optional[str] = None


@dataclass
class Relationship:
    """Represents the relationship history with a company."""
    domain: str
    company_name: str
    introducer: Optional[Introducer] = None
    contacts: List[Contact] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)
    summary: Optional[str] = None
    key_topics: List[str] = field(default_factory=list)
    sentiment: str = 'neutral'
    next_steps: Optional[str] = None
    doc_id: Optional[str] = None
    folder_id: Optional[str] = None

    @classmethod
    def from_firestore(cls, data: dict) -> 'Relationship':
        """Create Relationship from Firestore document."""
        introducer = None
        if data.get('introducer'):
            intro_data = data['introducer']
            introducer = Introducer(
                name=intro_data.get('name', 'Unknown'),
                email=intro_data.get('email'),
                context=intro_data.get('context')
            )

        contacts = [
            Contact(
                name=c.get('name', 'Unknown'),
                email=c.get('email'),
                role=c.get('role')
            )
            for c in data.get('contacts', [])
        ]

        timeline = [
            TimelineEvent(
                date=t.get('date', 'Unknown'),
                event=t.get('event', '')
            )
            for t in data.get('timeline', [])
        ]

        return cls(
            domain=data.get('domain', ''),
            company_name=data.get('company_name', ''),
            introducer=introducer,
            contacts=contacts,
            timeline=timeline,
            summary=data.get('summary'),
            key_topics=data.get('key_topics', []),
            sentiment=data.get('sentiment', 'neutral'),
            next_steps=data.get('next_steps'),
            doc_id=data.get('doc_id'),
            folder_id=data.get('folder_id')
        )

    def to_dict(self) -> dict:
        """Convert to dict for Firestore storage."""
        return {
            'domain': self.domain,
            'company_name': self.company_name,
            'introducer': {
                'name': self.introducer.name,
                'email': self.introducer.email,
                'context': self.introducer.context
            } if self.introducer else None,
            'contacts': [
                {'name': c.name, 'email': c.email, 'role': c.role}
                for c in self.contacts
            ],
            'timeline': [
                {'date': t.date, 'event': t.event}
                for t in self.timeline
            ],
            'summary': self.summary,
            'key_topics': self.key_topics,
            'sentiment': self.sentiment,
            'next_steps': self.next_steps,
            'doc_id': self.doc_id,
            'folder_id': self.folder_id
        }
