"""Business logic services for processing companies."""
import logging
import json
import re
import requests
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse, parse_qs
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import firestore
import vertexai
from vertexai.generative_models import GenerativeModel
from bs4 import BeautifulSoup
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


class FirestoreService:
    """Service for Firestore idempotency tracking."""

    def __init__(self):
        self.db = firestore.Client(project=config.project_id)
        self.collection = config.firestore_collection

    @staticmethod
    def normalize_domain(domain: str) -> str:
        """Normalize domain for consistent keying."""
        return domain.lower().strip()

    def is_processed(self, domain: str) -> bool:
        """Check if a domain has already been processed."""
        normalized = self.normalize_domain(domain)
        doc_ref = self.db.collection(self.collection).document(normalized)
        doc = doc_ref.get()
        return doc.exists

    def mark_processed(self, domain: str, company: str, doc_id: str, folder_id: str):
        """Mark a domain as processed with metadata."""
        normalized = self.normalize_domain(domain)
        doc_ref = self.db.collection(self.collection).document(normalized)

        doc_ref.set({
            'domain': domain,
            'normalized_domain': normalized,
            'company': company,
            'doc_id': doc_id,
            'folder_id': folder_id,
            'processed_at': firestore.SERVER_TIMESTAMP
        })

        logger.info(f"Marked {domain} as processed in Firestore")

    def get_processed(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get processed record for a domain."""
        normalized = self.normalize_domain(domain)
        doc_ref = self.db.collection(self.collection).document(normalized)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def clear_processed(self, domain: str) -> bool:
        """Clear the processed record for a domain to allow reprocessing."""
        normalized = self.normalize_domain(domain)
        doc_ref = self.db.collection(self.collection).document(normalized)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.delete()
            logger.info(f"Cleared processed record for {domain}")
            return True
        logger.info(f"No processed record found for {domain}")
        return False

    def get_yc_company_data(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Get stored YC company data (posts, founders) for a company."""
        company_key = company_name.lower().replace(' ', '-')
        doc_ref = self.db.collection('yc_companies').document(company_key)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def get_relationship_data(self, domain: str = None, company_name: str = None) -> Optional[Dict[str, Any]]:
        """Get relationship data (emails, timeline, contacts) for a company.

        Args:
            domain: Company domain to look up
            company_name: Company name to look up (fallback if no domain)
        """
        # Try by domain first
        if domain:
            normalized = domain.lower().strip()
            doc_ref = self.db.collection('relationships').document(normalized)
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()

        # Try by company name as key
        if company_name:
            company_key = company_name.lower().replace(' ', '-')
            doc_ref = self.db.collection('relationships').document(company_key)
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()

        return None


class DriveService:
    """Service for Google Drive operations."""

    def __init__(self, credentials):
        self.service = build('drive', 'v3', credentials=credentials)
        self.parent_folder_id = config.drive_parent_folder_id

    def find_existing_folder(self, company: str, domain: str) -> Optional[str]:
        """Find an existing folder for the company in the parent folder."""
        folder_name = f"{company} ({domain})"

        try:
            # Search for folder with exact name in parent folder
            query = (
                f"name = '{folder_name}' and "
                f"'{self.parent_folder_id}' in parents and "
                f"mimeType = 'application/vnd.google-apps.folder' and "
                f"trashed = false"
            )

            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora='allDrives'
            ).execute()

            files = results.get('files', [])
            if files:
                folder_id = files[0]['id']
                logger.info(f"Found existing folder '{folder_name}' with ID: {folder_id}")
                return folder_id

            return None

        except Exception as e:
            logger.error(f"Error searching for folder: {e}", exc_info=True)
            return None

    def create_folder(self, company: str, domain: str) -> str:
        """Create a folder in the parent folder, or return existing one."""
        folder_name = f"{company} ({domain})"

        # Check for existing folder first
        existing_folder_id = self.find_existing_folder(company, domain)
        if existing_folder_id:
            return existing_folder_id

        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [self.parent_folder_id]
            }

            folder = self.service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()

            folder_id = folder.get('id')
            logger.info(f"Created folder '{folder_name}' with ID: {folder_id}")
            return folder_id

        except Exception as e:
            logger.error(f"Error creating folder for {company}: {e}", exc_info=True)
            raise

    def find_document_in_folder(self, folder_id: str, doc_name: str) -> Optional[str]:
        """Find a document by name in a folder."""
        try:
            query = f"name = '{doc_name}' and '{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false"
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()

            files = results.get('files', [])
            if files:
                doc_id = files[0]['id']
                logger.info(f"Found existing document '{doc_name}' with ID: {doc_id}")
                return doc_id
            return None

        except Exception as e:
            logger.warning(f"Error searching for document: {e}")
            return None

    def create_document(self, folder_id: str, company: str) -> str:
        """Get or create the 'Initial Brief' document in the specified folder."""
        doc_name = "Initial Brief"

        # Check for existing Initial Brief document
        existing_doc_id = self.find_document_in_folder(folder_id, doc_name)
        if existing_doc_id:
            return existing_doc_id

        try:
            file_metadata = {
                'name': doc_name,
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [folder_id]
            }

            doc = self.service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()

            doc_id = doc.get('id')
            logger.info(f"Created document '{doc_name}' with ID: {doc_id}")
            return doc_id

        except Exception as e:
            logger.error(f"Error creating document for {company}: {e}", exc_info=True)
            raise


class ResearchService:
    """Deep research service for comprehensive company investigation."""

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    # Maximum pages to crawl per domain
    MAX_DOMAIN_PAGES = 15
    # Maximum external pages to scrape from search results
    MAX_EXTERNAL_PAGES = 10
    # Request timeout
    TIMEOUT = 10

    def __init__(self):
        self.linkedin_cookie = config.linkedin_cookie
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def research_company(self, company: str, domain: str, source: str = '') -> Dict[str, Any]:
        """Perform deep research on a company."""
        logger.info(f"Starting deep research for {company} ({domain or 'no domain'}) [source: {source or 'none'}]")

        research = {
            'company': company,
            'domain': domain,
            'source': source,
            'domain_pages': {},      # All pages crawled from company domain
            'search_results': [],     # Search result snippets
            'external_content': {},   # Content scraped from external sources
            'crunchbase': {},         # Crunchbase data
            'yc_data': {},           # Y Combinator data
            'news_articles': [],      # News articles found
            'errors': []
        }

        # 1. Deep crawl the company domain
        if domain:
            try:
                research['domain_pages'] = self._crawl_domain(domain)
                logger.info(f"Crawled {len(research['domain_pages'])} pages from {domain}")
            except Exception as e:
                logger.error(f"Error crawling domain: {e}")
                research['errors'].append(f"Domain crawl failed: {str(e)}")

        # 2. Search using DuckDuckGo (free, no API key needed)
        try:
            research['search_results'] = self._deep_search(company, domain, source)
            logger.info(f"Found {len(research['search_results'])} search results")
        except Exception as e:
            logger.error(f"Error with search: {e}")
            research['errors'].append(f"Search failed: {str(e)}")

        # 3. Scrape external pages from search results
        try:
            research['external_content'] = self._scrape_external_pages(research['search_results'])
            logger.info(f"Scraped {len(research['external_content'])} external pages")
        except Exception as e:
            logger.error(f"Error scraping external pages: {e}")
            research['errors'].append(f"External scraping failed: {str(e)}")

        # 4. Try Crunchbase
        try:
            research['crunchbase'] = self._scrape_crunchbase(company, domain)
        except Exception as e:
            logger.warning(f"Crunchbase scrape failed: {e}")

        # 5. Try Y Combinator directory
        if source and source.upper().startswith(('W', 'S')):
            try:
                research['yc_data'] = self._scrape_yc_directory(company)
            except Exception as e:
                logger.warning(f"YC directory scrape failed: {e}")

        total_content = (
            len(research['domain_pages']) +
            len(research['search_results']) +
            len(research['external_content'])
        )
        logger.info(f"Research complete for {company}: {total_content} total content items")
        return research

    def _crawl_domain(self, domain: str) -> Dict[str, str]:
        """Crawl entire domain starting from homepage, following internal links."""
        base_url = f"https://{domain}"
        pages = {}
        visited = set()
        to_visit = [base_url]

        # First try to get sitemap
        sitemap_urls = self._get_sitemap_urls(domain)
        if sitemap_urls:
            to_visit.extend(sitemap_urls[:20])  # Add up to 20 sitemap URLs
            logger.info(f"Found {len(sitemap_urls)} URLs in sitemap")

        # Also add common important paths
        important_paths = [
            '/', '/about', '/about-us', '/team', '/company', '/product', '/products',
            '/features', '/pricing', '/blog', '/news', '/press', '/careers',
            '/contact', '/faq', '/help', '/founders', '/leadership', '/story',
            '/mission', '/vision', '/customers', '/case-studies', '/solutions'
        ]
        for path in important_paths:
            to_visit.append(urljoin(base_url, path))

        while to_visit and len(pages) < self.MAX_DOMAIN_PAGES:
            url = to_visit.pop(0)

            # Normalize URL
            parsed = urlparse(url)
            if parsed.netloc and parsed.netloc != domain and not parsed.netloc.endswith('.' + domain):
                continue  # Skip external links
            normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')

            if normalized_url in visited:
                continue
            visited.add(normalized_url)

            try:
                resp = self.session.get(url, timeout=self.TIMEOUT, allow_redirects=True)
                if resp.status_code != 200:
                    continue

                content_type = resp.headers.get('content-type', '')
                if 'text/html' not in content_type:
                    continue

                soup = BeautifulSoup(resp.text, 'lxml')

                # Extract page title
                title = ''
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text(strip=True)

                # Extract meta description
                meta_desc = ''
                meta_tag = soup.find('meta', attrs={'name': 'description'})
                if meta_tag:
                    meta_desc = meta_tag.get('content', '')

                # Remove non-content elements
                for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe']):
                    tag.decompose()

                # Extract text content
                text = self._clean_text(soup.get_text())

                if text and len(text) > 100:  # Only keep pages with substantial content
                    pages[normalized_url] = {
                        'title': title,
                        'meta_description': meta_desc,
                        'content': text[:8000]  # Limit per page
                    }

                # Find internal links to crawl
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(url, href)
                    parsed_link = urlparse(full_url)

                    # Only follow internal links
                    if parsed_link.netloc == domain or parsed_link.netloc.endswith('.' + domain) or not parsed_link.netloc:
                        clean_url = f"{parsed_link.scheme or 'https'}://{parsed_link.netloc or domain}{parsed_link.path}".rstrip('/')
                        if clean_url not in visited and clean_url not in to_visit:
                            to_visit.append(clean_url)

            except Exception as e:
                logger.debug(f"Error crawling {url}: {e}")
                continue

        return pages

    def _get_sitemap_urls(self, domain: str) -> List[str]:
        """Try to get URLs from sitemap.xml."""
        urls = []
        sitemap_locations = [
            f"https://{domain}/sitemap.xml",
            f"https://{domain}/sitemap_index.xml",
            f"https://www.{domain}/sitemap.xml",
        ]

        for sitemap_url in sitemap_locations:
            try:
                resp = self.session.get(sitemap_url, timeout=self.TIMEOUT)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml-xml')
                    for loc in soup.find_all('loc'):
                        urls.append(loc.get_text(strip=True))
                    if urls:
                        break
            except Exception:
                continue

        return urls

    def _deep_search(self, company: str, domain: str, source: str = '') -> List[Dict[str, str]]:
        """Perform deep search using Serper API (Google results)."""
        results = []

        # Check if Serper API key is configured
        if not config.serper_api_key:
            logger.warning("Serper API key not configured, skipping web search")
            return results

        # Build multiple search queries for comprehensive coverage
        queries = []

        # Basic company queries
        if domain:
            queries.extend([
                f'{company} {domain}',
                f'{company} company',
            ])
        else:
            queries.extend([
                f'{company} company startup',
                f'{company} tech company',
            ])

        # Founder/team queries
        queries.extend([
            f'{company} founders',
            f'{company} CEO founder',
            f'{company} team leadership',
        ])

        # Funding/business queries
        queries.extend([
            f'{company} funding raised',
            f'{company} series seed investors',
        ])

        # News/press queries
        queries.extend([
            f'{company} TechCrunch',
            f'{company} news announcement',
        ])

        # Source-specific queries (YC)
        if source and source.upper().startswith(('W', 'S')):
            queries.extend([
                f'{company} Y Combinator {source}',
                f'site:ycombinator.com {company}',
            ])

        # Execute searches with Serper (limit to avoid burning through quota)
        for query in queries[:8]:  # Run up to 8 different searches
            try:
                serper_results = self._serper_search(query)
                results.extend(serper_results)
            except Exception as e:
                logger.debug(f"Search error for '{query}': {e}")
                continue

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in results:
            if r['url'] not in seen_urls:
                seen_urls.add(r['url'])
                unique_results.append(r)

        return unique_results

    def _serper_search(self, query: str) -> List[Dict[str, str]]:
        """Search using Serper API (Google results)."""
        results = []

        try:
            resp = requests.post(
                'https://google.serper.dev/search',
                headers={
                    'X-API-KEY': config.serper_api_key,
                    'Content-Type': 'application/json'
                },
                json={'q': query, 'num': 10},
                timeout=self.TIMEOUT
            )

            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('organic', []):
                    results.append({
                        'title': item.get('title', ''),
                        'url': item.get('link', ''),
                        'snippet': item.get('snippet', '')
                    })

        except Exception as e:
            logger.debug(f"Serper search error: {e}")

        return results

    def _scrape_external_pages(self, search_results: List[Dict[str, str]]) -> Dict[str, str]:
        """Scrape content from external pages found in search results."""
        external_content = {}
        scraped_count = 0

        # Prioritize certain domains
        priority_domains = ['techcrunch.com', 'crunchbase.com', 'ycombinator.com', 'forbes.com',
                          'bloomberg.com', 'reuters.com', 'venturebeat.com', 'producthunt.com']

        # Sort results to prioritize important sources
        sorted_results = sorted(search_results, key=lambda r: (
            0 if any(d in r.get('url', '') for d in priority_domains) else 1
        ))

        for result in sorted_results:
            if scraped_count >= self.MAX_EXTERNAL_PAGES:
                break

            url = result.get('url', '')
            if not url or not url.startswith('http'):
                continue

            # Skip certain domains
            skip_domains = ['linkedin.com', 'facebook.com', 'twitter.com', 'instagram.com',
                           'youtube.com', 'google.com', 'bing.com', 'duckduckgo.com']
            if any(d in url for d in skip_domains):
                continue

            try:
                resp = self.session.get(url, timeout=self.TIMEOUT)
                if resp.status_code != 200:
                    continue

                content_type = resp.headers.get('content-type', '')
                if 'text/html' not in content_type:
                    continue

                soup = BeautifulSoup(resp.text, 'lxml')

                # Remove non-content elements
                for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe', 'ads']):
                    tag.decompose()

                # Try to find article/main content
                article = soup.find('article') or soup.find('main') or soup.find(class_=re.compile(r'article|content|post'))
                if article:
                    text = self._clean_text(article.get_text())
                else:
                    text = self._clean_text(soup.get_text())

                if text and len(text) > 200:
                    external_content[url] = {
                        'title': result.get('title', ''),
                        'content': text[:5000]
                    }
                    scraped_count += 1

            except Exception as e:
                logger.debug(f"Error scraping {url}: {e}")
                continue

        return external_content

    def _scrape_crunchbase(self, company: str, domain: str) -> Dict[str, Any]:
        """Try to scrape Crunchbase for company info."""
        data = {}

        # Try company slug variations
        slugs = [
            company.lower().replace(' ', '-'),
            company.lower().replace(' ', ''),
            domain.split('.')[0] if domain else ''
        ]

        for slug in slugs:
            if not slug:
                continue
            try:
                url = f"https://www.crunchbase.com/organization/{slug}"
                resp = self.session.get(url, timeout=self.TIMEOUT)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')

                    # Extract what we can from the page
                    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                        tag.decompose()

                    text = self._clean_text(soup.get_text())
                    if text and 'crunchbase' in text.lower():
                        data = {
                            'url': url,
                            'content': text[:5000]
                        }
                        break

            except Exception:
                continue

        return data

    def _scrape_yc_directory(self, company: str) -> Dict[str, Any]:
        """Try to scrape Y Combinator directory for company info."""
        data = {}

        try:
            # Try YC company directory
            slug = company.lower().replace(' ', '-')
            url = f"https://www.ycombinator.com/companies/{slug}"
            resp = self.session.get(url, timeout=self.TIMEOUT)

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')

                for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                    tag.decompose()

                text = self._clean_text(soup.get_text())
                if text and len(text) > 200:
                    data = {
                        'url': url,
                        'content': text[:5000]
                    }

        except Exception as e:
            logger.debug(f"YC directory scrape error: {e}")

        return data

    def _clean_text(self, text: str) -> str:
        """Clean extracted text by removing excess whitespace."""
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text

    def format_research_context(self, research: Dict[str, Any], yc_data: Dict[str, Any] = None,
                                relationship_data: Dict[str, Any] = None) -> str:
        """Format research data into a comprehensive context string for the LLM.

        Args:
            research: Research data from deep web crawling
            yc_data: Optional YC company data from Bookface (posts, founders)
            relationship_data: Optional relationship data from forwarded emails (timeline, contacts, etc.)
        """
        parts = []

        domain_str = research.get('domain') or 'no website'
        source_str = research.get('source', '')

        header = f"=== COMPREHENSIVE RESEARCH DATA FOR {research['company']} ({domain_str}) ==="
        if source_str:
            header += f"\nSource: {source_str}"
            if source_str.upper().startswith(('W', 'S')) and len(source_str) <= 4:
                header += f" (Y Combinator batch)"
        parts.append(header + "\n")

        # Add relationship data from forwarded emails (highest priority - personal context)
        if relationship_data:
            parts.append("\n=== RELATIONSHIP & EMAIL HISTORY (from forwarded emails) ===")

            if relationship_data.get('introducer'):
                intro = relationship_data['introducer']
                parts.append(f"\n**Introducer:** {intro.get('name', 'Unknown')}")
                if intro.get('email'):
                    parts.append(f"  Email: {intro['email']}")
                if intro.get('context'):
                    parts.append(f"  Context: {intro['context']}")

            if relationship_data.get('contacts'):
                parts.append("\n**Key Contacts:**")
                for contact in relationship_data['contacts']:
                    contact_info = f"- {contact.get('name', 'Unknown')}"
                    if contact.get('email'):
                        contact_info += f" ({contact['email']})"
                    if contact.get('role'):
                        contact_info += f" - {contact['role']}"
                    parts.append(contact_info)

            if relationship_data.get('summary'):
                parts.append(f"\n**Relationship Summary:**\n{relationship_data['summary']}")

            if relationship_data.get('timeline'):
                parts.append("\n**Communication Timeline:**")
                for event in relationship_data['timeline'][:10]:  # Limit to 10 events
                    parts.append(f"- [{event.get('date', 'Unknown date')}] {event.get('event', '')}")

            if relationship_data.get('key_topics'):
                parts.append(f"\n**Key Topics Discussed:** {', '.join(relationship_data['key_topics'])}")

            if relationship_data.get('next_steps'):
                parts.append(f"\n**Next Steps:** {relationship_data['next_steps']}")

            # Include raw email content if available (very valuable context)
            if relationship_data.get('raw_messages'):
                parts.append("\n**Email Thread Content:**")
                for i, msg in enumerate(relationship_data['raw_messages'][:5]):  # Limit to 5 messages
                    parts.append(f"\n--- Email {i+1} ---")
                    if msg.get('from'):
                        parts.append(f"From: {msg['from']}")
                    if msg.get('date'):
                        parts.append(f"Date: {msg['date']}")
                    if msg.get('subject'):
                        parts.append(f"Subject: {msg['subject']}")
                    if msg.get('body'):
                        parts.append(msg['body'][:2000])

        # Add YC Bookface data if available (high quality founder-written content)
        if yc_data:
            if yc_data.get('founders'):
                parts.append("\n=== YC FOUNDERS (from Bookface) ===")
                for founder in yc_data['founders']:
                    founder_info = f"- {founder.get('name', 'Unknown')}"
                    if founder.get('email'):
                        founder_info += f" ({founder['email']})"
                    parts.append(founder_info)

            if yc_data.get('posts'):
                parts.append("\n=== YC BOOKFACE POSTS (founder-written content) ===")
                for i, post in enumerate(yc_data['posts'][:5]):
                    if post.get('title'):
                        parts.append(f"\n**Post {i+1}: {post['title']}**")
                    if post.get('author'):
                        parts.append(f"Author: {post['author']}")
                    if post.get('body'):
                        parts.append(post['body'][:2000])

        # Domain pages (crawled from company website)
        domain_pages = research.get('domain_pages', {})
        if domain_pages:
            parts.append(f"\n=== COMPANY WEBSITE CONTENT ({len(domain_pages)} pages crawled) ===")
            for url, page_data in list(domain_pages.items())[:10]:  # Limit to 10 pages in context
                parts.append(f"\n--- Page: {url} ---")
                if page_data.get('title'):
                    parts.append(f"Title: {page_data['title']}")
                if page_data.get('meta_description'):
                    parts.append(f"Description: {page_data['meta_description']}")
                if page_data.get('content'):
                    parts.append(page_data['content'][:3000])

        # Search results summaries
        search_results = research.get('search_results', [])
        if search_results:
            parts.append(f"\n=== SEARCH RESULTS ({len(search_results)} found) ===")
            for r in search_results[:15]:
                snippet = r.get('snippet', '')[:300]
                parts.append(f"- [{r.get('title', 'No title')}]({r.get('url', '')}): {snippet}")

        # External content (scraped from search result pages)
        external_content = research.get('external_content', {})
        if external_content:
            parts.append(f"\n=== EXTERNAL SOURCES ({len(external_content)} pages scraped) ===")
            for url, content_data in list(external_content.items())[:8]:
                parts.append(f"\n--- Source: {url} ---")
                if content_data.get('title'):
                    parts.append(f"Title: {content_data['title']}")
                if content_data.get('content'):
                    parts.append(content_data['content'][:3000])

        # Crunchbase data
        crunchbase = research.get('crunchbase', {})
        if crunchbase and crunchbase.get('content'):
            parts.append("\n=== CRUNCHBASE DATA ===")
            parts.append(crunchbase['content'][:4000])

        # YC Directory data
        yc_directory = research.get('yc_data', {})
        if yc_directory and yc_directory.get('content'):
            parts.append("\n=== Y COMBINATOR DIRECTORY ===")
            parts.append(yc_directory['content'][:4000])

        # Summary stats
        total_pages = len(domain_pages) + len(external_content)
        total_results = len(search_results)
        parts.append(f"\n=== RESEARCH SUMMARY ===")
        parts.append(f"Total pages crawled: {total_pages}")
        parts.append(f"Search results found: {total_results}")

        if research.get('errors'):
            parts.append(f"\nResearch errors: {'; '.join(research['errors'])}")

        return '\n'.join(parts)


class BookfaceService:
    """Service for scraping YC Bookface for batch companies."""

    BASE_FEED_URL = 'https://bookface.ycombinator.com/feed-v2.json'
    DEFAULT_PARAMS = 'feed=recent&filter_posts=false&omit_channels=false&comment_post_score_mode=off'

    # Rate limiting and pagination settings
    MAX_PAGES = 3  # Maximum pages to fetch per scrape
    RATE_LIMIT_SECONDS = 2  # Seconds to wait between requests

    def __init__(self, cookie: str):
        """Initialize with Bookface session cookie."""
        self.cookie = cookie

    def fetch_feed_page(self, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Fetch a single page of the Bookface feed.

        Args:
            cursor: Pagination cursor for next page (None for first page)

        Returns:
            Feed JSON response
        """
        import urllib.request
        import time

        url = f"{self.BASE_FEED_URL}?{self.DEFAULT_PARAMS}"
        if cursor:
            url += f"&cursor={cursor}"

        req = urllib.request.Request(url)
        req.add_header('accept', 'application/json')
        req.add_header('content-type', 'application/json')
        req.add_header('cookie', self.cookie)
        req.add_header('user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"Error fetching Bookface feed: {e}")
            raise

    def extract_batch_companies(self, batch: str = 'W26', max_pages: int = None) -> List[Dict[str, str]]:
        """Extract companies from a specific YC batch, paginating through the feed.

        Args:
            batch: The batch identifier, e.g., 'W26', 'S25'
            max_pages: Maximum pages to fetch (defaults to MAX_PAGES)

        Returns:
            List of dicts with 'id', 'name', and 'batch' keys
        """
        import time

        if max_pages is None:
            max_pages = self.MAX_PAGES

        companies = {}  # Use dict to deduplicate by company ID
        cursor = None
        pages_fetched = 0

        while pages_fetched < max_pages:
            # Rate limiting - wait before fetching (except for first page)
            if pages_fetched > 0:
                logger.info(f"Rate limiting: waiting {self.RATE_LIMIT_SECONDS}s before next request")
                time.sleep(self.RATE_LIMIT_SECONDS)

            logger.info(f"Fetching page {pages_fetched + 1}/{max_pages}" +
                       (f" (cursor: {cursor[:20]}...)" if cursor else ""))

            feed = self.fetch_feed_page(cursor)
            posts = feed.get('posts', [])

            if not posts:
                logger.info("No more posts, stopping pagination")
                break

            # Extract companies from this page
            for post in posts:
                user = post.get('user', {})
                user_companies = user.get('companies', [])
                post_body = post.get('body', '') or post.get('body_v2', '')
                post_title = post.get('title', '')

                for company in user_companies:
                    company_batch = company.get('batch', '')
                    if company_batch == batch:
                        company_id = company.get('id')
                        if company_id and company_id not in companies:
                            companies[company_id] = {
                                'id': company_id,
                                'name': company.get('name', ''),
                                'batch': company_batch,
                                'posts': [],
                                'founders': []
                            }

                        # Add post content to company
                        if company_id and post_body:
                            companies[company_id]['posts'].append({
                                'title': post_title,
                                'body': post_body[:5000],  # Limit size
                                'author': user.get('full_name', ''),
                                'author_email': user.get('email', '')
                            })

                        # Add founder info
                        if company_id and user.get('full_name'):
                            founder_info = {
                                'name': user.get('full_name', ''),
                                'email': user.get('email', ''),
                                'hnid': user.get('hnid', '')
                            }
                            if founder_info not in companies[company_id]['founders']:
                                companies[company_id]['founders'].append(founder_info)

            pages_fetched += 1

            # Check for next page
            cursor = feed.get('next_cursor')
            if not cursor:
                logger.info("No next_cursor, reached end of feed")
                break

        logger.info(f"Found {len(companies)} unique {batch} companies across {pages_fetched} pages")
        return list(companies.values())

    def scrape_and_add_companies(self, sheets_service, batch: str = 'W26',
                                  max_pages: int = None, firestore_svc=None) -> Dict[str, Any]:
        """Scrape Bookface for batch companies and add them to the sheet.

        Args:
            sheets_service: SheetsService instance
            batch: The batch to scrape, e.g., 'W26'
            max_pages: Maximum pages to fetch (defaults to MAX_PAGES)
            firestore_svc: FirestoreService instance (optional) to store company data

        Returns:
            Dict with results: added, skipped, errors
        """
        try:
            companies = self.extract_batch_companies(batch, max_pages=max_pages)

            results = {
                'added': [],
                'skipped': [],
                'errors': []
            }

            for company in companies:
                name = company['name']
                if not name:
                    continue

                result = sheets_service.add_company(
                    company=name,
                    domain='',  # Domain unknown from feed
                    source=batch
                )

                if result.get('success'):
                    results['added'].append(name)
                elif 'already exists' in result.get('error', ''):
                    results['skipped'].append(name)
                else:
                    results['errors'].append(f"{name}: {result.get('error')}")

                # Store company data in Firestore (posts, founders) for memo enrichment
                if firestore_svc and (company.get('posts') or company.get('founders')):
                    try:
                        self._store_yc_company_data(firestore_svc, company)
                    except Exception as e:
                        logger.warning(f"Failed to store YC data for {name}: {e}")

            logger.info(f"Bookface scrape complete: {len(results['added'])} added, "
                       f"{len(results['skipped'])} skipped, {len(results['errors'])} errors")

            return {
                'success': True,
                'batch': batch,
                'added': len(results['added']),
                'skipped': len(results['skipped']),
                'errors': len(results['errors']),
                'added_companies': results['added'],
                'error_details': results['errors']
            }

        except Exception as e:
            logger.error(f"Error in Bookface scrape: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _store_yc_company_data(self, firestore_svc, company: Dict[str, Any]):
        """Store YC company data (posts, founders) in Firestore for memo enrichment."""
        company_key = company['name'].lower().replace(' ', '-')
        doc_ref = firestore_svc.db.collection('yc_companies').document(company_key)

        # Get existing data to merge posts/founders
        existing = doc_ref.get()
        if existing.exists:
            existing_data = existing.to_dict()
            existing_posts = existing_data.get('posts', [])
            existing_founders = existing_data.get('founders', [])

            # Merge posts (avoid duplicates by title)
            existing_titles = {p.get('title') for p in existing_posts}
            for post in company.get('posts', []):
                if post.get('title') not in existing_titles:
                    existing_posts.append(post)

            # Merge founders (avoid duplicates by email)
            existing_emails = {f.get('email') for f in existing_founders}
            for founder in company.get('founders', []):
                if founder.get('email') not in existing_emails:
                    existing_founders.append(founder)

            company['posts'] = existing_posts
            company['founders'] = existing_founders

        doc_ref.set({
            'name': company['name'],
            'batch': company.get('batch', ''),
            'posts': company.get('posts', []),
            'founders': company.get('founders', []),
            'updated_at': firestore.SERVER_TIMESTAMP
        })

        logger.info(f"Stored YC data for {company['name']}: {len(company.get('posts', []))} posts, {len(company.get('founders', []))} founders")


class GeminiService:
    """Service for Google Gemini via Vertex AI."""

    def __init__(self):
        # Initialize Vertex AI
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-2.0-flash-001")

    def generate_memo(self, company: str, domain: str, research_context: str = None, custom_prompt: Optional[str] = None) -> str:
        """Generate investment memo content using Gemini. Returns markdown text."""
        if custom_prompt:
            # Substitute placeholders in custom prompt
            prompt = custom_prompt.replace('{company}', company).replace('{domain}', domain)
            logger.info(f"Using custom prompt for {company}")
        else:
            # Build context section if research data is available
            context_section = ""
            if research_context:
                context_section = f"""
IMPORTANT: Use the following research data to write an accurate memo. This is real data gathered from the company's website, Google search results, and LinkedIn. Base your analysis on this information - do not make up facts.

{research_context}

---

"""

            prompt = f"""You are a research analyst. Compile a factual research brief on the company below. Do NOT provide opinions, assessments, or recommendations. Only include verified facts.

Company: {company}
Website: {domain if domain and domain != 'Unknown' else 'Not provided'}
{context_section}
IMPORTANT: If the research data above is limited or empty, use your training knowledge about this company to fill in factual information. Many companies have public information available - use what you know. Only state "Not found" if you genuinely have no information about a topic.

Create a factual research brief with the following structure:

# {company} — Research Brief

## Company Overview
- **What they do:** Clear, factual description of the product/service
- **Website:** {domain}
- **Founded:** Year and location (only if found in research)
- **Headquarters:** Location (only if found in research)
- **Company size:** Employee count or range (only if found in research)

## Founders & Team
For each founder/key executive found in the research data:
- **[Name]** - [Title]
  - Background: [Education, previous companies, roles - only verified facts]
  - LinkedIn: [Include URL if provided in research data]

List only people confirmed in the research data. Do not invent team members.

## Product & Service
- Factual description of what the product does
- Key features mentioned on website or in articles
- Target customers/users (if stated)
- Pricing information (if publicly available)

## Traction & Metrics
Only include metrics that are explicitly stated in the research:
- User counts, customer numbers, or revenue figures
- Growth statistics
- Named customers or partnerships
- Funding raised (amount, date, investors)

If no traction data is available, state "No public traction data found."

## Online Presence & Discussion
- Social media following (if found)
- Press coverage or articles (list sources)
- Product Hunt, Reddit, Hacker News, or forum discussions
- App store ratings/reviews (if applicable)

## Background & Context
- Company history and timeline
- Notable news or announcements
- Industry or sector classification
- Any publicly stated company mission or vision

## Additional Information
- Known investors or advisors
- Notable partnerships or integrations
- Awards or recognition
- Any other relevant factual information

---

CRITICAL INSTRUCTIONS:
- Output ONLY facts. Do NOT provide opinions, analysis, or recommendations.
- Do NOT discuss market size, TAM, or growth potential.
- Do NOT assess the company's prospects or give investment advice.
- Use the research data above FIRST, then supplement with your training knowledge about the company.
- Only state "Not found" if you have NO information from either source.
- Start directly with: # {company} — Research Brief
- Include LinkedIn URLs for founders when available.
- Use markdown formatting with headers, bullet points, and bold text.
- Cite sources where helpful (e.g., "According to TechCrunch...")."""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 8192,
                    "temperature": 0.3,
                }
            )

            content = response.text.strip()
            logger.info(f"Generated memo for {company} ({len(content)} chars)")
            return content

        except Exception as e:
            logger.error(f"Error generating memo with Gemini: {e}", exc_info=True)
            raise


class DocsService:
    """Service for Google Docs operations."""

    def __init__(self, credentials):
        self.service = build('docs', 'v1', credentials=credentials)

    def insert_text(self, doc_id: str, content: str):
        """Insert markdown content into a Google Doc with proper formatting.

        Clears existing content before inserting new content.
        """
        try:
            # First, clear existing content from the document
            doc = self.service.documents().get(documentId=doc_id).execute()
            doc_content = doc.get('body', {}).get('content', [])

            # Find the end index of existing content
            end_index = 1
            for element in doc_content:
                if 'endIndex' in element:
                    end_index = max(end_index, element['endIndex'])

            # Delete existing content if there is any (leave index 1 which is required)
            if end_index > 2:
                delete_request = [{
                    'deleteContentRange': {
                        'range': {
                            'startIndex': 1,
                            'endIndex': end_index - 1
                        }
                    }
                }]
                self.service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': delete_request}
                ).execute()
                logger.info(f"Cleared existing content from document {doc_id}")

            # Parse markdown and convert to Google Docs format
            lines = content.split('\n')
            requests = []
            current_index = 1  # Google Docs index starts at 1

            # Track ranges for formatting
            heading_ranges = []  # (start, end, level)
            bold_ranges = []     # (start, end)

            # First pass: build plain text and track formatting ranges
            plain_lines = []
            for line in lines:
                original_line = line

                # Detect heading level
                heading_level = 0
                if line.startswith('# '):
                    heading_level = 1
                    line = line[2:]
                elif line.startswith('## '):
                    heading_level = 2
                    line = line[3:]
                elif line.startswith('### '):
                    heading_level = 3
                    line = line[4:]

                # Track heading range
                if heading_level > 0:
                    start = current_index
                    end = current_index + len(line)
                    heading_ranges.append((start, end, heading_level))

                # Track bold ranges (simple **text** pattern)
                line_with_bold = line
                bold_offset = 0
                for match in re.finditer(r'\*\*(.+?)\*\*', line):
                    # Adjust for removed ** markers
                    actual_start = current_index + match.start() - bold_offset
                    actual_end = actual_start + len(match.group(1))
                    bold_ranges.append((actual_start, actual_end))
                    bold_offset += 4  # Remove 4 chars (two ** on each side)

                # Remove markdown bold markers from text
                line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)

                plain_lines.append(line)
                current_index += len(line) + 1  # +1 for newline

            plain_text = '\n'.join(plain_lines)

            # Insert all text first
            requests.append({
                'insertText': {
                    'location': {'index': 1},
                    'text': plain_text
                }
            })

            # Apply heading styles (must be done after text insertion)
            for start, end, level in heading_ranges:
                heading_style = 'HEADING_1' if level == 1 else 'HEADING_2' if level == 2 else 'HEADING_3'
                requests.append({
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': start,
                            'endIndex': end
                        },
                        'paragraphStyle': {
                            'namedStyleType': heading_style
                        },
                        'fields': 'namedStyleType'
                    }
                })

            # Apply bold formatting
            for start, end in bold_ranges:
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': start,
                            'endIndex': end
                        },
                        'textStyle': {
                            'bold': True
                        },
                        'fields': 'bold'
                    }
                })

            self.service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Inserted formatted content into document {doc_id}")

        except Exception as e:
            logger.error(f"Error inserting text into document {doc_id}: {e}", exc_info=True)
            raise


class EmailAgentService:
    """Service for processing emails with AI-powered routing."""

    # Define available actions
    ACTIONS = {
        'GENERATE_MEMOS': {
            'description': 'Generate investment memos for new companies in the sheet'
        },
        'ADD_COMPANY': {
            'description': 'Add a new company to the deal flow spreadsheet. Extract company name and domain from the email.'
        },
        'UPDATE_COMPANY': {
            'description': 'Update/correct a company\'s domain or name. Use when someone provides a correction like "Domain is X" or "Actually the domain is X" or "Correct domain: X".'
        },
        'REGENERATE_MEMO': {
            'description': 'Regenerate an investment memo for a specific company. Use when a memo needs to be redone. Extract the domain OR company name from the email.'
        },
        'ANALYZE_THREAD': {
            'description': 'Analyze a forwarded email thread to create a relationship timeline and summary. Use when email contains forwarded messages (look for "Forwarded message", "From:", date patterns, or quoted content).'
        },
        'SCRAPE_YC': {
            'description': 'Scrape YC Bookface for companies in a specific batch and add them to the sheet. Default batch is W26.'
        },
        'HEALTH_CHECK': {
            'description': 'Check if the service is running properly'
        },
        'NONE': {
            'description': 'No action needed - not a valid command or unclear request'
        }
    }

    def __init__(self):
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-2.0-flash-001")

    def process_email(self, email_data: Dict[str, str], services: Dict) -> Dict[str, Any]:
        """Process an incoming email and execute the appropriate action."""
        logger.info(f"Processing email: {email_data.get('subject', 'No subject')}")

        # Get LLM decision
        decision = self._get_action_decision(email_data)
        logger.info(f"LLM decision: {decision}")

        # Execute the action
        result = self._execute_action(decision, services, email_data)

        # Format response for email reply
        response_text = self._format_response(decision, result)

        return {
            'decision': decision,
            'result': result,
            'reply_text': response_text
        }

    def _get_action_decision(self, email_data: Dict[str, str]) -> Dict[str, Any]:
        """Use Gemini to decide what action to take based on email content."""
        action_descriptions = '\n'.join(
            f"- {key}: {val['description']}"
            for key, val in self.ACTIONS.items()
        )

        prompt = f"""You are Keel, an AI assistant that processes emails and takes actions for a venture capital firm.

Available actions:
{action_descriptions}

Email:
From: {email_data.get('from', 'Unknown')}
Subject: {email_data.get('subject', 'No subject')}
Body:
{email_data.get('body', '')[:3000]}

CRITICAL: Analyze the ENTIRE email thread carefully. The email may contain:
1. Previous Keel responses (marked with ✓, **Company:**, **Domain:**, etc.)
2. User replies that CORRECT or UPDATE information
3. New commands to execute

Respond with JSON only (no markdown):
{{
  "action": "ACTION_NAME",
  "reasoning": "Brief explanation",
  "parameters": {{}},
  "also_do": null  // Optional: second action to perform after the first
}}

**HIGHEST PRIORITY - DETECTING CORRECTIONS:**
If the user provides a correction or update to information Keel previously processed, you MUST use UPDATE_COMPANY.

Correction patterns to look for:
- "Domain is https://..." or "Domain: https://..."
- "Actually the domain is..." or "Correct domain is..."
- "The website is..." or "Their site is..."
- "It should be..." or "Change it to..."
- A URL appearing right after Keel's "Company added" or "Domain:" response
- User typing a URL that differs from what Keel reported

Example correction scenario:
```
Keel: ✓ Company added! Company: HCA, Domain: hca.com
User: Domain is https://www.hcahealthcare.com/
      Generate memos
```
This should be: UPDATE_COMPANY with {{"company": "HCA", "new_domain": "hcahealthcare.com"}}, also_do: GENERATE_MEMOS

**UPDATE_COMPANY:**
- Use when correcting/updating a company's domain or name
- Parameters: {{"company": "Company Name", "new_domain": "correct.com"}}
- Can include "also_do" for a follow-up action like GENERATE_MEMOS

**ADD_COMPANY:**
- Use ONLY for adding NEW companies (not corrections)
- Parameters: {{"company": "Company Name", "domain": "example.com"}}

**GENERATE_MEMOS:**
- Use for: "run memos", "generate", "generate memos", "process"
- Parameters: {{"force": false}} (default) or {{"force": true}} for regenerating all

**REGENERATE_MEMO:**
- Use for: "regenerate memo for X", "redo X", "retry X"
- Parameters: {{"domain": "example.com"}} or {{"domain": "Company Name"}}

**ANALYZE_THREAD:**
- Use for FORWARDED email threads (look for "Forwarded message", multiple From:/Date: headers)
- No parameters needed

**SCRAPE_YC:**
- Use for: "scrape YC", "import YC batch", "get W26 companies"
- Parameters: {{"batch": "W26", "pages": 3}}

**HEALTH_CHECK:**
- Use for: "status", "health", "check"

Be helpful. When in doubt about whether something is a correction vs new addition, check if Keel previously mentioned that company in the thread."""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 500,
                    "temperature": 0.1,
                }
            )

            content = response.text.strip()
            # Clean markdown if present
            if content.startswith('```'):
                content = re.sub(r'```json?\n?', '', content)
                content = re.sub(r'```', '', content)
                content = content.strip()

            return json.loads(content)

        except Exception as e:
            logger.error(f"Error getting LLM decision: {e}", exc_info=True)
            return {
                'action': 'NONE',
                'reasoning': 'I had trouble understanding that request.',
                'parameters': {}
            }

    def _execute_action(self, decision: Dict[str, Any], services: Dict,
                        email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute the decided action."""
        action = decision.get('action', 'NONE')
        parameters = decision.get('parameters', {})
        also_do = decision.get('also_do')

        result = None

        if action == 'GENERATE_MEMOS':
            force = parameters.get('force', False)
            result = self._run_memo_generation(services, force=force)

        elif action == 'ADD_COMPANY':
            company = parameters.get('company', '')
            domain = parameters.get('domain', '')
            if not company and not domain:
                return {'success': False, 'error': 'Missing company name or domain'}
            # Allow adding company without domain (for YC companies)
            result = services['sheets'].add_company(company, domain)

        elif action == 'UPDATE_COMPANY':
            company = parameters.get('company', '')
            new_domain = parameters.get('new_domain', '') or parameters.get('domain', '')
            new_name = parameters.get('new_name', '')
            if not company:
                return {'success': False, 'error': 'Missing company name to update'}
            if not new_domain and not new_name:
                return {'success': False, 'error': 'Missing new domain or name to update'}
            result = services['sheets'].update_company(company, new_domain=new_domain, new_name=new_name)

        elif action == 'REGENERATE_MEMO':
            identifier = parameters.get('domain', '') or parameters.get('company', '')
            if not identifier:
                return {'success': False, 'error': 'Missing domain or company name to regenerate'}
            result = self._regenerate_memo(identifier, services)

        elif action == 'ANALYZE_THREAD':
            if not email_data:
                return {'success': False, 'error': 'No email data provided'}
            email_body = email_data.get('body', '')
            if not email_body:
                return {'success': False, 'error': 'No email body to analyze'}
            result = self._analyze_thread(email_body, services)

        elif action == 'SCRAPE_YC':
            batch = parameters.get('batch', 'W26')
            max_pages = parameters.get('pages', None)  # None = use default
            if max_pages is not None:
                max_pages = min(int(max_pages), 5)  # Cap at 5 pages max
            result = self._scrape_yc_batch(batch, services, max_pages=max_pages)

        elif action == 'HEALTH_CHECK':
            result = {'success': True, 'status': 'healthy', 'message': 'All systems operational'}

        else:
            return {'success': False, 'skipped': True}

        # Handle chained action (also_do)
        if also_do and result and result.get('success'):
            logger.info(f"Executing chained action: {also_do}")
            chained_decision = {'action': also_do, 'parameters': {}}

            # If we just updated a company and need to generate memo, use the updated company
            if also_do == 'GENERATE_MEMOS':
                chained_result = self._run_memo_generation(services, force=False)
            elif also_do == 'REGENERATE_MEMO' and result.get('company'):
                chained_result = self._regenerate_memo(result['company'], services)
            else:
                chained_result = self._execute_action(chained_decision, services, email_data)

            # Combine results
            result['chained_action'] = also_do
            result['chained_result'] = chained_result

        return result

    def _run_memo_generation(self, services: Dict, force: bool = False) -> Dict[str, Any]:
        """Run the memo generation process.

        Args:
            services: Dict of service instances
            force: If True, regenerate memos for ALL companies (even already processed)
        """
        try:
            sheets = services['sheets']
            firestore_svc = services['firestore']
            drive = services['drive']
            gemini = services['gemini']
            docs = services['docs']

            if force:
                # Get ALL companies from sheet (not just unprocessed)
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
                # Use company name as key if no domain
                key = row.get('domain') or row.get('company', '').lower().replace(' ', '-')
                if not key:
                    continue

                if force:
                    # Clear processed record so it will be regenerated
                    firestore_svc.clear_processed(key)
                result = self._process_single_company(row, sheets, firestore_svc, drive, gemini, docs)
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

    def _regenerate_memo(self, identifier: str, services: Dict) -> Dict[str, Any]:
        """Regenerate a memo for a specific company (by domain or company name)."""
        try:
            sheets = services['sheets']
            firestore_svc = services['firestore']
            drive = services['drive']
            gemini = services['gemini']
            docs = services['docs']

            # Clean up identifier (could be domain or company name)
            clean_id = identifier.lower().strip()
            clean_id = re.sub(r'^https?://', '', clean_id)
            clean_id = re.sub(r'^www\.', '', clean_id)
            clean_id = re.sub(r'/.*$', '', clean_id)

            # Find the company in the sheet - try by domain first, then by name
            result = sheets.service.spreadsheets().values().get(
                spreadsheetId=sheets.spreadsheet_id,
                range='Index!A:D'
            ).execute()

            values = result.get('values', [])
            company = None
            clean_domain = None
            row_number = None
            source = ''

            # First pass: try to match by domain
            for i, row in enumerate(values[1:], start=2):
                if len(row) > 1 and row[1].strip():
                    existing_domain = row[1].lower().strip()
                    if existing_domain == clean_id:
                        company = row[0]
                        clean_domain = existing_domain
                        row_number = i
                        source = row[3].strip() if len(row) > 3 else ''
                        break

            # Second pass: try to match by company name (if no domain match)
            if not company:
                for i, row in enumerate(values[1:], start=2):
                    if len(row) > 0:
                        existing_name = row[0].lower().strip()
                        if existing_name == clean_id or existing_name == clean_id.replace('.com', '').replace('.io', '').replace('.ai', ''):
                            company = row[0]
                            clean_domain = row[1].strip() if len(row) > 1 else ''
                            row_number = i
                            source = row[3].strip() if len(row) > 3 else ''
                            break

            if not company:
                return {
                    'success': False,
                    'error': f"Company '{identifier}' not found in the sheet (searched by domain and name)"
                }

            # Use company name as key if no domain
            firestore_key = clean_domain if clean_domain else company.lower().replace(' ', '-')
            folder_domain = clean_domain if clean_domain else 'no-domain'

            # Clear the processed record
            firestore_svc.clear_processed(firestore_key)

            # Create new folder and document (reuses existing folder if found)
            folder_id = drive.create_folder(company, folder_domain)
            doc_id = drive.create_document(folder_id, company)

            # Get stored YC company data if available
            yc_data = firestore_svc.get_yc_company_data(company)

            # Get relationship data from forwarded emails
            relationship_data = firestore_svc.get_relationship_data(domain=clean_domain, company_name=company)

            # Research the company (pass source for YC-enhanced search)
            research_svc = ResearchService()
            research = research_svc.research_company(company, clean_domain, source=source)
            research_context = research_svc.format_research_context(
                research, yc_data=yc_data, relationship_data=relationship_data
            )

            # Generate new memo with research context
            memo_content = gemini.generate_memo(company, clean_domain or 'Unknown', research_context=research_context)
            docs.insert_text(doc_id, memo_content)

            # Mark as processed again
            firestore_svc.mark_processed(firestore_key, company, doc_id, folder_id)

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

    def _analyze_thread(self, email_body: str, services: Dict) -> Dict[str, Any]:
        """Analyze a forwarded email thread and create/update relationship timeline."""
        try:
            sheets = services['sheets']
            firestore_svc = services['firestore']
            drive = services['drive']
            docs = services['docs']

            # Parse the email thread to extract individual messages
            new_messages = self._parse_email_thread(email_body)

            if not new_messages:
                return {
                    'success': False,
                    'error': 'Could not parse any emails from the forwarded thread'
                }

            # Extract domain from the email addresses
            domain = self._extract_domain_from_messages(new_messages)
            if not domain:
                return {
                    'success': False,
                    'error': 'Could not determine the domain from the email thread'
                }

            # Check if we have an existing relationship record
            existing = self._get_relationship(firestore_svc, domain)

            if existing:
                # Merge new messages with existing ones
                existing_messages = existing.get('raw_messages', [])
                all_messages = self._merge_messages(existing_messages, new_messages)
                doc_id = existing.get('doc_id')
                folder_id = existing.get('folder_id')
                company_name = existing.get('company_name', domain)
            else:
                all_messages = new_messages
                doc_id = None
                folder_id = None
                company_name = None

            # Use Gemini to create timeline and summary from ALL messages
            analysis = self._generate_relationship_analysis(all_messages, domain)

            if not company_name:
                company_name = analysis.get('company_name', domain)

            # Find or create the company folder
            if not folder_id:
                folder_id = drive.find_existing_folder(company_name, domain)
                if not folder_id:
                    folder_id = drive.create_folder(company_name, domain)
                    # Ensure company exists in Index sheet
                    sheets.add_company(company_name, domain)

            # Create or update the Timeline doc
            if doc_id:
                # Update existing doc by clearing and rewriting
                doc_id = self._update_timeline_doc(docs, doc_id, company_name, analysis)
            else:
                doc_id = self._create_timeline_doc(drive, docs, folder_id, company_name, analysis)

            # Store/update in Firestore
            self._store_relationship(firestore_svc, domain, all_messages, analysis, doc_id, folder_id, company_name)

            logger.info(f"Analyzed thread for domain {domain} ({len(all_messages)} total messages)")

            return {
                'success': True,
                'domain': domain,
                'company_name': company_name,
                'message_count': len(all_messages),
                'new_messages': len(new_messages),
                'updated': existing is not None,
                'doc_id': doc_id,
                'summary': analysis.get('summary', ''),
                'introducer': analysis.get('introducer', {})
            }

        except Exception as e:
            logger.error(f"Error analyzing thread: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _parse_email_thread(self, email_body: str) -> List[Dict[str, str]]:
        """Parse a forwarded email thread into individual messages."""
        messages = []

        # Common patterns for forwarded email headers
        # Pattern 1: "---------- Forwarded message ---------"
        # Pattern 2: "From: ... Date: ... Subject: ..."
        # Pattern 3: "On Mon, Jan 1, 2024 at 10:00 AM Name <email> wrote:"

        # Split by forwarded message markers
        forwarded_pattern = r'-{5,}\s*Forwarded message\s*-{5,}'
        parts = re.split(forwarded_pattern, email_body, flags=re.IGNORECASE)

        # Also try splitting by "On ... wrote:" pattern
        wrote_pattern = r'On\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^<]+<[^>]+>\s*wrote:'

        for part in parts:
            # Try to extract email metadata
            sub_messages = self._extract_messages_from_part(part)
            messages.extend(sub_messages)

        # If no messages found with standard parsing, treat as single message
        if not messages and email_body.strip():
            # Try to extract at least the from/date/subject from anywhere
            from_match = re.search(r'From:\s*([^\n]+)', email_body)
            date_match = re.search(r'Date:\s*([^\n]+)', email_body)
            subject_match = re.search(r'Subject:\s*([^\n]+)', email_body)

            messages.append({
                'from': from_match.group(1).strip() if from_match else 'Unknown',
                'date': date_match.group(1).strip() if date_match else 'Unknown',
                'subject': subject_match.group(1).strip() if subject_match else 'Unknown',
                'body': email_body.strip()
            })

        return messages

    def _extract_messages_from_part(self, text: str) -> List[Dict[str, str]]:
        """Extract individual email messages from a text block."""
        messages = []

        # Pattern for email headers block
        header_pattern = r'From:\s*([^\n]+)\n(?:.*?Date:\s*([^\n]+))?(?:.*?Subject:\s*([^\n]+))?'

        # Find all header blocks
        matches = list(re.finditer(header_pattern, text, re.DOTALL | re.IGNORECASE))

        for i, match in enumerate(matches):
            from_addr = match.group(1).strip() if match.group(1) else 'Unknown'
            date = match.group(2).strip() if match.group(2) else 'Unknown'
            subject = match.group(3).strip() if match.group(3) else 'Unknown'

            # Get body until next header or end
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()

            # Clean up body - remove quoted text markers
            body = re.sub(r'^>\s*', '', body, flags=re.MULTILINE)

            if from_addr != 'Unknown' or body:
                messages.append({
                    'from': from_addr,
                    'date': date,
                    'subject': subject,
                    'body': body[:2000]  # Limit body size
                })

        return messages

    def _extract_domain_from_messages(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """Extract the primary external domain from email messages."""
        domains = []

        for msg in messages:
            from_addr = msg.get('from', '')
            # Extract email address
            email_match = re.search(r'[\w\.-]+@([\w\.-]+)', from_addr)
            if email_match:
                domain = email_match.group(1).lower()
                # Skip common email providers and internal domains
                skip_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
                               'googlemail.com', 'icloud.com', 'me.com', 'friale.com']
                if domain not in skip_domains:
                    domains.append(domain)

        # Return most common external domain
        if domains:
            from collections import Counter
            return Counter(domains).most_common(1)[0][0]
        return None

    def _generate_relationship_analysis(self, messages: List[Dict[str, str]], domain: str) -> Dict[str, Any]:
        """Use Gemini to generate relationship timeline and summary."""
        # Format messages for the prompt
        messages_text = "\n\n---\n\n".join([
            f"From: {m['from']}\nDate: {m['date']}\nSubject: {m['subject']}\n\n{m['body']}"
            for m in messages
        ])

        prompt = f"""Analyze this email thread with {domain} and create a relationship summary.

EMAIL THREAD:
{messages_text[:15000]}

Create a JSON response with:
{{
  "company_name": "The company name (infer from domain or emails)",
  "introducer": {{
    "name": "Name of person who made the introduction (if identifiable)",
    "email": "Their email address",
    "context": "How/why they made the introduction (e.g., 'Mutual connection from Stanford', 'Met at TechCrunch Disrupt')"
  }},
  "contacts": [
    {{"name": "Person Name", "email": "email@domain.com", "role": "Their role if mentioned"}}
  ],
  "timeline": [
    {{"date": "YYYY-MM-DD or approximate", "event": "Brief description of what happened"}}
  ],
  "summary": "2-3 paragraph summary of the relationship: how it started, key discussions, current status",
  "key_topics": ["topic1", "topic2"],
  "sentiment": "positive/neutral/negative",
  "next_steps": "Any obvious next steps or follow-ups needed"
}}

IMPORTANT for introducer:
- Look for the FIRST email in the thread - often the introduction
- Look for phrases like "introducing you to", "wanted to connect you with", "meet [name]", "I'd like you to meet"
- The introducer is usually CC'd or is the sender of the first email if it's an intro
- If no clear introducer, set introducer to null

Be thorough in extracting the timeline. Include ALL significant touchpoints.
Sort timeline chronologically (oldest first).
Respond with JSON only, no markdown."""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 4000,
                    "temperature": 0.2,
                }
            )

            content = response.text.strip()
            # Clean markdown if present
            if content.startswith('```'):
                content = re.sub(r'```json?\n?', '', content)
                content = re.sub(r'```', '', content)
                content = content.strip()

            return json.loads(content)

        except Exception as e:
            logger.error(f"Error generating relationship analysis: {e}")
            return {
                'company_name': domain,
                'contacts': [],
                'timeline': [],
                'summary': f'Error analyzing thread: {str(e)}',
                'key_topics': [],
                'sentiment': 'neutral',
                'next_steps': ''
            }

    def _get_relationship(self, firestore_svc, domain: str) -> Optional[Dict[str, Any]]:
        """Get existing relationship data from Firestore."""
        normalized = domain.lower().strip()
        doc_ref = firestore_svc.db.collection('relationships').document(normalized)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def _merge_messages(self, existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """Merge new messages with existing ones, avoiding duplicates."""
        # Create a set of existing message signatures for deduplication
        existing_sigs = set()
        for msg in existing:
            sig = f"{msg.get('from', '')}|{msg.get('date', '')}|{msg.get('subject', '')}"
            existing_sigs.add(sig)

        merged = list(existing)
        for msg in new:
            sig = f"{msg.get('from', '')}|{msg.get('date', '')}|{msg.get('subject', '')}"
            if sig not in existing_sigs:
                merged.append(msg)
                existing_sigs.add(sig)

        return merged

    def _format_timeline_content(self, company_name: str, analysis: Dict[str, Any]) -> str:
        """Format the timeline document content."""
        # Introduction section
        introducer = analysis.get('introducer') or {}
        if introducer and introducer.get('name'):
            intro_text = f"**{introducer.get('name', 'Unknown')}**"
            if introducer.get('email'):
                intro_text += f" ({introducer.get('email')})"
            if introducer.get('context'):
                intro_text += f"\n{introducer.get('context')}"
        else:
            intro_text = "No introducer identified"

        # Contacts section
        contacts_text = "\n".join([
            f"- **{c.get('name', 'Unknown')}** ({c.get('email', '')}) - {c.get('role', 'Unknown role')}"
            for c in analysis.get('contacts', [])
        ]) or "No contacts identified"

        # Timeline section
        timeline_text = "\n".join([
            f"- **{t.get('date', 'Unknown date')}**: {t.get('event', '')}"
            for t in analysis.get('timeline', [])
        ]) or "No timeline events identified"

        # Topics section
        topics_text = ", ".join(analysis.get('key_topics', [])) or "None identified"

        content = f"""# Timeline: {company_name}

## Introduction
{intro_text}

## Contacts
{contacts_text}

## Summary
{analysis.get('summary', 'No summary available')}

## Timeline
{timeline_text}

## Key Topics
{topics_text}

## Sentiment
{analysis.get('sentiment', 'neutral').title()}

## Next Steps
{analysis.get('next_steps', 'None identified')}
"""
        return content

    def _create_timeline_doc(self, drive, docs, folder_id: str, company_name: str,
                            analysis: Dict[str, Any]) -> str:
        """Create a new Timeline doc in the company folder."""
        # Create document in the company folder
        doc_metadata = drive.service.files().create(
            body={
                'name': 'Timeline',
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [folder_id]
            },
            supportsAllDrives=True,
            fields='id'
        ).execute()

        doc_id = doc_metadata['id']
        content = self._format_timeline_content(company_name, analysis)
        docs.insert_text(doc_id, content)

        logger.info(f"Created Timeline doc {doc_id} in folder {folder_id}")
        return doc_id

    def _update_timeline_doc(self, docs, doc_id: str, company_name: str,
                            analysis: Dict[str, Any]) -> str:
        """Update an existing Timeline doc by clearing and rewriting content."""
        try:
            # Get the document to find current content length
            doc = docs.service.documents().get(documentId=doc_id).execute()
            content_end = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)

            # Delete all content (except the implicit newline at index 1)
            if content_end > 2:
                requests = [{
                    'deleteContentRange': {
                        'range': {
                            'startIndex': 1,
                            'endIndex': content_end - 1
                        }
                    }
                }]
                docs.service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': requests}
                ).execute()

            # Insert new content
            content = self._format_timeline_content(company_name, analysis)
            docs.insert_text(doc_id, content)

            logger.info(f"Updated Timeline doc {doc_id}")
            return doc_id

        except Exception as e:
            logger.error(f"Error updating timeline doc: {e}", exc_info=True)
            raise

    def _store_relationship(self, firestore_svc, domain: str, messages: List[Dict],
                           analysis: Dict[str, Any], doc_id: str, folder_id: str,
                           company_name: str):
        """Store relationship data in Firestore."""
        normalized = domain.lower().strip()
        doc_ref = firestore_svc.db.collection('relationships').document(normalized)

        doc_ref.set({
            'domain': domain,
            'company_name': company_name,
            'folder_id': folder_id,
            'doc_id': doc_id,
            'introducer': analysis.get('introducer'),
            'contacts': analysis.get('contacts', []),
            'timeline': analysis.get('timeline', []),
            'summary': analysis.get('summary', ''),
            'key_topics': analysis.get('key_topics', []),
            'sentiment': analysis.get('sentiment', 'neutral'),
            'next_steps': analysis.get('next_steps', ''),
            'message_count': len(messages),
            'raw_messages': messages,  # Store raw messages for merging later
            'analyzed_at': firestore.SERVER_TIMESTAMP
        })

        logger.info(f"Stored relationship data for {domain}")

    def _scrape_yc_batch(self, batch: str, services: Dict, max_pages: int = None) -> Dict[str, Any]:
        """Scrape YC Bookface for companies in a batch and add to sheet."""
        try:
            if not config.bookface_cookie:
                return {'success': False, 'error': 'Bookface cookie not configured'}

            bookface = BookfaceService(config.bookface_cookie)
            return bookface.scrape_and_add_companies(
                services['sheets'],
                batch,
                max_pages=max_pages,
                firestore_svc=services.get('firestore')
            )

        except Exception as e:
            logger.error(f"Error scraping YC batch: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _process_single_company(self, row: Dict, sheets, firestore_svc, drive, gemini, docs) -> Dict:
        """Process a single company row."""
        company = row['company']
        domain = row.get('domain', '')
        row_number = row['row_number']
        source = row.get('source', '')  # e.g., 'W26' for YC batch

        # Use company name as key if no domain
        firestore_key = domain if domain else company.lower().replace(' ', '-')

        try:
            if firestore_svc.is_processed(firestore_key):
                return {'company': company, 'domain': domain, 'status': 'skipped', 'reason': 'already_processed'}

            # Create folder - use company name if no domain
            folder_name_domain = domain if domain else 'no-domain'
            folder_id = drive.create_folder(company, folder_name_domain)
            doc_id = drive.create_document(folder_id, company)

            # Get stored YC company data if available (from Bookface scraping)
            yc_data = firestore_svc.get_yc_company_data(company)

            # Get relationship data from forwarded emails
            relationship_data = firestore_svc.get_relationship_data(domain=domain, company_name=company)

            # Research the company - pass source for YC-enhanced search
            research_svc = ResearchService()
            research = research_svc.research_company(company, domain, source=source)
            research_context = research_svc.format_research_context(
                research, yc_data=yc_data, relationship_data=relationship_data
            )

            # Generate memo with research context
            memo_content = gemini.generate_memo(company, domain or 'Unknown', research_context=research_context)
            docs.insert_text(doc_id, memo_content)
            firestore_svc.mark_processed(firestore_key, company, doc_id, folder_id)

            try:
                sheets.update_status(row_number, "Memo Created")
            except Exception:
                pass

            return {'company': company, 'domain': domain, 'status': 'success', 'doc_id': doc_id}

        except Exception as e:
            logger.error(f"Error processing {company}: {e}", exc_info=True)
            return {'company': company, 'domain': domain, 'status': 'error', 'error': str(e)}

    def _format_response(self, decision: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Format the response text for email reply."""
        action = decision.get('action', 'NONE')

        # Check for explicit boolean True (not truthy numbers like skipped count)
        if result.get('skipped') is True:
            actions_list = '\n'.join(
                f"• {val['description']}"
                for key, val in self.ACTIONS.items()
                if key != 'NONE'
            )
            return f"""I received your email but couldn't identify a specific action to take.

**My interpretation:** {decision.get('reasoning', 'Unknown')}

**Available commands:**
{actions_list}

Just reply with what you'd like me to do."""

        if not result.get('success'):
            return f"""I tried to run **{action}** but encountered an error:

```
{result.get('error', 'Unknown error')}
```

You might want to check the logs or try again."""

        # Success responses
        if action == 'ADD_COMPANY':
            return f"""✓ **Company added to deal flow!**

**Company:** {result.get('company')}
**Domain:** {result.get('domain') or '(none)'}

The memo will be generated on the next run. Reply "generate memos" to process it now."""

        elif action == 'UPDATE_COMPANY':
            updates_list = result.get('updates', [])
            updates_str = '\n'.join(f"  - {u}" for u in updates_list) if updates_list else "  - No changes needed"

            response = f"""✓ **Company updated!**

**Company:** {result.get('company')}
**Changes:**
{updates_str}"""

            # If there was a chained action, append its result
            chained_result = result.get('chained_result')
            if chained_result:
                chained_action = result.get('chained_action', '')
                if chained_action == 'GENERATE_MEMOS' and chained_result.get('success'):
                    processed = chained_result.get('processed', 0)
                    if processed > 0:
                        response += f"\n\n✓ **Also processed {processed} memo(s)!**"
                        if chained_result.get('results'):
                            for r in chained_result['results']:
                                if r.get('status') == 'success':
                                    doc_url = f"https://docs.google.com/document/d/{r['doc_id']}/edit"
                                    response += f"\n  → {r['company']}: {doc_url}"
                elif chained_action == 'REGENERATE_MEMO' and chained_result.get('success'):
                    doc_url = f"https://docs.google.com/document/d/{chained_result.get('doc_id')}/edit"
                    response += f"\n\n✓ **Memo regenerated:** {doc_url}"

            return response

        elif action == 'GENERATE_MEMOS':
            if result.get('processed', 0) == 0 and result.get('errors', 0) == 0:
                return "No new companies to process. All companies in the sheet have already been processed."

            details = ''
            if result.get('results'):
                detail_lines = []
                for r in result['results']:
                    if r['status'] == 'success':
                        doc_url = f"https://docs.google.com/document/d/{r['doc_id']}/edit"
                        detail_lines.append(f"• ✓ {r['company']} ({r['domain']})\n  → {doc_url}")
                    elif r['status'] == 'skipped':
                        detail_lines.append(f"• ⊘ {r['company']} - already processed")
                    else:
                        detail_lines.append(f"• ✗ {r['company']} - {r.get('error', 'error')}")
                details = '\n\n**Details:**\n' + '\n'.join(detail_lines)

            return f"""Done! Here's what happened:

✓ **Processed:** {result.get('processed', 0)}
⊘ **Skipped:** {result.get('skipped', 0)}
✗ **Errors:** {result.get('errors', 0)}
{details}

Let me know if you need anything else."""

        elif action == 'REGENERATE_MEMO':
            doc_url = f"https://docs.google.com/document/d/{result.get('doc_id')}/edit"
            domain_str = result.get('domain') or '(no domain)'
            return f"""✓ **Memo regenerated!**

**Company:** {result.get('company')}
**Domain:** {domain_str}

**New memo:** {doc_url}

Let me know if you need any other changes."""

        elif action == 'ANALYZE_THREAD':
            doc_url = f"https://docs.google.com/document/d/{result.get('doc_id')}/edit"
            summary = result.get('summary', '')
            # Truncate summary for email if too long
            if len(summary) > 500:
                summary = summary[:500] + '...'

            # Check if this was an update
            updated = result.get('updated', False)
            status = "Timeline updated!" if updated else "Timeline created!"

            # Introducer info
            introducer = result.get('introducer') or {}
            intro_text = ""
            if introducer and introducer.get('name'):
                intro_text = f"\n**Introduced by:** {introducer.get('name', 'Unknown')}"
                if introducer.get('context'):
                    intro_text += f" ({introducer.get('context')})"

            # Message count info
            if updated:
                msg_info = f"**Total messages:** {result.get('message_count', 0)} (+{result.get('new_messages', 0)} new)"
            else:
                msg_info = f"**Messages analyzed:** {result.get('message_count', 0)}"

            return f"""✓ **{status}**

**Company:** {result.get('company_name', result.get('domain'))}
**Domain:** {result.get('domain')}
{msg_info}{intro_text}

**Summary:**
{summary}

**Full timeline:** {doc_url}

Forward more threads to add to this relationship history."""

        elif action == 'SCRAPE_YC':
            batch = result.get('batch', 'W26')
            added = result.get('added', 0)
            skipped = result.get('skipped', 0)
            errors = result.get('errors', 0)

            # List added companies (limit to first 10)
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

        elif action == 'HEALTH_CHECK':
            return "✓ **All systems operational!** The service is running properly."

        else:
            return f"Action **{action}** completed successfully."
