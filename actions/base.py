"""Base action class."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseAction(ABC):
    """Base class for all email command actions."""

    # Action name (should match the key in ACTION_REGISTRY)
    name: str = 'BASE'

    # Action description for LLM routing
    description: str = 'Base action - should not be used directly'

    def __init__(self, services: Dict[str, Any]):
        """Initialize action with service dependencies.

        Args:
            services: Dict of service instances (sheets, drive, docs, etc.)
        """
        self.services = services

    @abstractmethod
    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute the action.

        Args:
            parameters: Action-specific parameters from LLM routing
            email_data: Original email data (from, subject, body) if needed

        Returns:
            Dict with 'success' bool and action-specific results
        """
        pass

    @abstractmethod
    def format_response(self, result: Dict[str, Any]) -> str:
        """Format the result as a human-readable email reply.

        Args:
            result: The result dict from execute()

        Returns:
            Formatted string for email reply
        """
        pass

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """Validate that required parameters are present.

        Args:
            parameters: Parameters to validate

        Returns:
            Error message if validation fails, None if valid
        """
        return None  # Override in subclasses if needed
