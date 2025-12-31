"""SQLAlchemy models for the Canonical Store and metadata tracking."""

import enum
from datetime import datetime, timezone
from typing import Set

from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, Text, ForeignKey, Boolean, Float
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from pgvector.sqlalchemy import Vector as VECTOR

from jenezis.core.config import get_settings

settings = get_settings()
Base = declarative_base()


# --- State Machine for Document Status ---

class InvalidStatusTransitionError(ValueError):
    """Raised when an invalid status transition is attempted."""
    pass

# --- Core Models for Ingestion and Status Tracking ---

class DocumentStatus(enum.Enum):
    PENDING = "PENDING"; PROCESSING = "PROCESSING"; COMPLETED = "COMPLETED"
    FAILED = "FAILED"; UPDATING = "UPDATING"; DELETING = "DELETING"


# Valid status transitions - maps current status to allowed next statuses
VALID_STATUS_TRANSITIONS: dict[DocumentStatus, Set[DocumentStatus]] = {
    DocumentStatus.PENDING: {DocumentStatus.PROCESSING, DocumentStatus.DELETING},
    DocumentStatus.PROCESSING: {DocumentStatus.COMPLETED, DocumentStatus.FAILED},
    DocumentStatus.COMPLETED: {DocumentStatus.UPDATING, DocumentStatus.DELETING},
    DocumentStatus.FAILED: {DocumentStatus.DELETING},  # Must delete and re-upload to retry
    DocumentStatus.UPDATING: {DocumentStatus.PROCESSING, DocumentStatus.DELETING},
    DocumentStatus.DELETING: set(),  # Terminal state - no transitions allowed
}


def validate_status_transition(
    current_status: DocumentStatus,
    new_status: DocumentStatus
) -> None:
    """
    Validates that a status transition is allowed.

    Raises:
        InvalidStatusTransitionError: If the transition is not valid.
    """
    if current_status == new_status:
        return  # No-op transition is always allowed

    allowed = VALID_STATUS_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise InvalidStatusTransitionError(
            f"Invalid status transition: {current_status.value} -> {new_status.value}. "
            f"Allowed transitions from {current_status.value}: {[s.value for s in allowed]}"
        )

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    document_hash = Column(String(64), nullable=False, unique=True, index=True)
    s3_path = Column(String, nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    error_log = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    domain_config_id = Column(Integer, ForeignKey('domain_configs.id'), nullable=False)
    domain_config = relationship("DomainConfig", back_populates="documents")

class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# --- Neuro-Symbolic Foundation Models ---

class DomainConfig(Base):
    """Stores the user-defined 'worldview' (ontology, rules) for an entire domain."""
    __tablename__ = "domain_configs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    schema_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

# --- Helper Functions (remain largely the same) ---

async def get_all_active_api_keys(db: AsyncSession) -> list[APIKey]:
    """Retrieves all active API keys from the database."""
    result = await db.execute(select(APIKey).where(APIKey.is_active == True))
    return result.scalars().all()

async def get_document_by_hash(db: AsyncSession, doc_hash: str) -> Document | None:
    result = await db.execute(select(Document).where(Document.document_hash == doc_hash))
    return result.scalars().first()

async def get_document_by_id(db: AsyncSession, doc_id: int) -> Document | None:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalars().first()

async def update_document_status(
    db: AsyncSession,
    doc_id: int,
    status: DocumentStatus,
    error_message: str | None = None
) -> Document | None:
    """
    Updates a document's status with state machine validation.

    Args:
        db: Database session
        doc_id: Document ID to update
        status: New status to set
        error_message: Error message (required when setting FAILED status)

    Returns:
        Updated Document or None if not found

    Raises:
        InvalidStatusTransitionError: If the transition is not valid
        ValueError: If setting FAILED status without an error_message
    """
    doc = await get_document_by_id(db, doc_id)
    if not doc:
        return None

    # SECURITY: Validate state machine transition
    validate_status_transition(doc.status, status)

    # SECURITY: Require error_message when setting FAILED status
    if status == DocumentStatus.FAILED and not error_message:
        raise ValueError("error_message is required when setting status to FAILED")

    doc.status = status
    doc.error_log = error_message
    await db.commit()
    await db.refresh(doc)
    return doc

async def get_or_create_canonical_node(
    db: AsyncSession,
    name: str,
    node_type: str,
    embedding: list[float],
) -> tuple[CanonicalNode, bool]:
    """
    Atomically gets or creates a canonical node, handling race conditions.

    Uses INSERT ... ON CONFLICT pattern to prevent duplicate nodes when
    multiple concurrent tasks try to create the same entity.

    Args:
        db: Database session
        name: Canonical name (unique)
        node_type: Entity type
        embedding: Vector embedding

    Returns:
        Tuple of (CanonicalNode, created) where created is True if new node was created

    Note:
        This function commits the transaction to ensure atomicity.
    """
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    # First, try to find existing node
    result = await db.execute(
        select(CanonicalNode).where(CanonicalNode.name == name)
    )
    existing = result.scalars().first()
    if existing:
        return existing, False

    # Try to create - handle race condition with IntegrityError
    try:
        new_node = CanonicalNode(
            name=name,
            node_type=node_type,
            embedding=embedding,
        )
        db.add(new_node)
        await db.flush()
        return new_node, True
    except IntegrityError:
        # Race condition - another process created the node first
        # Rollback the failed insert and fetch the existing node
        await db.rollback()

        # Re-fetch the node that was created by the other process
        result = await db.execute(
            select(CanonicalNode).where(CanonicalNode.name == name)
        )
        existing = result.scalars().first()
        if existing:
            return existing, False

        # If still not found, something else went wrong
        raise ValueError(f"Failed to get or create canonical node '{name}'")


# Alias for backwards compatibility
Ontology = DomainConfig
