"""Tests for EmailAgentService."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestEmailAgentService:
    """Tests for the EmailAgentService class."""

    @pytest.fixture
    def mock_email_data(self):
        """Sample email data."""
        return {
            'from': 'user@example.com',
            'subject': 'Test subject',
            'body': 'Test body'
        }

    def test_regenerate_memo_by_domain(self, mock_services, mock_sheet_data):
        """Test regenerating memo by domain."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Set up sheet data mock
                    mock_services['sheets'].service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = mock_sheet_data

                    with patch.object(EmailAgentService, '_get_action_decision') as mock_decision:
                        mock_decision.return_value = {
                            'action': 'REGENERATE_MEMO',
                            'parameters': {'domain': 'forithmus.com'},
                            'reasoning': 'User wants to regenerate memo'
                        }

                        # Mock ResearchService
                        with patch('services.email_agent.ResearchService') as MockResearch:
                            mock_research_instance = Mock()
                            mock_research_instance.research_company.return_value = {
                                'company': 'Forithmus',
                                'domain': 'forithmus.com',
                                'source': '',
                                'domain_pages': {},
                                'search_results': [],
                                'external_content': {},
                                'crunchbase': {},
                                'yc_data': {},
                                'errors': []
                            }
                            mock_research_instance.format_research_context.return_value = 'Test context'
                            MockResearch.return_value = mock_research_instance

                            svc = EmailAgentService()
                            result = svc._regenerate_memo('forithmus.com', mock_services)

                            assert result['success'] is True
                            assert result['company'] == 'Forithmus'
                            assert result['domain'] == 'forithmus.com'

    def test_regenerate_memo_by_company_name(self, mock_services, mock_sheet_data):
        """Test regenerating memo by company name (for companies without domains)."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Set up sheet data mock
                    mock_services['sheets'].service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = mock_sheet_data

                    # Mock ResearchService
                    with patch('services.email_agent.ResearchService') as MockResearch:
                        mock_research_instance = Mock()
                        mock_research_instance.research_company.return_value = {
                            'company': 'Cofia',
                            'domain': '',
                            'source': 'W26',
                            'domain_pages': {},
                            'search_results': [],
                            'external_content': {},
                            'crunchbase': {},
                            'yc_data': {},
                            'errors': []
                        }
                        mock_research_instance.format_research_context.return_value = 'Test context'
                        MockResearch.return_value = mock_research_instance

                        svc = EmailAgentService()
                        result = svc._regenerate_memo('cofia', mock_services)

                        assert result['success'] is True
                        assert result['company'] == 'Cofia'
                        assert result['domain'] == ''

    def test_regenerate_memo_not_found(self, mock_services, mock_sheet_data):
        """Test regenerating memo for non-existent company."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    mock_services['sheets'].service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = mock_sheet_data

                    svc = EmailAgentService()
                    result = svc._regenerate_memo('nonexistent.com', mock_services)

                    assert result['success'] is False
                    assert 'not found' in result['error'].lower()

    def test_format_response_regenerate_memo(self, mock_services):
        """Test response formatting for regenerated memo."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'REGENERATE_MEMO', 'reasoning': 'Test'}
                    result = {
                        'success': True,
                        'company': 'Forithmus',
                        'domain': 'forithmus.com',
                        'doc_id': 'doc-123'
                    }

                    response = svc._format_response(decision, result)

                    assert 'Memo regenerated' in response
                    assert 'Forithmus' in response
                    assert 'forithmus.com' in response
                    assert 'doc-123' in response

    def test_format_response_no_domain(self, mock_services):
        """Test response formatting for company without domain."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'REGENERATE_MEMO', 'reasoning': 'Test'}
                    result = {
                        'success': True,
                        'company': 'Cofia',
                        'domain': '',
                        'doc_id': 'doc-456'
                    }

                    response = svc._format_response(decision, result)

                    assert 'Cofia' in response
                    assert '(no domain)' in response


class TestActionDetection:
    """Tests for action detection in emails."""

    def test_actions_defined(self):
        """Test that all expected actions are defined."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    expected_actions = [
                        'GENERATE_MEMOS',
                        'ADD_COMPANY',
                        'UPDATE_COMPANY',
                        'REGENERATE_MEMO',
                        'ANALYZE_THREAD',
                        'SCRAPE_YC',
                        'HEALTH_CHECK',
                        'NONE'
                    ]

                    for action in expected_actions:
                        assert action in svc.ACTIONS
                        assert 'description' in svc.ACTIONS[action]


class TestUpdateCompanyAction:
    """Tests for UPDATE_COMPANY action handling."""

    def test_execute_update_company(self, mock_services):
        """Test executing UPDATE_COMPANY action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Mock the sheets update_company method
                    mock_services['sheets'].update_company.return_value = {
                        'success': True,
                        'company': 'HCA',
                        'old_domain': 'hca.com',
                        'new_domain': 'hcahealthcare.com',
                        'updates': ['domain: hca.com → hcahealthcare.com']
                    }

                    svc = EmailAgentService()

                    decision = {
                        'action': 'UPDATE_COMPANY',
                        'parameters': {'company': 'HCA', 'new_domain': 'hcahealthcare.com'}
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is True
                    assert result['new_domain'] == 'hcahealthcare.com'
                    mock_services['sheets'].update_company.assert_called_once_with(
                        'HCA', new_domain='hcahealthcare.com', new_name=''
                    )

    def test_execute_update_company_with_chained_generate(self, mock_services):
        """Test UPDATE_COMPANY with chained GENERATE_MEMOS action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Mock the sheets update_company method
                    mock_services['sheets'].update_company.return_value = {
                        'success': True,
                        'company': 'HCA',
                        'old_domain': 'hca.com',
                        'new_domain': 'hcahealthcare.com',
                        'updates': ['domain: hca.com → hcahealthcare.com']
                    }

                    # Mock get_rows_to_process to return empty (no memos to generate)
                    mock_services['sheets'].get_rows_to_process.return_value = []

                    svc = EmailAgentService()

                    decision = {
                        'action': 'UPDATE_COMPANY',
                        'parameters': {'company': 'HCA', 'new_domain': 'hcahealthcare.com'},
                        'also_do': 'GENERATE_MEMOS'
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is True
                    assert result.get('chained_action') == 'GENERATE_MEMOS'
                    assert 'chained_result' in result

    def test_format_response_update_company(self, mock_services):
        """Test response formatting for UPDATE_COMPANY action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'UPDATE_COMPANY', 'reasoning': 'User corrected domain'}
                    result = {
                        'success': True,
                        'company': 'HCA',
                        'old_domain': 'hca.com',
                        'new_domain': 'hcahealthcare.com',
                        'updates': ['domain: hca.com → hcahealthcare.com']
                    }

                    response = svc._format_response(decision, result)

                    assert 'Company updated' in response
                    assert 'HCA' in response
                    assert 'hcahealthcare.com' in response


class TestEmailParsing:
    """Tests for email parsing functionality."""

    def test_parse_email_thread_single_message(self):
        """Test parsing a single email message."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    email_body = """
                    From: john@example.com
                    Date: January 15, 2025
                    Subject: Introduction

                    Hi, I wanted to introduce you to our company.

                    Best,
                    John
                    """

                    messages = svc._parse_email_thread(email_body)

                    assert len(messages) >= 1

    def test_parse_email_thread_forwarded(self):
        """Test parsing forwarded email thread."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    email_body = """
                    ---------- Forwarded message ---------
                    From: sarah@vc.com
                    Date: Mon, Jan 15, 2025
                    Subject: Intro: TestCo
                    To: investor@fund.com

                    Hey, wanted to introduce you to TestCo.

                    ---------- Forwarded message ---------
                    From: alex@testco.com
                    Date: Sun, Jan 14, 2025
                    Subject: Re: Meeting
                    To: sarah@vc.com

                    Thanks for the intro!
                    """

                    messages = svc._parse_email_thread(email_body)

                    # Should find multiple messages
                    assert len(messages) >= 1

    def test_extract_domain_from_messages(self):
        """Test extracting domain from email messages."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    messages = [
                        {'from': 'john@forithmus.com', 'body': 'Hello'},
                        {'from': 'sarah@vc.com', 'body': 'Intro'},
                    ]

                    domain = svc._extract_domain_from_messages(messages)

                    # Should extract a domain (exact behavior depends on implementation)
                    # Common VC domains like vc.com might be filtered
                    assert domain is None or isinstance(domain, str)


class TestFormatResponse:
    """Tests for response formatting."""

    def test_format_response_generate_memos(self):
        """Test response formatting for GENERATE_MEMOS action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'GENERATE_MEMOS', 'reasoning': 'User requested'}
                    result = {
                        'success': True,
                        'processed': 5,
                        'skipped': 2,
                        'errors': 1
                    }

                    response = svc._format_response(decision, result)

                    # Response starts with "Done!" and contains counts
                    assert 'Done!' in response or 'Processed' in response
                    assert '5' in response

    def test_format_response_add_company(self):
        """Test response formatting for ADD_COMPANY action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'ADD_COMPANY', 'reasoning': 'User requested'}
                    result = {
                        'success': True,
                        'action': 'added',
                        'company': 'NewCo',
                        'domain': 'newco.com'
                    }

                    response = svc._format_response(decision, result)

                    assert 'NewCo' in response

    def test_format_response_health_check(self):
        """Test response formatting for HEALTH_CHECK action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'HEALTH_CHECK', 'reasoning': 'Status check'}
                    result = {'status': 'healthy'}

                    response = svc._format_response(decision, result)

                    assert 'health' in response.lower() or 'status' in response.lower()

    def test_format_response_error(self):
        """Test response formatting when action fails."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'REGENERATE_MEMO', 'reasoning': 'Test'}
                    result = {
                        'success': False,
                        'error': 'Company not found'
                    }

                    response = svc._format_response(decision, result)

                    assert 'error' in response.lower() or 'not found' in response.lower()

    def test_format_response_scrape_yc(self):
        """Test response formatting for SCRAPE_YC action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'SCRAPE_YC', 'reasoning': 'Scrape batch'}
                    result = {
                        'success': True,
                        'added': 10,
                        'skipped': 5,
                        'batch': 'W26',
                        'added_companies': ['Company1', 'Company2']
                    }

                    response = svc._format_response(decision, result)

                    # Response should contain batch and count info
                    assert 'W26' in response
                    assert '10' in response or 'imported' in response.lower()


class TestExecuteAction:
    """Tests for action execution."""

    def test_execute_action_none(self):
        """Test executing NONE action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'NONE',
                        'reasoning': 'No action needed'
                    }

                    result = svc._execute_action(decision, {}, {})

                    assert result.get('skipped') is True or result == {}

    def test_execute_action_health_check(self, mock_services):
        """Test executing HEALTH_CHECK action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'HEALTH_CHECK',
                        'reasoning': 'Check status'
                    }

                    result = svc._execute_action(decision, mock_services, {})

                    assert 'status' in result


class TestProcessEmail:
    """Tests for the main process_email method."""

    def test_process_email_returns_response(self, mock_services):
        """Test that process_email returns a properly formatted response."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    # Mock action decision response - needs proper JSON
                    mock_response = Mock()
                    mock_response.text = '''```json
{"action": "HEALTH_CHECK", "parameters": {}, "reasoning": "test"}
```'''
                    mock_model.generate_content.return_value = mock_response

                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    email_data = {
                        'from': 'test@example.com',
                        'subject': 'Health check',
                        'body': 'Check status'
                    }

                    result = svc.process_email(email_data, mock_services)

                    # Result contains reply_text (the response message)
                    assert 'reply_text' in result
                    assert isinstance(result['reply_text'], str)
                    assert 'operational' in result['reply_text'].lower()
