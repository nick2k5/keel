"""Tests for BookfaceService."""
import json
import pytest
from unittest.mock import MagicMock, patch, Mock


class TestBookfaceService:
    """Tests for BookfaceService class."""

    @patch('services.bookface.urllib.request.urlopen')
    def test_fetch_feed_page_basic(self, mock_urlopen):
        """Test basic feed page fetch."""
        from services.bookface import BookfaceService

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'posts': [{'id': 1}],
            'next_cursor': 'abc123'
        }).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        svc = BookfaceService(cookie='test-cookie')
        result = svc.fetch_feed_page()

        assert 'posts' in result
        assert result['next_cursor'] == 'abc123'

    @patch('services.bookface.urllib.request.urlopen')
    def test_fetch_feed_page_with_cursor(self, mock_urlopen):
        """Test feed page fetch with cursor."""
        from services.bookface import BookfaceService

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'posts': []}).encode('utf-8')
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        svc = BookfaceService(cookie='test-cookie')
        svc.fetch_feed_page(cursor='test-cursor')

        # Verify cursor was included in URL
        call_args = mock_urlopen.call_args[0][0]
        assert 'cursor=test-cursor' in call_args.full_url

    @patch('services.bookface.urllib.request.urlopen')
    def test_fetch_feed_page_error(self, mock_urlopen):
        """Test feed page fetch handles errors."""
        from services.bookface import BookfaceService

        mock_urlopen.side_effect = Exception('Network error')

        svc = BookfaceService(cookie='test-cookie')

        with pytest.raises(Exception):
            svc.fetch_feed_page()

    @patch('services.bookface.time.sleep')
    def test_extract_batch_companies(self, mock_sleep):
        """Test extracting companies from feed."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')

        # Mock fetch_feed_page to return companies
        with patch.object(svc, 'fetch_feed_page') as mock_fetch:
            mock_fetch.return_value = {
                'posts': [
                    {
                        'user': {
                            'full_name': 'John Founder',
                            'email': 'john@startup.com',
                            'hnid': 'john123',
                            'companies': [
                                {'id': '1', 'name': 'TestStartup', 'batch': 'W26'}
                            ]
                        },
                        'body': 'Great product launch!',
                        'title': 'Launch Post'
                    }
                ],
                'next_cursor': None  # Stop pagination
            }

            companies = svc.extract_batch_companies(batch='W26', max_pages=1)

            assert len(companies) == 1
            assert companies[0]['name'] == 'TestStartup'
            assert companies[0]['batch'] == 'W26'
            assert len(companies[0]['founders']) == 1
            assert companies[0]['founders'][0]['name'] == 'John Founder'

    @patch('services.bookface.time.sleep')
    def test_extract_batch_companies_pagination(self, mock_sleep):
        """Test extracting companies with pagination."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')

        call_count = [0]

        def mock_fetch(cursor=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'posts': [
                        {
                            'user': {
                                'full_name': 'Founder 1',
                                'companies': [{'id': '1', 'name': 'Company1', 'batch': 'W26'}]
                            },
                            'body': 'Post 1'
                        }
                    ],
                    'next_cursor': 'cursor2'
                }
            else:
                return {
                    'posts': [
                        {
                            'user': {
                                'full_name': 'Founder 2',
                                'companies': [{'id': '2', 'name': 'Company2', 'batch': 'W26'}]
                            },
                            'body': 'Post 2'
                        }
                    ],
                    'next_cursor': None
                }

        with patch.object(svc, 'fetch_feed_page', side_effect=mock_fetch):
            companies = svc.extract_batch_companies(batch='W26', max_pages=3)

            assert len(companies) == 2
            assert call_count[0] == 2

    @patch('services.bookface.time.sleep')
    def test_extract_batch_companies_filters_by_batch(self, mock_sleep):
        """Test that only companies from specified batch are extracted."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')

        with patch.object(svc, 'fetch_feed_page') as mock_fetch:
            mock_fetch.return_value = {
                'posts': [
                    {
                        'user': {
                            'companies': [
                                {'id': '1', 'name': 'W26Company', 'batch': 'W26'},
                                {'id': '2', 'name': 'S25Company', 'batch': 'S25'}
                            ]
                        }
                    }
                ],
                'next_cursor': None
            }

            companies = svc.extract_batch_companies(batch='W26', max_pages=1)

            assert len(companies) == 1
            assert companies[0]['name'] == 'W26Company'

    @patch('services.bookface.time.sleep')
    def test_extract_batch_companies_deduplicates(self, mock_sleep):
        """Test that duplicate companies are deduplicated."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')

        with patch.object(svc, 'fetch_feed_page') as mock_fetch:
            mock_fetch.return_value = {
                'posts': [
                    {
                        'user': {
                            'full_name': 'Founder A',
                            'companies': [{'id': '1', 'name': 'SameCompany', 'batch': 'W26'}]
                        },
                        'body': 'Post 1'
                    },
                    {
                        'user': {
                            'full_name': 'Founder B',
                            'companies': [{'id': '1', 'name': 'SameCompany', 'batch': 'W26'}]
                        },
                        'body': 'Post 2'
                    }
                ],
                'next_cursor': None
            }

            companies = svc.extract_batch_companies(batch='W26', max_pages=1)

            # Should be deduplicated to 1 company with 2 posts and 2 founders
            assert len(companies) == 1
            assert len(companies[0]['posts']) == 2
            assert len(companies[0]['founders']) == 2

    @patch('services.bookface.time.sleep')
    def test_extract_batch_companies_empty_posts(self, mock_sleep):
        """Test handling when feed has no posts."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')

        with patch.object(svc, 'fetch_feed_page') as mock_fetch:
            mock_fetch.return_value = {'posts': [], 'next_cursor': None}

            companies = svc.extract_batch_companies(batch='W26', max_pages=1)

            assert companies == []


class TestScrapeAndAddCompanies:
    """Tests for scrape_and_add_companies method."""

    @patch('services.bookface.time.sleep')
    def test_scrape_and_add_companies_success(self, mock_sleep):
        """Test successful scrape and add."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_sheets = MagicMock()
        mock_sheets.add_company.return_value = {'success': True}

        with patch.object(svc, 'extract_batch_companies') as mock_extract:
            mock_extract.return_value = [
                {'name': 'Company1', 'batch': 'W26', 'posts': [], 'founders': []},
                {'name': 'Company2', 'batch': 'W26', 'posts': [], 'founders': []}
            ]

            result = svc.scrape_and_add_companies(mock_sheets, batch='W26')

            assert result['success'] is True
            assert result['added'] == 2
            assert result['skipped'] == 0
            assert 'Company1' in result['added_companies']
            assert 'Company2' in result['added_companies']

    @patch('services.bookface.time.sleep')
    def test_scrape_and_add_companies_skips_existing(self, mock_sleep):
        """Test that existing companies are skipped."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_sheets = MagicMock()
        mock_sheets.add_company.side_effect = [
            {'success': True},
            {'success': False, 'error': 'Company already exists'}
        ]

        with patch.object(svc, 'extract_batch_companies') as mock_extract:
            mock_extract.return_value = [
                {'name': 'NewCompany', 'batch': 'W26', 'posts': [], 'founders': []},
                {'name': 'ExistingCompany', 'batch': 'W26', 'posts': [], 'founders': []}
            ]

            result = svc.scrape_and_add_companies(mock_sheets, batch='W26')

            assert result['success'] is True
            assert result['added'] == 1
            assert result['skipped'] == 1

    @patch('services.bookface.time.sleep')
    def test_scrape_and_add_companies_handles_errors(self, mock_sleep):
        """Test that errors are tracked."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_sheets = MagicMock()
        mock_sheets.add_company.return_value = {'success': False, 'error': 'Unknown error'}

        with patch.object(svc, 'extract_batch_companies') as mock_extract:
            mock_extract.return_value = [
                {'name': 'Company1', 'batch': 'W26', 'posts': [], 'founders': []}
            ]

            result = svc.scrape_and_add_companies(mock_sheets, batch='W26')

            assert result['success'] is True
            assert result['errors'] == 1
            assert 'Company1' in result['error_details'][0]

    @patch('services.bookface.time.sleep')
    def test_scrape_and_add_companies_skips_empty_names(self, mock_sleep):
        """Test that companies without names are skipped."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_sheets = MagicMock()

        with patch.object(svc, 'extract_batch_companies') as mock_extract:
            mock_extract.return_value = [
                {'name': '', 'batch': 'W26', 'posts': [], 'founders': []},  # Empty name
                {'name': 'ValidCompany', 'batch': 'W26', 'posts': [], 'founders': []}
            ]
            mock_sheets.add_company.return_value = {'success': True}

            result = svc.scrape_and_add_companies(mock_sheets, batch='W26')

            # Only one company should be added (the valid one)
            assert mock_sheets.add_company.call_count == 1

    @patch('services.bookface.time.sleep')
    def test_scrape_and_add_companies_stores_firestore_data(self, mock_sleep):
        """Test that company data is stored in Firestore."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_sheets = MagicMock()
        mock_sheets.add_company.return_value = {'success': True}
        mock_firestore = MagicMock()

        with patch.object(svc, 'extract_batch_companies') as mock_extract:
            with patch.object(svc, '_store_yc_company_data') as mock_store:
                mock_extract.return_value = [
                    {
                        'name': 'Company1',
                        'batch': 'W26',
                        'posts': [{'title': 'Post', 'body': 'Content'}],
                        'founders': [{'name': 'John', 'email': 'john@example.com'}]
                    }
                ]

                svc.scrape_and_add_companies(mock_sheets, batch='W26', firestore_svc=mock_firestore)

                mock_store.assert_called_once()

    @patch('services.bookface.time.sleep')
    def test_scrape_and_add_companies_exception(self, mock_sleep):
        """Test handling of exceptions during scrape."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_sheets = MagicMock()

        with patch.object(svc, 'extract_batch_companies') as mock_extract:
            mock_extract.side_effect = Exception('API Error')

            result = svc.scrape_and_add_companies(mock_sheets, batch='W26')

            assert result['success'] is False
            assert 'API Error' in result['error']


class TestStoreYCCompanyData:
    """Tests for _store_yc_company_data method."""

    @patch('google.cloud.firestore.SERVER_TIMESTAMP', 'MOCK_TIMESTAMP')
    def test_store_yc_company_data_new(self):
        """Test storing new company data."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_firestore = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_firestore.db.collection().document().get.return_value = mock_doc

        company = {
            'name': 'TestStartup',
            'batch': 'W26',
            'posts': [{'title': 'Launch', 'body': 'We launched!'}],
            'founders': [{'name': 'Jane', 'email': 'jane@test.com'}]
        }

        svc._store_yc_company_data(mock_firestore, company)

        mock_firestore.db.collection().document().set.assert_called_once()

    @patch('google.cloud.firestore.SERVER_TIMESTAMP', 'MOCK_TIMESTAMP')
    def test_store_yc_company_data_merge_existing(self):
        """Test merging with existing company data."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_firestore = MagicMock()

        # Simulate existing data
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            'posts': [{'title': 'Old Post', 'body': 'Old content'}],
            'founders': [{'name': 'Old Founder', 'email': 'old@test.com'}]
        }
        mock_firestore.db.collection().document().get.return_value = mock_doc

        company = {
            'name': 'TestStartup',
            'batch': 'W26',
            'posts': [{'title': 'New Post', 'body': 'New content'}],
            'founders': [{'name': 'New Founder', 'email': 'new@test.com'}]
        }

        svc._store_yc_company_data(mock_firestore, company)

        # Should have merged posts and founders
        call_args = mock_firestore.db.collection().document().set.call_args[0][0]
        assert len(call_args['posts']) == 2
        assert len(call_args['founders']) == 2

    @patch('google.cloud.firestore.SERVER_TIMESTAMP', 'MOCK_TIMESTAMP')
    def test_store_yc_company_data_avoids_duplicate_posts(self):
        """Test that duplicate posts are not added."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_firestore = MagicMock()

        # Simulate existing data with same post title
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            'posts': [{'title': 'Same Title', 'body': 'Old content'}],
            'founders': []
        }
        mock_firestore.db.collection().document().get.return_value = mock_doc

        company = {
            'name': 'TestStartup',
            'batch': 'W26',
            'posts': [{'title': 'Same Title', 'body': 'New content'}],  # Same title
            'founders': []
        }

        svc._store_yc_company_data(mock_firestore, company)

        call_args = mock_firestore.db.collection().document().set.call_args[0][0]
        # Should still be 1 post (duplicate not added)
        assert len(call_args['posts']) == 1

    @patch('google.cloud.firestore.SERVER_TIMESTAMP', 'MOCK_TIMESTAMP')
    def test_store_yc_company_data_avoids_duplicate_founders(self):
        """Test that duplicate founders are not added."""
        from services.bookface import BookfaceService

        svc = BookfaceService(cookie='test-cookie')
        mock_firestore = MagicMock()

        # Simulate existing data with same founder email
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            'posts': [],
            'founders': [{'name': 'John', 'email': 'john@test.com'}]
        }
        mock_firestore.db.collection().document().get.return_value = mock_doc

        company = {
            'name': 'TestStartup',
            'batch': 'W26',
            'posts': [],
            'founders': [{'name': 'John Updated', 'email': 'john@test.com'}]  # Same email
        }

        svc._store_yc_company_data(mock_firestore, company)

        call_args = mock_firestore.db.collection().document().set.call_args[0][0]
        # Should still be 1 founder (duplicate not added)
        assert len(call_args['founders']) == 1
