"""Update company action."""
import logging
from typing import Dict, Any, Optional

from actions.base import BaseAction

logger = logging.getLogger(__name__)


class UpdateCompanyAction(BaseAction):
    """Update/correct a company's domain or name."""

    name = 'UPDATE_COMPANY'
    description = "Update/correct a company's domain or name. Use when someone provides a correction."

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        company = parameters.get('company', '')
        new_domain = parameters.get('new_domain', '') or parameters.get('domain', '')
        new_name = parameters.get('new_name', '')

        if not company:
            return {'success': False, 'error': 'Missing company name to update'}

        if not new_domain and not new_name:
            return {'success': False, 'error': 'Missing new domain or name to update'}

        sheets = self.services.get('sheets')
        if not sheets:
            return {'success': False, 'error': 'Sheets service not available'}

        return sheets.update_company(company, new_domain=new_domain, new_name=new_name)

    def format_response(self, result: Dict[str, Any]) -> str:
        if not result.get('success'):
            return f"Failed to update company: {result.get('error', 'Unknown error')}"

        updates_list = result.get('updates', [])
        updates_str = '\n'.join(f"  - {u}" for u in updates_list) if updates_list else "  - No changes needed"

        response = f"""✓ **Company updated!**

**Company:** {result.get('company')}
**Changes:**
{updates_str}"""

        return response
