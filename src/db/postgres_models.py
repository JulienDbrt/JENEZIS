"""
PostgreSQL SQLAlchemy models for JENEZIS - Knowledge Graph System.

This replaces the SQLite schema with a production-ready PostgreSQL implementation.
Includes pgvector support for semantic similarity search.

Note: This is the v1.x schema still in production.
      The v2.0 universal schema (genesis_models) is archived for future migration.
"""

import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# ============================================================================
# ONTOLOGY SCHEMA (Skills)
# ============================================================================


class Skill(Base):
    """Canonical skill entities."""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    canonical_name = Column(String(255), unique=True, nullable=False, index=True)
    embedding = Column(Vector(1536))  # OpenAI embeddings for semantic search
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    aliases = relationship("Alias", back_populates="skill", cascade="all, delete-orphan")
    children = relationship(
        "Hierarchy",
        foreign_keys="Hierarchy.parent_id",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parents = relationship(
        "Hierarchy",
        foreign_keys="Hierarchy.child_id",
        back_populates="child",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, canonical_name='{self.canonical_name}')>"


class Alias(Base):
    """Skill aliases mapping to canonical skills."""

    __tablename__ = "aliases"

    id = Column(Integer, primary_key=True)
    alias_name = Column(String(255), unique=True, nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    confidence = Column(Integer, default=100)  # 0-100 confidence score
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    skill = relationship("Skill", back_populates="aliases")

    __table_args__ = (Index("idx_aliases_skill_id", "skill_id"),)

    def __repr__(self) -> str:
        return f"<Alias(alias_name='{self.alias_name}', skill_id={self.skill_id})>"


class Hierarchy(Base):
    """Hierarchical relationships between skills."""

    __tablename__ = "hierarchy"

    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    child = relationship("Skill", foreign_keys=[child_id], back_populates="parents")
    parent = relationship("Skill", foreign_keys=[parent_id], back_populates="children")

    __table_args__ = (
        UniqueConstraint("child_id", "parent_id", name="uq_hierarchy"),
        Index("idx_hierarchy_child", "child_id"),
        Index("idx_hierarchy_parent", "parent_id"),
    )

    def __repr__(self) -> str:
        return f"<Hierarchy(child_id={self.child_id}, parent_id={self.parent_id})>"


# ============================================================================
# ENTITY RESOLVER SCHEMA (Companies/Schools)
# ============================================================================


class EntityType(str, enum.Enum):
    """Entity types enum."""

    COMPANY = "COMPANY"
    SCHOOL = "SCHOOL"


class EnrichmentStatus(str, enum.Enum):
    """Enrichment status enum."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class CanonicalEntity(Base):
    """Canonical entities (companies/schools)."""

    __tablename__ = "canonical_entities"

    id = Column(Integer, primary_key=True)
    canonical_id = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    entity_type = Column(SQLEnum(EntityType), nullable=False, index=True)
    entity_metadata = Column(JSON, default=dict)  # 'metadata' is reserved by SQLAlchemy
    embedding = Column(Vector(1536))  # Semantic search support
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    aliases = relationship(
        "EntityAlias", back_populates="canonical_entity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<CanonicalEntity(canonical_id='{self.canonical_id}', type={self.entity_type})>"


class EntityAlias(Base):
    """Entity aliases mapping to canonical entities."""

    __tablename__ = "entity_aliases"

    id = Column(Integer, primary_key=True)
    alias_name = Column(String(255), unique=True, nullable=False, index=True)
    canonical_id = Column(
        Integer, ForeignKey("canonical_entities.id", ondelete="CASCADE"), nullable=False
    )
    confidence = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    canonical_entity = relationship("CanonicalEntity", back_populates="aliases")

    __table_args__ = (Index("idx_entity_aliases_canonical_id", "canonical_id"),)

    def __repr__(self) -> str:
        return f"<EntityAlias(alias_name='{self.alias_name}', canonical_id={self.canonical_id})>"


class EnrichmentQueue(Base):
    """Queue for entities requiring enrichment."""

    __tablename__ = "enrichment_queue"

    id = Column(Integer, primary_key=True)
    canonical_id = Column(String(255), unique=True, nullable=False, index=True)
    entity_type = Column(SQLEnum(EntityType), nullable=False)
    status = Column(SQLEnum(EnrichmentStatus), default=EnrichmentStatus.PENDING, nullable=False)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("idx_enrichment_status", "status"),)

    def __repr__(self) -> str:
        return f"<EnrichmentQueue(canonical_id='{self.canonical_id}', status={self.status})>"


# ============================================================================
# ASYNC TASK QUEUE SCHEMA
# ============================================================================


class TaskStatus(str, enum.Enum):
    """Task execution status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AsyncTask(Base):
    """Async task tracking for Celery jobs."""

    __tablename__ = "async_tasks"

    id = Column(String(255), primary_key=True)  # Celery task ID
    task_name = Column(String(255), nullable=False, index=True)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("idx_task_status", "status"), Index("idx_task_created", "created_at"))

    def __repr__(self) -> str:
        return f"<AsyncTask(id='{self.id}', task_name='{self.task_name}', status={self.status})>"
