#!/usr/bin/env python3
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, load_ontology_cache


@pytest.fixture
def test_db():
    """Crée une base de test temporaire."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        pass

    conn = sqlite3.connect(temp_db.name)
    cursor = conn.cursor()

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
        skill_id INTEGER NOT NULL,
        FOREIGN KEY (skill_id) REFERENCES skills(id)
    )"""
    )

    cursor.execute(
        """CREATE TABLE hierarchy (
        child_id INTEGER NOT NULL,
        parent_id INTEGER NOT NULL,
        PRIMARY KEY (child_id, parent_id)
    )"""
    )

    cursor.execute("INSERT INTO skills (id, canonical_name) VALUES (1, 'python')")
    cursor.execute("INSERT INTO skills (id, canonical_name) VALUES (2, 'javascript')")
    cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('python', 1)")
    cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('py', 1)")
    cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('javascript', 2)")
    cursor.execute("INSERT INTO aliases (alias_name, skill_id) VALUES ('js', 2)")

    conn.commit()
    conn.close()

    yield temp_db.name

    Path(temp_db.name).unlink()


@pytest.fixture
def auth_headers():
    """Headers d'authentification pour les tests admin."""
    # Utiliser un token de test ou mocker l'authentification
    os.environ["API_AUTH_TOKEN"] = "test_token_123"
    return {"Authorization": "Bearer test_token_123"}


@pytest.fixture
def client(test_db, monkeypatch):
    """Client de test avec DB temporaire."""
    monkeypatch.setattr("src.api.main.DB_FILE", test_db)
    # Mock auth for tests
    os.environ["API_AUTH_TOKEN"] = "test_token_123"
    load_ontology_cache()
    return TestClient(app)


def test_harmonize_known_skills(client):
    """Test avec des compétences connues."""
    response = client.post("/harmonize", json={"skills": ["Python", "JS", "py"]})
    assert response.status_code == 200
    data = response.json()

    assert len(data["results"]) == 3
    assert data["results"][0]["canonical_skill"] == "python"
    assert data["results"][0]["is_known"] is True
    assert data["results"][1]["canonical_skill"] == "javascript"
    assert data["results"][1]["is_known"] is True
    assert data["results"][2]["canonical_skill"] == "python"
    assert data["results"][2]["is_known"] is True


def test_harmonize_unknown_skills(client):
    """Test avec des compétences inconnues."""
    response = client.post("/harmonize", json={"skills": ["rust", "golang"]})
    assert response.status_code == 200
    data = response.json()

    assert len(data["results"]) == 2
    assert data["results"][0]["canonical_skill"] == "rust"
    assert data["results"][0]["is_known"] is False
    assert data["results"][1]["canonical_skill"] == "golang"
    assert data["results"][1]["is_known"] is False


def test_harmonize_mixed_skills(client):
    """Test avec un mix de compétences."""
    response = client.post("/harmonize", json={"skills": ["python", "unknown_skill", "js"]})
    assert response.status_code == 200
    data = response.json()

    assert len(data["results"]) == 3
    assert data["results"][0]["is_known"] is True
    assert data["results"][1]["is_known"] is False
    assert data["results"][2]["is_known"] is True


def test_reload_cache(client, auth_headers):
    """Test du rechargement du cache."""
    response = client.post("/admin/reload", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "alias_count" in data
    assert data["alias_count"] == 4


def test_stats_endpoint(client):
    """Test de l'endpoint de statistiques."""
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_skills"] == 2
    assert data["total_aliases"] == 4
    assert data["total_relations"] == 0
