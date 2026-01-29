"""Tests for AnswerQuestionAction and QuestionService."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestAnswerQuestionAction:
    """Tests for AnswerQuestionAction class."""

    def test_initialization(self):
        """Test AnswerQuestionAction initialization."""
        from actions.answer_question import AnswerQuestionAction

        services = {'firestore': Mock(), 'gemini': Mock()}
        action = AnswerQuestionAction(services)

        assert action.services == services
        assert action.name == 'ANSWER_QUESTION'

    def test_execute_with_question_parameter(self):
        """Test execute with question in parameters."""
        from actions.answer_question import AnswerQuestionAction

        mock_services = {'firestore': Mock(), 'gemini': Mock()}

        # Patch at the location where it's imported in the action module
        with patch('actions.answer_question.QuestionService') as MockQuestionService:
            mock_qs = MockQuestionService.return_value
            mock_qs.answer.return_value = {
                'answer': 'Test answer',
                'sources_used': ['relationships'],
                'classification': {'type': 'company'},
                'data_found': {'relationship': True}
            }

            action = AnswerQuestionAction(mock_services)
            result = action.execute({'question': 'What do we know about Stripe?'})

            assert result['success'] is True
            assert result['answer'] == 'Test answer'
            assert 'relationships' in result['sources_used']

    def test_execute_with_email_body_fallback(self):
        """Test execute falls back to email body when no question parameter."""
        from actions.answer_question import AnswerQuestionAction

        mock_services = {'firestore': Mock(), 'gemini': Mock()}

        # Patch at the location where it's imported in the action module
        with patch('actions.answer_question.QuestionService') as MockQuestionService:
            mock_qs = MockQuestionService.return_value
            mock_qs.answer.return_value = {
                'answer': 'Test answer',
                'sources_used': [],
                'classification': {'type': 'general'},
                'data_found': {}
            }

            action = AnswerQuestionAction(mock_services)
            email_data = {
                'from': 'test@example.com',
                'subject': 'Question',
                'body': 'What is happening with Acme?'
            }
            result = action.execute({}, email_data)

            assert result['success'] is True
            mock_qs.answer.assert_called_once()
            # The question should include subject and body
            call_args = mock_qs.answer.call_args[0][0]
            assert 'Acme' in call_args

    def test_execute_no_question(self):
        """Test execute with no question returns error."""
        from actions.answer_question import AnswerQuestionAction

        action = AnswerQuestionAction({})
        result = action.execute({})

        assert result['success'] is False
        assert 'No question' in result['error']

    def test_format_response_success(self):
        """Test format_response with successful result."""
        from actions.answer_question import AnswerQuestionAction

        action = AnswerQuestionAction({})
        result = {
            'success': True,
            'answer': 'Here is what I found about Stripe.',
            'sources_used': ['relationships', 'email_research'],
            'data_found': {'relationship': True, 'emails': 5}
        }

        response = action.format_response(result)

        assert 'Here is what I found about Stripe' in response
        assert 'Sources:' in response
        assert 'relationship history' in response
        assert 'inbox (5 emails)' in response

    def test_format_response_error(self):
        """Test format_response with error result."""
        from actions.answer_question import AnswerQuestionAction

        action = AnswerQuestionAction({})
        result = {
            'success': False,
            'error': 'Something went wrong'
        }

        response = action.format_response(result)

        assert "couldn't answer" in response.lower()
        assert 'Something went wrong' in response


class TestQuestionService:
    """Tests for QuestionService class."""

    @patch('services.question.vertexai')
    @patch('services.question.GenerativeModel')
    def test_initialization(self, mock_model, mock_vertexai):
        """Test QuestionService initialization."""
        from services.question import QuestionService

        mock_firestore = Mock()
        services = {'firestore': mock_firestore}

        qs = QuestionService(services)

        assert qs.firestore == mock_firestore
        mock_vertexai.init.assert_called_once()

    @patch('services.question.vertexai')
    @patch('services.question.GenerativeModel')
    def test_classify_question_company(self, mock_model_class, mock_vertexai):
        """Test question classification for company questions."""
        from services.question import QuestionService

        mock_model = Mock()
        mock_model_class.return_value = mock_model
        mock_model.generate_content.return_value = Mock(
            text='{"type": "company", "entities": {"company": "Stripe", "domain": "stripe.com"}, "intent": "Know about Stripe"}'
        )

        qs = QuestionService({})
        classification = qs._classify_question("What do we know about Stripe?")

        assert classification['type'] == 'company'
        assert classification['entities']['company'] == 'Stripe'

    @patch('services.question.vertexai')
    @patch('services.question.GenerativeModel')
    def test_classify_question_person(self, mock_model_class, mock_vertexai):
        """Test question classification for person questions."""
        from services.question import QuestionService

        mock_model = Mock()
        mock_model_class.return_value = mock_model
        mock_model.generate_content.return_value = Mock(
            text='{"type": "person", "entities": {"person": "Sarah Chen"}, "intent": "Last contact with Sarah"}'
        )

        qs = QuestionService({})
        classification = qs._classify_question("When did I last talk to Sarah Chen?")

        assert classification['type'] == 'person'
        assert classification['entities']['person'] == 'Sarah Chen'

    @patch('services.question.vertexai')
    @patch('services.question.GenerativeModel')
    def test_infer_domain_known_company(self, mock_model, mock_vertexai):
        """Test domain inference for well-known companies."""
        from services.question import QuestionService

        qs = QuestionService({})

        assert qs._infer_domain('Stripe') == 'stripe.com'
        assert qs._infer_domain('Google') == 'google.com'
        assert qs._infer_domain('OpenAI') == 'openai.com'

    @patch('services.question.vertexai')
    @patch('services.question.GenerativeModel')
    def test_infer_domain_unknown_company(self, mock_model, mock_vertexai):
        """Test domain inference for unknown companies."""
        from services.question import QuestionService

        qs = QuestionService({})

        # "Acme Corp" -> removes "Corp" suffix -> "Acme" -> "acme.com"
        assert qs._infer_domain('Acme Corp') == 'acme.com'
        # "Test Inc." -> removes "Inc." suffix -> "Test" -> "test.com"
        assert qs._infer_domain('Test Inc.') == 'test.com'
        # Simple company name without suffix
        assert qs._infer_domain('Forithmus') == 'forithmus.com'

    @patch('services.question.vertexai')
    @patch('services.question.GenerativeModel')
    def test_get_relationship_data(self, mock_model, mock_vertexai):
        """Test getting relationship data from Firestore."""
        from services.question import QuestionService

        mock_firestore = Mock()
        mock_firestore.get_relationship_data.return_value = {
            'company_name': 'Stripe',
            'summary': 'Active partnership discussions'
        }

        qs = QuestionService({'firestore': mock_firestore})
        data = qs._get_relationship_data('stripe.com')

        assert data['company_name'] == 'Stripe'
        mock_firestore.get_relationship_data.assert_called_once_with(
            domain='stripe.com',
            company_name=None
        )

    @patch('services.question.vertexai')
    @patch('services.question.GenerativeModel')
    def test_gather_data_for_company(self, mock_model_class, mock_vertexai):
        """Test gathering data for company questions."""
        from services.question import QuestionService

        mock_firestore = Mock()
        mock_firestore.get_relationship_data.return_value = {'summary': 'Test'}
        mock_firestore.get_processed.return_value = {'doc_id': 'doc123'}
        mock_firestore.db.collection.return_value.where.return_value.order_by.return_value.limit.return_value.stream.return_value = []

        qs = QuestionService({'firestore': mock_firestore})

        classification = {
            'type': 'company',
            'entities': {'company': 'Stripe', 'domain': 'stripe.com'}
        }

        data = qs._gather_data(classification, "What about Stripe?")

        assert 'relationships' in data['sources_used']
        assert 'processed_domains' in data['sources_used']


class TestActionRegistry:
    """Tests for action registry integration."""

    def test_answer_question_in_registry(self):
        """Test that ANSWER_QUESTION is in the action registry."""
        from actions import ACTION_REGISTRY, AnswerQuestionAction

        assert 'ANSWER_QUESTION' in ACTION_REGISTRY
        assert ACTION_REGISTRY['ANSWER_QUESTION'] == AnswerQuestionAction

    def test_answer_question_in_descriptions(self):
        """Test that ANSWER_QUESTION appears in action descriptions."""
        from actions import get_action_descriptions

        descriptions = get_action_descriptions()

        assert 'ANSWER_QUESTION' in descriptions
        assert 'description' in descriptions['ANSWER_QUESTION']
        assert 'question' in descriptions['ANSWER_QUESTION']['description'].lower()


class TestEmailRouterIntegration:
    """Tests for email router integration with ANSWER_QUESTION."""

    def test_router_includes_answer_question(self):
        """Test that router ACTIONS include ANSWER_QUESTION."""
        with patch('core.email_router.vertexai'):
            with patch('core.email_router.GenerativeModel'):
                from core.email_router import EmailRouter
                router = EmailRouter()

                actions = router.ACTIONS

                assert 'ANSWER_QUESTION' in actions
                assert 'description' in actions['ANSWER_QUESTION']
