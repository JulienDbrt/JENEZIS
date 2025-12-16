"""
Adversarial test specific fixtures.
"""
import pytest


@pytest.fixture
def dangerous_cypher_patterns() -> list[str]:
    """Patterns that should never appear in Cypher queries from user input."""
    return [
        "DETACH DELETE",
        "DROP ",
        "CREATE INDEX",
        "DROP INDEX",
        "CREATE CONSTRAINT",
        "DROP CONSTRAINT",
        "apoc.trigger",
        "apoc.export",
        "apoc.import",
        "LOAD CSV",
        "CALL db.index.fulltext.drop",
        "CALL dbms.",
        "CALL db.clearQueryCaches",
    ]


@pytest.fixture
def safe_entity_type_pattern() -> str:
    """Regex pattern for safe entity types (alphanumeric + underscore only)."""
    return r"^[A-Za-z][A-Za-z0-9_]*$"
