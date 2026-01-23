"""Bookface service for scraping YC batch companies."""
import json
import logging
import time
import urllib.request
from typing import Dict, List, Any, Optional

from google.cloud import firestore as firestore_module

logger = logging.getLogger(__name__)


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
            'updated_at': firestore_module.SERVER_TIMESTAMP
        })

        logger.info(f"Stored YC data for {company['name']}: {len(company.get('posts', []))} posts, {len(company.get('founders', []))} founders")
