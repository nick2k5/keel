"""Tests for DocsService."""
import pytest
from unittest.mock import Mock, patch, MagicMock

from services import DocsService


class TestDocsService:
    """Tests for the DocsService class."""

    def test_insert_text_empty_doc(self):
        """Test inserting text into an empty document."""
        with patch('services.google.docs.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            # Mock getting document (empty, end_index = 1)
            mock_service.documents.return_value.get.return_value.execute.return_value = {
                'body': {'content': [{'endIndex': 1}]}
            }

            pass  # DocsService imported at module level
            svc = DocsService(Mock())

            svc.insert_text('doc-123', 'Hello World')

            # Should call batchUpdate to insert text
            mock_service.documents.return_value.batchUpdate.assert_called_once()

    def test_insert_text_replaces_existing_content(self):
        """Test that insert_text clears existing content before inserting."""
        with patch('services.google.docs.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            # Mock document with existing content (end_index > 2)
            mock_service.documents.return_value.get.return_value.execute.return_value = {
                'body': {'content': [{'endIndex': 100}]}
            }

            pass  # DocsService imported at module level
            svc = DocsService(Mock())

            svc.insert_text('doc-123', 'New Content')

            # Should call batchUpdate twice: once to delete, once to insert
            assert mock_service.documents.return_value.batchUpdate.call_count == 2

    def test_insert_text_formats_content(self):
        """Test that insert_text includes the content in the request."""
        with patch('services.google.docs.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.documents.return_value.get.return_value.execute.return_value = {
                'body': {'content': [{'endIndex': 1}]}
            }

            pass  # DocsService imported at module level
            svc = DocsService(Mock())

            test_content = "# Test Memo\n\nThis is a test."
            svc.insert_text('doc-123', test_content)

            # Verify batchUpdate was called
            mock_service.documents.return_value.batchUpdate.assert_called_once()

            # Get the call arguments
            call_args = mock_service.documents.return_value.batchUpdate.call_args
            # The content should be in the request somewhere
            call_str = str(call_args)
            assert 'Test Memo' in call_str or 'insertText' in call_str

    def test_insert_text_handles_multiline(self):
        """Test inserting multi-line content."""
        with patch('services.google.docs.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.documents.return_value.get.return_value.execute.return_value = {
                'body': {'content': [{'endIndex': 1}]}
            }

            pass  # DocsService imported at module level
            svc = DocsService(Mock())

            multiline_content = """# Company Memo

## Overview
This is the overview section.

## Team
- CEO: John Doe
- CTO: Jane Smith

## Product
The product does amazing things.
"""
            svc.insert_text('doc-123', multiline_content)

            mock_service.documents.return_value.batchUpdate.assert_called_once()


class TestDocsServiceEdgeCases:
    """Edge case tests for DocsService."""

    def test_insert_text_empty_content(self):
        """Test inserting empty content."""
        with patch('services.google.docs.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.documents.return_value.get.return_value.execute.return_value = {
                'body': {'content': [{'endIndex': 1}]}
            }

            pass  # DocsService imported at module level
            svc = DocsService(Mock())

            # Should not raise an error
            svc.insert_text('doc-123', '')

    def test_insert_text_special_characters(self):
        """Test inserting content with special characters."""
        with patch('services.google.docs.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service

            mock_service.documents.return_value.get.return_value.execute.return_value = {
                'body': {'content': [{'endIndex': 1}]}
            }

            pass  # DocsService imported at module level
            svc = DocsService(Mock())

            special_content = "Company: Tëst™ Inc. — Revenue: $1M+ (2024)"
            svc.insert_text('doc-123', special_content)

            mock_service.documents.return_value.batchUpdate.assert_called_once()
