"""Pytest fixtures and mock data for testing."""
import pytest
from unittest.mock import Mock, MagicMock, patch
import os

# Set test environment variables before importing services
os.environ['GCP_PROJECT_ID'] = 'test-project'
os.environ['SPREADSHEET_ID'] = 'test-spreadsheet-id'
os.environ['DRIVE_PARENT_FOLDER_ID'] = 'test-folder-id'
os.environ['SERPER_API_KEY'] = 'test-serper-key'
os.environ['VERTEX_AI_REGION'] = 'us-central1'


# ============ MOCK DATA FIXTURES ============

@pytest.fixture
def mock_sheet_data():
    """Mock spreadsheet data with companies."""
    return {
        'values': [
            ['Company', 'Domain', 'Status', 'Source'],  # Header row
            ['Forithmus', 'forithmus.com', '', ''],
            ['Stripe', 'stripe.com', 'Memo Created', ''],
            ['Cofia', '', '', 'W26'],
            ['Vela', '', '', 'W26'],
            ['Embassi', '', 'New', 'W26'],
        ]
    }


@pytest.fixture
def mock_company_forithmus():
    """Mock company data for Forithmus."""
    return {
        'company': 'Forithmus',
        'domain': 'forithmus.com',
        'row_number': 2,
        'status': '',
        'source': ''
    }


@pytest.fixture
def mock_company_no_domain():
    """Mock company data for company without domain."""
    return {
        'company': 'Cofia',
        'domain': '',
        'row_number': 4,
        'status': '',
        'source': 'W26'
    }


@pytest.fixture
def mock_yc_company_data():
    """Mock YC Bookface data."""
    return {
        'name': 'Cofia',
        'batch': 'W26',
        'posts': [
            {
                'title': 'Introducing Cofia',
                'body': 'We are building the future of coffee logistics...',
                'author': 'John Founder',
                'author_email': 'john@cofia.com'
            }
        ],
        'founders': [
            {
                'name': 'John Founder',
                'email': 'john@cofia.com',
                'hnid': 'johnfounder'
            }
        ]
    }


@pytest.fixture
def mock_relationship_data():
    """Mock relationship data from forwarded emails."""
    return {
        'domain': 'forithmus.com',
        'company_name': 'Forithmus',
        'introducer': {
            'name': 'Sarah Connector',
            'email': 'sarah@vc.com',
            'context': 'Met at TechCrunch Disrupt'
        },
        'contacts': [
            {'name': 'Alex CEO', 'email': 'alex@forithmus.com', 'role': 'CEO'},
            {'name': 'Bob CTO', 'email': 'bob@forithmus.com', 'role': 'CTO'}
        ],
        'summary': 'Strong AI healthcare startup with experienced team.',
        'timeline': [
            {'date': '2025-01-15', 'event': 'Initial intro email from Sarah'},
            {'date': '2025-01-18', 'event': 'First call with Alex'}
        ],
        'key_topics': ['AI', 'Healthcare', 'Medical Imaging'],
        'next_steps': 'Schedule deep dive call',
        'message_count': 5,
        'raw_messages': [
            {
                'from': 'sarah@vc.com',
                'date': '2025-01-15',
                'subject': 'Intro: Forithmus',
                'body': 'Hey, wanted to connect you with Alex from Forithmus...'
            }
        ]
    }


@pytest.fixture
def mock_search_results():
    """Mock Serper search results (uses 'link' field like real Serper API)."""
    return [
        {
            'title': 'Forithmus - AI Healthcare Platform',
            'link': 'https://forithmus.com/',
            'snippet': 'AI-powered platform delivering capabilities to healthcare providers.'
        },
        {
            'title': 'Forithmus | LinkedIn',
            'link': 'https://linkedin.com/company/forithmus',
            'snippet': 'Forithmus is transforming healthcare with AI...'
        },
        {
            'title': 'Forithmus raises $5M seed round - TechCrunch',
            'link': 'https://techcrunch.com/forithmus-funding',
            'snippet': 'Healthcare AI startup Forithmus announced a $5M seed round...'
        }
    ]


@pytest.fixture
def mock_domain_pages():
    """Mock crawled domain pages."""
    return {
        'https://forithmus.com': {
            'title': 'Forithmus - AI Healthcare',
            'meta_description': 'AI-powered healthcare solutions',
            'content': 'Forithmus delivers AI capabilities to healthcare providers worldwide...'
        },
        'https://forithmus.com/about': {
            'title': 'About Forithmus',
            'meta_description': 'About our company',
            'content': 'Founded in 2024, Forithmus is on a mission to transform healthcare...'
        },
        'https://forithmus.com/team': {
            'title': 'Our Team',
            'meta_description': 'Meet the Forithmus team',
            'content': 'Alex Smith, CEO - Former Google AI researcher...'
        }
    }


@pytest.fixture
def mock_research_data(mock_domain_pages):
    """Complete mock research data (with processed search results containing 'url')."""
    return {
        'company': 'Forithmus',
        'domain': 'forithmus.com',
        'source': '',
        'domain_pages': mock_domain_pages,
        'search_results': [
            {
                'title': 'Forithmus - AI Healthcare Platform',
                'url': 'https://forithmus.com/',
                'snippet': 'AI-powered platform delivering capabilities to healthcare providers.'
            },
            {
                'title': 'Forithmus | LinkedIn',
                'url': 'https://linkedin.com/company/forithmus',
                'snippet': 'Forithmus is transforming healthcare with AI...'
            },
            {
                'title': 'Forithmus raises $5M seed round - TechCrunch',
                'url': 'https://techcrunch.com/forithmus-funding',
                'snippet': 'Healthcare AI startup Forithmus announced a $5M seed round...'
            }
        ],
        'external_content': {
            'https://techcrunch.com/forithmus-funding': {
                'title': 'Forithmus raises $5M',
                'content': 'Healthcare AI startup Forithmus today announced...'
            }
        },
        'crunchbase': {},
        'yc_data': {},
        'errors': []
    }


@pytest.fixture
def mock_generated_memo():
    """Mock generated memo content."""
    return """# Forithmus — Research Brief

## Company Overview
- **What they do:** AI-powered platform delivering capabilities to healthcare providers
- **Website:** forithmus.com
- **Founded:** 2024
- **Headquarters:** San Francisco, CA

## Founders & Team
- **Alex Smith** - CEO
  - Background: Former Google AI researcher
  - LinkedIn: https://linkedin.com/in/alexsmith

## Product & Service
- AI-powered healthcare solutions
- Medical imaging analysis
- Clinical decision support

## Traction & Metrics
- $5M seed funding raised
- 10+ healthcare provider partnerships

## Online Presence & Discussion
- Active on LinkedIn and Twitter
- Featured in TechCrunch
"""


# ============ SERVICE MOCKS ============

@pytest.fixture
def mock_sheets_service(mock_sheet_data):
    """Mock SheetsService."""
    mock = Mock()
    mock.spreadsheet_id = 'test-spreadsheet-id'

    # Mock the underlying Google API
    mock.service = Mock()
    mock.service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = mock_sheet_data

    # Mock methods
    mock.get_rows_to_process.return_value = [
        {'row_number': 2, 'company': 'Forithmus', 'domain': 'forithmus.com', 'status': '', 'source': ''}
    ]
    mock.get_all_companies.return_value = [
        {'row_number': 2, 'company': 'Forithmus', 'domain': 'forithmus.com', 'status': '', 'source': ''},
        {'row_number': 3, 'company': 'Stripe', 'domain': 'stripe.com', 'status': 'Memo Created', 'source': ''},
        {'row_number': 4, 'company': 'Cofia', 'domain': '', 'status': '', 'source': 'W26'},
    ]
    mock.add_company.return_value = {'success': True}
    mock.update_status.return_value = None
    mock.company_exists.return_value = False

    return mock


@pytest.fixture
def mock_firestore_service(mock_yc_company_data, mock_relationship_data):
    """Mock FirestoreService."""
    mock = Mock()
    mock.db = Mock()
    mock.collection = 'processed_domains'

    mock.is_processed.return_value = False
    mock.mark_processed.return_value = None
    mock.clear_processed.return_value = True
    mock.get_processed.return_value = None
    mock.get_yc_company_data.return_value = mock_yc_company_data
    mock.get_relationship_data.return_value = mock_relationship_data

    return mock


@pytest.fixture
def mock_drive_service():
    """Mock DriveService."""
    mock = Mock()
    mock.parent_folder_id = 'test-folder-id'

    mock.create_folder.return_value = 'folder-123'
    mock.find_existing_folder.return_value = None
    mock.create_document.return_value = 'doc-456'
    mock.find_document_in_folder.return_value = None

    return mock


@pytest.fixture
def mock_docs_service():
    """Mock DocsService."""
    mock = Mock()
    mock.insert_text.return_value = None
    return mock


@pytest.fixture
def mock_gemini_service(mock_generated_memo):
    """Mock GeminiService."""
    mock = Mock()
    mock.generate_memo.return_value = mock_generated_memo
    return mock


@pytest.fixture
def mock_gmail_service():
    """Mock GmailService."""
    mock = Mock()
    mock.user_email = 'nick@friale.com'
    mock.fetch_emails.return_value = []
    mock.fetch_thread.return_value = []
    return mock


@pytest.fixture
def mock_services(mock_sheets_service, mock_firestore_service, mock_drive_service,
                  mock_docs_service, mock_gemini_service, mock_gmail_service):
    """Combined mock services dictionary."""
    return {
        'sheets': mock_sheets_service,
        'firestore': mock_firestore_service,
        'drive': mock_drive_service,
        'docs': mock_docs_service,
        'gemini': mock_gemini_service,
        'gmail': mock_gmail_service
    }


# ============ PATCH HELPERS ============

@pytest.fixture
def patch_config():
    """Patch config module."""
    with patch('services.research.config') as mock_config:
        mock_config.project_id = 'test-project'
        mock_config.spreadsheet_id = 'test-spreadsheet-id'
        mock_config.drive_parent_folder_id = 'test-folder-id'
        mock_config.serper_api_key = 'test-serper-key'
        mock_config.vertex_ai_region = 'us-central1'
        mock_config.linkedin_cookie = ''
        mock_config.bookface_cookie = ''
        yield mock_config


@pytest.fixture
def patch_requests(mock_search_results, mock_domain_pages):
    """Patch requests for web scraping tests."""
    with patch('services.research.requests') as mock_requests:
        # Mock session
        mock_session = Mock()
        mock_requests.Session.return_value = mock_session

        # Mock responses
        def mock_get(url, *args, **kwargs):
            response = Mock()
            response.status_code = 200
            response.headers = {'content-type': 'text/html'}

            if 'serper.dev' in url:
                response.json.return_value = {'organic': mock_search_results}
            elif 'forithmus.com' in url:
                page_data = mock_domain_pages.get(url, {})
                response.text = f"<html><head><title>{page_data.get('title', '')}</title></head><body>{page_data.get('content', '')}</body></html>"
            else:
                response.text = '<html><body>Test content</body></html>'

            return response

        mock_session.get = mock_get
        mock_requests.post = Mock(return_value=Mock(
            status_code=200,
            json=Mock(return_value={'organic': mock_search_results})
        ))
        mock_requests.utils.quote = lambda x: x.replace(' ', '+')

        yield mock_requests
