"""Research service for comprehensive company investigation."""
import logging
import re
import requests
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from config import config

logger = logging.getLogger(__name__)


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
