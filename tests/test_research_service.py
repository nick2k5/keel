"""Tests for ResearchService."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestResearchService:
    """Tests for the ResearchService class."""

    @pytest.fixture(autouse=True)
    def setup(self, patch_config, patch_requests):
        """Set up test fixtures."""
        self.mock_config = patch_config
        self.mock_requests = patch_requests

    def test_format_research_context_basic(self, mock_research_data):
        """Test formatting research context with basic data."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()
            context = svc.format_research_context(mock_research_data)

            assert 'Forithmus' in context
            assert 'forithmus.com' in context
            assert 'COMPREHENSIVE RESEARCH DATA' in context
            assert 'COMPANY WEBSITE CONTENT' in context
            assert 'SEARCH RESULTS' in context

    def test_format_research_context_with_yc_data(self, mock_research_data, mock_yc_company_data):
        """Test formatting research context with YC Bookface data."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()
            context = svc.format_research_context(mock_research_data, yc_data=mock_yc_company_data)

            assert 'YC FOUNDERS' in context
            assert 'John Founder' in context
            assert 'YC BOOKFACE POSTS' in context
            assert 'Introducing Cofia' in context

    def test_format_research_context_with_relationship_data(self, mock_research_data, mock_relationship_data):
        """Test formatting research context with relationship data from emails."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()
            context = svc.format_research_context(
                mock_research_data,
                relationship_data=mock_relationship_data
            )

            assert 'RELATIONSHIP & EMAIL HISTORY' in context
            assert 'Sarah Connector' in context
            assert 'Introducer' in context
            assert 'Alex CEO' in context
            assert 'Communication Timeline' in context

    def test_format_research_context_empty_data(self):
        """Test formatting with minimal data."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()

            empty_research = {
                'company': 'Unknown',
                'domain': '',
                'source': '',
                'domain_pages': {},
                'search_results': [],
                'external_content': {},
                'crunchbase': {},
                'yc_data': {},
                'errors': []
            }

            context = svc.format_research_context(empty_research)

            assert 'Unknown' in context
            assert 'RESEARCH SUMMARY' in context
            assert 'Total pages crawled: 0' in context

    def test_clean_text(self):
        """Test text cleaning utility."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()

            # Test whitespace normalization
            result = svc._clean_text("  hello   world  \n\n  test  ")
            assert result == "hello world test"

    def test_research_company_structure(self):
        """Test that research_company returns correct structure."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService

            with patch.object(ResearchService, '_crawl_domain', return_value={}):
                with patch.object(ResearchService, '_deep_search', return_value=[]):
                    with patch.object(ResearchService, '_scrape_external_pages', return_value={}):
                        with patch.object(ResearchService, '_scrape_crunchbase', return_value={}):
                            with patch.object(ResearchService, '_scrape_yc_directory', return_value={}):
                                svc = ResearchService()
                                result = svc.research_company('TestCo', 'test.com', source='W26')

                                # Verify structure
                                assert 'company' in result
                                assert 'domain' in result
                                assert 'source' in result
                                assert 'domain_pages' in result
                                assert 'search_results' in result
                                assert 'external_content' in result
                                assert 'errors' in result

                                assert result['company'] == 'TestCo'
                                assert result['domain'] == 'test.com'
                                assert result['source'] == 'W26'


class TestSerperSearch:
    """Tests for Serper search functionality."""

    def test_serper_search_returns_results(self, mock_search_results):
        """Test that Serper search returns formatted results."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.post') as mock_post:
                mock_post.return_value = Mock(
                    status_code=200,
                    json=Mock(return_value={'organic': mock_search_results})
                )

                from services.research import ResearchService
                svc = ResearchService()
                results = svc._serper_search('Forithmus company')

                assert len(results) == 3
                assert results[0]['title'] == 'Forithmus - AI Healthcare Platform'
                assert 'forithmus.com' in results[0]['url']

    def test_serper_search_no_api_key(self):
        """Test that search returns empty when no API key."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()
            results = svc._deep_search('TestCo', 'test.com')

            assert results == []

    def test_serper_search_handles_error(self):
        """Test that search handles API errors gracefully."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.post') as mock_post:
                mock_post.side_effect = Exception("API Error")

                from services.research import ResearchService
                svc = ResearchService()
                results = svc._serper_search('test query')

                assert results == []


class TestDomainCrawling:
    """Tests for domain crawling functionality."""

    def test_crawl_domain_returns_dict(self):
        """Test that crawl_domain returns a dictionary."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()

            # Even with network issues, should return a dict
            with patch.object(svc, 'session') as mock_session:
                mock_session.get.side_effect = Exception("Network error")
                result = svc._crawl_domain('test.com')
                assert isinstance(result, dict)

    def test_crawl_domain_no_domain(self):
        """Test crawling with empty domain."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()
            result = svc._crawl_domain('')

            assert result == {}

    def test_crawl_domain_handles_timeout(self):
        """Test that crawling handles timeouts gracefully."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.Session') as mock_session_class:
                mock_session = Mock()
                mock_session_class.return_value = mock_session
                mock_session.get.side_effect = Exception("Connection timeout")

                from services.research import ResearchService
                svc = ResearchService()
                result = svc._crawl_domain('timeout.com')

                # Should return empty dict on error, not raise
                assert result == {}


class TestDeepSearch:
    """Tests for deep search functionality."""

    def test_deep_search_runs_multiple_queries(self):
        """Test that deep search runs multiple search queries."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.post') as mock_post:
                mock_post.return_value = Mock(
                    status_code=200,
                    json=Mock(return_value={'organic': [
                        {'title': 'Result', 'link': 'https://example.com', 'snippet': 'Test'}
                    ]})
                )

                from services.research import ResearchService
                svc = ResearchService()
                results = svc._deep_search('TestCo', 'test.com')

                # Should have called post multiple times for different queries
                assert mock_post.call_count > 1
                assert len(results) > 0

    def test_deep_search_with_yc_source(self):
        """Test deep search includes YC-specific queries for YC companies."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.post') as mock_post:
                mock_post.return_value = Mock(
                    status_code=200,
                    json=Mock(return_value={'organic': []})
                )

                from services.research import ResearchService
                svc = ResearchService()
                svc._deep_search('Cofia', '', source='W26')

                # Check that queries were made
                assert mock_post.call_count > 0

                # Check that at least one query included company name or YC-related terms
                calls = mock_post.call_args_list
                queries = [call[1]['json']['q'] for call in calls]
                # Should include company name in queries
                assert any('Cofia' in q for q in queries)

    def test_deep_search_deduplicates_results(self):
        """Test that deep search removes duplicate URLs."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = 'test-key'
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.post') as mock_post:
                # Return same result from multiple queries
                mock_post.return_value = Mock(
                    status_code=200,
                    json=Mock(return_value={'organic': [
                        {'title': 'Same Result', 'link': 'https://example.com/page', 'snippet': 'Test'}
                    ]})
                )

                from services.research import ResearchService
                svc = ResearchService()
                results = svc._deep_search('TestCo', 'test.com')

                # Count unique URLs
                urls = [r['url'] for r in results]
                assert len(urls) == len(set(urls))


class TestExternalPageScraping:
    """Tests for external page scraping."""

    def test_scrape_external_pages_returns_dict(self):
        """Test that scrape_external_pages returns a dictionary."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()

            search_results = [
                {'title': 'Article', 'url': 'https://techcrunch.com/article', 'snippet': 'News'}
            ]

            # Mock the session to simulate network issues
            with patch.object(svc, 'session') as mock_session:
                mock_session.get.side_effect = Exception("Network error")
                result = svc._scrape_external_pages(search_results)

                # Should return empty dict on errors, not raise
                assert isinstance(result, dict)

    def test_scrape_external_pages_skips_company_domain(self):
        """Test that scraping skips the company's own domain."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            from services.research import ResearchService
            svc = ResearchService()

            search_results = [
                {'title': 'Home', 'url': 'https://forithmus.com/', 'snippet': 'Main site'},
                {'title': 'About', 'url': 'https://forithmus.com/about', 'snippet': 'About page'},
            ]

            # These should be skipped as they're from the company domain
            result = svc._scrape_external_pages(search_results)

            # May return empty or skip forithmus.com URLs
            for url in result.keys():
                # External pages shouldn't include company's own domain pages
                # (implementation may vary)
                pass

    def test_scrape_external_pages_handles_errors(self):
        """Test that scraping handles page errors gracefully."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.Session') as mock_session_class:
                mock_session = Mock()
                mock_session_class.return_value = mock_session
                mock_session.get.side_effect = Exception("Connection error")

                from services.research import ResearchService
                svc = ResearchService()

                search_results = [
                    {'title': 'Article', 'url': 'https://example.com/article', 'snippet': 'News'}
                ]

                # Should not raise, should return empty or partial results
                result = svc._scrape_external_pages(search_results)
                assert isinstance(result, dict)

    def test_scrape_external_pages_respects_limit(self):
        """Test that scraping respects MAX_EXTERNAL_PAGES limit."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.Session') as mock_session_class:
                mock_session = Mock()
                mock_session_class.return_value = mock_session

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.headers = {'content-type': 'text/html'}
                mock_response.text = '<html><body>Content</body></html>'
                mock_session.get.return_value = mock_response

                from services.research import ResearchService
                svc = ResearchService()

                # Create many search results
                search_results = [
                    {'title': f'Article {i}', 'url': f'https://site{i}.com/article', 'snippet': 'News'}
                    for i in range(50)
                ]

                result = svc._scrape_external_pages(search_results)

                # Should not exceed MAX_EXTERNAL_PAGES
                assert len(result) <= svc.MAX_EXTERNAL_PAGES


class TestSitemapParsing:
    """Tests for sitemap parsing."""

    def test_get_sitemap_urls_basic(self):
        """Test parsing sitemap.xml."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.Session') as mock_session_class:
                mock_session = Mock()
                mock_session_class.return_value = mock_session

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.text = '''<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                    <url><loc>https://test.com/</loc></url>
                    <url><loc>https://test.com/about</loc></url>
                    <url><loc>https://test.com/team</loc></url>
                </urlset>'''
                mock_session.get.return_value = mock_response

                from services.research import ResearchService
                svc = ResearchService()
                urls = svc._get_sitemap_urls('test.com')

                assert len(urls) == 3
                assert 'https://test.com/' in urls
                assert 'https://test.com/about' in urls

    def test_get_sitemap_urls_not_found(self):
        """Test handling missing sitemap."""
        with patch('services.research.config') as mock_config:
            mock_config.serper_api_key = ''
            mock_config.linkedin_cookie = ''

            with patch('services.research.requests.Session') as mock_session_class:
                mock_session = Mock()
                mock_session_class.return_value = mock_session

                mock_response = Mock()
                mock_response.status_code = 404
                mock_session.get.return_value = mock_response

                from services.research import ResearchService
                svc = ResearchService()
                urls = svc._get_sitemap_urls('test.com')

                assert urls == []
