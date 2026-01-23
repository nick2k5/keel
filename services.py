"""Business logic services for processing companies."""
import logging
import json
import re
import requests
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import firestore
import vertexai
from vertexai.preview.generative_models import GenerativeModel
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
                range='Index!A:C'
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

                # Process if Status is empty or "New"
                if not status or status == "New":
                    if company and domain:
                        rows_to_process.append({
                            'row_number': idx,
                            'company': company,
                            'domain': domain,
                            'status': status
                        })

            logger.info(f"Found {len(rows_to_process)} rows to process")
            return rows_to_process

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

    def add_company(self, company: str, domain: str) -> Dict[str, Any]:
        """Add a new company to the spreadsheet."""
        try:
            # Clean up domain
            clean_domain = domain.lower().strip()
            clean_domain = re.sub(r'^https?://', '', clean_domain)
            clean_domain = re.sub(r'^www\.', '', clean_domain)
            clean_domain = re.sub(r'/.*$', '', clean_domain)

            # Check if domain already exists
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Index!A:C'
            ).execute()

            values = result.get('values', [])
            for i, row in enumerate(values[1:], start=2):
                if len(row) > 1:
                    existing_domain = row[1].lower().strip()
                    if existing_domain == clean_domain:
                        return {
                            'success': False,
                            'error': f"Company with domain {clean_domain} already exists (row {i}: {row[0]})"
                        }

            # Append new row
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Index!A:C',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [[company.strip(), clean_domain, '']]}
            ).execute()

            logger.info(f"Added company: {company} ({clean_domain})")

            return {
                'success': True,
                'company': company.strip(),
                'domain': clean_domain
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

    def create_document(self, folder_id: str, company: str) -> str:
        """Create a new Google Doc in the specified folder."""
        try:
            file_metadata = {
                'name': f"{company} - Investment Memo",
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [folder_id]
            }

            doc = self.service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()

            doc_id = doc.get('id')
            logger.info(f"Created document with ID: {doc_id}")
            return doc_id

        except Exception as e:
            logger.error(f"Error creating document for {company}: {e}", exc_info=True)
            raise


class ResearchService:
    """Service for researching companies via web scraping."""

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    def __init__(self):
        self.linkedin_cookie = config.linkedin_cookie
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def research_company(self, company: str, domain: str) -> Dict[str, Any]:
        """Perform comprehensive research on a company."""
        logger.info(f"Researching {company} ({domain})")

        research = {
            'company': company,
            'domain': domain,
            'website': {},
            'google_results': [],
            'linkedin_people': [],
            'errors': []
        }

        # 1. Scrape company website
        try:
            research['website'] = self._scrape_website(domain)
        except Exception as e:
            logger.error(f"Error scraping website: {e}")
            research['errors'].append(f"Website scraping failed: {str(e)}")

        # 2. Google search for company info
        try:
            research['google_results'] = self._google_search(company, domain)
        except Exception as e:
            logger.error(f"Error with Google search: {e}")
            research['errors'].append(f"Google search failed: {str(e)}")

        # 3. LinkedIn search for founders/team
        if self.linkedin_cookie:
            try:
                research['linkedin_people'] = self._linkedin_search(company, domain)
            except Exception as e:
                logger.error(f"Error with LinkedIn search: {e}")
                research['errors'].append(f"LinkedIn search failed: {str(e)}")

        logger.info(f"Research complete for {company}: {len(research['google_results'])} Google results, {len(research['linkedin_people'])} LinkedIn profiles")
        return research

    def _scrape_website(self, domain: str) -> Dict[str, Any]:
        """Scrape the company website for key information."""
        base_url = f"https://{domain}"
        website_data = {
            'homepage': '',
            'about': '',
            'team': '',
            'meta_description': '',
            'title': ''
        }

        # Scrape homepage
        try:
            resp = self.session.get(base_url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'lxml')

            # Extract meta info
            title_tag = soup.find('title')
            website_data['title'] = title_tag.get_text(strip=True) if title_tag else ''

            meta_desc = soup.find('meta', attrs={'name': 'description'})
            website_data['meta_description'] = meta_desc.get('content', '') if meta_desc else ''

            # Extract main content (remove scripts, styles, nav, footer)
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                tag.decompose()

            website_data['homepage'] = self._clean_text(soup.get_text())[:5000]

        except Exception as e:
            logger.warning(f"Error scraping homepage: {e}")

        # Try to find and scrape about page
        about_paths = ['/about', '/about-us', '/company', '/about-us/', '/company/about']
        for path in about_paths:
            try:
                resp = self.session.get(urljoin(base_url, path), timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                        tag.decompose()
                    website_data['about'] = self._clean_text(soup.get_text())[:5000]
                    break
            except Exception:
                continue

        # Try to find and scrape team page
        team_paths = ['/team', '/about/team', '/people', '/leadership', '/our-team', '/about-us/team']
        for path in team_paths:
            try:
                resp = self.session.get(urljoin(base_url, path), timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                        tag.decompose()
                    website_data['team'] = self._clean_text(soup.get_text())[:5000]
                    break
            except Exception:
                continue

        return website_data

    def _google_search(self, company: str, domain: str) -> List[Dict[str, str]]:
        """Search Google for company information."""
        results = []

        # Search queries to try
        queries = [
            f'"{company}" {domain} company',
            f'"{company}" founders CEO',
            f'"{company}" funding raised investors',
            f'site:crunchbase.com "{company}"',
            f'site:techcrunch.com "{company}"',
        ]

        for query in queries[:3]:  # Limit to first 3 queries to avoid rate limiting
            try:
                # Use Google's public search (note: may be rate limited)
                search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
                resp = self.session.get(search_url, timeout=10)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')

                    # Extract search results
                    for g in soup.select('div.g')[:3]:  # Top 3 results per query
                        title_elem = g.select_one('h3')
                        link_elem = g.select_one('a')
                        snippet_elem = g.select_one('div[data-sncf]') or g.select_one('.VwiC3b')

                        if title_elem and link_elem:
                            results.append({
                                'title': title_elem.get_text(strip=True),
                                'url': link_elem.get('href', ''),
                                'snippet': snippet_elem.get_text(strip=True) if snippet_elem else ''
                            })

            except Exception as e:
                logger.warning(f"Google search error for '{query}': {e}")
                continue

        return results[:10]  # Return top 10 results

    def _linkedin_search(self, company: str, domain: str) -> List[Dict[str, str]]:
        """Search LinkedIn for company founders and key people."""
        if not self.linkedin_cookie:
            return []

        people = []

        # Set up LinkedIn session with cookie
        linkedin_headers = {
            **self.HEADERS,
            'Cookie': self.linkedin_cookie,
            'csrf-token': 'ajax:123456789',
        }

        try:
            # Search for people at the company
            search_url = f"https://www.linkedin.com/search/results/people/?keywords={requests.utils.quote(company)}&origin=GLOBAL_SEARCH_HEADER"

            resp = self.session.get(search_url, headers=linkedin_headers, timeout=15)

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')

                # Try to find people results
                # LinkedIn's HTML structure varies, so we try multiple selectors
                for result in soup.select('.entity-result__item, .search-result__wrapper')[:10]:
                    name_elem = result.select_one('.entity-result__title-text a, .actor-name')
                    title_elem = result.select_one('.entity-result__primary-subtitle, .subline-level-1')
                    link_elem = result.select_one('a[href*="/in/"]')

                    if name_elem:
                        person = {
                            'name': name_elem.get_text(strip=True),
                            'title': title_elem.get_text(strip=True) if title_elem else '',
                            'linkedin_url': ''
                        }

                        if link_elem:
                            href = link_elem.get('href', '')
                            if '/in/' in href:
                                # Extract clean LinkedIn URL
                                parsed = urlparse(href)
                                person['linkedin_url'] = f"https://www.linkedin.com{parsed.path.split('?')[0]}"

                        # Filter for likely founders/executives
                        title_lower = person['title'].lower()
                        if any(role in title_lower for role in ['founder', 'ceo', 'cto', 'coo', 'chief', 'co-founder', 'president', 'partner']):
                            people.append(person)

        except Exception as e:
            logger.warning(f"LinkedIn search error: {e}")

        # Also try company page
        try:
            company_slug = company.lower().replace(' ', '-').replace(',', '').replace('.', '')
            company_url = f"https://www.linkedin.com/company/{company_slug}/people/"

            resp = self.session.get(company_url, headers=linkedin_headers, timeout=15)

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')

                for result in soup.select('.org-people-profile-card')[:10]:
                    name_elem = result.select_one('.org-people-profile-card__profile-title')
                    title_elem = result.select_one('.lt-line-clamp--single-line')
                    link_elem = result.select_one('a[href*="/in/"]')

                    if name_elem:
                        person = {
                            'name': name_elem.get_text(strip=True),
                            'title': title_elem.get_text(strip=True) if title_elem else '',
                            'linkedin_url': ''
                        }

                        if link_elem:
                            href = link_elem.get('href', '')
                            if '/in/' in href:
                                parsed = urlparse(href)
                                person['linkedin_url'] = f"https://www.linkedin.com{parsed.path.split('?')[0]}"

                        if person not in people:
                            people.append(person)

        except Exception as e:
            logger.warning(f"LinkedIn company page error: {e}")

        return people

    def _clean_text(self, text: str) -> str:
        """Clean extracted text by removing excess whitespace."""
        # Replace multiple whitespace with single space
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        return text

    def format_research_context(self, research: Dict[str, Any]) -> str:
        """Format research data into a context string for the LLM."""
        parts = []

        parts.append(f"=== RESEARCH DATA FOR {research['company']} ({research['domain']}) ===\n")

        # Website data
        if research['website']:
            ws = research['website']
            if ws.get('title'):
                parts.append(f"Website Title: {ws['title']}")
            if ws.get('meta_description'):
                parts.append(f"Meta Description: {ws['meta_description']}")
            if ws.get('homepage'):
                parts.append(f"\n--- Homepage Content ---\n{ws['homepage'][:3000]}")
            if ws.get('about'):
                parts.append(f"\n--- About Page ---\n{ws['about'][:2000]}")
            if ws.get('team'):
                parts.append(f"\n--- Team Page ---\n{ws['team'][:2000]}")

        # Google results
        if research['google_results']:
            parts.append("\n--- Google Search Results ---")
            for r in research['google_results'][:5]:
                parts.append(f"- {r['title']}: {r['snippet'][:200]}")

        # LinkedIn people
        if research['linkedin_people']:
            parts.append("\n--- LinkedIn Profiles (Founders/Executives) ---")
            for p in research['linkedin_people']:
                profile_info = f"- {p['name']}"
                if p['title']:
                    profile_info += f" - {p['title']}"
                if p['linkedin_url']:
                    profile_info += f" ({p['linkedin_url']})"
                parts.append(profile_info)

        if research['errors']:
            parts.append(f"\n--- Research Errors ---\n{'; '.join(research['errors'])}")

        return '\n'.join(parts)


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

            prompt = f"""You are a senior venture capital analyst at a top-tier firm. Write a comprehensive investment memo for the company below in the style of Sequoia Capital and Chamath Palihapitiya's Social Capital memos.

Company: {company}
Website: {domain}
{context_section}
Write a detailed, analytically rigorous investment memo with the following structure:

# {company} — Investment Memo

## Investment Thesis
A compelling 2-3 sentence summary of why this company could be a category-defining investment. Be specific about the opportunity and conviction level.

## Company Overview
- **What they do:** Clear, jargon-free explanation of the product/service
- **Founded:** Year and location (if findable)
- **Stage:** Estimated company stage (Pre-seed, Seed, Series A, etc.)

## The Problem
What specific pain point does this company address? Describe:
- The customer's current frustration or unmet need
- How this problem is solved today (status quo)
- Why existing solutions fall short

## The Solution
- How the product works and why it's differentiated
- Key features and unique value proposition
- Any proprietary technology, data moats, or IP

## Why Now?
What macro trends, technological shifts, or market changes make this the right moment? Consider:
- Technology enablers (AI, cloud, mobile, etc.)
- Regulatory or behavioral shifts
- Market timing and urgency

## Market Opportunity
- **TAM (Total Addressable Market):** The entire market if they captured 100%
- **SAM (Serviceable Addressable Market):** The realistic target segment
- **SOM (Serviceable Obtainable Market):** What they can capture in 3-5 years
- Growth rate and trajectory of the market

## Competitive Landscape
| Competitor | Strengths | Weaknesses |
|------------|-----------|------------|
| [Competitor 1] | ... | ... |
| [Competitor 2] | ... | ... |

**Differentiation:** Why {company} wins against these alternatives.

## Business Model
- How they make money (SaaS, marketplace, transactional, etc.)
- Pricing strategy and unit economics (if estimable)
- Path to profitability

## Team
For each founder/key executive found in the research data:
- **[Name]** - [Title] - [Brief background and relevant experience]
  - LinkedIn: [Include LinkedIn URL if provided in research data]
- Why this team is uniquely positioned to win
- Any notable advisors or investors (if known)

IMPORTANT: If LinkedIn profiles were provided in the research data, you MUST include the LinkedIn URLs for each founder/executive.

## Traction & Metrics
What evidence exists of product-market fit?
- Users, customers, or revenue (if public)
- Growth indicators
- Notable customers or partnerships

## Risks & Concerns
Be intellectually honest about the challenges:
1. **[Risk Category]:** Description and potential mitigation
2. **[Risk Category]:** Description and potential mitigation
3. **[Risk Category]:** Description and potential mitigation

## Due Diligence Questions
Key questions to answer before investing:
- [ ] Question about team/founders
- [ ] Question about market/competition
- [ ] Question about technology/product
- [ ] Question about business model/unit economics
- [ ] Question about fundraising/runway

## Investment Recommendation
**Recommendation:** [STRONG PASS / PASS / WORTH MONITORING / MEET / STRONG CONVICTION]

Provide a clear, direct recommendation with 2-3 sentences of rationale. If recommending to meet or invest, specify what would increase conviction.

---

CRITICAL INSTRUCTIONS:
- Output ONLY the memo content. Do NOT include any preamble, introduction, or conversational text like "Okay, let's analyze..." or "Here's the memo..."
- Start directly with the memo title: # {company} — Investment Memo
- Write in a crisp, analytical VC style
- IMPORTANT: Base your analysis ONLY on the research data provided above. Do not make up facts or confuse this company with another company with a similar name.
- Include LinkedIn profile URLs for founders/executives if provided in the research data
- Be specific with data where possible
- Acknowledge uncertainty rather than fabricating details - if information is not available, say "Information not available" rather than guessing
- Use markdown formatting with headers, bullet points, bold text, and tables"""

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
        """Insert markdown content into a Google Doc with proper formatting."""
        try:
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
        'REGENERATE_MEMO': {
            'description': 'Regenerate an investment memo for a specific company. Use when a memo needs to be redone. Extract the domain from the email.'
        },
        'ANALYZE_THREAD': {
            'description': 'Analyze a forwarded email thread to create a relationship timeline and summary. Use when email contains forwarded messages (look for "Forwarded message", "From:", date patterns, or quoted content).'
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
{email_data.get('body', '')[:2000]}

Analyze this email and decide what action to take. Respond with JSON only (no markdown):
{{
  "action": "ACTION_NAME",
  "reasoning": "Brief explanation in a friendly tone",
  "parameters": {{}}
}}

IMPORTANT for ADD_COMPANY:
- If the email contains a company name and/or website URL, use ADD_COMPANY
- Extract the company name and domain from the email content
- Parameters must include: {{"company": "Company Name", "domain": "example.com"}}
- Clean the domain: remove https://, www., and any paths
- If only a URL is provided, infer the company name from the domain

Examples:
- "Add Acme Corp acme.com" → ADD_COMPANY with {{"company": "Acme Corp", "domain": "acme.com"}}
- "stripe.com" → ADD_COMPANY with {{"company": "Stripe", "domain": "stripe.com"}}
- "run memos" or "generate" → GENERATE_MEMOS
- "regenerate memo for acme.com" or "redo acme.com" → REGENERATE_MEMO with {{"domain": "acme.com"}}
- "status" or "health" → HEALTH_CHECK
- Forwarded email thread with multiple messages → ANALYZE_THREAD

IMPORTANT for REGENERATE_MEMO:
- Use when someone wants to redo/regenerate/retry a memo for a specific company
- Extract the domain from the email
- Parameters must include: {{"domain": "example.com"}}

IMPORTANT for ANALYZE_THREAD:
- Use when the email contains a FORWARDED email thread (multiple messages)
- Look for patterns like: "---------- Forwarded message ---------", "From:", "Date:", "Subject:" repeated
- Look for "On [date] [person] wrote:" patterns
- Look for the subject starting with "Fwd:" or "Fw:"
- The goal is to create a timeline and relationship summary from the email history
- No parameters needed - the entire email body will be analyzed

Be helpful and assume good intent."""

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

        if action == 'GENERATE_MEMOS':
            return self._run_memo_generation(services)

        elif action == 'ADD_COMPANY':
            company = parameters.get('company', '')
            domain = parameters.get('domain', '')
            if not company or not domain:
                return {'success': False, 'error': 'Missing company name or domain'}
            return services['sheets'].add_company(company, domain)

        elif action == 'REGENERATE_MEMO':
            domain = parameters.get('domain', '')
            if not domain:
                return {'success': False, 'error': 'Missing domain to regenerate'}
            return self._regenerate_memo(domain, services)

        elif action == 'ANALYZE_THREAD':
            if not email_data:
                return {'success': False, 'error': 'No email data provided'}
            email_body = email_data.get('body', '')
            if not email_body:
                return {'success': False, 'error': 'No email body to analyze'}
            return self._analyze_thread(email_body, services)

        elif action == 'HEALTH_CHECK':
            return {'success': True, 'status': 'healthy', 'message': 'All systems operational'}

        else:
            return {'success': False, 'skipped': True}

    def _run_memo_generation(self, services: Dict) -> Dict[str, Any]:
        """Run the memo generation process."""
        try:
            sheets = services['sheets']
            firestore_svc = services['firestore']
            drive = services['drive']
            gemini = services['gemini']
            docs = services['docs']

            rows = sheets.get_rows_to_process()

            if not rows:
                return {
                    'success': True,
                    'processed': 0,
                    'skipped': 0,
                    'errors': 0,
                    'message': 'No new companies to process'
                }

            results = []
            for row in rows:
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

    def _regenerate_memo(self, domain: str, services: Dict) -> Dict[str, Any]:
        """Regenerate a memo for a specific domain."""
        try:
            sheets = services['sheets']
            firestore_svc = services['firestore']
            drive = services['drive']
            gemini = services['gemini']
            docs = services['docs']

            # Clean up domain
            clean_domain = domain.lower().strip()
            clean_domain = re.sub(r'^https?://', '', clean_domain)
            clean_domain = re.sub(r'^www\.', '', clean_domain)
            clean_domain = re.sub(r'/.*$', '', clean_domain)

            # Find the company in the sheet
            result = sheets.service.spreadsheets().values().get(
                spreadsheetId=sheets.spreadsheet_id,
                range='Index!A:C'
            ).execute()

            values = result.get('values', [])
            company = None
            row_number = None

            for i, row in enumerate(values[1:], start=2):
                if len(row) > 1:
                    existing_domain = row[1].lower().strip()
                    if existing_domain == clean_domain:
                        company = row[0]
                        row_number = i
                        break

            if not company:
                return {
                    'success': False,
                    'error': f"Company with domain {clean_domain} not found in the sheet"
                }

            # Clear the processed record
            firestore_svc.clear_processed(clean_domain)

            # Create new folder and document (reuses existing folder if found)
            folder_id = drive.create_folder(company, clean_domain)
            doc_id = drive.create_document(folder_id, company)

            # Research the company
            research_svc = ResearchService()
            research = research_svc.research_company(company, clean_domain)
            research_context = research_svc.format_research_context(research)

            # Generate new memo with research context
            memo_content = gemini.generate_memo(company, clean_domain, research_context=research_context)
            docs.insert_text(doc_id, memo_content)

            # Mark as processed again
            firestore_svc.mark_processed(clean_domain, company, doc_id, folder_id)

            # Update sheet status
            try:
                sheets.update_status(row_number, "Memo Regenerated")
            except Exception:
                pass

            logger.info(f"Regenerated memo for {company} ({clean_domain})")

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
        """Analyze a forwarded email thread and create relationship timeline."""
        try:
            firestore_svc = services['firestore']
            drive = services['drive']
            docs = services['docs']

            # Parse the email thread to extract individual messages
            messages = self._parse_email_thread(email_body)

            if not messages:
                return {
                    'success': False,
                    'error': 'Could not parse any emails from the forwarded thread'
                }

            # Extract domain from the email addresses
            domain = self._extract_domain_from_messages(messages)
            if not domain:
                return {
                    'success': False,
                    'error': 'Could not determine the domain from the email thread'
                }

            # Use Gemini to create timeline and summary
            analysis = self._generate_relationship_analysis(messages, domain)

            # Create a Google Doc with the analysis
            folder_id = drive.parent_folder_id  # Use parent folder
            doc_id = self._create_relationship_doc(drive, docs, domain, analysis)

            # Store in Firestore under relationships collection
            self._store_relationship(firestore_svc, domain, messages, analysis, doc_id)

            logger.info(f"Analyzed thread for domain {domain}")

            return {
                'success': True,
                'domain': domain,
                'message_count': len(messages),
                'doc_id': doc_id,
                'summary': analysis.get('summary', '')
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

Be thorough in extracting the timeline. Include all significant touchpoints.
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

    def _create_relationship_doc(self, drive, docs, domain: str, analysis: Dict[str, Any]) -> str:
        """Create a Google Doc with the relationship analysis."""
        company_name = analysis.get('company_name', domain)

        # Create document
        doc_metadata = drive.service.files().create(
            body={
                'name': f"Relationship: {company_name}",
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [drive.parent_folder_id]
            },
            supportsAllDrives=True,
            fields='id'
        ).execute()

        doc_id = doc_metadata['id']

        # Format the content
        contacts_text = "\n".join([
            f"- {c.get('name', 'Unknown')} ({c.get('email', '')}) - {c.get('role', 'Unknown role')}"
            for c in analysis.get('contacts', [])
        ]) or "No contacts identified"

        timeline_text = "\n".join([
            f"- {t.get('date', 'Unknown date')}: {t.get('event', '')}"
            for t in analysis.get('timeline', [])
        ]) or "No timeline events identified"

        topics_text = ", ".join(analysis.get('key_topics', [])) or "None identified"

        content = f"""# Relationship Summary: {company_name}

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

        # Insert content
        docs.insert_text(doc_id, content)

        return doc_id

    def _store_relationship(self, firestore_svc, domain: str, messages: List[Dict],
                           analysis: Dict[str, Any], doc_id: str):
        """Store relationship data in Firestore."""
        normalized = domain.lower().strip()
        doc_ref = firestore_svc.db.collection('relationships').document(normalized)

        doc_ref.set({
            'domain': domain,
            'company_name': analysis.get('company_name', domain),
            'contacts': analysis.get('contacts', []),
            'timeline': analysis.get('timeline', []),
            'summary': analysis.get('summary', ''),
            'key_topics': analysis.get('key_topics', []),
            'sentiment': analysis.get('sentiment', 'neutral'),
            'next_steps': analysis.get('next_steps', ''),
            'message_count': len(messages),
            'doc_id': doc_id,
            'analyzed_at': firestore.SERVER_TIMESTAMP
        })

        logger.info(f"Stored relationship data for {domain}")

    def _process_single_company(self, row: Dict, sheets, firestore_svc, drive, gemini, docs) -> Dict:
        """Process a single company row."""
        company = row['company']
        domain = row['domain']
        row_number = row['row_number']

        try:
            if firestore_svc.is_processed(domain):
                return {'company': company, 'domain': domain, 'status': 'skipped', 'reason': 'already_processed'}

            folder_id = drive.create_folder(company, domain)
            doc_id = drive.create_document(folder_id, company)

            # Research the company
            research_svc = ResearchService()
            research = research_svc.research_company(company, domain)
            research_context = research_svc.format_research_context(research)

            # Generate memo with research context
            memo_content = gemini.generate_memo(company, domain, research_context=research_context)
            docs.insert_text(doc_id, memo_content)
            firestore_svc.mark_processed(domain, company, doc_id, folder_id)

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

        if result.get('skipped'):
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
**Domain:** {result.get('domain')}

The memo will be generated on the next run. Reply "generate memos" to process it now."""

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
            return f"""✓ **Memo regenerated!**

**Company:** {result.get('company')}
**Domain:** {result.get('domain')}

**New memo:** {doc_url}

Let me know if you need any other changes."""

        elif action == 'HEALTH_CHECK':
            return "✓ **All systems operational!** The service is running properly."

        else:
            return f"Action **{action}** completed successfully."
