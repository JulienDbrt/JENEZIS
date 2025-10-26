"""
PostgreSQL connection management with pooling and async support.

Replaces SQLite connections with production-ready PostgreSQL.
"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

# PostgreSQL connection URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jenezis:jenezis@localhost:5433/jenezis")

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,  # Base pool size
    max_overflow=40,  # Maximum overflow connections
    pool_timeout=30,  # Connection timeout in seconds
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_pre_ping=True,  # Verify connections before using
    echo=False,  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Engine, "connect")
def set_postgres_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
    """Set PostgreSQL session parameters on connection."""
    cursor = dbapi_connection.cursor()
    # Enable statement timeout (30 seconds)
    cursor.execute("SET statement_timeout = '30s'")
    # Set timezone to UTC
    cursor.execute("SET timezone = 'UTC'")
    cursor.close()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Get database session with automatic cleanup.

    Yields:
        Session: SQLAlchemy session

    Example:
        with get_db() as db:
            skills = db.query(Skill).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database schema.

    Creates all tables defined in postgres_models.py.
    Also enables pgvector extension.
    """
    from src.db.postgres_models import Base

    # Enable pgvector extension
    with engine.connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()

    # Create all tables
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all database tables. USE WITH CAUTION."""
    from src.db.postgres_models import Base

    Base.metadata.drop_all(bind=engine)


# ============================================================================
# ASYNC SUPPORT (for FastAPI background tasks)
# ============================================================================

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Async engine for non-blocking operations
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_recycle=3600,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_async_db() -> AsyncSession:
    """
    Get async database session for FastAPI dependencies.

    Yields:
        AsyncSession: Async SQLAlchemy session

    Example:
        @app.get("/skills")
        async def get_skills(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(Skill))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
