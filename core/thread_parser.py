"""Email thread parsing logic."""
import re
import logging
from typing import List, Dict, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class ThreadParser:
    """Parses forwarded email threads into structured data."""

    # Domains to exclude when extracting company domains
    EXCLUDED_DOMAINS = {
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'googlemail.com', 'icloud.com', 'me.com', 'friale.com',
        'aol.com', 'protonmail.com', 'mail.com', 'live.com', 'msn.com'
    }

    def parse_thread(self, email_body: str) -> List[Dict[str, str]]:
        """Parse a forwarded email thread into individual messages.

        Args:
            email_body: Raw email body text

        Returns:
            List of message dicts with 'from', 'date', 'subject', 'body'
        """
        messages = []

        # Split by forwarded message markers
        forwarded_pattern = r'-{5,}\s*Forwarded message\s*-{5,}'
        parts = re.split(forwarded_pattern, email_body, flags=re.IGNORECASE)

        for part in parts:
            sub_messages = self._extract_messages_from_part(part)
            messages.extend(sub_messages)

        # If no messages found, treat as single message
        if not messages and email_body.strip():
            from_match = re.search(r'From:\s*([^\n]+)', email_body)
            date_match = re.search(r'Date:\s*([^\n]+)', email_body)
            subject_match = re.search(r'Subject:\s*([^\n]+)', email_body)

            messages.append({
                'from': from_match.group(1).strip() if from_match else 'Unknown',
                'date': date_match.group(1).strip() if date_match else 'Unknown',
                'subject': subject_match.group(1).strip() if subject_match else 'Unknown',
                'body': email_body.strip()
            })

        return messages

    def _extract_messages_from_part(self, text: str) -> List[Dict[str, str]]:
        """Extract individual email messages from a text block."""
        messages = []

        # Pattern for email headers block
        header_pattern = r'From:\s*([^\n]+)\n(?:.*?Date:\s*([^\n]+))?(?:.*?Subject:\s*([^\n]+))?'

        matches = list(re.finditer(header_pattern, text, re.DOTALL | re.IGNORECASE))

        for i, match in enumerate(matches):
            from_addr = match.group(1).strip() if match.group(1) else 'Unknown'
            date = match.group(2).strip() if match.group(2) else 'Unknown'
            subject = match.group(3).strip() if match.group(3) else 'Unknown'

            # Get body until next header or end
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()

            # Clean up body - remove quoted text markers
            body = re.sub(r'^>\s*', '', body, flags=re.MULTILINE)

            if from_addr != 'Unknown' or body:
                messages.append({
                    'from': from_addr,
                    'date': date,
                    'subject': subject,
                    'body': body[:2000]
                })

        return messages

    def extract_domain(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """Extract the primary external domain from email messages.

        Args:
            messages: List of parsed message dicts

        Returns:
            Most common external domain, or None
        """
        domains = []

        for msg in messages:
            from_addr = msg.get('from', '')
            email_match = re.search(r'[\w\.-]+@([\w\.-]+)', from_addr)
            if email_match:
                domain = email_match.group(1).lower()
                if domain not in self.EXCLUDED_DOMAINS:
                    domains.append(domain)

        if domains:
            return Counter(domains).most_common(1)[0][0]
        return None

    def merge_messages(self, existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """Merge new messages with existing ones, avoiding duplicates.

        Args:
            existing: List of existing message dicts
            new: List of new message dicts to merge

        Returns:
            Merged list without duplicates
        """
        existing_sigs = set()
        for msg in existing:
            sig = f"{msg.get('from', '')}|{msg.get('date', '')}|{msg.get('subject', '')}"
            existing_sigs.add(sig)

        merged = list(existing)
        for msg in new:
            sig = f"{msg.get('from', '')}|{msg.get('date', '')}|{msg.get('subject', '')}"
            if sig not in existing_sigs:
                merged.append(msg)
                existing_sigs.add(sig)

        return merged
