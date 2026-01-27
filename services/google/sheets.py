"""Google Sheets service for spreadsheet operations."""
import logging
import re
from typing import Dict, List, Any

from googleapiclient.discovery import build
from config import config

logger = logging.getLogger(__name__)


class SheetsService:
    """Service for interacting with Google Sheets."""

    def __init__(self, credentials):
        self.service = build('sheets', 'v4', credentials=credentials)
        self.spreadsheet_id = config.spreadsheet_id

    def get_rows_to_process(self) -> List[Dict]:
        """Get rows from Index tab that need processing."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Index!A:D'
            ).execute()

            values = result.get('values', [])
            if not values:
                logger.info("No data found in spreadsheet")
                return []

            # Skip header row
            headers = values[0] if values else []
            rows_to_process = []

            for idx, row in enumerate(values[1:], start=2):
                if len(row) < 2:  # Need at least Company and Domain
                    continue

                company = row[0].strip() if len(row) > 0 else ""
                domain = row[1].strip() if len(row) > 1 else ""
                status = row[2].strip() if len(row) > 2 else ""
                source = row[3].strip() if len(row) > 3 else ""

                # Process if Status is empty or "New"
                if not status or status == "New":
                    if company and domain:
                        rows_to_process.append({
                            'row_number': idx,
                            'company': company,
                            'domain': domain,
                            'status': status,
                            'source': source
                        })

            logger.info(f"Found {len(rows_to_process)} rows to process")
            return rows_to_process

        except Exception as e:
            logger.error(f"Error reading spreadsheet: {e}", exc_info=True)
            raise

    def get_all_companies(self) -> List[Dict]:
        """Get ALL companies from Index tab (for force regeneration)."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Index!A:D'
            ).execute()

            values = result.get('values', [])
            if not values:
                logger.info("No data found in spreadsheet")
                return []

            companies = []
            for idx, row in enumerate(values[1:], start=2):
                if len(row) < 1:
                    continue

                company = row[0].strip() if len(row) > 0 else ""
                domain = row[1].strip() if len(row) > 1 else ""

                # Only include rows that have at least a company name
                if company:
                    companies.append({
                        'row_number': idx,
                        'company': company,
                        'domain': domain,
                        'status': row[2].strip() if len(row) > 2 else "",
                        'source': row[3].strip() if len(row) > 3 else ""
                    })

            logger.info(f"Found {len(companies)} total companies in sheet")
            return companies

        except Exception as e:
            logger.error(f"Error reading spreadsheet: {e}", exc_info=True)
            raise

    def update_status(self, row_number: int, status: str):
        """Update the Status column for a specific row."""
        try:
            range_name = f'Index!C{row_number}'
            body = {'values': [[status]]}

            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()

            logger.info(f"Updated row {row_number} status to '{status}'")

        except Exception as e:
            logger.error(f"Error updating status for row {row_number}: {e}", exc_info=True)
            raise

    def update_company(self, identifier: str, new_domain: str = None, new_name: str = None) -> Dict[str, Any]:
        """Update a company's domain or name in the spreadsheet.

        Args:
            identifier: Company name or domain to find
            new_domain: New domain to set (optional)
            new_name: New company name to set (optional)
        """
        try:
            # Get all companies to find the matching row
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Index!A:D'
            ).execute()

            values = result.get('values', [])
            if not values:
                return {'success': False, 'error': 'No data found in spreadsheet'}

            clean_identifier = identifier.lower().strip()
            # Also clean URL format from identifier
            clean_identifier = re.sub(r'^https?://', '', clean_identifier)
            clean_identifier = re.sub(r'^www\.', '', clean_identifier)
            clean_identifier = re.sub(r'/.*$', '', clean_identifier)

            found_row = None
            found_data = None

            for i, row in enumerate(values[1:], start=2):
                existing_company = row[0].lower().strip() if len(row) > 0 else ''
                existing_domain = row[1].lower().strip() if len(row) > 1 else ''

                # Match by company name or domain
                if clean_identifier == existing_company or clean_identifier == existing_domain:
                    found_row = i
                    found_data = {
                        'company': row[0] if len(row) > 0 else '',
                        'domain': row[1] if len(row) > 1 else '',
                        'status': row[2] if len(row) > 2 else '',
                        'source': row[3] if len(row) > 3 else ''
                    }
                    break

            if not found_row:
                return {'success': False, 'error': f"Company '{identifier}' not found in spreadsheet"}

            # Clean the new domain if provided
            clean_new_domain = ''
            if new_domain:
                clean_new_domain = new_domain.lower().strip()
                clean_new_domain = re.sub(r'^https?://', '', clean_new_domain)
                clean_new_domain = re.sub(r'^www\.', '', clean_new_domain)
                clean_new_domain = re.sub(r'/.*$', '', clean_new_domain)

            updates = []

            # Update domain (column B)
            if new_domain and clean_new_domain != found_data['domain']:
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f'Index!B{found_row}',
                    valueInputOption='RAW',
                    body={'values': [[clean_new_domain]]}
                ).execute()
                updates.append(f"domain: {found_data['domain']} → {clean_new_domain}")

            # Update company name (column A)
            if new_name and new_name.strip().lower() != found_data['company'].lower():
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f'Index!A{found_row}',
                    valueInputOption='RAW',
                    body={'values': [[new_name.strip()]]}
                ).execute()
                updates.append(f"name: {found_data['company']} → {new_name.strip()}")

            # Clear the processed status so it can be reprocessed with correct domain
            if updates and found_data['status']:
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f'Index!C{found_row}',
                    valueInputOption='RAW',
                    body={'values': [['']]}
                ).execute()
                updates.append("status cleared for reprocessing")

            if not updates:
                return {
                    'success': True,
                    'company': found_data['company'],
                    'message': 'No changes needed - values are the same'
                }

            logger.info(f"Updated company {found_data['company']}: {', '.join(updates)}")

            return {
                'success': True,
                'company': found_data['company'],
                'old_domain': found_data['domain'],
                'new_domain': clean_new_domain if new_domain else found_data['domain'],
                'updates': updates,
                'row_number': found_row
            }

        except Exception as e:
            logger.error(f"Error updating company: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def add_company(self, company: str, domain: str = '', source: str = '') -> Dict[str, Any]:
        """Add a new company to the spreadsheet.

        Args:
            company: Company name
            domain: Company domain (optional)
            source: Source of the company, e.g., 'W26' for YC batch (optional)
        """
        try:
            # Clean up domain if provided
            clean_domain = ''
            if domain:
                clean_domain = domain.lower().strip()
                clean_domain = re.sub(r'^https?://', '', clean_domain)
                clean_domain = re.sub(r'^www\.', '', clean_domain)
                clean_domain = re.sub(r'/.*$', '', clean_domain)

            # Check if company/domain already exists
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Index!A:D'
            ).execute()

            values = result.get('values', [])
            clean_company = company.strip().lower()

            for i, row in enumerate(values[1:], start=2):
                existing_company = row[0].lower().strip() if len(row) > 0 else ''
                existing_domain = row[1].lower().strip() if len(row) > 1 else ''

                # Check by domain if provided, otherwise by company name
                if clean_domain and existing_domain == clean_domain:
                    return {
                        'success': False,
                        'error': f"Company with domain {clean_domain} already exists (row {i}: {row[0]})"
                    }
                if not clean_domain and existing_company == clean_company:
                    return {
                        'success': False,
                        'error': f"Company {company} already exists (row {i})"
                    }

            # Append new row with Source column
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Index!A:D',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [[company.strip(), clean_domain, '', source]]}
            ).execute()

            logger.info(f"Added company: {company} ({clean_domain or 'no domain'}) [source: {source or 'none'}]")

            return {
                'success': True,
                'company': company.strip(),
                'domain': clean_domain,
                'source': source
            }

        except Exception as e:
            logger.error(f"Error adding company: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
