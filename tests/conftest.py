#!/usr/bin/env python3
"""
Shared pytest fixtures and configuration for all tests.
"""

import json
import sqlite3
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ============================================================================
# Test Data
# ============================================================================

# Test skills data for mocking database responses
TEST_SKILLS = {
    "python": 1,
    "javascript": 2,
    "react": 3,
    "programming_languages": 4,
    "frontend": 5,
    "data_science": 6,
    "machine_learning": 7,
}

TEST_ALIASES = {
    "python": "python",
    "py": "python",
    "python3": "python",
    "javascript": "javascript",
    "js": "javascript",
    "ecmascript": "javascript",
    "react": "react",
    "reactjs": "react",
    "react.js": "react",
    "ml": "machine_learning",
    "machine learning": "machine_learning",
}

TEST_HIERARCHY = {
    "python": ["programming_languages"],
    "javascript": ["programming_languages"],
    "react": ["javascript", "frontend"],
    "machine_learning": ["data_science"],
}

# Test entity data
TEST_ENTITIES = {
    "google": {"canonical_id": "google", "canonical_name": "Google", "entity_type": "COMPANY"},
    "google inc": {"canonical_id": "google", "canonical_name": "Google", "entity_type": "COMPANY"},
    "google llc": {"canonical_id": "google", "canonical_name": "Google", "entity_type": "COMPANY"},
    "microsoft": {"canonical_id": "microsoft", "canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
    "microsoft corp": {"canonical_id": "microsoft", "canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
    "msft": {"canonical_id": "microsoft", "canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
    "bnp": {"canonical_id": "bnp_paribas", "canonical_name": "BNP Paribas", "entity_type": "COMPANY"},
    "bnp paribas": {"canonical_id": "bnp_paribas", "canonical_name": "BNP Paribas", "entity_type": "COMPANY"},
    "polytechnique": {"canonical_id": "ecole_polytechnique", "canonical_name": "École Polytechnique", "entity_type": "SCHOOL"},
    "x": {"canonical_id": "ecole_polytechnique", "canonical_name": "École Polytechnique", "entity_type": "SCHOOL"},
    "massachusetts institute of technology": {"canonical_id": "mit", "canonical_name": "MIT", "entity_type": "SCHOOL"},
    "mit": {"canonical_id": "mit", "canonical_name": "MIT", "entity_type": "SCHOOL"},
}


# ============================================================================
# Database Fixtures (SQLite for legacy tests)
# ============================================================================


@pytest.fixture
def temp_ontology_db() -> Generator[str, None, None]:
    """Create a temporary ontology database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = f.name

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Create schema
    cursor.execute(
        """
        CREATE TABLE skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias_name TEXT UNIQUE NOT NULL,
            skill_id INTEGER NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE hierarchy (
            child_id INTEGER NOT NULL,
            parent_id INTEGER NOT NULL,
            PRIMARY KEY (child_id, parent_id),
            FOREIGN KEY (child_id) REFERENCES skills(id),
            FOREIGN KEY (parent_id) REFERENCES skills(id)
        )
    """
    )

    # Add indexes
    cursor.execute("CREATE INDEX idx_aliases_name ON aliases(alias_name)")
    cursor.execute("CREATE INDEX idx_hierarchy_child ON hierarchy(child_id)")
    cursor.execute("CREATE INDEX idx_hierarchy_parent ON hierarchy(parent_id)")

    # Insert test data
    test_skills = [
        (1, "python"),
        (2, "javascript"),
        (3, "react"),
        (4, "programming_languages"),
        (5, "frontend"),
        (6, "data_science"),
        (7, "machine_learning"),
    ]

    cursor.executemany("INSERT INTO skills (id, canonical_name) VALUES (?, ?)", test_skills)

    test_aliases = [
        ("python", 1),
        ("py", 1),
        ("python3", 1),
        ("javascript", 2),
        ("js", 2),
        ("ecmascript", 2),
        ("react", 3),
        ("reactjs", 3),
        ("react.js", 3),
        ("ml", 7),
        ("machine learning", 7),
    ]

    cursor.executemany("INSERT INTO aliases (alias_name, skill_id) VALUES (?, ?)", test_aliases)

    # Add hierarchy
    test_hierarchy = [
        (1, 4),  # python -> programming_languages
        (2, 4),  # javascript -> programming_languages
        (3, 2),  # react -> javascript
        (3, 5),  # react -> frontend
        (7, 6),  # machine_learning -> data_science
    ]

    cursor.executemany("INSERT INTO hierarchy (child_id, parent_id) VALUES (?, ?)", test_hierarchy)

    conn.commit()
    conn.close()

    yield temp_db

    # Cleanup
    Path(temp_db).unlink(missing_ok=True)


@pytest.fixture
def temp_entity_db() -> Generator[str, None, None]:
    """Create a temporary entity resolver database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = f.name

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Create schema
    cursor.execute(
        """
        CREATE TABLE canonical_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_id TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            metadata TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE entity_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias_name TEXT UNIQUE NOT NULL,
            canonical_id INTEGER NOT NULL,
            FOREIGN KEY (canonical_id) REFERENCES canonical_entities(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE enrichment_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_id TEXT UNIQUE NOT NULL,
            entity_type TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            error_message TEXT
        )
    """
    )

    # Insert test data
    test_entities = [
        ("google", "Google", "COMPANY", json.dumps({"sector": "Technology"})),
        ("microsoft", "Microsoft Corporation", "COMPANY", json.dumps({"sector": "Technology"})),
        ("bnp_paribas", "BNP Paribas", "COMPANY", json.dumps({"sector": "Finance"})),
        (
            "ecole_polytechnique",
            "École Polytechnique",
            "SCHOOL",
            json.dumps({"type": "University"}),
        ),
        ("mit", "MIT", "SCHOOL", json.dumps({"type": "University", "location": "USA"})),
    ]

    for canonical_id, display_name, entity_type, metadata in test_entities:
        cursor.execute(
            "INSERT INTO canonical_entities (canonical_id, display_name, entity_type, metadata) VALUES (?, ?, ?, ?)",
            (canonical_id, display_name, entity_type, metadata),
        )

    test_aliases = [
        ("google", 1),
        ("google inc", 1),
        ("google llc", 1),
        ("microsoft", 2),
        ("microsoft corp", 2),
        ("msft", 2),
        ("bnp", 3),
        ("bnp paribas", 3),
        ("polytechnique", 4),
        ("x", 4),
        ("massachusetts institute of technology", 5),
        ("mit", 5),
    ]

    cursor.executemany(
        "INSERT INTO entity_aliases (alias_name, canonical_id) VALUES (?, ?)", test_aliases
    )

    conn.commit()
    conn.close()

    yield temp_db

    # Cleanup
    Path(temp_db).unlink(missing_ok=True)


# ============================================================================
# API Client Fixtures
# ============================================================================


@pytest.fixture
def harmonizer_client(monkeypatch) -> TestClient:
    """Create a test client for the Harmonizer API with mocked database."""
    import os

    os.environ["API_AUTH_TOKEN"] = "test_token_123"

    # Import and patch the API module
    import api.main
    from api.main import app

    # Set up in-memory caches with test data
    api.main.ALIAS_CACHE = TEST_ALIASES.copy()
    api.main.SKILLS_CACHE = TEST_SKILLS.copy()
    api.main.HIERARCHY_CACHE = TEST_HIERARCHY.copy()

    # Reinitialize auth middleware with test token
    from api.auth import auth

    auth.auth_token = "test_token_123"
    auth.is_enabled = True

    return TestClient(app)


@pytest.fixture
def entity_resolver_client(monkeypatch) -> TestClient:
    """Create a test client for the Entity Resolver API with mocked database."""
    import os

    os.environ["API_AUTH_TOKEN"] = "test_token_123"

    # Import and patch the API module
    import entity_resolver.api
    from entity_resolver.api import app

    # Set up in-memory cache with test data
    entity_resolver.api.ENTITY_ALIAS_CACHE = TEST_ENTITIES.copy()
    entity_resolver.api.CANONICAL_ENTITIES = {
        "google": {"canonical_name": "Google", "entity_type": "COMPANY"},
        "microsoft": {"canonical_name": "Microsoft Corporation", "entity_type": "COMPANY"},
        "bnp_paribas": {"canonical_name": "BNP Paribas", "entity_type": "COMPANY"},
        "ecole_polytechnique": {"canonical_name": "École Polytechnique", "entity_type": "SCHOOL"},
        "mit": {"canonical_name": "MIT", "entity_type": "SCHOOL"},
    }

    # Reinitialize auth middleware with test token
    from api.auth import auth

    auth.auth_token = "test_token_123"
    auth.is_enabled = True

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authentication headers for admin endpoints."""
    return {"Authorization": "Bearer test_token_123"}


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing LLM features."""
    with patch("openai.OpenAI") as mock_openai:
        mock_client = Mock()
        mock_openai.return_value = mock_client

        # Mock chat completion response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content='["python", "javascript", "react"]'))]
        mock_client.chat.completions.create.return_value = mock_response

        yield mock_client


@pytest.fixture
def mock_env_with_openai(monkeypatch):
    """Set up environment with mock OpenAI API key."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-123")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")


# ============================================================================
# Data Fixtures
# ============================================================================


@pytest.fixture
def sample_cv_data() -> dict[str, Any]:
    """Sample CV data for testing graph ingestion."""
    return {
        "candidat": {"nom": "Doe", "prenom": "John", "email": "john.doe@example.com"},
        "experiences": [
            {
                "entreprise": "Google",
                "poste": "Software Engineer",
                "date_debut": "2020-01-01",
                "date_fin": "2023-01-01",
                "competences": ["Python", "JavaScript", "React"],
            }
        ],
        "formations": [
            {
                "ecole": "MIT",
                "diplome": "Master's in Computer Science",
                "date_obtention": "2019-06-01",
            }
        ],
    }


@pytest.fixture
def sample_dataframe() -> pd.DataFrame:
    """Sample DataFrame for testing pandas operations."""
    return pd.DataFrame(
        {
            "skill": ["Python", "JavaScript", "React", "Unknown_Skill"],
            "frequency": [100, 80, 60, 5],
            "canonical": ["python", "javascript", "react", None],
        }
    )


@pytest.fixture
def sample_excel_file() -> Generator[str, None, None]:
    """Create a temporary Excel file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        temp_file = f.name

    df = pd.DataFrame(
        {
            "skill": ["Python", "JavaScript", "React"],
            "count": [100, 80, 60],
            "canonical_name": ["python", "javascript", "react"],
            "aliases": ["py,python3", "js,ecmascript", "reactjs,react.js"],
            "parents": ["programming_languages", "programming_languages", "frontend,javascript"],
            "approve": ["OUI", "OUI", "NON"],
        }
    )

    df.to_excel(temp_file, index=False)

    yield temp_file

    # Cleanup
    Path(temp_file).unlink(missing_ok=True)


# ============================================================================
# Utility Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_environment(monkeypatch):
    """Reset environment variables for each test."""
    # Clear any existing env vars that might interfere
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)


@pytest.fixture
def capture_logs():
    """Capture log output for testing."""
    import logging
    from io import StringIO

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)

    # Get root logger
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    yield log_capture

    # Clean up
    logger.removeHandler(handler)


@pytest.fixture
def mock_requests():
    """Mock requests library for external API calls."""
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_get.return_value = mock_response
        yield mock_get
