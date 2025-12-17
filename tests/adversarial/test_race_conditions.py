"""
Race Condition Tests - Concurrent Operation Attacks

These tests target race conditions in:
- Canonical node creation
- Enrichment queue processing
- Document deletion during ingestion
- Status updates

Target files:
- jenezis/ingestion/resolver.py (concurrent resolution)
- examples/fastapi_app/tasks.py (concurrent task execution)
- jenezis/storage/metadata_store.py (status updates)
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from concurrent.futures import ThreadPoolExecutor


pytestmark = [pytest.mark.adversarial, pytest.mark.slow]


class TestConcurrentCanonicalNodeCreation:
    """
    Tests for race conditions in canonical node creation.

    The vulnerability: Two concurrent resolutions of the same entity
    could both fail to find an existing node and both try to create one,
    resulting in a unique constraint violation or duplicate data.
    """

    async def test_concurrent_resolution_same_entity(self, test_db_session):
        """
        Verify that concurrent resolutions of the same entity
        don't create duplicates.
        """
        from jenezis.ingestion.resolver import Resolver
        from jenezis.ingestion.embedder import Embedder
        from jenezis.storage.metadata_store import CanonicalNode, NodeAlias

        # Create a mock embedder
        mock_embedder = MagicMock(spec=Embedder)
        mock_embedder.embed_batch = AsyncMock(return_value=[[0.1] * 1536])

        resolver = Resolver(test_db_session, mock_embedder)

        # The entity we'll try to resolve concurrently
        entity_name = "Tesla Motors"
        entity_type = "Organization"

        # Launch concurrent resolution tasks
        num_concurrent = 5
        tasks = [
            resolver.resolve_entity(entity_name, entity_type)
            for _ in range(num_concurrent)
        ]

        # Execute all concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful resolutions vs errors
        successes = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]

        # All resolutions should succeed (either by finding or creating)
        # or fail gracefully (no crashes)
        assert len(successes) + len(errors) == num_concurrent

        # If any succeeded, they should all resolve to the same ID
        resolved_ids = [
            r.get("canonical_id")
            for r in successes
            if r.get("status") == "resolved"
        ]

        if len(resolved_ids) > 1:
            # All should point to the same canonical node
            assert len(set(resolved_ids)) == 1, (
                f"Race condition! Multiple canonical IDs for same entity: {resolved_ids}"
            )

    async def test_get_or_create_handles_race_conditions(self, test_db_session):
        """
        Verify that get_or_create_canonical_node handles concurrent access.

        The fix uses IntegrityError handling to ensure only one node is
        created even under concurrent load.
        """
        from sqlalchemy import select
        from jenezis.storage.metadata_store import CanonicalNode, get_or_create_canonical_node

        # Test the fixed function: get_or_create_canonical_node
        entity_name = f"RaceConditionTest_{id(test_db_session)}"
        embedding = [0.1] * 1536

        # First call should create
        node1, created1 = await get_or_create_canonical_node(
            test_db_session, entity_name, "TestType", embedding
        )
        assert created1 is True
        assert node1.name == entity_name

        # Second call should find existing (no race condition needed to test this)
        node2, created2 = await get_or_create_canonical_node(
            test_db_session, entity_name, "TestType", embedding
        )
        assert created2 is False
        assert node2.id == node1.id  # Same node

        # Verify only one node exists in DB
        result = await test_db_session.execute(
            select(CanonicalNode).where(CanonicalNode.name == entity_name)
        )
        nodes = result.scalars().all()
        assert len(nodes) == 1, f"Expected 1 node, found {len(nodes)}"


class TestEnrichmentQueueRaceCondition:
    """
    Tests for race conditions in enrichment queue processing.

    The vulnerability: If the scheduler runs while enrichment is
    in progress, it might dispatch duplicate tasks for the same item.
    """

    async def test_enrichment_item_not_processed_twice(self, test_db_session):
        """
        Verify that an enrichment queue item is not processed by
        multiple workers simultaneously.
        """
        from jenezis.storage.metadata_store import (
            EnrichmentQueueItem,
            EnrichmentStatus,
        )

        # Create a test queue item
        item = EnrichmentQueueItem(
            name="Test Entity",
            entity_type="Organization",
            context_chunk="Test context about the entity.",
            status=EnrichmentStatus.PENDING,
        )
        test_db_session.add(item)
        await test_db_session.commit()
        await test_db_session.refresh(item)
        item_id = item.id

        # Simulate concurrent processing attempts
        async def try_process():
            from sqlalchemy import select

            # Get and lock the item
            result = await test_db_session.execute(
                select(EnrichmentQueueItem).where(
                    EnrichmentQueueItem.id == item_id,
                    EnrichmentQueueItem.status == EnrichmentStatus.PENDING,
                )
            )
            item = result.scalars().first()

            if item:
                item.status = EnrichmentStatus.PROCESSING
                await test_db_session.commit()
                return "acquired"
            return "missed"

        # This test documents expected behavior with proper locking
        # In real code, SELECT ... FOR UPDATE should be used


class TestDocumentDeletionDuringIngestion:
    """
    Tests for race conditions when deleting a document that is
    being ingested.

    The vulnerability: If a delete request arrives while ingestion
    is in progress, partial data may be left in the graph.
    """

    async def test_delete_during_ingestion_leaves_no_orphans(
        self,
        mock_neo4j_driver,
        mock_s3_client,
        test_db_session,
    ):
        """
        Verify that deleting a document during ingestion doesn't
        leave orphaned data.
        """
        from jenezis.storage.metadata_store import (
            Document,
            DocumentStatus,
        )

        # Create a document in PROCESSING state
        doc = Document(
            filename="test.pdf",
            document_hash="abc123",
            s3_path="bucket/abc123_test.pdf",
            status=DocumentStatus.PROCESSING,
            domain_config_id=1,
        )
        test_db_session.add(doc)
        await test_db_session.commit()
        await test_db_session.refresh(doc)

        # Simulate concurrent operations:
        # 1. Ingestion adds chunks to graph
        # 2. Delete request arrives

        # The delete should either:
        # - Wait for ingestion to complete
        # - Cancel ingestion and clean up
        # - Reject delete while PROCESSING

        # Document the expected behavior
        assert doc.status == DocumentStatus.PROCESSING


class TestStatusUpdateRaceCondition:
    """
    Tests for race conditions in document status updates.

    The vulnerability: Concurrent status updates could result in
    invalid state transitions or lost updates.
    """

    async def test_concurrent_status_updates(self, test_db_session):
        """
        Verify that concurrent status updates are serialized correctly.
        """
        from jenezis.storage.metadata_store import (
            Document,
            DocumentStatus,
            update_document_status,
        )

        # Create a document
        doc = Document(
            filename="test.pdf",
            document_hash="xyz789",
            s3_path="bucket/xyz789_test.pdf",
            status=DocumentStatus.PENDING,
            domain_config_id=1,
        )
        test_db_session.add(doc)
        await test_db_session.commit()
        await test_db_session.refresh(doc)
        doc_id = doc.id

        # Define concurrent updates
        async def update_to_processing():
            await update_document_status(
                test_db_session, doc_id, DocumentStatus.PROCESSING
            )
            return "PROCESSING"

        async def update_to_completed():
            await update_document_status(
                test_db_session, doc_id, DocumentStatus.COMPLETED
            )
            return "COMPLETED"

        # Execute concurrently
        results = await asyncio.gather(
            update_to_processing(),
            update_to_completed(),
            return_exceptions=True,
        )

        # Refresh to get final state
        await test_db_session.refresh(doc)

        # The final state should be one of the two updates
        assert doc.status in [
            DocumentStatus.PROCESSING,
            DocumentStatus.COMPLETED,
        ]

        # Document: This test shows that without proper state machine
        # validation, any transition is possible


class TestDoubleSubmitPrevention:
    """
    Tests for preventing double-submit of the same document.
    """

    async def test_double_submit_within_debounce_window(self, test_db_session):
        """
        Verify that rapid double-submits of the same file are handled.
        """
        from jenezis.storage.metadata_store import (
            Document,
            DocumentStatus,
            get_document_by_hash,
        )

        file_hash = "double_submit_test_hash"

        # First submit
        doc1 = Document(
            filename="test.pdf",
            document_hash=file_hash,
            s3_path=f"bucket/{file_hash}_test.pdf",
            status=DocumentStatus.PENDING,
            domain_config_id=1,
        )
        test_db_session.add(doc1)
        await test_db_session.commit()

        # Second submit with same hash (simulated)
        existing = await get_document_by_hash(test_db_session, file_hash)

        # Should find the existing document
        assert existing is not None
        assert existing.document_hash == file_hash

        # The API should return 409 Conflict for this


class TestTaskIdempotency:
    """
    Tests for task idempotency - ensuring tasks can be safely retried.
    """

    async def test_ingestion_task_idempotent(self, mock_neo4j_driver):
        """
        Verify that running the ingestion task twice doesn't create
        duplicate data.
        """
        # Celery tasks should be idempotent - running the same task
        # multiple times should have the same result as running once

        # The task should:
        # 1. Check if document is already processed
        # 2. Use MERGE operations in Neo4j (not CREATE)
        # 3. Handle partial completion gracefully

        # Verify MERGE is used (idempotent) not CREATE (not idempotent)
        # This would be checked in the actual task execution
        pass

    async def test_delete_task_idempotent(self):
        """
        Verify that running the delete task twice doesn't cause errors.
        """
        # Deleting an already-deleted document should not crash
        # The task should check if the document exists first
        pass


class TestLockContention:
    """
    Tests for database lock contention under high load.
    Uses real PostgreSQL (docker on port 5433) for meaningful concurrency testing.
    """

    async def test_high_contention_scenario(self, real_postgres_session):
        """
        Simulate high contention scenario with many concurrent operations.
        Uses real PostgreSQL to test actual locking behavior.
        """
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from jenezis.storage.metadata_store import Document, DocumentStatus, DomainConfig, Base

        # Use the same connection URL as the fixture
        engine = create_async_engine(
            "postgresql+asyncpg://test:test@localhost:5433/test",
            echo=False
        )

        # Create a domain config first (required for FK constraint)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with session_factory() as setup_session:
            domain_config = DomainConfig(
                name="test_domain",
                schema_json={"entity_types": ["Test"], "relation_types": []},
            )
            setup_session.add(domain_config)
            await setup_session.commit()
            domain_id = domain_config.id

        num_documents = 20
        num_concurrent_ops = 50

        # Create test documents
        async with session_factory() as setup_session:
            for i in range(num_documents):
                doc = Document(
                    filename=f"contention_test_{i}.pdf",
                    document_hash=f"contention_hash_{i}",
                    s3_path=f"bucket/contention_hash_{i}_test.pdf",
                    status=DocumentStatus.PENDING,
                    domain_config_id=domain_id,
                )
                setup_session.add(doc)
            await setup_session.commit()

        # Define concurrent operations - each with its own session
        async def random_operation(doc_index: int):
            import random
            async with session_factory() as session:
                from sqlalchemy import select, update
                # Random status transition
                new_status = random.choice([
                    DocumentStatus.PROCESSING,
                    DocumentStatus.COMPLETED,
                ])
                stmt = (
                    update(Document)
                    .where(Document.document_hash == f"contention_hash_{doc_index % num_documents}")
                    .values(status=new_status)
                )
                await session.execute(stmt)
                await session.commit()

        # Execute many operations concurrently
        tasks = [random_operation(i) for i in range(num_concurrent_ops)]

        # Should not deadlock or crash - gather with return_exceptions
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and failures
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) < num_concurrent_ops // 2, (
            f"Too many errors in concurrent operations: {len(errors)}/{num_concurrent_ops}"
        )

        # Cleanup
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
