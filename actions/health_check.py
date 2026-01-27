"""Health check action."""
from typing import Dict, Any, Optional

from actions.base import BaseAction


class HealthCheckAction(BaseAction):
    """Check if the service is running properly."""

    name = 'HEALTH_CHECK'
    description = 'Check if the service is running properly'

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return {
            'success': True,
            'status': 'healthy',
            'message': 'All systems operational'
        }

    def format_response(self, result: Dict[str, Any]) -> str:
        return "✓ **All systems operational!** The service is running properly."
