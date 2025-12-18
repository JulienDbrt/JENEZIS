"""
Factories and connection managers for external services like databases and S3.
Ensures that connections are handled cleanly and efficiently.
"""
import logging
from contextlib import asynccontextmanager

import boto3
from botocore.client import Config
from celery import Celery
from neo4j import AsyncGraphDatabase
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from jenezis.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# --- Celery App ---
celery_app = Celery(
    "jenezis",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["examples.fastapi_app.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)


# --- Metadata Store (SQLAlchemy) ---
# Use NullPool to avoid connection sharing issues in forked Celery workers
# NullPool creates new connections each time and closes them immediately after use
try:
    sql_engine = create_async_engine(
        settings.METADATA_STORE_URL,
        poolclass=NullPool,  # Critical for Celery worker compatibility
    )
    AsyncSessionFactory = async_sessionmaker(
        sql_engine, expire_on_commit=False, class_=AsyncSession
    )
    logger.info("Successfully created SQLAlchemy engine and session factory.")
except Exception as e:
    logger.error(f"Failed to create SQLAlchemy engine: {e}", exc_info=True)
    sql_engine = None
    AsyncSessionFactory = None

async def get_db_session_dep():
    """FastAPI dependency for database sessions. Use with Depends(get_db_session_dep)."""
    if AsyncSessionFactory is None:
        raise RuntimeError("Database not initialized. Check METADATA_STORE_URL.")

    session = AsyncSessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

@asynccontextmanager
async def get_db_session():
    """Async context manager for database sessions. Use with 'async with get_db_session()'."""
    if AsyncSessionFactory is None:
        raise RuntimeError("Database not initialized. Check METADATA_STORE_URL.")

    session = AsyncSessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# --- Graph Store (Neo4j) ---
try:
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        database=settings.NEO4J_DATABASE,
    )
    logger.info("Successfully created Neo4j driver.")
except Exception as e:
    logger.error(f"Failed to create Neo4j driver: {e}", exc_info=True)
    neo4j_driver = None

async def get_neo4j_driver():
    """Returns the application-wide Neo4j driver instance."""
    if neo4j_driver is None:
        raise RuntimeError("Neo4j driver not initialized. Check Neo4j connection settings.")
    return neo4j_driver


# --- Document Store (S3) ---
try:
    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_AWS_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION_NAME,
        config=Config(signature_version="s3v4"),
    )
    # Check if bucket exists, create if not
    try:
        s3_client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
        logger.info(f"S3 bucket '{settings.S3_BUCKET_NAME}' already exists.")
    except s3_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            logger.info(f"S3 bucket '{settings.S3_BUCKET_NAME}' not found. Creating it.")
            s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)
        else:
            raise
    logger.info("Successfully created S3 client.")
except Exception as e:
    logger.error(f"Failed to create S3 client: {e}", exc_info=True)
    s3_client = None

def get_s3_client():
    """Returns the application-wide S3 client instance."""
    if s3_client is None:
        raise RuntimeError("S3 client not initialized. Check S3 connection settings.")
    return s3_client


# --- Redis Client ---
try:
    redis_client = Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)
    logger.info("Successfully created Redis client.")
except Exception as e:
    logger.error(f"Failed to create Redis client: {e}", exc_info=True)
    redis_client = None

async def get_redis_client():
    """Returns the application-wide async Redis client instance."""
    if redis_client is None:
        raise RuntimeError("Redis client not initialized. Check CELERY_BROKER_URL.")
    return redis_client


# --- Application Lifecycle ---
async def close_connections():
    """Gracefully closes all connections."""
    if neo4j_driver:
        await neo4j_driver.close()
        logger.info("Neo4j connection closed.")
    if sql_engine:
        await sql_engine.dispose()
        logger.info("SQLAlchemy engine disposed.")
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed.")
