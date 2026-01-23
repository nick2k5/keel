"""Tests for FirestoreService."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestFirestoreService:
    """Tests for the FirestoreService class."""

    def test_normalize_domain(self):
        """Test domain normalization."""
        with patch('services.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.firestore_collection = 'processed_domains'

            with patch('services.firestore.Client'):
                from services import FirestoreService
                svc = FirestoreService()

                # Test basic normalization (lowercase and strip)
                assert svc.normalize_domain('Example.com') == 'example.com'
                assert svc.normalize_domain('  EXAMPLE.COM  ') == 'example.com'
                assert svc.normalize_domain('FORITHMUS.COM') == 'forithmus.com'

    def test_is_processed_true(self):
        """Test checking if domain is processed."""
        with patch('services.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.firestore_collection = 'processed_domains'

            with patch('services.firestore.Client') as mock_client:
                mock_db = Mock()
                mock_client.return_value = mock_db

                mock_doc = Mock()
                mock_doc.exists = True
                mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

                from services import FirestoreService
                svc = FirestoreService()

                result = svc.is_processed('example.com')

                assert result is True
                mock_db.collection.assert_called_with('processed_domains')

    def test_is_processed_false(self):
        """Test checking if domain is not processed."""
        with patch('services.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.firestore_collection = 'processed_domains'

            with patch('services.firestore.Client') as mock_client:
                mock_db = Mock()
                mock_client.return_value = mock_db

                mock_doc = Mock()
                mock_doc.exists = False
                mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

                from services import FirestoreService
                svc = FirestoreService()

                result = svc.is_processed('example.com')

                assert result is False

    def test_get_yc_company_data_exists(self):
        """Test getting YC company data when it exists."""
        with patch('services.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.firestore_collection = 'processed_domains'

            with patch('services.firestore.Client') as mock_client:
                mock_db = Mock()
                mock_client.return_value = mock_db

                mock_doc = Mock()
                mock_doc.exists = True
                mock_doc.to_dict.return_value = {
                    'name': 'Cofia',
                    'batch': 'W26',
                    'posts': [],
                    'founders': []
                }
                mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

                from services import FirestoreService
                svc = FirestoreService()

                result = svc.get_yc_company_data('Cofia')

                assert result is not None
                assert result['name'] == 'Cofia'
                mock_db.collection.assert_called_with('yc_companies')

    def test_get_yc_company_data_not_exists(self):
        """Test getting YC company data when it doesn't exist."""
        with patch('services.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.firestore_collection = 'processed_domains'

            with patch('services.firestore.Client') as mock_client:
                mock_db = Mock()
                mock_client.return_value = mock_db

                mock_doc = Mock()
                mock_doc.exists = False
                mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

                from services import FirestoreService
                svc = FirestoreService()

                result = svc.get_yc_company_data('NonExistent')

                assert result is None

    def test_get_relationship_data_by_domain(self):
        """Test getting relationship data by domain."""
        with patch('services.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.firestore_collection = 'processed_domains'

            with patch('services.firestore.Client') as mock_client:
                mock_db = Mock()
                mock_client.return_value = mock_db

                mock_doc = Mock()
                mock_doc.exists = True
                mock_doc.to_dict.return_value = {
                    'domain': 'forithmus.com',
                    'company_name': 'Forithmus',
                    'introducer': {'name': 'Sarah'},
                    'contacts': []
                }
                mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

                from services import FirestoreService
                svc = FirestoreService()

                result = svc.get_relationship_data(domain='forithmus.com')

                assert result is not None
                assert result['company_name'] == 'Forithmus'
                mock_db.collection.assert_called_with('relationships')

    def test_get_relationship_data_by_company_name(self):
        """Test getting relationship data by company name (when no domain provided)."""
        with patch('services.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.firestore_collection = 'processed_domains'

            with patch('services.firestore.Client') as mock_client:
                mock_db = Mock()
                mock_client.return_value = mock_db

                # When domain is empty string, it's falsy so only company_name lookup runs
                mock_doc_found = Mock()
                mock_doc_found.exists = True
                mock_doc_found.to_dict.return_value = {
                    'company_name': 'Cofia',
                    'introducer': {'name': 'John'}
                }
                mock_db.collection.return_value.document.return_value.get.return_value = mock_doc_found

                from services import FirestoreService
                svc = FirestoreService()

                # Empty domain string is falsy, so it goes straight to company_name lookup
                result = svc.get_relationship_data(domain='', company_name='Cofia')

                assert result is not None
                assert result['company_name'] == 'Cofia'
                # Verify it looked up by company key (lowercase, spaces replaced)
                mock_db.collection.assert_called_with('relationships')
                mock_db.collection.return_value.document.assert_called_with('cofia')

    def test_clear_processed_exists(self):
        """Test clearing processed record when it exists."""
        with patch('services.config') as mock_config:
            mock_config.project_id = 'test-project'
            mock_config.firestore_collection = 'processed_domains'

            with patch('services.firestore.Client') as mock_client:
                mock_db = Mock()
                mock_client.return_value = mock_db

                mock_doc = Mock()
                mock_doc.exists = True
                mock_doc_ref = Mock()
                mock_doc_ref.get.return_value = mock_doc
                mock_db.collection.return_value.document.return_value = mock_doc_ref

                from services import FirestoreService
                svc = FirestoreService()

                result = svc.clear_processed('example.com')

                assert result is True
                mock_doc_ref.delete.assert_called_once()
