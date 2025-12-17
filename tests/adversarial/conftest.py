"""
Adversarial test specific fixtures.
"""
import os
import pytest
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from jenezis.storage.metadata_store import Base


# Real PostgreSQL for high-contention tests (requires docker container on port 5433)
REAL_POSTGRES_URL = "postgresql+asyncpg://test:test@localhost:5433/test"


@pytest.fixture
async def real_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Creates a real PostgreSQL session for tests requiring actual DB behavior.

    Requires: docker run -d --name jenezis-test-postgres -e POSTGRES_USER=test
              -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test -p 5433:5432 pgvector/pgvector:pg16
    """
    engine = create_async_engine(REAL_POSTGRES_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session
        await session.rollback()

    # Cleanup tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


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
