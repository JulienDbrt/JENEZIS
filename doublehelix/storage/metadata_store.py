"""SQLAlchemy models for the Canonical Store and metadata tracking."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, Text, ForeignKey, Boolean, Float
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from pgvector.sqlalchemy import Vector as VECTOR

from doublehelix.core.config import get_settings

settings = get_settings()
Base = declarative_base()

# --- Core Models for Ingestion and Status Tracking ---

class DocumentStatus(enum.Enum):
    PENDING = "PENDING"; PROCESSING = "PROCESSING"; COMPLETED = "COMPLETED"
    FAILED = "FAILED"; UPDATING = "UPDATING"; DELETING = "DELETING"

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    document_hash = Column(String(64), nullable=False, unique=True, index=True)
    s3_path = Column(String, nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    error_log = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    domain_config_id = Column(Integer, ForeignKey('domain_configs.id'), nullable=False)
    domain_config = relationship("DomainConfig", back_populates="documents")

class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# --- Neuro-Symbolic Foundation Models ---

class DomainConfig(Base):
    """Stores the user-defined 'worldview' (ontology, rules) for an entire domain."""
    __tablename__ = "domain_configs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    schema_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    documents = relationship("Document", back_populates="domain_config")

class CanonicalNode(Base):
    """The 'Canonical Store' - a single source of truth for every known entity."""
    __tablename__ = "canonical_nodes"
    id = Column(Integer, primary_key=True, index=True)
    node_type = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False, unique=True)
    embedding = Column(VECTOR(settings.EMBEDDING_DIMENSIONS), nullable=False)
    aliases = relationship("NodeAlias", back_populates="canonical_node")

class NodeAlias(Base):
    """Maps a raw extracted string (alias) to a canonical node."""
    __tablename__ = "node_aliases"
    id = Column(Integer, primary_key=True, index=True)
    alias = Column(String, nullable=False, unique=True, index=True)
    canonical_node_id = Column(Integer, ForeignKey('canonical_nodes.id'), nullable=False)
    confidence_score = Column(Float, nullable=False, default=1.0)
    canonical_node = relationship("CanonicalNode", back_populates="aliases")

class EnrichmentStatus(enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class EnrichmentQueueItem(Base):
    """Stores unresolved entities for asynchronous enrichment."""
    __tablename__ = "enrichment_queue"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False)
    context_chunk = Column(Text, nullable=True)
    status = Column(Enum(EnrichmentStatus), default=EnrichmentStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

# --- Helper Functions (remain largely the same) ---

async def get_api_key_by_hash(db: AsyncSession, key_hash: str) -> APIKey | None:
    result = await db.execute(select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True))
    return result.scalars().first()

async def get_document_by_hash(db: AsyncSession, doc_hash: str) -> Document | None:
    result = await db.execute(select(Document).where(Document.document_hash == doc_hash))
    return result.scalars().first()

async def get_document_by_id(db: AsyncSession, doc_id: int) -> Document | None:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalars().first()

async def update_document_status(db: AsyncSession, doc_id: int, status: DocumentStatus, error_message: str | None = None) -> Document | None:
    doc = await get_document_by_id(db, doc_id)
    if doc:
        doc.status = status; doc.error_log = error_message
        await db.commit(); await db.refresh(doc)
    return doc
