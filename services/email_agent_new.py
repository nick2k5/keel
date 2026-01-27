"""Email agent service - refactored to use actions and core modules."""
import logging
from typing import Dict, Any

from core.email_router import EmailRouter
from actions import ACTION_REGISTRY

logger = logging.getLogger(__name__)


class EmailAgentService:
    """Service for processing emails with AI-powered routing.

    This is the refactored version that delegates to action handlers.
    """

    def __init__(self, services: Dict[str, Any] = None):
        """Initialize the email agent.

        Args:
            services: Optional dict of service instances. If not provided,
                      must be passed to process_email().
        """
        self.services = services or {}
        self.router = EmailRouter()
        self._actions = {}

    def _get_action(self, action_name: str):
        """Get or create an action handler."""
        if action_name not in self._actions:
            action_class = ACTION_REGISTRY.get(action_name)
            if action_class:
                self._actions[action_name] = action_class(self.services)
        return self._actions.get(action_name)

    def process_email(self, email_data: Dict[str, str],
                      services: Dict[str, Any] = None) -> Dict[str, Any]:
        """Process an incoming email and execute the appropriate action.

        Args:
            email_data: Dict with 'from', 'subject', 'body'
            services: Optional services dict (overrides constructor services)

        Returns:
            Dict with 'decision', 'result', 'reply_text'
        """
        # Use provided services or fall back to constructor services
        if services:
            self.services = services
            self._actions = {}  # Clear cached actions to use new services

        logger.info(f"Processing email: {email_data.get('subject', 'No subject')}")

        # Get LLM decision
        decision = self.router.decide(email_data)
        logger.info(f"LLM decision: {decision}")

        # Execute the action
        action_name = decision.get('action', 'NONE')
        parameters = decision.get('parameters', {})
        also_do = decision.get('also_do')

        result = self._execute_action(action_name, parameters, email_data)

        # Handle chained action
        if also_do and result and result.get('success'):
            logger.info(f"Executing chained action: {also_do}")
            chained_result = self._execute_action(also_do, {}, email_data)
            result['chained_action'] = also_do
            result['chained_result'] = chained_result

        # Format response
        response_text = self._format_response(action_name, decision, result)

        return {
            'decision': decision,
            'result': result,
            'reply_text': response_text
        }

    def _execute_action(self, action_name: str, parameters: Dict[str, Any],
                        email_data: Dict[str, str]) -> Dict[str, Any]:
        """Execute an action by name."""
        if action_name == 'NONE':
            return {'success': False, 'skipped': True}

        action = self._get_action(action_name)
        if not action:
            logger.warning(f"Unknown action: {action_name}")
            return {'success': False, 'error': f'Unknown action: {action_name}'}

        return action.execute(parameters, email_data)

    def _format_response(self, action_name: str, decision: Dict[str, Any],
                         result: Dict[str, Any]) -> str:
        """Format the response text for email reply."""
        # Handle skipped/no-action case
        if result.get('skipped') is True:
            actions_list = '\n'.join(
                f"• {val['description']}"
                for key, val in EmailRouter.ACTIONS.items()
                if key != 'NONE'
            )
            return f"""I received your email but couldn't identify a specific action to take.

**My interpretation:** {decision.get('reasoning', 'Unknown')}

**Available commands:**
{actions_list}

Just reply with what you'd like me to do."""

        # Handle errors
        if not result.get('success'):
            return f"""I tried to run **{action_name}** but encountered an error:

```
{result.get('error', 'Unknown error')}
```

You might want to check the logs or try again."""

        # Get action handler for formatting
        action = self._get_action(action_name)
        if action:
            response = action.format_response(result)

            # Handle chained action results
            chained_result = result.get('chained_result')
            if chained_result and chained_result.get('success'):
                chained_action = result.get('chained_action')
                chained_handler = self._get_action(chained_action)
                if chained_handler:
                    chained_text = chained_handler.format_response(chained_result)
                    response += f"\n\n{chained_text}"

            return response

        return f"Action **{action_name}** completed successfully."
