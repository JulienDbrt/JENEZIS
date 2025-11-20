"""Configuration management using Pydantic Settings."""
import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.
    """
    # API KEYS & SECURITY
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None

    # LLM & EMBEDDING & RAG CONFIG
    LLM_PROVIDER: Literal["openai", "anthropic", "openrouter"] = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536
    EMBEDDING_BATCH_SIZE: int = 128
    EXTRACTION_MODEL: str = "gpt-3.5-turbo"
    GENERATOR_MODEL: str = "gpt-4-turbo"
    RRF_K: int = 60

    # INGESTION CONFIG
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    ENTITY_RESOLUTION_THRESHOLD: int = 85

    # DATABASE & STORAGE CONFIG
    METADATA_STORE_URL: str = "sqlite+aiosqlite:///./doublehelix.db"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str
    NEO4J_DATABASE: str = "neo4j"

    S3_ENDPOINT_URL: str | None = None
    S3_AWS_ACCESS_KEY_ID: str
    S3_AWS_SECRET_ACCESS_KEY: str
    S3_BUCKET_NAME: str
    S3_REGION_NAME: str = "us-east-1"

    # CELERY & REDIS CONFIG
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # RAGAS EVALUATION
    RAGAS_FAITHFULNESS_THRESHOLD: float = 0.85
    RAGAS_CONTEXT_RECALL_THRESHOLD: float = 0.80

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached instance of the application settings.
    This function is intended to be used as a FastAPI dependency.
    """
    return Settings()
