#!/usr/bin/env python3
"""
Comprehensive tests for wikipedia_enricher.py module.
"""

from unittest.mock import Mock, patch

import pytest
import requests


class TestWikipediaEnricherComprehensive:
    """Comprehensive tests for Wikipedia enricher functionality."""

    @pytest.mark.unit
    def test_get_entity_info_from_wikipedia_success(self):
        """Test successful Wikipedia data retrieval."""
        from src.enrichment.wikipedia_enricher import get_entity_info_from_wikipedia

        # Mock search response
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "query": {"search": [{"title": "Test Company", "snippet": "Test snippet"}]}
        }

        # Mock extract response
        extract_response = Mock()
        extract_response.status_code = 200
        extract_response.json.return_value = {
            "query": {
                "pages": {
                    "12345": {
                        "pageid": 12345,
                        "title": "Test Company",
                        "extract": "Test Company is a technology company.",
                        "categories": [{"title": "Category:Technology"}],
                    }
                }
            }
        }

        with patch("requests.get", side_effect=[search_response, extract_response]):
            result = get_entity_info_from_wikipedia("Test Company", "fr")

        assert result is not None
        assert "Test Company" in result.get("description", "")

    @pytest.mark.unit
    def test_get_entity_info_not_found(self):
        """Test Wikipedia data retrieval when page not found."""
        from src.enrichment.wikipedia_enricher import get_entity_info_from_wikipedia

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"query": {"search": []}}

        with patch("requests.get", return_value=mock_response):
            result = get_entity_info_from_wikipedia("NonExistentCompany", "fr")

        assert result == {}

    @pytest.mark.unit
    def test_get_entity_info_api_error(self):
        """Test Wikipedia data retrieval with API error."""
        from src.enrichment.wikipedia_enricher import get_entity_info_from_wikipedia

        with patch("requests.get", side_effect=requests.RequestException("API Error")):
            result = get_entity_info_from_wikipedia("Test Company", "fr")

        assert result == {}

    @pytest.mark.unit
    def test_simulate_neo4j_update(self):
        """Test simulated Neo4j update function."""
        from src.enrichment.wikipedia_enricher import simulate_neo4j_update

        # Should not raise any errors
        simulate_neo4j_update("Company", "test_id", {"description": "Test"})

    @pytest.mark.unit
    def test_main_function(self):
        """Test main function execution."""
        from src.enrichment.wikipedia_enricher import main

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with (
            patch("sqlite3.connect", return_value=mock_conn),
            patch("sys.argv", ["enricher.py"]),
            patch("os.getenv", return_value="test_password"),
        ):
            main(use_neo4j=False)

        mock_conn.close.assert_called()

    @pytest.mark.unit
    def test_main_with_neo4j(self):
        """Test main function with Neo4j enabled."""
        from src.enrichment.wikipedia_enricher import main

        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_driver = Mock()
        mock_driver.close = Mock()

        # Mock the neo4j module entirely
        mock_neo4j = Mock()
        mock_neo4j.GraphDatabase.driver.return_value = mock_driver

        with (
            patch("sqlite3.connect", return_value=mock_conn),
            patch.dict("sys.modules", {"neo4j": mock_neo4j}),
            patch("sys.argv", ["enricher.py"]),
            patch("os.getenv", return_value="test_password"),
        ):
            main(use_neo4j=True)

        mock_conn.close.assert_called()
        mock_driver.close.assert_called()
