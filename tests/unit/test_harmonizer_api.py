#!/usr/bin/env python3
"""
Comprehensive unit tests for the Harmonizer API.
Tests all endpoints, error handling, cache mechanisms, and LLM integration.
"""

from unittest.mock import Mock, patch

import pytest


class TestHarmonizerAPI:
    """Test suite for Harmonizer API endpoints and functionality."""

    # ========================================================================
    # Test /harmonize endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_known_skills(self, harmonizer_client):
        """Test harmonization with known skills from the ontology."""
        response = harmonizer_client.post(
            "/harmonize", json={"skills": ["Python", "JS", "react.js", "ML"]}
        )

        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert len(data["results"]) == 4

        # Check first skill - Python
        assert data["results"][0]["original_skill"] == "Python"
        assert data["results"][0]["canonical_skill"] == "python"
        assert data["results"][0]["is_known"] is True

        # Check JS alias
        assert data["results"][1]["original_skill"] == "JS"
        assert data["results"][1]["canonical_skill"] == "javascript"
        assert data["results"][1]["is_known"] is True

        # Check react.js alias
        assert data["results"][2]["original_skill"] == "react.js"
        assert data["results"][2]["canonical_skill"] == "react"
        assert data["results"][2]["is_known"] is True

        # Check ML alias
        assert data["results"][3]["original_skill"] == "ML"
        assert data["results"][3]["canonical_skill"] == "machine_learning"
        assert data["results"][3]["is_known"] is True

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_unknown_skills(self, harmonizer_client):
        """Test harmonization with unknown skills."""
        response = harmonizer_client.post(
            "/harmonize", json={"skills": ["rust", "golang", "kotlin"]}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 3
        for i, skill in enumerate(["rust", "golang", "kotlin"]):
            assert data["results"][i]["original_skill"] == skill
            assert data["results"][i]["canonical_skill"] == skill.lower()
            assert data["results"][i]["is_known"] is False

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_mixed_skills(self, harmonizer_client):
        """Test harmonization with a mix of known and unknown skills."""
        response = harmonizer_client.post(
            "/harmonize", json={"skills": ["python", "unknown_framework", "javascript"]}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 3
        assert data["results"][0]["is_known"] is True
        assert data["results"][1]["is_known"] is False
        assert data["results"][2]["is_known"] is True

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_empty_list(self, harmonizer_client):
        """Test harmonization with empty skill list."""
        response = harmonizer_client.post("/harmonize", json={"skills": []})

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_case_insensitive(self, harmonizer_client):
        """Test that harmonization is case-insensitive."""
        skills_variations = ["PYTHON", "Python", "python", "PythoN"]
        response = harmonizer_client.post("/harmonize", json={"skills": skills_variations})

        assert response.status_code == 200
        data = response.json()

        for result in data["results"]:
            assert result["canonical_skill"] == "python"
            assert result["is_known"] is True

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_whitespace_handling(self, harmonizer_client):
        """Test harmonization handles whitespace correctly."""
        response = harmonizer_client.post(
            "/harmonize", json={"skills": ["  python  ", "\tjavascript\n", " react "]}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["results"][0]["canonical_skill"] == "python"
        assert data["results"][1]["canonical_skill"] == "javascript"
        assert data["results"][2]["canonical_skill"] == "react"

    # ========================================================================
    # Test /suggest endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_exact_match(self, harmonizer_client):
        """Test suggestions for an exact match returns the skill."""
        response = harmonizer_client.post("/suggest", json={"skill": "python", "top_k": 3})

        assert response.status_code == 200
        data = response.json()

        assert data["original_skill"] == "python"
        assert data["method"] == "exact_match"
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["canonical_name"] == "python"
        assert data["suggestions"][0]["similarity_score"] == 1.0
        assert "programming_languages" in data["suggestions"][0]["parents"]

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_string_similarity(self, harmonizer_client):
        """Test string similarity-based suggestions."""
        response = harmonizer_client.post(
            "/suggest", json={"skill": "pytho", "top_k": 3, "use_llm": False}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["method"] == "string_similarity"
        assert len(data["suggestions"]) > 0
        # Python should be the top suggestion due to high similarity
        assert "python" in [s["canonical_name"] for s in data["suggestions"]]

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_with_llm(self, harmonizer_client, mock_openai_client, mock_env_with_openai):
        """Test LLM-based skill suggestions."""
        # Mock the OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content='["python", "javascript", "react"]'))]
        mock_openai_client.chat.completions.create.return_value = mock_response

        with patch("api.main.openai.OpenAI", return_value=mock_openai_client):
            response = harmonizer_client.post(
                "/suggest", json={"skill": "web development", "top_k": 3, "use_llm": True}
            )

        assert response.status_code == 200
        data = response.json()

        assert data["method"] == "llm"
        assert len(data["suggestions"]) == 3
        suggested_names = [s["canonical_name"] for s in data["suggestions"]]
        assert "python" in suggested_names
        assert "javascript" in suggested_names
        assert "react" in suggested_names

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_llm_fallback_to_similarity(self, harmonizer_client):
        """Test fallback to string similarity when LLM fails."""
        response = harmonizer_client.post(
            "/suggest", json={"skill": "javscript", "top_k": 2, "use_llm": True}
        )

        assert response.status_code == 200
        data = response.json()

        # Should fallback to string similarity since no API key
        assert data["method"] == "string_similarity"
        assert len(data["suggestions"]) > 0
        # JavaScript should be suggested due to similarity
        assert "javascript" in [s["canonical_name"] for s in data["suggestions"]]

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_top_k_limit(self, harmonizer_client):
        """Test that top_k parameter limits the number of suggestions."""
        for k in [1, 2, 5]:
            response = harmonizer_client.post("/suggest", json={"skill": "programming", "top_k": k})

            assert response.status_code == 200
            data = response.json()
            assert len(data["suggestions"]) <= k

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_low_similarity_threshold(self, harmonizer_client):
        """Test that low similarity matches are filtered out."""
        response = harmonizer_client.post("/suggest", json={"skill": "xyz123", "top_k": 10})

        assert response.status_code == 200
        data = response.json()

        # Should have few or no suggestions due to low similarity
        for suggestion in data["suggestions"]:
            assert suggestion["similarity_score"] > 0.3

    # ========================================================================
    # Test /stats endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_stats_endpoint(self, harmonizer_client):
        """Test the statistics endpoint returns correct counts."""
        response = harmonizer_client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        assert "total_skills" in data
        assert "total_aliases" in data
        assert "total_relations" in data

        # Based on our test data
        assert data["total_skills"] == 7  # Based on test fixture
        assert data["total_aliases"] == 11  # Based on test fixture
        assert data["total_relations"] == 5  # Based on test fixture

    # ========================================================================
    # Test /admin/reload endpoint
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_admin_reload_cache(self, harmonizer_client, temp_ontology_db, auth_headers):
        """Test cache reload functionality."""
        # First reload
        response = harmonizer_client.post("/admin/reload", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"] == "Cache reloaded"
        assert "alias_count" in data
        initial_count = data["alias_count"]

        # Add a new skill to the database
        import sqlite3

        conn = sqlite3.connect(temp_ontology_db)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO skills (canonical_name) VALUES ('new_skill')")
        cursor.execute(
            "INSERT INTO aliases (alias_name, skill_id) VALUES ('new_skill', last_insert_rowid())"
        )
        conn.commit()
        conn.close()

        # Reload again
        response = harmonizer_client.post("/admin/reload", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["alias_count"] == initial_count + 1

    # ========================================================================
    # Test error handling
    # ========================================================================

    @pytest.mark.unit
    @pytest.mark.api
    def test_harmonize_invalid_request_body(self, harmonizer_client):
        """Test harmonize endpoint with invalid request body."""
        # Missing required field
        response = harmonizer_client.post("/harmonize", json={})
        assert response.status_code == 422

        # Wrong type for skills field
        response = harmonizer_client.post("/harmonize", json={"skills": "not_a_list"})
        assert response.status_code == 422

    @pytest.mark.unit
    @pytest.mark.api
    def test_suggest_invalid_request_body(self, harmonizer_client):
        """Test suggest endpoint with invalid request body."""
        # Missing required field
        response = harmonizer_client.post("/suggest", json={})
        assert response.status_code == 422

        # Invalid top_k value
        response = harmonizer_client.post(
            "/suggest", json={"skill": "python", "top_k": "not_a_number"}
        )
        assert response.status_code == 422

    # ========================================================================
    # Test cache mechanisms
    # ========================================================================

    @pytest.mark.unit
    def test_cache_loading_with_empty_db(self, monkeypatch):
        """Test cache loading with empty database."""
        import tempfile

        from api.main import load_ontology_cache

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db = f.name

        import sqlite3

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Create empty tables
        cursor.execute(
            """CREATE TABLE skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT UNIQUE NOT NULL
        )"""
        )
        cursor.execute(
            """CREATE TABLE aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias_name TEXT UNIQUE NOT NULL,
            skill_id INTEGER NOT NULL
        )"""
        )
        cursor.execute(
            """CREATE TABLE hierarchy (
            child_id INTEGER NOT NULL,
            parent_id INTEGER NOT NULL
        )"""
        )
        conn.commit()
        conn.close()

        import api.main

        api.main.DB_FILE = temp_db

        # Load cache - should handle empty DB gracefully
        load_ontology_cache()

        assert len(api.main.ALIAS_CACHE) == 0
        assert len(api.main.SKILLS_CACHE) == 0
        assert len(api.main.HIERARCHY_CACHE) == 0

    @pytest.mark.unit
    def test_cache_loading_with_missing_db(self, monkeypatch, capsys):
        """Test cache loading when database file doesn't exist."""
        import api.main
        from api.main import load_ontology_cache

        api.main.DB_FILE = "/non/existent/database.db"

        # Should handle missing DB gracefully
        load_ontology_cache()

        captured = capsys.readouterr()
        assert "Erreur critique" in captured.out

        # Caches should be empty
        assert api.main.ALIAS_CACHE == {}
        assert api.main.SKILLS_CACHE == {}
        assert api.main.HIERARCHY_CACHE == {}

    # ========================================================================
    # Test LLM integration
    # ========================================================================

    @pytest.mark.unit
    def test_get_llm_suggestions_no_api_key(self, harmonizer_client):
        """Test LLM suggestions without API key returns empty list."""
        from api.main import get_llm_suggestions

        suggestions = get_llm_suggestions("test_skill", top_k=3)
        assert suggestions == []

    @pytest.mark.unit
    def test_get_llm_suggestions_with_error(self, mock_env_with_openai):
        """Test LLM suggestions handles errors gracefully."""
        from api.main import get_llm_suggestions

        with patch("api.main.openai.OpenAI") as mock_openai:
            mock_openai.side_effect = Exception("API Error")

            suggestions = get_llm_suggestions("test_skill", top_k=3)
            assert suggestions == []

    @pytest.mark.unit
    def test_get_llm_suggestions_invalid_json(self, mock_env_with_openai):
        """Test LLM suggestions handles invalid JSON response."""
        from api.main import get_llm_suggestions

        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="not valid json"))]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("api.main.openai.OpenAI", return_value=mock_client):
            suggestions = get_llm_suggestions("test_skill", top_k=3)
            assert suggestions == []

    # ========================================================================
    # Test string similarity function
    # ========================================================================

    @pytest.mark.unit
    def test_calculate_string_similarity(self):
        """Test string similarity calculation."""
        from api.main import calculate_string_similarity

        # Exact match
        assert calculate_string_similarity("python", "python") == 1.0

        # Case insensitive
        assert calculate_string_similarity("Python", "PYTHON") == 1.0

        # Similar strings
        similarity = calculate_string_similarity("javascript", "javscript")
        assert 0.8 < similarity < 1.0

        # Very different strings
        similarity = calculate_string_similarity("python", "rust")
        assert similarity < 0.5

        # Empty strings
        assert calculate_string_similarity("", "") == 1.0
        assert calculate_string_similarity("python", "") == 0.0
