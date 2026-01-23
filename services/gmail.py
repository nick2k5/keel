"""Gmail service for fetching and processing inbox emails."""
import base64
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from email.utils import parsedate_to_datetime

from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.auth import default
from bs4 import BeautifulSoup

from config import config

logger = logging.getLogger(__name__)


class GmailService:
    """Service for fetching emails from Gmail API."""

    # Firestore collection for tracking processed emails
    PROCESSED_EMAILS_COLLECTION = 'processed_emails'

    def __init__(self, credentials=None, user_email: str = None):
        """Initialize Gmail service.

        Args:
            credentials: Google credentials (if None, uses default with delegation)
            user_email: Email address to impersonate (required for service account delegation)
        """
        self.user_email = user_email

        if credentials:
            self.credentials = credentials
        else:
            # For service account with domain-wide delegation
            scopes = ['https://www.googleapis.com/auth/gmail.readonly']
            self.credentials, _ = default(scopes=scopes)

        # If using service account delegation, create delegated credentials
        if user_email and hasattr(self.credentials, 'with_subject'):
            self.credentials = self.credentials.with_subject(user_email)

        self.service = build('gmail', 'v1', credentials=self.credentials)

    def fetch_emails(
        self,
        query: str = None,
        max_results: int = 50,
        after_date: datetime = None,
        before_date: datetime = None,
        label_ids: List[str] = None,
        include_spam_trash: bool = False
    ) -> List[Dict[str, Any]]:
        """Fetch emails from Gmail matching the query.

        Args:
            query: Gmail search query (e.g., "from:someone@example.com")
            max_results: Maximum number of emails to fetch
            after_date: Only fetch emails after this date
            before_date: Only fetch emails before this date
            label_ids: Filter by label IDs (e.g., ['INBOX', 'UNREAD'])
            include_spam_trash: Include spam and trash in results

        Returns:
            List of parsed email dictionaries
        """
        # Build query string
        query_parts = []
        if query:
            query_parts.append(query)
        if after_date:
            query_parts.append(f"after:{after_date.strftime('%Y/%m/%d')}")
        if before_date:
            query_parts.append(f"before:{before_date.strftime('%Y/%m/%d')}")

        full_query = ' '.join(query_parts) if query_parts else None

        logger.info(f"Fetching emails with query: {full_query}, max_results: {max_results}")

        try:
            # List messages
            list_params = {
                'userId': 'me',
                'maxResults': max_results,
                'includeSpamTrash': include_spam_trash
            }
            if full_query:
                list_params['q'] = full_query
            if label_ids:
                list_params['labelIds'] = label_ids

            results = self.service.users().messages().list(**list_params).execute()
            messages = results.get('messages', [])

            if not messages:
                logger.info("No messages found")
                return []

            # Fetch full message details
            emails = []
            for msg in messages:
                try:
                    email_data = self._get_email_details(msg['id'])
                    if email_data:
                        emails.append(email_data)
                except Exception as e:
                    logger.warning(f"Error fetching email {msg['id']}: {e}")
                    continue

            logger.info(f"Fetched {len(emails)} emails")
            return emails

        except Exception as e:
            logger.error(f"Error fetching emails: {e}", exc_info=True)
            raise

    def _get_email_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get full details of a single email.

        Args:
            message_id: Gmail message ID

        Returns:
            Parsed email dictionary or None if error
        """
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            # Extract headers
            headers = {h['name'].lower(): h['value'] for h in message['payload'].get('headers', [])}

            # Parse date
            date_str = headers.get('date', '')
            try:
                parsed_date = parsedate_to_datetime(date_str)
            except Exception:
                parsed_date = None

            # Extract body
            body = self._extract_body(message['payload'])

            return {
                'id': message_id,
                'thread_id': message.get('threadId'),
                'from': headers.get('from', ''),
                'to': headers.get('to', ''),
                'cc': headers.get('cc', ''),
                'subject': headers.get('subject', ''),
                'date': date_str,
                'parsed_date': parsed_date,
                'body': body,
                'snippet': message.get('snippet', ''),
                'labels': message.get('labelIds', []),
                'internal_date': message.get('internalDate')
            }

        except Exception as e:
            logger.error(f"Error getting email details for {message_id}: {e}")
            return None

    def _extract_body(self, payload: Dict) -> str:
        """Extract email body from payload, preferring plain text over HTML.

        Args:
            payload: Gmail message payload

        Returns:
            Extracted body text
        """
        body = ''

        # Check for simple body
        if 'body' in payload and payload['body'].get('data'):
            body = self._decode_base64(payload['body']['data'])
            if payload.get('mimeType') == 'text/html':
                body = self._html_to_text(body)
            return body

        # Check for multipart
        parts = payload.get('parts', [])
        plain_text = ''
        html_text = ''

        for part in parts:
            mime_type = part.get('mimeType', '')

            if mime_type == 'text/plain':
                if part.get('body', {}).get('data'):
                    plain_text = self._decode_base64(part['body']['data'])
            elif mime_type == 'text/html':
                if part.get('body', {}).get('data'):
                    html_text = self._decode_base64(part['body']['data'])
            elif mime_type.startswith('multipart/'):
                # Recursively extract from nested parts
                nested_body = self._extract_body(part)
                if nested_body:
                    if not plain_text:
                        plain_text = nested_body

        # Prefer plain text, fall back to HTML
        if plain_text:
            return plain_text
        elif html_text:
            return self._html_to_text(html_text)

        return body

    def _decode_base64(self, data: str) -> str:
        """Decode base64url encoded data."""
        try:
            # Gmail uses URL-safe base64
            decoded = base64.urlsafe_b64decode(data)
            return decoded.decode('utf-8', errors='replace')
        except Exception as e:
            logger.warning(f"Error decoding base64: {e}")
            return ''

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text."""
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Remove script and style elements
            for tag in soup(['script', 'style', 'head']):
                tag.decompose()

            # Get text
            text = soup.get_text(separator='\n')

            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines()]
            text = '\n'.join(line for line in lines if line)

            return text
        except Exception as e:
            logger.warning(f"Error converting HTML to text: {e}")
            return html

    def fetch_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """Fetch all messages in an email thread.

        Args:
            thread_id: Gmail thread ID

        Returns:
            List of parsed email dictionaries in chronological order
        """
        try:
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full'
            ).execute()

            messages = []
            for msg in thread.get('messages', []):
                headers = {h['name'].lower(): h['value'] for h in msg['payload'].get('headers', [])}

                date_str = headers.get('date', '')
                try:
                    parsed_date = parsedate_to_datetime(date_str)
                except Exception:
                    parsed_date = None

                body = self._extract_body(msg['payload'])

                messages.append({
                    'id': msg['id'],
                    'thread_id': thread_id,
                    'from': headers.get('from', ''),
                    'to': headers.get('to', ''),
                    'subject': headers.get('subject', ''),
                    'date': date_str,
                    'parsed_date': parsed_date,
                    'body': body,
                    'snippet': msg.get('snippet', '')
                })

            # Sort by date (oldest first)
            messages.sort(key=lambda m: m.get('internal_date') or m.get('date', ''))

            return messages

        except Exception as e:
            logger.error(f"Error fetching thread {thread_id}: {e}", exc_info=True)
            return []

    def get_labels(self) -> List[Dict[str, str]]:
        """Get all Gmail labels.

        Returns:
            List of label dictionaries with 'id' and 'name'
        """
        try:
            results = self.service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])
            return [{'id': l['id'], 'name': l['name']} for l in labels]
        except Exception as e:
            logger.error(f"Error fetching labels: {e}")
            return []


class InboxSyncService:
    """Service for syncing inbox emails to Keel for processing."""

    def __init__(self, gmail_service: GmailService, firestore_service, email_agent_service=None):
        """Initialize inbox sync service.

        Args:
            gmail_service: GmailService instance
            firestore_service: FirestoreService instance for tracking
            email_agent_service: Optional EmailAgentService for processing
        """
        self.gmail = gmail_service
        self.firestore = firestore_service
        self.email_agent = email_agent_service

    def sync_inbox(
        self,
        query: str = None,
        max_emails: int = 50,
        days_back: int = 7,
        process_with_agent: bool = False,
        store_for_research: bool = True,
        services: Dict = None
    ) -> Dict[str, Any]:
        """Sync emails from inbox.

        Args:
            query: Gmail search query to filter emails
            max_emails: Maximum emails to process
            days_back: How many days back to look
            process_with_agent: Whether to process emails through EmailAgentService
            store_for_research: Whether to store emails in Firestore for research
            services: Services dict needed if process_with_agent is True

        Returns:
            Sync results summary
        """
        after_date = datetime.now() - timedelta(days=days_back)

        logger.info(f"Starting inbox sync: query={query}, max={max_emails}, days_back={days_back}")

        # Fetch emails
        emails = self.gmail.fetch_emails(
            query=query,
            max_results=max_emails,
            after_date=after_date
        )

        results = {
            'total_fetched': len(emails),
            'already_processed': 0,
            'newly_processed': 0,
            'stored_for_research': 0,
            'agent_processed': 0,
            'errors': 0,
            'details': []
        }

        for email in emails:
            email_id = email['id']

            # Check if already processed
            if self._is_email_processed(email_id):
                results['already_processed'] += 1
                continue

            try:
                # Store for research if enabled
                if store_for_research:
                    self._store_email_for_research(email)
                    results['stored_for_research'] += 1

                # Process with agent if enabled
                if process_with_agent and self.email_agent and services:
                    email_data = {
                        'from': email['from'],
                        'subject': email['subject'],
                        'body': email['body']
                    }
                    agent_result = self.email_agent.process_email(email_data, services)
                    results['agent_processed'] += 1
                    results['details'].append({
                        'email_id': email_id,
                        'subject': email['subject'],
                        'action': agent_result['decision'].get('action'),
                        'result': 'success'
                    })

                # Mark as processed
                self._mark_email_processed(email_id, email)
                results['newly_processed'] += 1

            except Exception as e:
                logger.error(f"Error processing email {email_id}: {e}")
                results['errors'] += 1
                results['details'].append({
                    'email_id': email_id,
                    'subject': email.get('subject', 'Unknown'),
                    'error': str(e)
                })

        logger.info(f"Inbox sync complete: {results['newly_processed']} new, "
                   f"{results['already_processed']} skipped, {results['errors']} errors")

        return results

    def _is_email_processed(self, email_id: str) -> bool:
        """Check if email has already been processed."""
        doc_ref = self.firestore.db.collection(GmailService.PROCESSED_EMAILS_COLLECTION).document(email_id)
        return doc_ref.get().exists

    def _mark_email_processed(self, email_id: str, email: Dict[str, Any]):
        """Mark email as processed in Firestore."""
        from google.cloud import firestore as firestore_module

        doc_ref = self.firestore.db.collection(GmailService.PROCESSED_EMAILS_COLLECTION).document(email_id)
        doc_ref.set({
            'email_id': email_id,
            'thread_id': email.get('thread_id'),
            'from': email.get('from'),
            'subject': email.get('subject'),
            'date': email.get('date'),
            'processed_at': firestore_module.SERVER_TIMESTAMP
        })

    def _store_email_for_research(self, email: Dict[str, Any]):
        """Store email content in Firestore for research/analysis."""
        from google.cloud import firestore as firestore_module

        # Extract domain from sender for grouping
        from_addr = email.get('from', '')
        domain_match = re.search(r'@([\w.-]+)', from_addr)
        domain = domain_match.group(1).lower() if domain_match else 'unknown'

        # Skip common email providers for domain grouping
        skip_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'googlemail.com']
        if domain in skip_domains:
            # Try to extract company domain from email content or use sender name
            domain = 'personal'

        doc_ref = self.firestore.db.collection('email_research').document(email['id'])
        doc_ref.set({
            'email_id': email['id'],
            'thread_id': email.get('thread_id'),
            'from': email.get('from'),
            'to': email.get('to'),
            'cc': email.get('cc'),
            'subject': email.get('subject'),
            'date': email.get('date'),
            'body': email.get('body', '')[:50000],  # Limit size
            'snippet': email.get('snippet'),
            'domain': domain,
            'labels': email.get('labels', []),
            'stored_at': firestore_module.SERVER_TIMESTAMP
        })

    def get_emails_by_domain(self, domain: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get stored emails for a specific domain.

        Args:
            domain: Domain to filter by
            limit: Maximum emails to return

        Returns:
            List of stored email documents
        """
        docs = (self.firestore.db
                .collection('email_research')
                .where('domain', '==', domain.lower())
                .order_by('date', direction='DESCENDING')
                .limit(limit)
                .stream())

        return [doc.to_dict() for doc in docs]

    def search_emails(self, search_term: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search stored emails by subject or snippet.

        Note: This is a simple search. For full-text search, consider using
        Firestore's array-contains or a dedicated search service.

        Args:
            search_term: Term to search for
            limit: Maximum emails to return

        Returns:
            List of matching email documents
        """
        # Firestore doesn't support full-text search natively
        # This fetches recent emails and filters client-side
        docs = (self.firestore.db
                .collection('email_research')
                .order_by('date', direction='DESCENDING')
                .limit(limit * 3)  # Fetch more to account for filtering
                .stream())

        results = []
        search_lower = search_term.lower()

        for doc in docs:
            data = doc.to_dict()
            subject = (data.get('subject') or '').lower()
            snippet = (data.get('snippet') or '').lower()
            from_addr = (data.get('from') or '').lower()

            if search_lower in subject or search_lower in snippet or search_lower in from_addr:
                results.append(data)
                if len(results) >= limit:
                    break

        return results
