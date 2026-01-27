"""Generate memos action."""
import logging
from typing import Dict, Any, Optional

from actions.base import BaseAction
from models.company import Company

logger = logging.getLogger(__name__)


class GenerateMemosAction(BaseAction):
    """Generate investment memos for companies in the sheet."""

    name = 'GENERATE_MEMOS'
    description = 'Generate investment memos for new companies in the sheet'

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        force = parameters.get('force', False)

        sheets = self.services.get('sheets')
        firestore = self.services.get('firestore')
        drive = self.services.get('drive')
        gemini = self.services.get('gemini')
        docs = self.services.get('docs')

        if not all([sheets, firestore, drive, gemini, docs]):
            return {'success': False, 'error': 'Missing required services'}

        try:
            if force:
                rows = sheets.get_all_companies()
            else:
                rows = sheets.get_rows_to_process()

            if not rows:
                return {
                    'success': True,
                    'processed': 0,
                    'skipped': 0,
                    'errors': 0,
                    'message': 'No companies to process'
                }

            results = []
            for row in rows:
                company = Company.from_sheet_row(row)
                if not company.name:
                    continue

                if force:
                    firestore.clear_processed(company.firestore_key)

                result = self._process_company(company)
                results.append(result)

            successes = sum(1 for r in results if r['status'] == 'success')
            errors = sum(1 for r in results if r['status'] == 'error')
            skipped = sum(1 for r in results if r['status'] == 'skipped')

            return {
                'success': True,
                'processed': successes,
                'skipped': skipped,
                'errors': errors,
                'results': results
            }

        except Exception as e:
            logger.error(f"Error in memo generation: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _process_company(self, company: Company) -> Dict[str, Any]:
        """Process a single company."""
        sheets = self.services['sheets']
        firestore = self.services['firestore']
        drive = self.services['drive']
        gemini = self.services['gemini']
        docs = self.services['docs']

        try:
            if firestore.is_processed(company.firestore_key):
                return {
                    'company': company.name,
                    'domain': company.domain,
                    'status': 'skipped',
                    'reason': 'already_processed'
                }

            # Create folder and document
            folder_domain = company.domain if company.domain else 'no-domain'
            folder_id = drive.create_folder(company.name, folder_domain)
            doc_id = drive.create_document(folder_id, company.name)

            # Get additional data
            yc_data = firestore.get_yc_company_data(company.name)
            relationship_data = firestore.get_relationship_data(
                domain=company.domain,
                company_name=company.name
            )

            # Research and generate memo
            research = gemini.research_company(
                company.name,
                company.domain or '',
                source=company.source or ''
            )
            research_context = gemini.format_research_context(
                research,
                yc_data=yc_data,
                relationship_data=relationship_data
            )

            memo_content = gemini.generate_memo(
                company.name,
                company.domain or 'Unknown',
                research_context=research_context
            )
            docs.insert_text(doc_id, memo_content)

            # Mark as processed
            firestore.mark_processed(
                company.firestore_key,
                company.name,
                doc_id,
                folder_id
            )

            # Update sheet status
            try:
                if company.row_number:
                    sheets.update_status(company.row_number, "Memo Created")
            except Exception:
                pass

            logger.info(f"Processed {company.name} ({company.domain or 'no domain'})")

            return {
                'company': company.name,
                'domain': company.domain,
                'status': 'success',
                'doc_id': doc_id
            }

        except Exception as e:
            logger.error(f"Error processing {company.name}: {e}", exc_info=True)
            return {
                'company': company.name,
                'domain': company.domain,
                'status': 'error',
                'error': str(e)
            }

    def format_response(self, result: Dict[str, Any]) -> str:
        if not result.get('success'):
            return f"Error generating memos: {result.get('error', 'Unknown error')}"

        processed = result.get('processed', 0)
        skipped = result.get('skipped', 0)
        errors = result.get('errors', 0)

        if processed == 0 and errors == 0:
            return "No new companies to process. All companies in the sheet have already been processed."

        details = ''
        results_list = result.get('results', [])
        if results_list:
            detail_lines = []
            for r in results_list:
                if r['status'] == 'success':
                    doc_url = f"https://docs.google.com/document/d/{r['doc_id']}/edit"
                    detail_lines.append(f"• ✓ {r['company']} ({r['domain']})\n  → {doc_url}")
                elif r['status'] == 'skipped':
                    detail_lines.append(f"• ⊘ {r['company']} - already processed")
                else:
                    detail_lines.append(f"• ✗ {r['company']} - {r.get('error', 'error')}")
            details = '\n\n**Details:**\n' + '\n'.join(detail_lines)

        return f"""Done! Here's what happened:

✓ **Processed:** {processed}
⊘ **Skipped:** {skipped}
✗ **Errors:** {errors}
{details}

Let me know if you need anything else."""
