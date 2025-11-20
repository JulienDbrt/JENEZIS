"""SQLAlchemy models for metadata tracking and document status."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Enum,
    Text,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

Base = declarative_base()

class DocumentStatus(enum.Enum):
    """Enumeration for the status of a document in the ingestion pipeline."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UPDATING = "UPDATING"
    DELETING = "DELETING"


class Document(Base):
    """
    Represents a document's metadata and its status in the system.
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    document_hash = Column(String(64), nullable=False, unique=True, index=True)
    s3_path = Column(String, nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    error_log = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    ontology_id = Column(Integer, ForeignKey('ontologies.id'), nullable=True)
    ontology = relationship("Ontology", back_populates="documents")

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"


class APIKey(Base):
    """Represents a secure API key for authentication."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<APIKey(id={self.id}, description='{self.description}', is_active={self.is_active})>"

class Ontology(Base):
    """Represents a dynamic ontology schema for extraction."""
    __tablename__ = "ontologies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    schema_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    documents = relationship("Document", back_populates="ontology")

    def __repr__(self):
        return f"<Ontology(id={self.id}, name='{self.name}')>"


async def get_api_key_by_hash(db: AsyncSession, key_hash: str) -> APIKey | None:
    """Retrieves an active API key by its SHA256 hash."""
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True)
    )
    return result.scalars().first()


async def get_document_by_hash(db: AsyncSession, doc_hash: str) -> Document | None:
    """Retrieves a document by its SHA256 hash."""
    result = await db.execute(select(Document).where(Document.document_hash == doc_hash))
    return result.scalars().first()

async def get_document_by_id(db: AsyncSession, doc_id: int) -> Document | None:
    """Retrieves a document by its primary key ID."""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalars().first()

async def update_document_status(db: AsyncSession, doc_id: int, status: DocumentStatus, error_message: str | None = None) -> Document | None:
    """Updates the status and optional error log of a document."""
    doc = await get_document_by_id(db, doc_id)
    if doc:
        doc.status = status
        if error_message:
            doc.error_log = error_message
        await db.commit()
        await db.refresh(doc)
    return doc
