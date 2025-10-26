#!/usr/bin/env python3
"""
Comprehensive tests for the graph ingestion module.
Tests CV parsing, API interactions, and Cypher query generation.
"""

import json
from unittest.mock import Mock, mock_open, patch

import pytest
import requests


class TestAPIClients:
    """Test API client functions for harmonizer and entity resolver."""

    @pytest.mark.unit
    def test_call_harmonizer_success(self):
        """Test successful harmonizer API call."""
        from src.graph_ingestion.ingest import call_harmonizer

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "mapped": [
                {"original_skill": "Python", "canonical_skill": "python"},
                {"original_skill": "JavaScript", "canonical_skill": "javascript"},
            ],
            "unmapped": ["Unknown Skill"],
        }

        with patch("src.graph_ingestion.ingest.requests.post", return_value=mock_response):
            result = call_harmonizer(["Python", "JavaScript", "Unknown Skill"])

        assert result["Python"] == "python"
        assert result["JavaScript"] == "javascript"
        assert result["Unknown Skill"] == "unknown_skill"

    @pytest.mark.unit
    def test_call_harmonizer_empty_list(self):
        """Test harmonizer with empty skill list."""
        from src.graph_ingestion.ingest import call_harmonizer

        result = call_harmonizer([])
        assert result == {}

    @pytest.mark.unit
    def test_call_harmonizer_api_failure(self):
        """Test harmonizer fallback when API fails."""
        from src.graph_ingestion.ingest import call_harmonizer

        with patch(
            "src.graph_ingestion.ingest.requests.post",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            result = call_harmonizer(["Python", "Java Script"])

        assert result["Python"] == "python"
        assert result["Java Script"] == "java_script"

    @pytest.mark.unit
    def test_call_entity_resolver_success(self):
        """Test successful entity resolver API call."""
        from src.graph_ingestion.ingest import call_entity_resolver

        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {
                    "original_name": "Google",
                    "canonical_id": "google",
                    "display_name": "Google LLC",
                    "is_known": True,
                },
                {
                    "original_name": "Unknown Corp",
                    "canonical_id": "unknown_corp",
                    "display_name": "Unknown Corp",
                    "is_known": False,
                },
            ]
        }

        with patch("src.graph_ingestion.ingest.requests.post", return_value=mock_response):
            result = call_entity_resolver(["Google", "Unknown Corp"])

        assert result["Google"]["id"] == "google"
        assert result["Google"]["name"] == "Google LLC"
        assert result["Google"]["is_known"] is True
        assert result["Unknown Corp"]["is_known"] is False

    @pytest.mark.unit
    def test_call_entity_resolver_empty_list(self):
        """Test entity resolver with empty list."""
        from src.graph_ingestion.ingest import call_entity_resolver

        result = call_entity_resolver([])
        assert result == {}

    @pytest.mark.unit
    def test_call_entity_resolver_api_failure(self):
        """Test entity resolver fallback when API fails."""
        from src.graph_ingestion.ingest import call_entity_resolver

        with patch(
            "src.graph_ingestion.ingest.requests.post", side_effect=requests.exceptions.Timeout()
        ):
            result = call_entity_resolver(["Google"])

        assert result["Google"]["id"] == "google"
        assert result["Google"]["name"] == "Google"
        assert result["Google"]["is_known"] is False


class TestDataTransformers:
    """Test data transformation functions."""

    @pytest.mark.unit
    def test_escape_cypher_string(self):
        """Test string escaping for Cypher queries."""
        from src.graph_ingestion.ingest import escape_cypher_string

        assert escape_cypher_string("O'Reilly") == "O\\'Reilly"
        assert escape_cypher_string(None) == ""
        assert escape_cypher_string("Normal Text") == "Normal Text"
        assert escape_cypher_string("Test\\Path") == "Test\\\\Path"

    @pytest.mark.unit
    def test_extract_all_skills(self):
        """Test skill extraction from CV data."""
        from src.graph_ingestion.ingest import extract_all_skills

        parsed_data = {
            "documents": [
                {
                    "parsed_data": {
                        "extracted_data": {
                            "profile": {
                                "basics": {"skills": ["Python", "JavaScript"]},
                                "professional_experiences": [{"skills_used": ["React", "Node.js"]}],
                                "projects": [{"technologies_used": ["Docker", "Python"]}],
                            }
                        }
                    }
                }
            ]
        }

        skills = extract_all_skills(parsed_data)
        assert len(skills) == 5  # Python, JavaScript, React, Node.js, Docker (Python is deduped)
        assert "Python" in skills
        assert "Docker" in skills

    @pytest.mark.unit
    def test_process_parsed_cv(self):
        """Test CV processing with entity resolution."""
        from src.graph_ingestion.ingest import process_parsed_cv

        parsed_data = {
            "documents": [
                {
                    "parsed_data": {
                        "extracted_data": {
                            "profile": {
                                "basics": {
                                    "first_name": "John",
                                    "last_name": "Doe",
                                    "emails": ["john@example.com"],
                                },
                                "professional_experiences": [
                                    {
                                        "company": "Google",
                                        "title": "Engineer",
                                        "skills_used": ["Python"],
                                    }
                                ],
                            }
                        }
                    }
                }
            ]
        }

        # Mock API calls
        with patch("src.graph_ingestion.ingest.call_harmonizer") as mock_harm:
            mock_harm.return_value = {"Python": "python"}
            with patch("src.graph_ingestion.ingest.call_entity_resolver") as mock_entity:
                mock_entity.return_value = {
                    "Google": {"id": "google", "name": "Google Inc", "is_known": True}
                }

                result = process_parsed_cv(parsed_data)

        assert "nodes" in result
        assert "relations" in result
        assert len(result["nodes"]) > 0


class TestCypherGenerators:
    """Test Cypher query generation functions."""

    @pytest.mark.unit
    def test_generate_cypher_queries(self):
        """Test Cypher query generation from graph data."""
        from src.graph_ingestion.ingest import generate_cypher_queries

        graph_data = {
            "nodes": [
                {
                    "label": "Candidat",
                    "properties": {
                        "id": "CAND_123",
                        "firstName": "John",
                        "lastName": "Doe",
                        "email": "john@example.com",
                    },
                },
                {"label": "Competence", "properties": {"name": "python", "originalName": "Python"}},
            ],
            "relations": [
                {
                    "from": {"label": "Candidat", "id": "CAND_123"},
                    "to": {"label": "Competence", "name": "python"},
                    "type": "MAITRISE",
                    "properties": {},
                }
            ],
        }

        queries = generate_cypher_queries(graph_data)
        assert len(queries) >= 3  # At least 2 nodes + 1 relation
        assert any("MERGE" in q for q in queries)
        assert any("Candidat" in q for q in queries)
        assert any("Competence" in q for q in queries)

    @pytest.mark.unit
    def test_escape_cypher_string_special_chars(self):
        """Test escaping special characters for Cypher."""
        from src.graph_ingestion.ingest import escape_cypher_string

        # Test with apostrophe
        assert escape_cypher_string("O'Reilly") == "O\\'Reilly"

        # Test with backslash
        assert escape_cypher_string("C:\\Windows") == "C:\\\\Windows"

        # Test with mixed special chars
        text = "John's\\Path"
        escaped = escape_cypher_string(text)
        assert "\\\\" in escaped  # Backslash is escaped
        assert "\\'" in escaped  # Apostrophe is escaped

    @pytest.mark.unit
    def test_generate_cypher_with_relations(self):
        """Test Cypher generation with multiple node types and relations."""
        from src.graph_ingestion.ingest import generate_cypher_queries

        graph_data = {
            "nodes": [
                {"label": "Candidat", "properties": {"id": "CAND_001", "firstName": "Alice"}},
                {"label": "Experience", "properties": {"id": "EXP_001", "title": "Developer"}},
                {"label": "Entreprise", "properties": {"id": "google", "name": "Google"}},
            ],
            "relations": [
                {
                    "from": {"label": "Candidat", "id": "CAND_001"},
                    "to": {"label": "Experience", "id": "EXP_001"},
                    "type": "A_TRAVAILLE",
                    "properties": {},
                },
                {
                    "from": {"label": "Experience", "id": "EXP_001"},
                    "to": {"label": "Entreprise", "id": "google"},
                    "type": "CHEZ",
                    "properties": {},
                },
            ],
        }

        queries = generate_cypher_queries(graph_data)
        assert len(queries) >= 5  # 3 nodes + 2 relations

        # Check that candidate node is created
        candidate_query = [q for q in queries if "Candidat" in q][0]
        assert "CAND_001" in candidate_query
        assert "Alice" in candidate_query


class TestMainPipeline:
    """Test the main pipeline functions."""

    @pytest.mark.unit
    def test_main_function_missing_file(self, capsys):
        """Test main function when input file is missing."""
        from src.graph_ingestion.ingest import main

        with patch("src.graph_ingestion.ingest.Path.exists", return_value=False):
            result = main()

        assert result == 1  # Error code
        captured = capsys.readouterr()
        assert "n'existe pas" in captured.out

    @pytest.mark.unit
    def test_main_function_success(self, capsys):
        """Test successful execution of main function."""
        from src.graph_ingestion.ingest import main

        sample_data = {
            "documents": [
                {
                    "parsed_data": {
                        "extracted_data": {
                            "profile": {
                                "basics": {
                                    "first_name": "John",
                                    "last_name": "Doe",
                                    "emails": ["john@example.com"],
                                }
                            }
                        }
                    }
                }
            ]
        }

        with (
            patch("src.graph_ingestion.ingest.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(sample_data))),
            patch("src.graph_ingestion.ingest.call_harmonizer", return_value={}),
            patch("src.graph_ingestion.ingest.call_entity_resolver", return_value={}),
        ):
            result = main()

        assert result == 0  # Success
        captured = capsys.readouterr()
        assert "PIPELINE TERMINÉ AVEC SUCCÈS" in captured.out

    @pytest.mark.unit
    def test_handle_empty_cv_data(self):
        """Test handling of CV with missing documents."""
        from src.graph_ingestion.ingest import process_parsed_cv

        cv_data = {"documents": []}  # Empty documents

        with pytest.raises(ValueError, match="Aucun document trouvé"):
            process_parsed_cv(cv_data)

    @pytest.mark.unit
    def test_handle_special_characters(self):
        """Test handling of special characters in Cypher generation."""
        from src.graph_ingestion.ingest import escape_cypher_string, generate_cypher_queries

        # Test escaping directly
        escaped = escape_cypher_string("O'Connell")
        assert escaped == "O\\'Connell"

        # Test in context of query generation
        graph_data = {
            "nodes": [
                {
                    "label": "Candidat",
                    "properties": {
                        "id": "TEST_123",
                        "firstName": "O'Connell",
                        "lastName": 'Jane "JJ"',
                    },
                }
            ],
            "relations": [],
        }

        queries = generate_cypher_queries(graph_data)
        assert len(queries) > 0
        # Verify escaping in generated query
        assert "O\\'Connell" in queries[0]
