"""Answer question action."""
import logging
from typing import Dict, Any, Optional

from actions.base import BaseAction
from services.question import QuestionService

logger = logging.getLogger(__name__)


class AnswerQuestionAction(BaseAction):
    """Answer open-ended questions by searching inbox, Firestore, and the web."""

    name = 'ANSWER_QUESTION'
    description = 'Answer open-ended questions about people, companies, relationships, or anything else by searching inbox, Firestore, and the web'

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute the question answering action.

        Args:
            parameters: Should contain 'question' key
            email_data: Original email data (from, subject, body)

        Returns:
            Dict with 'success', 'answer', 'sources_used', 'classification'
        """
        # Extract question from parameters or fall back to email body
        question = parameters.get('question', '')

        if not question and email_data:
            # Use the email body as the question
            question = email_data.get('body', '')

            # Also check subject for context
            subject = email_data.get('subject', '')
            if subject and not subject.lower().startswith(('re:', 'fwd:')):
                question = f"{subject}: {question}"

        if not question:
            return {
                'success': False,
                'error': 'No question provided'
            }

        try:
            question_service = QuestionService(self.services)
            result = question_service.answer(question)

            return {
                'success': True,
                'question': question,
                'answer': result.get('answer', 'No answer found'),
                'sources_used': result.get('sources_used', []),
                'classification': result.get('classification', {}),
                'data_found': result.get('data_found', {})
            }

        except Exception as e:
            logger.error(f"Error answering question: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def format_response(self, result: Dict[str, Any]) -> str:
        """Format the result as a human-readable email reply.

        Args:
            result: The result dict from execute()

        Returns:
            Formatted string for email reply
        """
        if not result.get('success'):
            error = result.get('error', 'Unknown error')
            return f"I couldn't answer that question: {error}"

        answer = result.get('answer', 'No answer found')
        sources = result.get('sources_used', [])
        data_found = result.get('data_found', {})

        response_parts = [answer]

        # Add source attribution
        if sources:
            source_info = []
            if 'relationships' in sources:
                source_info.append('relationship history')
            if 'email_research' in sources:
                email_count = data_found.get('emails', 0)
                source_info.append(f'inbox ({email_count} emails)')
            if 'processed_domains' in sources:
                source_info.append('company memo')
            if 'web_search' in sources:
                source_info.append('web search')

            if source_info:
                response_parts.append(f"\n\n*Sources: {', '.join(source_info)}*")

        return '\n'.join(response_parts)
