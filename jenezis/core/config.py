"""Configuration management using Pydantic Settings."""
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret_file(env_var_name: str) -> str | None:
    """
    Read a secret from a Docker secret file.

    Docker secrets are mounted at /run/secrets/<name> and can be referenced
    via environment variables ending in _FILE (e.g., POSTGRES_PASSWORD_FILE).

    Args:
        env_var_name: The name of the environment variable (without _FILE suffix)

    Returns:
        The secret value if found, None otherwise
    """
    file_env_var = f"{env_var_name}_FILE"
    secret_path = os.environ.get(file_env_var)

    if secret_path:
        path = Path(secret_path)
        if path.exists() and path.is_file():
            return path.read_text().strip()

    return None


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.

    SECURITY: Supports Docker secrets via _FILE environment variables.
    If OPENAI_API_KEY_FILE is set, it reads from that file path.
    """
    # API KEYS & SECURITY
    INITIAL_ADMIN_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None

    @field_validator('OPENAI_API_KEY', mode='before')
    @classmethod
    def load_openai_key_from_secret(cls, v):
        """Load OPENAI_API_KEY from Docker secret file if available."""
        secret = _read_secret_file('OPENAI_API_KEY')
        return secret if secret else v

    @field_validator('ANTHROPIC_API_KEY', mode='before')
    @classmethod
    def load_anthropic_key_from_secret(cls, v):
        """Load ANTHROPIC_API_KEY from Docker secret file if available."""
        secret = _read_secret_file('ANTHROPIC_API_KEY')
        return secret if secret else v

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
    METADATA_STORE_URL: str = "sqlite+aiosqlite:///./jenezis.db"

    # FalkorDB (Graph Database - replaces Neo4j)
    FALKOR_HOST: str = "localhost"
    FALKOR_PORT: int = 6379
    FALKOR_PASSWORD: str | None = None
    FALKOR_GRAPH: str = "jenezis"

    @field_validator('FALKOR_PASSWORD', mode='before')
    @classmethod
    def load_falkor_password_from_secret(cls, v):
        """Load FALKOR_PASSWORD from Docker secret file if available."""
        secret = _read_secret_file('FALKOR_PASSWORD')
        return secret if secret else v

    # DEPRECATED: Neo4j settings (kept for migration, will be removed)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"

    @field_validator('NEO4J_PASSWORD', mode='before')
    @classmethod
    def load_neo4j_password_from_secret(cls, v):
        """Load NEO4J_PASSWORD from Docker secret file if available."""
        secret = _read_secret_file('NEO4J_PASSWORD')
        return secret if secret else v

    S3_ENDPOINT_URL: str | None = None
    S3_AWS_ACCESS_KEY_ID: str = ""
    S3_AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = "jenezis-documents"
    S3_REGION_NAME: str = "us-east-1"

    @field_validator('S3_AWS_SECRET_ACCESS_KEY', mode='before')
    @classmethod
    def load_s3_secret_from_secret(cls, v):
        """Load S3_AWS_SECRET_ACCESS_KEY from Docker secret file if available."""
        secret = _read_secret_file('S3_AWS_SECRET_ACCESS_KEY')
        return secret if secret else v

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
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached instance of the application settings.
    This function is intended to be used as a FastAPI dependency.
    """
    return Settings()
