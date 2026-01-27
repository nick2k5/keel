"""Regenerate memo action."""
import logging
import re
from typing import Dict, Any, Optional

from actions.base import BaseAction

logger = logging.getLogger(__name__)


class RegenerateMemoAction(BaseAction):
    """Regenerate an investment memo for a specific company."""

    name = 'REGENERATE_MEMO'
    description = 'Regenerate an investment memo for a specific company. Use when a memo needs to be redone.'

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        identifier = parameters.get('domain', '') or parameters.get('company', '')

        if not identifier:
            return {'success': False, 'error': 'Missing domain or company name to regenerate'}

        sheets = self.services.get('sheets')
        firestore = self.services.get('firestore')
        drive = self.services.get('drive')
        gemini = self.services.get('gemini')
        docs = self.services.get('docs')

        if not all([sheets, firestore, drive, gemini, docs]):
            return {'success': False, 'error': 'Missing required services'}

        try:
            # Clean up identifier
            clean_id = identifier.lower().strip()
            clean_id = re.sub(r'^https?://', '', clean_id)
            clean_id = re.sub(r'^www\.', '', clean_id)
            clean_id = re.sub(r'/.*$', '', clean_id)

            # Find the company in the sheet
            result = sheets.service.spreadsheets().values().get(
                spreadsheetId=sheets.spreadsheet_id,
                range='Index!A:D'
            ).execute()

            values = result.get('values', [])
            company = None
            clean_domain = None
            row_number = None
            source = ''

            # Try to match by domain first
            for i, row in enumerate(values[1:], start=2):
                if len(row) > 1 and row[1].strip():
                    existing_domain = row[1].lower().strip()
                    if existing_domain == clean_id:
                        company = row[0]
                        clean_domain = existing_domain
                        row_number = i
                        source = row[3].strip() if len(row) > 3 else ''
                        break

            # Try to match by company name
            if not company:
                for i, row in enumerate(values[1:], start=2):
                    if len(row) > 0:
                        existing_name = row[0].lower().strip()
                        name_variations = [
                            clean_id,
                            clean_id.replace('.com', '').replace('.io', '').replace('.ai', '')
                        ]
                        if existing_name in name_variations:
                            company = row[0]
                            clean_domain = row[1].strip() if len(row) > 1 else ''
                            row_number = i
                            source = row[3].strip() if len(row) > 3 else ''
                            break

            if not company:
                return {
                    'success': False,
                    'error': f"Company '{identifier}' not found in the sheet"
                }

            # Clear processed record
            firestore_key = clean_domain if clean_domain else company.lower().replace(' ', '-')
            firestore.clear_processed(firestore_key)

            # Create folder and document
            folder_domain = clean_domain if clean_domain else 'no-domain'
            folder_id = drive.create_folder(company, folder_domain)
            doc_id = drive.create_document(folder_id, company)

            # Get additional data
            yc_data = firestore.get_yc_company_data(company)
            relationship_data = firestore.get_relationship_data(
                domain=clean_domain,
                company_name=company
            )

            # Research and generate memo
            research = gemini.research_company(company, clean_domain or '', source=source)
            research_context = gemini.format_research_context(
                research,
                yc_data=yc_data,
                relationship_data=relationship_data
            )

            memo_content = gemini.generate_memo(
                company,
                clean_domain or 'Unknown',
                research_context=research_context
            )
            docs.insert_text(doc_id, memo_content)

            # Mark as processed
            firestore.mark_processed(firestore_key, company, doc_id, folder_id)

            # Update sheet status
            try:
                sheets.update_status(row_number, "Memo Regenerated")
            except Exception:
                pass

            logger.info(f"Regenerated memo for {company} ({clean_domain or 'no domain'})")

            return {
                'success': True,
                'company': company,
                'domain': clean_domain,
                'doc_id': doc_id
            }

        except Exception as e:
            logger.error(f"Error regenerating memo: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def format_response(self, result: Dict[str, Any]) -> str:
        if not result.get('success'):
            return f"Failed to regenerate memo: {result.get('error', 'Unknown error')}"

        doc_url = f"https://docs.google.com/document/d/{result.get('doc_id')}/edit"
        domain_str = result.get('domain') or '(no domain)'

        return f"""✓ **Memo regenerated!**

**Company:** {result.get('company')}
**Domain:** {domain_str}

**New memo:** {doc_url}

Let me know if you need any other changes."""
