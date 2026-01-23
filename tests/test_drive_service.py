"""Tests for DriveService."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDriveService:
    """Tests for the DriveService class."""

    def test_find_existing_folder_found(self):
        """Test finding an existing folder."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': [{'id': 'folder-123', 'name': 'Forithmus (forithmus.com)'}]
            }

            from services.drive import DriveService
            svc = DriveService(Mock())
            svc.parent_folder_id = 'parent-folder-id'

            result = svc.find_existing_folder('Forithmus', 'forithmus.com')

            assert result == 'folder-123'

    def test_find_existing_folder_not_found(self):
        """Test when folder doesn't exist."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': []
            }

            from services.drive import DriveService
            svc = DriveService(Mock())
            svc.parent_folder_id = 'parent-folder-id'

            result = svc.find_existing_folder('Forithmus', 'forithmus.com')

            assert result is None

    def test_find_existing_folder_no_domain(self):
        """Test finding folder for company without domain."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': [{'id': 'folder-456', 'name': 'Cofia (no-domain)'}]
            }

            from services.drive import DriveService
            svc = DriveService(Mock())
            svc.parent_folder_id = 'parent-folder-id'

            result = svc.find_existing_folder('Cofia', '')

            assert result == 'folder-456'

    def test_create_folder_new(self):
        """Test creating a new folder."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            # First call to list returns no existing folder
            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': []
            }
            # Create returns the new folder
            mock_service.files.return_value.create.return_value.execute.return_value = {
                'id': 'new-folder-id'
            }

            from services.drive import DriveService
            svc = DriveService(Mock())
            svc.parent_folder_id = 'parent-folder-id'

            result = svc.create_folder('NewCo', 'newco.com')

            assert result == 'new-folder-id'
            mock_service.files.return_value.create.assert_called_once()

    def test_create_folder_already_exists(self):
        """Test create_folder when folder already exists."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': [{'id': 'existing-folder-id', 'name': 'Forithmus (forithmus.com)'}]
            }

            from services.drive import DriveService
            svc = DriveService(Mock())
            svc.parent_folder_id = 'parent-folder-id'

            result = svc.create_folder('Forithmus', 'forithmus.com')

            assert result == 'existing-folder-id'
            mock_service.files.return_value.create.assert_not_called()

    def test_find_document_in_folder_found(self):
        """Test finding a document in a folder."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': [{'id': 'doc-123', 'name': 'Initial Brief'}]
            }

            from services.drive import DriveService
            svc = DriveService(Mock())

            result = svc.find_document_in_folder('folder-123', 'Initial Brief')

            assert result == 'doc-123'

    def test_find_document_in_folder_not_found(self):
        """Test when document doesn't exist in folder."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': []
            }

            from services.drive import DriveService
            svc = DriveService(Mock())

            result = svc.find_document_in_folder('folder-123', 'Initial Brief')

            assert result is None

    def test_create_document_new(self):
        """Test creating a new document."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            # No existing document
            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': []
            }
            # Create returns new doc
            mock_service.files.return_value.create.return_value.execute.return_value = {
                'id': 'new-doc-id'
            }

            from services.drive import DriveService
            svc = DriveService(Mock())

            result = svc.create_document('folder-123', 'Forithmus')

            assert result == 'new-doc-id'
            mock_service.files.return_value.create.assert_called_once()
            # Verify doc name is "Initial Brief"
            call_kwargs = mock_service.files.return_value.create.call_args
            assert call_kwargs[1]['body']['name'] == 'Initial Brief'

    def test_create_document_reuses_existing(self):
        """Test that create_document reuses existing 'Initial Brief' doc."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': [{'id': 'existing-doc-id', 'name': 'Initial Brief'}]
            }

            from services.drive import DriveService
            svc = DriveService(Mock())

            result = svc.create_document('folder-123', 'Forithmus')

            assert result == 'existing-doc-id'
            mock_service.files.return_value.create.assert_not_called()

    def test_create_folder_uses_shared_drive_params(self):
        """Test that create_folder includes supportsAllDrives parameter."""
        with patch('services.drive.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': []
            }
            mock_service.files.return_value.create.return_value.execute.return_value = {
                'id': 'new-folder-id'
            }

            from services.drive import DriveService
            svc = DriveService(Mock())
            svc.parent_folder_id = 'parent-folder-id'

            svc.create_folder('TestCo', 'test.com')

            # Verify supportsAllDrives is in the call
            call_kwargs = mock_service.files.return_value.create.call_args
            assert call_kwargs[1].get('supportsAllDrives') is True
