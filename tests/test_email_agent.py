"""Tests for EmailAgentService (new modular architecture)."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestEmailAgentService:
    """Tests for the refactored EmailAgentService class."""

    def test_initialization(self):
        """Test EmailAgentService initialization."""
        from services.email_agent import EmailAgentService

        services = {'sheets': Mock(), 'firestore': Mock()}
        agent = EmailAgentService(services)

        assert agent.services == services
        assert agent._actions == {}

    def test_initialization_no_services(self):
        """Test EmailAgentService with no services."""
        from services.email_agent import EmailAgentService

        agent = EmailAgentService()
        assert agent.services == {}

    def test_get_action_creates_action(self):
        """Test that _get_action creates action handlers."""
        from services.email_agent import EmailAgentService

        services = {'sheets': Mock()}
        agent = EmailAgentService(services)

        # Clear caches
        agent._actions = {}

        action = agent._get_action('HEALTH_CHECK')
        assert action is not None
        assert 'HEALTH_CHECK' in agent._actions

    def test_get_action_returns_none_for_unknown(self):
        """Test that _get_action returns None for unknown actions."""
        from services.email_agent import EmailAgentService

        agent = EmailAgentService({})
        action = agent._get_action('UNKNOWN_ACTION')
        assert action is None

    def test_execute_action_none(self):
        """Test executing NONE action returns skipped."""
        from services.email_agent import EmailAgentService

        agent = EmailAgentService({})
        result = agent._execute_action('NONE', {}, {})

        assert result['success'] is False
        assert result['skipped'] is True


class TestProcessEmail:
    """Tests for process_email method."""

    def test_process_email_with_mocked_router(self):
        """Test process_email calls router and executes action."""
        from services.email_agent import EmailAgentService

        mock_router = Mock()
        mock_router.decide.return_value = {
            'action': 'HEALTH_CHECK',
            'reasoning': 'Status check requested',
            'parameters': {}
        }

        agent = EmailAgentService({})
        agent._router = mock_router

        email_data = {
            'from': 'test@example.com',
            'subject': 'Status check',
            'body': 'Check health'
        }

        result = agent.process_email(email_data)

        assert 'decision' in result
        assert 'result' in result
        assert 'reply_text' in result
        mock_router.decide.assert_called_once_with(email_data)


class TestFormatResponse:
    """Tests for response formatting."""

    def test_format_response_skipped(self):
        """Test formatting response when action was skipped."""
        from services.email_agent import EmailAgentService

        agent = EmailAgentService({})
        decision = {'reasoning': 'Could not understand request'}
        result = {'skipped': True}

        response = agent._format_response('NONE', decision, result)

        assert "couldn't identify" in response.lower()
        assert 'Available commands' in response

    def test_format_response_error(self):
        """Test formatting response when action failed."""
        from services.email_agent import EmailAgentService

        agent = EmailAgentService({})
        decision = {'reasoning': 'Test'}
        result = {'success': False, 'error': 'Something went wrong'}

        response = agent._format_response('ADD_COMPANY', decision, result)

        assert 'error' in response.lower()
        assert 'Something went wrong' in response


class TestActionDescriptions:
    """Tests for action description functions."""

    def test_get_action_descriptions(self):
        """Test that action descriptions are available."""
        from actions import get_action_descriptions

        descriptions = get_action_descriptions()

        assert 'ADD_COMPANY' in descriptions
        assert 'GENERATE_MEMOS' in descriptions
        assert 'HEALTH_CHECK' in descriptions
        assert 'NONE' in descriptions

        # Each should have a description key
        for name, data in descriptions.items():
            assert 'description' in data
            assert isinstance(data['description'], str)

    def test_action_registry(self):
        """Test that ACTION_REGISTRY contains all expected actions."""
        from actions import ACTION_REGISTRY

        expected_actions = [
            'ADD_COMPANY',
            'UPDATE_COMPANY',
            'GENERATE_MEMOS',
            'REGENERATE_MEMO',
            'ANALYZE_THREAD',
            'SUMMARIZE_UPDATES',
            'SCRAPE_YC',
            'HEALTH_CHECK',
        ]

        for action_name in expected_actions:
            assert action_name in ACTION_REGISTRY
            assert hasattr(ACTION_REGISTRY[action_name], 'execute')
            assert hasattr(ACTION_REGISTRY[action_name], 'format_response')


class TestEmailRouter:
    """Tests for EmailRouter class."""

    def test_router_actions_property(self):
        """Test that router ACTIONS property returns descriptions."""
        with patch('core.email_router.vertexai'):
            with patch('core.email_router.GenerativeModel'):
                from core.email_router import EmailRouter
                router = EmailRouter()

                actions = router.ACTIONS

                assert 'ADD_COMPANY' in actions
                assert 'NONE' in actions
                assert 'description' in actions['ADD_COMPANY']


class TestIndividualActions:
    """Tests for individual action classes."""

    def test_health_check_action(self):
        """Test HealthCheckAction execution."""
        from actions import HealthCheckAction

        action = HealthCheckAction({})
        result = action.execute({})

        assert result['success'] is True
        assert result['status'] == 'healthy'

    def test_add_company_action_missing_params(self):
        """Test AddCompanyAction with missing parameters."""
        from actions import AddCompanyAction

        action = AddCompanyAction({})
        result = action.execute({})

        assert result['success'] is False
        assert 'Missing' in result.get('error', '')

    def test_add_company_action_success(self):
        """Test AddCompanyAction with valid parameters."""
        from actions import AddCompanyAction

        mock_sheets = Mock()
        mock_sheets.add_company.return_value = {
            'success': True,
            'company': 'TestCo',
            'domain': 'test.com'
        }

        action = AddCompanyAction({'sheets': mock_sheets})
        result = action.execute({'company': 'TestCo', 'domain': 'test.com'})

        assert result['success'] is True
        mock_sheets.add_company.assert_called_once_with('TestCo', 'test.com', '')

    def test_action_format_response(self):
        """Test action format_response methods."""
        from actions import HealthCheckAction

        action = HealthCheckAction({})
        result = {'success': True, 'status': 'healthy'}
        response = action.format_response(result)

        assert 'operational' in response.lower()
