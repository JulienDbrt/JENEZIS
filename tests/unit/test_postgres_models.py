#!/usr/bin/env python3
"""
Tests for PostgreSQL SQLAlchemy models.
"""

import pytest
from datetime import datetime


class TestPostgresModels:
    """Tests for PostgreSQL models in src/db/postgres_models.py."""

    @pytest.mark.unit
    def test_skill_model_representation(self):
        """Test Skill model __repr__ method."""
        from src.db.postgres_models import Skill

        skill = Skill(id=1, canonical_name="python")
        repr_str = repr(skill)

        assert "Skill" in repr_str
        assert "python" in repr_str
        assert "1" in repr_str

    @pytest.mark.unit
    def test_alias_model_representation(self):
        """Test Alias model __repr__ method."""
        from src.db.postgres_models import Alias

        alias = Alias(alias_name="py", skill_id=1)
        repr_str = repr(alias)

        assert "Alias" in repr_str
        assert "py" in repr_str

    @pytest.mark.unit
    def test_hierarchy_model_representation(self):
        """Test Hierarchy model __repr__ method."""
        from src.db.postgres_models import Hierarchy

        hierarchy = Hierarchy(child_id=1, parent_id=2)
        repr_str = repr(hierarchy)

        assert "Hierarchy" in repr_str
        assert "child_id=1" in repr_str
        assert "parent_id=2" in repr_str

    @pytest.mark.unit
    def test_entity_type_enum(self):
        """Test EntityType enum values."""
        from src.db.postgres_models import EntityType

        assert EntityType.COMPANY.value == "COMPANY"
        assert EntityType.SCHOOL.value == "SCHOOL"

    @pytest.mark.unit
    def test_enrichment_status_enum(self):
        """Test EnrichmentStatus enum values."""
        from src.db.postgres_models import EnrichmentStatus

        assert EnrichmentStatus.PENDING.value == "PENDING"
        assert EnrichmentStatus.PROCESSING.value == "PROCESSING"
        assert EnrichmentStatus.COMPLETED.value == "COMPLETED"
        assert EnrichmentStatus.FAILED.value == "FAILED"
        assert EnrichmentStatus.NEEDS_REVIEW.value == "NEEDS_REVIEW"

    @pytest.mark.unit
    def test_task_status_enum(self):
        """Test TaskStatus enum values."""
        from src.db.postgres_models import TaskStatus

        assert TaskStatus.PENDING.value == "PENDING"
        assert TaskStatus.RUNNING.value == "RUNNING"
        assert TaskStatus.SUCCESS.value == "SUCCESS"
        assert TaskStatus.FAILED.value == "FAILED"
        assert TaskStatus.CANCELLED.value == "CANCELLED"

    @pytest.mark.unit
    def test_canonical_entity_model_representation(self):
        """Test CanonicalEntity model __repr__ method."""
        from src.db.postgres_models import CanonicalEntity, EntityType

        entity = CanonicalEntity(
            canonical_id="google",
            display_name="Google",
            entity_type=EntityType.COMPANY
        )
        repr_str = repr(entity)

        assert "CanonicalEntity" in repr_str
        assert "google" in repr_str
        assert "COMPANY" in repr_str

    @pytest.mark.unit
    def test_entity_alias_model_representation(self):
        """Test EntityAlias model __repr__ method."""
        from src.db.postgres_models import EntityAlias

        alias = EntityAlias(alias_name="google inc", canonical_id=1)
        repr_str = repr(alias)

        assert "EntityAlias" in repr_str
        assert "google inc" in repr_str

    @pytest.mark.unit
    def test_enrichment_queue_model_representation(self):
        """Test EnrichmentQueue model __repr__ method."""
        from src.db.postgres_models import EnrichmentQueue, EntityType, EnrichmentStatus

        queue_item = EnrichmentQueue(
            canonical_id="test_entity",
            entity_type=EntityType.COMPANY,
            status=EnrichmentStatus.PENDING
        )
        repr_str = repr(queue_item)

        assert "EnrichmentQueue" in repr_str
        assert "test_entity" in repr_str
        assert "PENDING" in repr_str

    @pytest.mark.unit
    def test_async_task_model_representation(self):
        """Test AsyncTask model __repr__ method."""
        from src.db.postgres_models import AsyncTask, TaskStatus

        task = AsyncTask(
            id="task-123",
            task_name="enrichment.process",
            status=TaskStatus.RUNNING
        )
        repr_str = repr(task)

        assert "AsyncTask" in repr_str
        assert "task-123" in repr_str
        assert "enrichment.process" in repr_str
        assert "RUNNING" in repr_str

    @pytest.mark.unit
    def test_base_class_exists(self):
        """Test that Base class is properly defined."""
        from src.db.postgres_models import Base

        assert hasattr(Base, "metadata")
        assert hasattr(Base, "registry")

    @pytest.mark.unit
    def test_skill_table_name(self):
        """Test Skill table name."""
        from src.db.postgres_models import Skill

        assert Skill.__tablename__ == "skills"

    @pytest.mark.unit
    def test_alias_table_name(self):
        """Test Alias table name."""
        from src.db.postgres_models import Alias

        assert Alias.__tablename__ == "aliases"

    @pytest.mark.unit
    def test_hierarchy_table_name(self):
        """Test Hierarchy table name."""
        from src.db.postgres_models import Hierarchy

        assert Hierarchy.__tablename__ == "hierarchy"

    @pytest.mark.unit
    def test_canonical_entity_table_name(self):
        """Test CanonicalEntity table name."""
        from src.db.postgres_models import CanonicalEntity

        assert CanonicalEntity.__tablename__ == "canonical_entities"

    @pytest.mark.unit
    def test_entity_alias_table_name(self):
        """Test EntityAlias table name."""
        from src.db.postgres_models import EntityAlias

        assert EntityAlias.__tablename__ == "entity_aliases"

    @pytest.mark.unit
    def test_enrichment_queue_table_name(self):
        """Test EnrichmentQueue table name."""
        from src.db.postgres_models import EnrichmentQueue

        assert EnrichmentQueue.__tablename__ == "enrichment_queue"

    @pytest.mark.unit
    def test_async_task_table_name(self):
        """Test AsyncTask table name."""
        from src.db.postgres_models import AsyncTask

        assert AsyncTask.__tablename__ == "async_tasks"
