"""Tests for Gmail service."""
import base64
import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timedelta

from services import GmailService, InboxSyncService


class TestGmailService:
    """Tests for GmailService class."""

    @patch('services.google.gmail.build')
    @patch('services.google.gmail.default')
    def test_init_with_default_credentials(self, mock_default, mock_build):
        """Test initialization with default credentials."""
        mock_creds = MagicMock()
        mock_default.return_value = (mock_creds, 'project-id')

        service = GmailService()

        mock_default.assert_called_once()
        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)
        assert service.user_email is None

    @patch('services.google.gmail.build')
    def test_init_with_provided_credentials(self, mock_build):
        """Test initialization with provided credentials."""
        mock_creds = MagicMock(spec=[])  # No with_subject attribute

        service = GmailService(credentials=mock_creds, user_email='test@example.com')

        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)
        assert service.user_email == 'test@example.com'

    @patch('services.google.gmail.build')
    def test_init_with_delegation(self, mock_build):
        """Test initialization with domain-wide delegation."""
        mock_creds = MagicMock()
        mock_delegated_creds = MagicMock()
        mock_creds.with_subject.return_value = mock_delegated_creds

        service = GmailService(credentials=mock_creds, user_email='user@domain.com')

        mock_creds.with_subject.assert_called_once_with('user@domain.com')
        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_delegated_creds)

    @patch('services.google.gmail.build')
    def test_fetch_emails_basic(self, mock_build):
        """Test basic email fetching."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock list response
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg1'}, {'id': 'msg2'}]
        }

        # Mock get response for each message
        mock_service.users().messages().get().execute.side_effect = [
            {
                'id': 'msg1',
                'threadId': 'thread1',
                'snippet': 'Test snippet 1',
                'labelIds': ['INBOX'],
                'internalDate': '1234567890000',
                'payload': {
                    'headers': [
                        {'name': 'From', 'value': 'sender@example.com'},
                        {'name': 'To', 'value': 'recipient@example.com'},
                        {'name': 'Subject', 'value': 'Test Subject 1'},
                        {'name': 'Date', 'value': 'Mon, 1 Jan 2024 12:00:00 +0000'}
                    ],
                    'body': {'data': base64.urlsafe_b64encode(b'Test body 1').decode()}
                }
            },
            {
                'id': 'msg2',
                'threadId': 'thread2',
                'snippet': 'Test snippet 2',
                'labelIds': ['INBOX'],
                'internalDate': '1234567891000',
                'payload': {
                    'headers': [
                        {'name': 'From', 'value': 'another@example.com'},
                        {'name': 'Subject', 'value': 'Test Subject 2'},
                        {'name': 'Date', 'value': 'Tue, 2 Jan 2024 12:00:00 +0000'}
                    ],
                    'body': {'data': base64.urlsafe_b64encode(b'Test body 2').decode()}
                }
            }
        ]

        gmail = GmailService(credentials=MagicMock())
        emails = gmail.fetch_emails(max_results=10)

        assert len(emails) == 2
        assert emails[0]['id'] == 'msg1'
        assert emails[0]['from'] == 'sender@example.com'
        assert emails[0]['subject'] == 'Test Subject 1'

    @patch('services.google.gmail.build')
    def test_fetch_emails_with_query(self, mock_build):
        """Test email fetching with query parameters."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.users().messages().list().execute.return_value = {'messages': []}

        gmail = GmailService(credentials=MagicMock())
        after_date = datetime(2024, 1, 1)
        before_date = datetime(2024, 1, 31)

        gmail.fetch_emails(
            query='from:test@example.com',
            max_results=25,
            after_date=after_date,
            before_date=before_date,
            label_ids=['INBOX', 'UNREAD']
        )

        # Verify list was called with correct params
        mock_service.users().messages().list.assert_called()

    @patch('services.google.gmail.build')
    def test_fetch_emails_no_messages(self, mock_build):
        """Test fetching when no messages found."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.users().messages().list().execute.return_value = {}

        gmail = GmailService(credentials=MagicMock())
        emails = gmail.fetch_emails()

        assert emails == []

    @patch('services.google.gmail.build')
    def test_fetch_emails_handles_error_on_single_message(self, mock_build):
        """Test that errors on individual messages don't stop processing."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg1'}, {'id': 'msg2'}]
        }

        # First message raises error, second succeeds
        mock_service.users().messages().get().execute.side_effect = [
            Exception('API error'),
            {
                'id': 'msg2',
                'threadId': 'thread2',
                'snippet': 'Test',
                'labelIds': [],
                'payload': {
                    'headers': [
                        {'name': 'From', 'value': 'test@example.com'},
                        {'name': 'Subject', 'value': 'Test'},
                        {'name': 'Date', 'value': 'Mon, 1 Jan 2024 12:00:00 +0000'}
                    ],
                    'body': {}
                }
            }
        ]

        gmail = GmailService(credentials=MagicMock())
        emails = gmail.fetch_emails()

        assert len(emails) == 1
        assert emails[0]['id'] == 'msg2'

    @patch('services.google.gmail.build')
    def test_extract_body_plain_text(self, mock_build):
        """Test extracting plain text body."""
        gmail = GmailService(credentials=MagicMock())

        payload = {
            'mimeType': 'text/plain',
            'body': {'data': base64.urlsafe_b64encode(b'Plain text content').decode()}
        }

        body = gmail._extract_body(payload)
        assert body == 'Plain text content'

    @patch('services.google.gmail.build')
    def test_extract_body_html(self, mock_build):
        """Test extracting and converting HTML body."""
        gmail = GmailService(credentials=MagicMock())

        html_content = '<html><body><p>HTML content</p></body></html>'
        payload = {
            'mimeType': 'text/html',
            'body': {'data': base64.urlsafe_b64encode(html_content.encode()).decode()}
        }

        body = gmail._extract_body(payload)
        assert 'HTML content' in body

    @patch('services.google.gmail.build')
    def test_extract_body_multipart(self, mock_build):
        """Test extracting body from multipart message."""
        gmail = GmailService(credentials=MagicMock())

        payload = {
            'mimeType': 'multipart/alternative',
            'parts': [
                {
                    'mimeType': 'text/plain',
                    'body': {'data': base64.urlsafe_b64encode(b'Plain version').decode()}
                },
                {
                    'mimeType': 'text/html',
                    'body': {'data': base64.urlsafe_b64encode(b'<p>HTML version</p>').decode()}
                }
            ]
        }

        body = gmail._extract_body(payload)
        # Should prefer plain text
        assert body == 'Plain version'

    @patch('services.google.gmail.build')
    def test_extract_body_nested_multipart(self, mock_build):
        """Test extracting body from nested multipart message."""
        gmail = GmailService(credentials=MagicMock())

        payload = {
            'mimeType': 'multipart/mixed',
            'parts': [
                {
                    'mimeType': 'multipart/alternative',
                    'parts': [
                        {
                            'mimeType': 'text/plain',
                            'body': {'data': base64.urlsafe_b64encode(b'Nested plain text').decode()}
                        }
                    ]
                }
            ]
        }

        body = gmail._extract_body(payload)
        assert 'Nested plain text' in body

    @patch('services.google.gmail.build')
    def test_decode_base64_handles_errors(self, mock_build):
        """Test base64 decoding handles invalid data."""
        gmail = GmailService(credentials=MagicMock())

        result = gmail._decode_base64('invalid!!base64')
        assert result == ''

    @patch('services.google.gmail.build')
    def test_html_to_text_removes_scripts_and_styles(self, mock_build):
        """Test HTML to text conversion removes scripts and styles."""
        gmail = GmailService(credentials=MagicMock())

        html = '''
        <html>
        <head><style>body { color: red; }</style></head>
        <body>
        <script>alert('test');</script>
        <p>Visible content</p>
        </body>
        </html>
        '''

        text = gmail._html_to_text(html)
        assert 'Visible content' in text
        assert 'alert' not in text
        assert 'color: red' not in text

    @patch('services.google.gmail.build')
    def test_fetch_thread(self, mock_build):
        """Test fetching email thread."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.users().threads().get().execute.return_value = {
            'messages': [
                {
                    'id': 'msg1',
                    'payload': {
                        'headers': [
                            {'name': 'From', 'value': 'user1@example.com'},
                            {'name': 'To', 'value': 'user2@example.com'},
                            {'name': 'Subject', 'value': 'Thread Subject'},
                            {'name': 'Date', 'value': 'Mon, 1 Jan 2024 12:00:00 +0000'}
                        ],
                        'body': {'data': base64.urlsafe_b64encode(b'First message').decode()}
                    },
                    'snippet': 'First message'
                },
                {
                    'id': 'msg2',
                    'payload': {
                        'headers': [
                            {'name': 'From', 'value': 'user2@example.com'},
                            {'name': 'To', 'value': 'user1@example.com'},
                            {'name': 'Subject', 'value': 'Re: Thread Subject'},
                            {'name': 'Date', 'value': 'Mon, 1 Jan 2024 13:00:00 +0000'}
                        ],
                        'body': {'data': base64.urlsafe_b64encode(b'Reply message').decode()}
                    },
                    'snippet': 'Reply message'
                }
            ]
        }

        gmail = GmailService(credentials=MagicMock())
        messages = gmail.fetch_thread('thread123')

        assert len(messages) == 2
        assert messages[0]['from'] == 'user1@example.com'
        assert messages[1]['from'] == 'user2@example.com'

    @patch('services.google.gmail.build')
    def test_fetch_thread_error(self, mock_build):
        """Test fetching thread handles errors."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.users().threads().get().execute.side_effect = Exception('API error')

        gmail = GmailService(credentials=MagicMock())
        messages = gmail.fetch_thread('thread123')

        assert messages == []

    @patch('services.google.gmail.build')
    def test_get_labels(self, mock_build):
        """Test fetching Gmail labels."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.users().labels().list().execute.return_value = {
            'labels': [
                {'id': 'INBOX', 'name': 'INBOX'},
                {'id': 'SENT', 'name': 'SENT'},
                {'id': 'Label_1', 'name': 'Custom Label'}
            ]
        }

        gmail = GmailService(credentials=MagicMock())
        labels = gmail.get_labels()

        assert len(labels) == 3
        assert {'id': 'INBOX', 'name': 'INBOX'} in labels

    @patch('services.google.gmail.build')
    def test_get_labels_error(self, mock_build):
        """Test fetching labels handles errors."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.users().labels().list().execute.side_effect = Exception('API error')

        gmail = GmailService(credentials=MagicMock())
        labels = gmail.get_labels()

        assert labels == []


class TestInboxSyncService:
    """Tests for InboxSyncService class."""

    def test_init(self):
        """Test InboxSyncService initialization."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()
        mock_email_agent = MagicMock()

        service = InboxSyncService(mock_gmail, mock_firestore, mock_email_agent)

        assert service.gmail == mock_gmail
        assert service.firestore == mock_firestore
        assert service.email_agent == mock_email_agent

    def test_sync_inbox_basic(self):
        """Test basic inbox sync."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()

        mock_gmail.fetch_emails.return_value = [
            {
                'id': 'email1',
                'thread_id': 'thread1',
                'from': 'sender@company.com',
                'to': 'recipient@example.com',
                'subject': 'Test Email',
                'date': 'Mon, 1 Jan 2024 12:00:00 +0000',
                'body': 'Test body',
                'snippet': 'Test snippet',
                'labels': ['INBOX']
            }
        ]

        # Mock Firestore - email not processed
        mock_doc_ref = MagicMock()
        mock_doc_ref.get().exists = False
        mock_firestore.db.collection().document.return_value = mock_doc_ref

        service = InboxSyncService(mock_gmail, mock_firestore)
        result = service.sync_inbox(max_emails=10, days_back=7)

        assert result['total_fetched'] == 1
        assert result['newly_processed'] == 1
        assert result['already_processed'] == 0

    def test_sync_inbox_skips_already_processed(self):
        """Test that sync skips already processed emails."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()

        mock_gmail.fetch_emails.return_value = [
            {'id': 'email1', 'from': 'test@example.com', 'subject': 'Test'}
        ]

        # Mock Firestore - email already processed
        mock_doc_ref = MagicMock()
        mock_doc_ref.get().exists = True
        mock_firestore.db.collection().document.return_value = mock_doc_ref

        service = InboxSyncService(mock_gmail, mock_firestore)
        result = service.sync_inbox()

        assert result['already_processed'] == 1
        assert result['newly_processed'] == 0

    def test_sync_inbox_with_agent_processing(self):
        """Test sync with email agent processing."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()
        mock_email_agent = MagicMock()

        mock_gmail.fetch_emails.return_value = [
            {
                'id': 'email1',
                'thread_id': 'thread1',
                'from': 'sender@company.com',
                'to': 'recipient@example.com',
                'subject': 'Test Email',
                'body': 'Test body'
            }
        ]

        # Email not processed
        mock_doc_ref = MagicMock()
        mock_doc_ref.get().exists = False
        mock_firestore.db.collection().document.return_value = mock_doc_ref

        mock_email_agent.process_email.return_value = {
            'decision': {'action': 'none'},
            'result': {}
        }

        services = {'sheets': MagicMock(), 'firestore': mock_firestore}

        service = InboxSyncService(mock_gmail, mock_firestore, mock_email_agent)
        result = service.sync_inbox(process_with_agent=True, services=services)

        assert result['agent_processed'] == 1

    def test_sync_inbox_handles_processing_error(self):
        """Test sync handles errors on individual emails."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()

        mock_gmail.fetch_emails.return_value = [
            {'id': 'email1', 'from': 'test@example.com', 'subject': 'Test'}
        ]

        # Email not processed, but store fails
        mock_doc_ref = MagicMock()
        mock_doc_ref.get().exists = False
        mock_doc_ref.set.side_effect = Exception('Firestore error')
        mock_firestore.db.collection().document.return_value = mock_doc_ref

        service = InboxSyncService(mock_gmail, mock_firestore)
        result = service.sync_inbox()

        assert result['errors'] == 1
        assert len(result['details']) == 1
        assert 'error' in result['details'][0]

    @patch('google.cloud.firestore.SERVER_TIMESTAMP', 'MOCK_TIMESTAMP')
    def test_store_email_for_research(self):
        """Test storing email for research."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()
        mock_doc_ref = MagicMock()
        mock_firestore.db.collection().document.return_value = mock_doc_ref

        service = InboxSyncService(mock_gmail, mock_firestore)

        email = {
            'id': 'email123',
            'thread_id': 'thread123',
            'from': 'sender@company.com',
            'to': 'recipient@example.com',
            'cc': 'cc@example.com',
            'subject': 'Test Subject',
            'date': 'Mon, 1 Jan 2024 12:00:00 +0000',
            'body': 'Test body content',
            'snippet': 'Test snippet',
            'labels': ['INBOX']
        }

        service._store_email_for_research(email)

        mock_doc_ref.set.assert_called_once()
        call_args = mock_doc_ref.set.call_args[0][0]
        assert call_args['email_id'] == 'email123'
        assert call_args['domain'] == 'company.com'

    @patch('google.cloud.firestore.SERVER_TIMESTAMP', 'MOCK_TIMESTAMP')
    def test_store_email_extracts_domain_from_sender(self):
        """Test domain extraction from sender email."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()
        mock_doc_ref = MagicMock()
        mock_firestore.db.collection().document.return_value = mock_doc_ref

        service = InboxSyncService(mock_gmail, mock_firestore)

        # Test with full name format
        email = {
            'id': 'email1',
            'from': 'John Doe <john@startup.io>',
            'subject': 'Test'
        }

        service._store_email_for_research(email)

        call_args = mock_doc_ref.set.call_args[0][0]
        assert call_args['domain'] == 'startup.io'

    @patch('google.cloud.firestore.SERVER_TIMESTAMP', 'MOCK_TIMESTAMP')
    def test_store_email_marks_personal_domains(self):
        """Test that common email providers are marked as personal."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()
        mock_doc_ref = MagicMock()
        mock_firestore.db.collection().document.return_value = mock_doc_ref

        service = InboxSyncService(mock_gmail, mock_firestore)

        for provider in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']:
            email = {
                'id': f'email_{provider}',
                'from': f'user@{provider}',
                'subject': 'Test'
            }

            service._store_email_for_research(email)

            call_args = mock_doc_ref.set.call_args[0][0]
            assert call_args['domain'] == 'personal'

    @patch('google.cloud.firestore.SERVER_TIMESTAMP', 'MOCK_TIMESTAMP')
    def test_mark_email_processed(self):
        """Test marking email as processed."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()
        mock_doc_ref = MagicMock()
        mock_firestore.db.collection().document.return_value = mock_doc_ref

        service = InboxSyncService(mock_gmail, mock_firestore)

        email = {
            'id': 'email123',
            'thread_id': 'thread123',
            'from': 'sender@example.com',
            'subject': 'Test Subject',
            'date': 'Mon, 1 Jan 2024 12:00:00 +0000'
        }

        service._mark_email_processed('email123', email)

        mock_firestore.db.collection.assert_called_with('processed_emails')
        mock_doc_ref.set.assert_called_once()

    def test_get_emails_by_domain(self):
        """Test getting emails by domain."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()

        mock_doc1 = MagicMock()
        mock_doc1.to_dict.return_value = {
            'email_id': 'email1',
            'domain': 'company.com',
            'subject': 'Test 1'
        }
        mock_doc2 = MagicMock()
        mock_doc2.to_dict.return_value = {
            'email_id': 'email2',
            'domain': 'company.com',
            'subject': 'Test 2'
        }

        mock_firestore.db.collection().where().order_by().limit().stream.return_value = [
            mock_doc1, mock_doc2
        ]

        service = InboxSyncService(mock_gmail, mock_firestore)
        results = service.get_emails_by_domain('company.com', limit=10)

        assert len(results) == 2
        assert results[0]['domain'] == 'company.com'

    def test_search_emails(self):
        """Test searching emails."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()

        mock_doc1 = MagicMock()
        mock_doc1.to_dict.return_value = {
            'email_id': 'email1',
            'subject': 'Meeting about Project Alpha',
            'snippet': 'Let us discuss...',
            'from': 'person@company.com'
        }
        mock_doc2 = MagicMock()
        mock_doc2.to_dict.return_value = {
            'email_id': 'email2',
            'subject': 'Unrelated Email',
            'snippet': 'Something else',
            'from': 'other@example.com'
        }

        mock_firestore.db.collection().order_by().limit().stream.return_value = [
            mock_doc1, mock_doc2
        ]

        service = InboxSyncService(mock_gmail, mock_firestore)
        results = service.search_emails('project alpha', limit=10)

        assert len(results) == 1
        assert 'Project Alpha' in results[0]['subject']

    def test_search_emails_matches_from_address(self):
        """Test that search matches sender address."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()

        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            'email_id': 'email1',
            'subject': 'Hello',
            'snippet': 'Hi there',
            'from': 'john@acme.com'
        }

        mock_firestore.db.collection().order_by().limit().stream.return_value = [mock_doc]

        service = InboxSyncService(mock_gmail, mock_firestore)
        results = service.search_emails('acme', limit=10)

        assert len(results) == 1

    def test_search_emails_respects_limit(self):
        """Test that search respects limit."""
        mock_gmail = MagicMock()
        mock_firestore = MagicMock()

        # Create 5 matching docs
        mock_docs = []
        for i in range(5):
            mock_doc = MagicMock()
            mock_doc.to_dict.return_value = {
                'email_id': f'email{i}',
                'subject': 'Match keyword',
                'snippet': 'Match content',
                'from': 'test@example.com'
            }
            mock_docs.append(mock_doc)

        mock_firestore.db.collection().order_by().limit().stream.return_value = mock_docs

        service = InboxSyncService(mock_gmail, mock_firestore)
        results = service.search_emails('match', limit=3)

        assert len(results) == 3
