"""Tests for GeminiService."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestGeminiService:
    """Tests for the GeminiService class."""

    def test_generate_memo_basic(self):
        """Test basic memo generation."""
        with patch('services.gemini.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.gemini.vertexai') as mock_vertexai:
                with patch('services.gemini.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    mock_response = Mock()
                    mock_response.text = "# Test Memo\n\nThis is a generated memo."
                    mock_model.generate_content.return_value = mock_response

                    from services.gemini import GeminiService
                    svc = GeminiService()

                    result = svc.generate_memo('TestCo', 'test.com')

                    assert '# Test Memo' in result
                    mock_model.generate_content.assert_called_once()

    def test_generate_memo_with_research_context(self):
        """Test memo generation with research context."""
        with patch('services.gemini.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.gemini.vertexai'):
                with patch('services.gemini.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    mock_response = Mock()
                    mock_response.text = "# Forithmus Research Brief\n\n## Overview\nAI Healthcare company."
                    mock_model.generate_content.return_value = mock_response

                    from services.gemini import GeminiService
                    svc = GeminiService()

                    research_context = """
                    === COMPANY WEBSITE CONTENT ===
                    Forithmus is an AI healthcare platform.
                    Founded in 2024.
                    """

                    result = svc.generate_memo('Forithmus', 'forithmus.com', research_context=research_context)

                    assert 'Forithmus' in result
                    # Verify research context was passed to the model
                    call_args = mock_model.generate_content.call_args
                    prompt = call_args[0][0]
                    assert 'Forithmus' in prompt

    def test_generate_memo_with_custom_prompt(self):
        """Test memo generation with custom prompt."""
        with patch('services.gemini.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.gemini.vertexai'):
                with patch('services.gemini.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    mock_response = Mock()
                    mock_response.text = "Custom analysis output"
                    mock_model.generate_content.return_value = mock_response

                    from services.gemini import GeminiService
                    svc = GeminiService()

                    custom_prompt = "Analyze this company focusing only on their team."
                    result = svc.generate_memo('TestCo', 'test.com', custom_prompt=custom_prompt)

                    # Verify custom prompt was used
                    call_args = mock_model.generate_content.call_args
                    prompt = call_args[0][0]
                    assert 'Analyze this company focusing only on their team' in prompt

    def test_generate_memo_no_domain(self):
        """Test memo generation for company without domain."""
        with patch('services.gemini.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.gemini.vertexai'):
                with patch('services.gemini.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    mock_response = Mock()
                    mock_response.text = "# Cofia Brief\n\nYC W26 Company"
                    mock_model.generate_content.return_value = mock_response

                    from services.gemini import GeminiService
                    svc = GeminiService()

                    result = svc.generate_memo('Cofia', '')

                    assert 'Cofia' in result

    def test_generate_memo_handles_empty_response(self):
        """Test handling of empty model response."""
        with patch('services.gemini.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.gemini.vertexai'):
                with patch('services.gemini.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model

                    mock_response = Mock()
                    mock_response.text = ""
                    mock_model.generate_content.return_value = mock_response

                    from services.gemini import GeminiService
                    svc = GeminiService()

                    result = svc.generate_memo('TestCo', 'test.com')

                    assert result == ""

    def test_gemini_service_initializes_vertexai(self):
        """Test that GeminiService initializes Vertex AI correctly."""
        with patch('services.gemini.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.gemini.vertexai') as mock_vertexai:
                with patch('services.gemini.GenerativeModel'):
                    from services.gemini import GeminiService
                    svc = GeminiService()

                    mock_vertexai.init.assert_called_once_with(
                        project='test-project',
                        location='us-central1'
                    )

    def test_generate_memo_uses_correct_model(self):
        """Test that the correct Gemini model is used."""
        with patch('services.gemini.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.vertex_ai_region = 'us-central1'

            with patch('services.gemini.vertexai'):
                with patch('services.gemini.GenerativeModel') as mock_model_class:
                    mock_model = Mock()
                    mock_model_class.return_value = mock_model
                    mock_response = Mock()
                    mock_response.text = "Test"
                    mock_model.generate_content.return_value = mock_response

                    from services.gemini import GeminiService
                    svc = GeminiService()

                    # Verify model name contains 'gemini'
                    call_args = mock_model_class.call_args
                    model_name = call_args[0][0]
                    assert 'gemini' in model_name.lower()
