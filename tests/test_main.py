"""Tests for main.py Flask endpoints."""
import pytest
from unittest.mock import patch, Mock


class TestEmailEndpointSecurity:
    """Tests for email endpoint domain security filter."""

    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        from main import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    def test_email_rejects_unauthorized_sender(self, client):
        """Emails from non-friale.com domains should be rejected with 403."""
        response = client.post('/email', json={
            'from': 'attacker@evil.com',
            'subject': 'Test',
            'body': 'Hello'
        })

        assert response.status_code == 403
        data = response.get_json()
        assert data['status'] == 'error'
        assert data['message'] == 'Unauthorized sender domain'

    def test_email_rejects_empty_sender(self, client):
        """Emails with no sender should be rejected with 403."""
        response = client.post('/email', json={
            'subject': 'Test',
            'body': 'Hello'
        })

        assert response.status_code == 403
        data = response.get_json()
        assert data['status'] == 'error'
        assert data['message'] == 'Unauthorized sender domain'

    def test_email_rejects_partial_domain_match(self, client):
        """Emails from domains containing but not ending with friale.com should be rejected."""
        response = client.post('/email', json={
            'from': 'user@friale.com.evil.com',
            'subject': 'Test',
            'body': 'Hello'
        })

        assert response.status_code == 403

    def test_email_rejects_similar_domain(self, client):
        """Emails from similar-looking domains should be rejected."""
        response = client.post('/email', json={
            'from': 'user@notfriale.com',
            'subject': 'Test',
            'body': 'Hello'
        })

        assert response.status_code == 403

    @patch('main.ServiceFactory')
    @patch('main.get_gmail_credentials')
    @patch('main.EmailAgentService')
    def test_email_accepts_friale_domain(self, mock_agent, mock_creds, mock_factory, client):
        """Emails from @friale.com should be processed."""
        # Setup mocks
        mock_services = {'sheets': Mock(), 'firestore': Mock()}
        mock_factory.create.return_value.create_all.return_value = mock_services
        mock_creds.return_value = Mock()

        mock_agent_instance = Mock()
        mock_agent_instance.process_email.return_value = {
            'decision': {'action': 'HEALTH_CHECK', 'reasoning': 'Test'},
            'reply_text': 'OK',
            'result': {'status': 'healthy'}
        }
        mock_agent.return_value = mock_agent_instance

        response = client.post('/email', json={
            'from': 'nick@friale.com',
            'subject': 'Test',
            'body': 'Hello'
        })

        assert response.status_code == 200
        mock_agent_instance.process_email.assert_called_once()

    @patch('main.ServiceFactory')
    @patch('main.get_gmail_credentials')
    @patch('main.EmailAgentService')
    def test_email_accepts_friale_domain_case_insensitive(self, mock_agent, mock_creds, mock_factory, client):
        """Email domain check should be case-insensitive."""
        mock_services = {'sheets': Mock(), 'firestore': Mock()}
        mock_factory.create.return_value.create_all.return_value = mock_services
        mock_creds.return_value = Mock()

        mock_agent_instance = Mock()
        mock_agent_instance.process_email.return_value = {
            'decision': {'action': 'HEALTH_CHECK', 'reasoning': 'Test'},
            'reply_text': 'OK',
            'result': {'status': 'healthy'}
        }
        mock_agent.return_value = mock_agent_instance

        response = client.post('/email', json={
            'from': 'Nick@FRIALE.COM',
            'subject': 'Test',
            'body': 'Hello'
        })

        assert response.status_code == 200

