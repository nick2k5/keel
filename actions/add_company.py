"""Add company action."""
import logging
from typing import Dict, Any, Optional

from actions.base import BaseAction

logger = logging.getLogger(__name__)


class AddCompanyAction(BaseAction):
    """Add a new company to the deal flow spreadsheet."""

    name = 'ADD_COMPANY'
    description = 'Add a new company to the deal flow spreadsheet. Extract company name and domain from the email.'

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        company = parameters.get('company', '')
        domain = parameters.get('domain', '')
        source = parameters.get('source', '')

        if not company and not domain:
            return {'success': False, 'error': 'Missing company name or domain'}

        sheets = self.services.get('sheets')
        if not sheets:
            return {'success': False, 'error': 'Sheets service not available'}

        return sheets.add_company(company, domain, source)

    def format_response(self, result: Dict[str, Any]) -> str:
        if not result.get('success'):
            return f"Failed to add company: {result.get('error', 'Unknown error')}"

        domain_display = result.get('domain') or '(none)'
        return f"""✓ **Company added to deal flow!**

**Company:** {result.get('company')}
**Domain:** {domain_display}

The memo will be generated on the next run. Reply "generate memos" to process it now."""
