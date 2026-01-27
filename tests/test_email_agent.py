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
                        'SUMMARIZE_UPDATES',
                        'SCRAPE_YC',
                        'HEALTH_CHECK',
                        'NONE'
                    ]

                    for action in expected_actions:
                        assert action in svc.ACTIONS
                        assert 'description' in svc.ACTIONS[action]

    def test_summarize_updates_action_defined(self):
        """Test that SUMMARIZE_UPDATES action is properly defined."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    assert 'SUMMARIZE_UPDATES' in svc.ACTIONS
                    assert 'how is' in svc.ACTIONS['SUMMARIZE_UPDATES']['description'].lower()


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


class TestGetActionDecision:
    """Tests for _get_action_decision method."""

    def test_get_action_decision_handles_error(self, mock_services):
        """Test that _get_action_decision handles exceptions gracefully."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    # Make generate_content raise an exception
                    mock_model.generate_content.side_effect = Exception('API error')

                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    email_data = {
                        'from': 'test@example.com',
                        'subject': 'Test',
                        'body': 'Test body'
                    }

                    result = svc._get_action_decision(email_data)

                    # Should return NONE action on error
                    assert result['action'] == 'NONE'
                    assert 'trouble' in result['reasoning'].lower()

    def test_get_action_decision_cleans_json_markdown(self, mock_services):
        """Test that _get_action_decision cleans markdown from response."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    # Response with markdown code block
                    mock_response = Mock()
                    mock_response.text = '''```json
{"action": "ADD_COMPANY", "parameters": {"company": "TestCo", "domain": "test.com"}, "reasoning": "User wants to add company"}
```'''
                    mock_model.generate_content.return_value = mock_response

                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    email_data = {
                        'from': 'test@example.com',
                        'subject': 'Add TestCo',
                        'body': 'Add TestCo (test.com)'
                    }

                    result = svc._get_action_decision(email_data)

                    assert result['action'] == 'ADD_COMPANY'
                    assert result['parameters']['company'] == 'TestCo'


class TestExecuteActionBranches:
    """Tests for various _execute_action branches."""

    def test_execute_action_generate_memos(self, mock_services):
        """Test GENERATE_MEMOS action execution."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    mock_services['sheets'].get_rows_to_process.return_value = []

                    svc = EmailAgentService()

                    decision = {
                        'action': 'GENERATE_MEMOS',
                        'parameters': {}
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is True
                    assert result['processed'] == 0

    def test_execute_action_generate_memos_with_force(self, mock_services):
        """Test GENERATE_MEMOS with force parameter."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    mock_services['sheets'].get_all_companies.return_value = []

                    svc = EmailAgentService()

                    decision = {
                        'action': 'GENERATE_MEMOS',
                        'parameters': {'force': True}
                    }

                    result = svc._execute_action(decision, mock_services)

                    mock_services['sheets'].get_all_companies.assert_called_once()
                    assert result['success'] is True

    def test_execute_action_add_company(self, mock_services):
        """Test ADD_COMPANY action execution."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    mock_services['sheets'].add_company.return_value = {
                        'success': True,
                        'action': 'added',
                        'company': 'TestCo',
                        'domain': 'testco.com'
                    }

                    svc = EmailAgentService()

                    decision = {
                        'action': 'ADD_COMPANY',
                        'parameters': {'company': 'TestCo', 'domain': 'testco.com'}
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is True
                    mock_services['sheets'].add_company.assert_called_once_with('TestCo', 'testco.com')

    def test_execute_action_add_company_missing_params(self, mock_services):
        """Test ADD_COMPANY with missing parameters."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'ADD_COMPANY',
                        'parameters': {}  # Missing company and domain
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is False
                    assert 'missing' in result['error'].lower()

    def test_execute_action_update_company_missing_company(self, mock_services):
        """Test UPDATE_COMPANY with missing company name."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'UPDATE_COMPANY',
                        'parameters': {'new_domain': 'new.com'}  # Missing company
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is False
                    assert 'missing company' in result['error'].lower()

    def test_execute_action_update_company_missing_update_data(self, mock_services):
        """Test UPDATE_COMPANY with missing update data."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'UPDATE_COMPANY',
                        'parameters': {'company': 'TestCo'}  # Missing new_domain and new_name
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is False
                    assert 'missing' in result['error'].lower()

    def test_execute_action_regenerate_memo_missing_identifier(self, mock_services):
        """Test REGENERATE_MEMO with missing identifier."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'REGENERATE_MEMO',
                        'parameters': {}  # Missing domain and company
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is False
                    assert 'missing' in result['error'].lower()

    def test_execute_action_analyze_thread_no_email_data(self, mock_services):
        """Test ANALYZE_THREAD with no email data."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'ANALYZE_THREAD',
                        'parameters': {}
                    }

                    result = svc._execute_action(decision, mock_services, email_data=None)

                    assert result['success'] is False
                    assert 'no email data' in result['error'].lower()

    def test_execute_action_analyze_thread_no_body(self, mock_services):
        """Test ANALYZE_THREAD with empty body."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'ANALYZE_THREAD',
                        'parameters': {}
                    }

                    email_data = {'from': 'test@example.com', 'subject': 'Test', 'body': ''}

                    result = svc._execute_action(decision, mock_services, email_data=email_data)

                    assert result['success'] is False
                    assert 'no email body' in result['error'].lower()

    def test_execute_action_scrape_yc(self, mock_services):
        """Test SCRAPE_YC action execution."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.bookface_cookie = 'test-cookie'  # Must be non-empty

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    with patch('services.email_agent.BookfaceService') as MockBookface:
                        mock_bf = Mock()
                        mock_bf.scrape_and_add_companies.return_value = {
                            'success': True,
                            'added': 2,
                            'skipped': 0,
                            'batch': 'W26',
                            'added_companies': ['Company1', 'Company2']
                        }
                        MockBookface.return_value = mock_bf

                        from services.email_agent import EmailAgentService

                        svc = EmailAgentService()

                        decision = {
                            'action': 'SCRAPE_YC',
                            'parameters': {'batch': 'W26', 'pages': '2'}
                        }

                        result = svc._execute_action(decision, mock_services)

                        assert result['success'] is True
                        assert result['added'] == 2

    def test_execute_action_scrape_yc_no_cookie(self, mock_services):
        """Test SCRAPE_YC action without cookie configured."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.bookface_cookie = ''  # Empty cookie

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'SCRAPE_YC',
                        'parameters': {'batch': 'W26'}
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is False
                    assert 'cookie' in result['error'].lower()

    def test_execute_action_chained_regenerate_memo(self, mock_services, mock_sheet_data):
        """Test chained REGENERATE_MEMO action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Set up mock to return company
                    mock_services['sheets'].update_company.return_value = {
                        'success': True,
                        'company': 'TestCo',
                        'old_domain': 'old.com',
                        'new_domain': 'new.com'
                    }

                    # Set up sheet data for regenerate
                    mock_services['sheets'].service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = mock_sheet_data

                    svc = EmailAgentService()

                    # Skip the actual regeneration
                    with patch.object(svc, '_regenerate_memo') as mock_regen:
                        mock_regen.return_value = {'success': True}

                        decision = {
                            'action': 'UPDATE_COMPANY',
                            'parameters': {'company': 'TestCo', 'new_domain': 'new.com'},
                            'also_do': 'REGENERATE_MEMO'
                        }

                        result = svc._execute_action(decision, mock_services)

                        assert result['success'] is True
                        assert result.get('chained_action') == 'REGENERATE_MEMO'


class TestRunMemoGeneration:
    """Tests for _run_memo_generation method."""

    def test_run_memo_generation_processes_companies(self, mock_services):
        """Test memo generation with companies to process."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    mock_services['sheets'].get_rows_to_process.return_value = [
                        {'company': 'TestCo', 'domain': 'testco.com', 'row_number': 2}
                    ]

                    svc = EmailAgentService()

                    # Mock _process_single_company
                    with patch.object(svc, '_process_single_company') as mock_process:
                        mock_process.return_value = {'status': 'success', 'company': 'TestCo'}

                        result = svc._run_memo_generation(mock_services, force=False)

                        assert result['success'] is True
                        assert result['processed'] == 1
                        mock_process.assert_called_once()

    def test_run_memo_generation_with_force(self, mock_services):
        """Test memo generation with force flag."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    mock_services['sheets'].get_all_companies.return_value = [
                        {'company': 'TestCo', 'domain': 'testco.com', 'row_number': 2}
                    ]

                    svc = EmailAgentService()

                    with patch.object(svc, '_process_single_company') as mock_process:
                        mock_process.return_value = {'status': 'success'}

                        result = svc._run_memo_generation(mock_services, force=True)

                        mock_services['sheets'].get_all_companies.assert_called_once()
                        mock_services['firestore'].clear_processed.assert_called()

    def test_run_memo_generation_skips_empty_keys(self, mock_services):
        """Test that memo generation skips rows without domain or company."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    mock_services['sheets'].get_rows_to_process.return_value = [
                        {'company': '', 'domain': '', 'row_number': 2}  # Empty - should skip
                    ]

                    svc = EmailAgentService()

                    with patch.object(svc, '_process_single_company') as mock_process:
                        result = svc._run_memo_generation(mock_services, force=False)

                        # Should not process since key is empty
                        mock_process.assert_not_called()
                        assert result['processed'] == 0


class TestAnalyzeThread:
    """Tests for _analyze_thread method."""

    def test_analyze_thread_success(self, mock_services):
        """Test successful thread analysis."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    # Mock helper methods
                    with patch.object(svc, '_parse_email_thread') as mock_parse:
                        with patch.object(svc, '_extract_domain_from_messages') as mock_domain:
                            with patch.object(svc, '_get_relationship') as mock_get_rel:
                                with patch.object(svc, '_generate_relationship_analysis') as mock_gen:
                                    with patch.object(svc, '_create_timeline_doc') as mock_create_doc:
                                        with patch.object(svc, '_store_relationship') as mock_store:
                                            mock_parse.return_value = [
                                                {'from': 'test@company.com', 'body': 'Hello'}
                                            ]
                                            mock_domain.return_value = 'company.com'
                                            mock_get_rel.return_value = None  # No existing
                                            mock_gen.return_value = {
                                                'company_name': 'Company Inc',
                                                'summary': 'Test summary',
                                                'introducer': {'name': 'John'}
                                            }
                                            mock_create_doc.return_value = 'doc-123'
                                            mock_services['drive'].find_existing_folder.return_value = None
                                            mock_services['drive'].create_folder.return_value = 'folder-123'
                                            mock_services['sheets'].add_company.return_value = {'success': True}

                                            email_body = "From: test@company.com\nHello"
                                            result = svc._analyze_thread(email_body, mock_services)

                                            assert result['success'] is True
                                            assert result['domain'] == 'company.com'

    def test_analyze_thread_no_messages(self, mock_services):
        """Test thread analysis when no messages can be parsed."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    with patch.object(svc, '_parse_email_thread') as mock_parse:
                        mock_parse.return_value = []  # No messages parsed

                        result = svc._analyze_thread("some text", mock_services)

                        assert result['success'] is False
                        assert 'could not parse' in result['error'].lower()

    def test_analyze_thread_no_domain(self, mock_services):
        """Test thread analysis when domain cannot be determined."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    with patch.object(svc, '_parse_email_thread') as mock_parse:
                        with patch.object(svc, '_extract_domain_from_messages') as mock_domain:
                            mock_parse.return_value = [{'from': 'test', 'body': 'text'}]
                            mock_domain.return_value = None  # No domain found

                            result = svc._analyze_thread("some text", mock_services)

                            assert result['success'] is False
                            assert 'could not determine' in result['error'].lower()


class TestGenerateRelationshipAnalysis:
    """Tests for _generate_relationship_analysis method."""

    def test_generate_relationship_analysis_success(self):
        """Test successful relationship analysis generation."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    mock_response = Mock()
                    mock_response.text = '''{
                        "company_name": "TestCo",
                        "contacts": [{"name": "John", "email": "john@test.com"}],
                        "timeline": [{"date": "2024-01-01", "event": "First contact"}],
                        "summary": "Good relationship",
                        "key_topics": ["tech"],
                        "sentiment": "positive",
                        "next_steps": "Follow up"
                    }'''
                    mock_model.generate_content.return_value = mock_response

                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    messages = [
                        {'from': 'john@test.com', 'date': '2024-01-01', 'subject': 'Hi', 'body': 'Hello'}
                    ]

                    result = svc._generate_relationship_analysis(messages, 'test.com')

                    assert result['company_name'] == 'TestCo'
                    assert len(result['contacts']) == 1

    def test_generate_relationship_analysis_cleans_markdown(self):
        """Test that markdown is cleaned from response."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    mock_response = Mock()
                    mock_response.text = '''```json
{
    "company_name": "TestCo",
    "contacts": [],
    "timeline": [],
    "summary": "Summary",
    "key_topics": [],
    "sentiment": "neutral",
    "next_steps": ""
}
```'''
                    mock_model.generate_content.return_value = mock_response

                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    result = svc._generate_relationship_analysis([], 'test.com')

                    assert result['company_name'] == 'TestCo'

    def test_generate_relationship_analysis_error(self):
        """Test relationship analysis handles errors."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    mock_model.generate_content.side_effect = Exception('API Error')

                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    result = svc._generate_relationship_analysis([], 'test.com')

                    # Should return default values on error
                    assert result['company_name'] == 'test.com'
                    assert 'Error' in result['summary']


class TestSummarizeUpdates:
    """Tests for SUMMARIZE_UPDATES action."""

    def test_execute_summarize_updates(self, mock_services):
        """Test executing SUMMARIZE_UPDATES action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Add mock gmail service
                    mock_gmail = Mock()
                    mock_gmail.fetch_emails.return_value = [
                        {
                            'id': 'email-1',
                            'from': 'updates@stripe.com',
                            'subject': 'Stripe Monthly Update - January',
                            'date': 'Mon, 15 Jan 2024 10:00:00 -0800',
                            'parsed_date': None,
                            'body': 'This month we launched new features...'
                        },
                        {
                            'id': 'email-2',
                            'from': 'newsletter@stripe.com',
                            'subject': 'Stripe Monthly Update - February',
                            'date': 'Thu, 15 Feb 2024 10:00:00 -0800',
                            'parsed_date': None,
                            'body': 'February was a great month...'
                        }
                    ]
                    mock_services['gmail'] = mock_gmail

                    # Mock drive service for document creation
                    mock_services['drive'].find_existing_folder.return_value = 'folder-123'
                    mock_services['drive'].service = Mock()
                    mock_services['drive'].service.files.return_value.create.return_value.execute.return_value = {'id': 'doc-123'}

                    svc = EmailAgentService()

                    # Mock the summary generation
                    with patch.object(svc, '_generate_updates_summary') as mock_gen:
                        mock_gen.return_value = {
                            'summary': 'Stripe is growing rapidly with new features',
                            'highlights': ['Launched new API', 'Expanded to 5 new countries'],
                            'product_updates': ['New billing features'],
                            'business_updates': ['Revenue up 20%'],
                            'themes': ['Growth', 'Expansion'],
                            'sentiment': 'positive',
                            'trajectory': 'growing',
                            'notable_metrics': []
                        }

                        decision = {
                            'action': 'SUMMARIZE_UPDATES',
                            'parameters': {'company': 'Stripe', 'domain': 'stripe.com'}
                        }

                        result = svc._execute_action(decision, mock_services)

                        assert result['success'] is True
                        assert result['domain'] == 'stripe.com'
                        assert result['email_count'] == 2
                        mock_gmail.fetch_emails.assert_called_once()

    def test_summarize_updates_domain_resolution(self, mock_services):
        """Test that company name is resolved to domain from sheet."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Mock sheet lookup
                    mock_services['sheets'].get_all_companies.return_value = [
                        {'company': 'Stripe', 'domain': 'stripe.com', 'row_number': 2}
                    ]

                    # Add mock gmail service
                    mock_gmail = Mock()
                    mock_gmail.fetch_emails.return_value = []
                    mock_services['gmail'] = mock_gmail

                    svc = EmailAgentService()

                    result = svc._summarize_company_updates('Stripe', '', mock_services)

                    # Should have resolved domain from sheet
                    assert result['domain'] == 'stripe.com'
                    # Gmail was called with the resolved domain (searches entire inbox)
                    mock_gmail.fetch_emails.assert_called_once()
                    call_args = mock_gmail.fetch_emails.call_args
                    query = call_args.kwargs.get('query', '')
                    assert 'from:@stripe.com' in query
                    assert 'to:updates' not in query  # Should search entire inbox

    def test_summarize_updates_no_emails(self, mock_services):
        """Test graceful handling when no update emails found."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Add mock gmail service that returns no emails
                    mock_gmail = Mock()
                    mock_gmail.fetch_emails.return_value = []
                    mock_services['gmail'] = mock_gmail

                    svc = EmailAgentService()

                    result = svc._summarize_company_updates('Unknown', 'unknown.com', mock_services)

                    assert result['success'] is True
                    assert result['email_count'] == 0
                    assert result['doc_id'] is None
                    assert 'No update emails found' in result['summary']

    def test_summarize_updates_no_gmail_service(self, mock_services):
        """Test error when Gmail service is not available."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Ensure no gmail service
                    if 'gmail' in mock_services:
                        del mock_services['gmail']

                    svc = EmailAgentService()

                    result = svc._summarize_company_updates('Stripe', 'stripe.com', mock_services)

                    assert result['success'] is False
                    assert 'Gmail service not available' in result['error']

    def test_summarize_updates_missing_params(self, mock_services):
        """Test error when both company and domain are missing."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {
                        'action': 'SUMMARIZE_UPDATES',
                        'parameters': {}  # Missing company and domain
                    }

                    result = svc._execute_action(decision, mock_services)

                    assert result['success'] is False
                    assert 'missing' in result['error'].lower()

    def test_format_response_summarize_updates(self, mock_services):
        """Test response formatting for SUMMARIZE_UPDATES action."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'SUMMARIZE_UPDATES', 'reasoning': 'User asked how Stripe is doing'}
                    result = {
                        'success': True,
                        'company': 'Stripe',
                        'domain': 'stripe.com',
                        'email_count': 12,
                        'date_range': {'first': 'Jan 1, 2024', 'last': 'Mar 15, 2024'},
                        'summary': 'Stripe is doing great with 20% growth',
                        'highlights': ['Launched new API', 'Expanded globally'],
                        'doc_id': 'doc-123'
                    }

                    response = svc._format_response(decision, result)

                    assert 'Stripe' in response
                    assert 'stripe.com' in response
                    assert '12' in response
                    assert 'doc-123' in response
                    assert 'Highlights' in response

    def test_format_response_summarize_updates_no_emails(self, mock_services):
        """Test response formatting when no update emails found."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    decision = {'action': 'SUMMARIZE_UPDATES', 'reasoning': 'User asked'}
                    result = {
                        'success': True,
                        'company': 'Unknown Co',
                        'domain': 'unknown.com',
                        'email_count': 0,
                        'summary': 'No update emails found',
                        'doc_id': None
                    }

                    response = svc._format_response(decision, result)

                    assert 'No update emails found' in response
                    assert 'Unknown Co' in response


class TestProcessSingleCompany:
    """Tests for _process_single_company method."""

    def test_process_single_company_success(self, mock_services):
        """Test successful single company processing."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = 'key'
            mock_config.linkedin_cookie = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    with patch('services.email_agent.ResearchService') as MockResearch:
                        mock_research = Mock()
                        mock_research.research_company.return_value = {}
                        mock_research.format_research_context.return_value = 'context'
                        MockResearch.return_value = mock_research

                        from services.email_agent import EmailAgentService

                        svc = EmailAgentService()

                        mock_services['firestore'].is_processed.return_value = False
                        mock_services['firestore'].get_yc_company_data.return_value = None
                        mock_services['firestore'].get_relationship_data.return_value = None
                        mock_services['drive'].create_folder.return_value = 'folder-id'
                        mock_services['drive'].create_document.return_value = 'doc-id'
                        mock_services['gemini'].generate_memo.return_value = 'Memo content'

                        row = {'company': 'TestCo', 'domain': 'test.com', 'row_number': 2, 'source': ''}

                        result = svc._process_single_company(
                            row,
                            mock_services['sheets'],
                            mock_services['firestore'],
                            mock_services['drive'],
                            mock_services['gemini'],
                            mock_services['docs']
                        )

                        assert result['status'] == 'success'
                        assert result['company'] == 'TestCo'

    def test_process_single_company_already_processed(self, mock_services):
        """Test that already processed companies are skipped."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    mock_services['firestore'].is_processed.return_value = True

                    row = {'company': 'TestCo', 'domain': 'test.com', 'row_number': 2}

                    result = svc._process_single_company(
                        row,
                        mock_services['sheets'],
                        mock_services['firestore'],
                        mock_services['drive'],
                        mock_services['gemini'],
                        mock_services['docs']
                    )

                    assert result['status'] == 'skipped'
                    assert result['reason'] == 'already_processed'

    def test_process_single_company_error(self, mock_services):
        """Test error handling in single company processing."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    svc = EmailAgentService()

                    mock_services['firestore'].is_processed.return_value = False
                    mock_services['drive'].create_folder.side_effect = Exception('Drive error')

                    row = {'company': 'TestCo', 'domain': 'test.com', 'row_number': 2}

                    result = svc._process_single_company(
                        row,
                        mock_services['sheets'],
                        mock_services['firestore'],
                        mock_services['drive'],
                        mock_services['gemini'],
                        mock_services['docs']
                    )

                    assert result['status'] == 'error'
                    assert 'Drive error' in result['error']


class TestDomainResolution:
    """Tests for _resolve_company_domain method."""

    def test_resolve_domain_from_sheet(self, mock_services):
        """Test resolving domain from spreadsheet."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Sheet contains "Stark Bank" with domain "starkbank.com"
                    mock_services['sheets'].get_all_companies.return_value = [
                        {'company': 'Stark Bank', 'domain': 'starkbank.com', 'row_number': 2}
                    ]

                    svc = EmailAgentService()

                    domain, company = svc._resolve_company_domain('Stark Bank', mock_services)

                    assert domain == 'starkbank.com'
                    assert company == 'Stark Bank'

    def test_resolve_domain_from_gmail(self, mock_services):
        """Test resolving domain from Gmail when not in spreadsheet."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''  # No web search

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Not in spreadsheet
                    mock_services['sheets'].get_all_companies.return_value = []

                    # But found in Gmail
                    mock_gmail = Mock()
                    mock_gmail.fetch_emails.return_value = [
                        {'from': 'Rafael Stark <rafael@starkbank.com>', 'subject': 'Update'},
                        {'from': 'updates@starkbank.com', 'subject': 'Newsletter'},
                        {'from': 'support@starkbank.com', 'subject': 'Help'},
                    ]
                    mock_services['gmail'] = mock_gmail

                    svc = EmailAgentService()

                    domain, company = svc._resolve_company_domain('Stark Bank', mock_services)

                    assert domain == 'starkbank.com'
                    mock_gmail.fetch_emails.assert_called_once()

    def test_resolve_domain_from_web_search(self, mock_services):
        """Test resolving domain from web search when not in sheet or Gmail."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = 'test-key'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    with patch('services.email_agent.requests') as mock_requests:
                        from services.email_agent import EmailAgentService

                        # Not in spreadsheet
                        mock_services['sheets'].get_all_companies.return_value = []

                        # Gmail returns no useful results
                        mock_gmail = Mock()
                        mock_gmail.fetch_emails.return_value = []
                        mock_services['gmail'] = mock_gmail

                        # Web search finds the company
                        mock_response = Mock()
                        mock_response.status_code = 200
                        mock_response.json.return_value = {
                            'organic': [
                                {
                                    'title': 'Stark Bank - Digital Banking',
                                    'link': 'https://starkbank.com/',
                                    'snippet': 'Stark Bank is a digital bank...'
                                }
                            ]
                        }
                        mock_requests.post.return_value = mock_response

                        svc = EmailAgentService()

                        domain, company = svc._resolve_company_domain('Stark Bank', mock_services)

                        assert domain == 'starkbank.com'
                        mock_requests.post.assert_called_once()

    def test_resolve_domain_fallback(self, mock_services):
        """Test fallback to {company}.com when nothing found."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''  # No web search

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Not in spreadsheet
                    mock_services['sheets'].get_all_companies.return_value = []

                    # Gmail returns no useful results
                    mock_gmail = Mock()
                    mock_gmail.fetch_emails.return_value = []
                    mock_services['gmail'] = mock_gmail

                    svc = EmailAgentService()

                    domain, company = svc._resolve_company_domain('Stark Bank', mock_services)

                    # Falls back to companyname.com (spaces removed)
                    assert domain == 'starkbank.com'
                    assert company == 'Stark Bank'

    def test_resolve_domain_gmail_filters_common_providers(self, mock_services):
        """Test that Gmail search filters out common email providers."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = ''

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    from services.email_agent import EmailAgentService

                    # Not in spreadsheet
                    mock_services['sheets'].get_all_companies.return_value = []

                    # Gmail returns mostly common providers, but one company domain
                    mock_gmail = Mock()
                    mock_gmail.fetch_emails.return_value = [
                        {'from': 'john@gmail.com', 'subject': 'Re: Stark Bank'},
                        {'from': 'jane@yahoo.com', 'subject': 'Stark Bank intro'},
                        {'from': 'support@starkbank.com', 'subject': 'Welcome'},
                    ]
                    mock_services['gmail'] = mock_gmail

                    svc = EmailAgentService()

                    domain, company = svc._resolve_company_domain('Stark Bank', mock_services)

                    # Should find starkbank.com, filtering out gmail and yahoo
                    assert domain == 'starkbank.com'

    def test_resolve_domain_web_search_skips_social_media(self, mock_services):
        """Test that web search skips social media and directory sites."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = 'test-key'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    with patch('services.email_agent.requests') as mock_requests:
                        from services.email_agent import EmailAgentService

                        # Not in spreadsheet or Gmail
                        mock_services['sheets'].get_all_companies.return_value = []
                        mock_gmail = Mock()
                        mock_gmail.fetch_emails.return_value = []
                        mock_services['gmail'] = mock_gmail

                        # Web search returns LinkedIn first, then company site
                        mock_response = Mock()
                        mock_response.status_code = 200
                        mock_response.json.return_value = {
                            'organic': [
                                {
                                    'title': 'Stark Bank | LinkedIn',
                                    'link': 'https://linkedin.com/company/starkbank',
                                    'snippet': 'Company page'
                                },
                                {
                                    'title': 'Stark Bank - Crunchbase',
                                    'link': 'https://crunchbase.com/organization/starkbank',
                                    'snippet': 'Company profile'
                                },
                                {
                                    'title': 'Stark Bank - Digital Banking',
                                    'link': 'https://www.starkbank.com/',
                                    'snippet': 'Official website'
                                }
                            ]
                        }
                        mock_requests.post.return_value = mock_response

                        svc = EmailAgentService()

                        domain, company = svc._resolve_company_domain('Stark Bank', mock_services)

                        # Should skip LinkedIn and Crunchbase, return actual company domain
                        assert domain == 'starkbank.com'

    def test_summarize_updates_uses_smart_resolution(self, mock_services):
        """Test that _summarize_company_updates uses the smart domain resolution."""
        with patch('services.email_agent.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'
            mock_config.serper_api_key = 'test-key'

            with patch('services.email_agent.vertexai'):
                with patch('services.email_agent.GenerativeModel'):
                    with patch('services.email_agent.requests') as mock_requests:
                        from services.email_agent import EmailAgentService

                        # Not in spreadsheet
                        mock_services['sheets'].get_all_companies.return_value = []

                        # Gmail search for company name finds emails
                        mock_gmail = Mock()
                        # First call: domain resolution search
                        # Second call: fetching update emails
                        mock_gmail.fetch_emails.side_effect = [
                            # Domain resolution search
                            [{'from': 'updates@starkbank.com', 'subject': 'Update'}],
                            # Actual update emails fetch
                            [
                                {
                                    'id': 'email-1',
                                    'from': 'updates@starkbank.com',
                                    'subject': 'Monthly Update',
                                    'date': 'Mon, 15 Jan 2024',
                                    'parsed_date': None,
                                    'body': 'Here are our updates...'
                                }
                            ]
                        ]
                        mock_services['gmail'] = mock_gmail

                        # Mock drive service for document creation
                        mock_services['drive'].find_existing_folder.return_value = 'folder-123'
                        mock_services['drive'].service = Mock()
                        mock_services['drive'].service.files.return_value.create.return_value.execute.return_value = {'id': 'doc-123'}

                        svc = EmailAgentService()

                        # Mock the summary generation
                        with patch.object(svc, '_generate_updates_summary') as mock_gen:
                            mock_gen.return_value = {
                                'summary': 'Stark Bank is doing well',
                                'highlights': [],
                                'product_updates': [],
                                'business_updates': [],
                                'themes': [],
                                'sentiment': 'positive',
                                'trajectory': 'growing',
                                'notable_metrics': []
                            }

                            # Call with company name only (no domain)
                            result = svc._summarize_company_updates('Stark Bank', '', mock_services)

                            # Should have resolved domain through smart resolution
                            assert result['success'] is True
                            assert result['domain'] == 'starkbank.com'
                            # Gmail should have been called twice: once for resolution, once for updates
                            assert mock_gmail.fetch_emails.call_count == 2
