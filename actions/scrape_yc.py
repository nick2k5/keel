"""Scrape YC action."""
import logging
from typing import Dict, Any, Optional

from actions.base import BaseAction
from services.bookface import BookfaceService
from config import config

logger = logging.getLogger(__name__)


class ScrapeYCAction(BaseAction):
    """Scrape YC Bookface for companies in a batch."""

    name = 'SCRAPE_YC'
    description = 'Scrape YC Bookface for companies in a specific batch and add them to the sheet.'

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        batch = parameters.get('batch', 'W26')
        max_pages = parameters.get('pages', None)

        if not config.bookface_cookie:
            return {'success': False, 'error': 'Bookface cookie not configured'}

        try:
            if max_pages is not None:
                max_pages = min(int(max_pages), 5)  # Cap at 5 pages

            bookface = BookfaceService(config.bookface_cookie)
            result = bookface.scrape_and_add_companies(
                self.services['sheets'],
                batch,
                max_pages=max_pages,
                firestore_svc=self.services.get('firestore')
            )

            return result

        except Exception as e:
            logger.error(f"Error scraping YC batch: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def format_response(self, result: Dict[str, Any]) -> str:
        if not result.get('success'):
            return f"Failed to scrape YC: {result.get('error', 'Unknown error')}"

        batch = result.get('batch', 'W26')
        added = result.get('added', 0)
        skipped = result.get('skipped', 0)
        errors = result.get('errors', 0)

        added_companies = result.get('added_companies', [])
        if added_companies:
            companies_list = '\n'.join(f"  - {c}" for c in added_companies[:10])
            if len(added_companies) > 10:
                companies_list += f"\n  - ... and {len(added_companies) - 10} more"
        else:
            companies_list = "  (none)"

        return f"""✓ **YC {batch} companies imported!**

**Added:** {added}
**Skipped (already exists):** {skipped}
**Errors:** {errors}

**New companies:**
{companies_list}

Reply "generate memos" to create memos for the new companies."""
