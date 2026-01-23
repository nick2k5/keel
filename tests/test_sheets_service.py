"""Tests for SheetsService."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestSheetsService:
    """Tests for the SheetsService class."""

    def test_get_rows_to_process_returns_unprocessed(self):
        """Test that get_rows_to_process returns rows without status (requires domain)."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            # Mock spreadsheet response
            # Note: get_rows_to_process requires BOTH company AND domain
            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],  # Header
                    ['Forithmus', 'forithmus.com', '', ''],  # Should be returned (has domain, no status)
                    ['Stripe', 'stripe.com', 'Memo Created', ''],  # Should be skipped (has status)
                    ['NewCo', 'newco.com', 'New', ''],  # Should be returned (status = 'New')
                    ['Vela', '', '', 'W26'],  # Skipped - no domain
                ]
            }

            from services import SheetsService
            mock_creds = Mock()
            svc = SheetsService(mock_creds)
            svc.spreadsheet_id = 'test-sheet-id'

            rows = svc.get_rows_to_process()

            # Only rows with both company AND domain and empty/New status are returned
            assert len(rows) == 2
            assert rows[0]['company'] == 'Forithmus'
            assert rows[0]['domain'] == 'forithmus.com'
            assert rows[0]['row_number'] == 2
            assert rows[1]['company'] == 'NewCo'

    def test_get_rows_to_process_empty_sheet(self):
        """Test get_rows_to_process with empty sheet."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],  # Header only
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            rows = svc.get_rows_to_process()

            assert rows == []

    def test_get_rows_to_process_no_values_key(self):
        """Test get_rows_to_process when API returns no values."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {}

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            rows = svc.get_rows_to_process()

            assert rows == []

    def test_get_all_companies(self):
        """Test get_all_companies returns all rows."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['Forithmus', 'forithmus.com', 'Memo Created', ''],
                    ['Stripe', 'stripe.com', 'Memo Created', ''],
                    ['Cofia', '', '', 'W26'],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            companies = svc.get_all_companies()

            assert len(companies) == 3
            assert companies[0]['company'] == 'Forithmus'
            assert companies[1]['company'] == 'Stripe'
            assert companies[2]['company'] == 'Cofia'
            assert companies[2]['source'] == 'W26'

    def test_update_status(self):
        """Test updating row status."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            svc.update_status(5, 'Memo Created')

            mock_service.spreadsheets.return_value.values.return_value.update.assert_called_once()
            call_kwargs = mock_service.spreadsheets.return_value.values.return_value.update.call_args
            assert 'Index!C5' in str(call_kwargs)

    def test_add_company_new(self):
        """Test adding a new company."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            # Mock get to return existing companies (none matching)
            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['Existing', 'existing.com', '', ''],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            result = svc.add_company('NewCo', 'newco.com', 'W26')

            assert result['success'] is True
            assert result['company'] == 'NewCo'
            assert result['domain'] == 'newco.com'
            mock_service.spreadsheets.return_value.values.return_value.append.assert_called_once()

    def test_add_company_already_exists(self):
        """Test adding a company that already exists returns error."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['Forithmus', 'forithmus.com', '', ''],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            result = svc.add_company('Forithmus', 'forithmus.com')

            # Returns success=False when company exists
            assert result['success'] is False
            assert 'already exists' in result['error']
            mock_service.spreadsheets.return_value.values.return_value.append.assert_not_called()

    def test_add_company_case_insensitive_match(self):
        """Test that domain matching is case-insensitive."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['FORITHMUS', 'forithmus.com', '', ''],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            result = svc.add_company('forithmus', 'FORITHMUS.COM')

            # Should detect as existing due to case-insensitive domain match
            assert result['success'] is False
            assert 'already exists' in result['error']


class TestUpdateCompany:
    """Tests for the update_company method."""

    def test_update_company_domain(self):
        """Test updating a company's domain."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['HCA', 'hca.com', '', ''],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            result = svc.update_company('HCA', new_domain='https://www.hcahealthcare.com/')

            assert result['success'] is True
            assert result['company'] == 'HCA'
            assert result['old_domain'] == 'hca.com'
            assert result['new_domain'] == 'hcahealthcare.com'
            # Verify the update was called
            mock_service.spreadsheets.return_value.values.return_value.update.assert_called()

    def test_update_company_cleans_url(self):
        """Test that update_company cleans URLs properly."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['TestCo', 'old.com', '', ''],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            result = svc.update_company('TestCo', new_domain='https://www.newdomain.com/path/page')

            assert result['success'] is True
            assert result['new_domain'] == 'newdomain.com'

    def test_update_company_not_found(self):
        """Test updating a company that doesn't exist."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['Other', 'other.com', '', ''],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            result = svc.update_company('NonExistent', new_domain='new.com')

            assert result['success'] is False
            assert 'not found' in result['error'].lower()

    def test_update_company_clears_status(self):
        """Test that updating domain clears the status for reprocessing."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['HCA', 'hca.com', 'Memo Created', ''],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            result = svc.update_company('HCA', new_domain='hcahealthcare.com')

            assert result['success'] is True
            # Should have cleared status (3 update calls: domain, status clear)
            assert 'status cleared' in str(result.get('updates', []))

    def test_update_company_by_domain_identifier(self):
        """Test finding company by domain to update."""
        with patch('services.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
                'values': [
                    ['Company', 'Domain', 'Status', 'Source'],
                    ['HCA', 'hca.com', '', ''],
                ]
            }

            from services import SheetsService
            svc = SheetsService(Mock())
            svc.spreadsheet_id = 'test-sheet-id'

            # Find by domain instead of company name
            result = svc.update_company('hca.com', new_domain='hcahealthcare.com')

            assert result['success'] is True
            assert result['company'] == 'HCA'
