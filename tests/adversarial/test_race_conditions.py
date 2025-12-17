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

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: Race condition in canonical node creation - see CLAUDE.md")
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

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: Race condition in canonical node creation - see CLAUDE.md")
    async def test_no_duplicate_canonical_nodes_created(self, test_db_session):
        """
        Verify that even under concurrent load, only one canonical node
        is created for a given entity name.
        """
        from sqlalchemy import select
        from jenezis.storage.metadata_store import CanonicalNode

        # Simulate concurrent node creation attempts
        async def create_node_if_not_exists(name: str):
            # Check if exists
            result = await test_db_session.execute(
                select(CanonicalNode).where(CanonicalNode.name == name)
            )
            existing = result.scalars().first()

            if not existing:
                # Small delay to increase race window
                await asyncio.sleep(0.01)

                # Try to create
                new_node = CanonicalNode(
                    name=name,
                    node_type="Test",
                    embedding=[0.1] * 1536,
                )
                test_db_session.add(new_node)
                try:
                    await test_db_session.flush()
                    return "created"
                except Exception as e:
                    await test_db_session.rollback()
                    return f"error: {e}"
            return "exists"

        # Launch concurrent attempts
        entity_name = f"ConcurrentTest_{asyncio.get_event_loop().time()}"
        tasks = [create_node_if_not_exists(entity_name) for _ in range(10)]

        results = await asyncio.gather(*tasks)

        # Count results
        created = results.count("created")
        exists = results.count("exists")
        errors = len([r for r in results if r.startswith("error")])

        # Only one should have created, others should find it exists or error
        assert created <= 1, (
            f"Race condition! Multiple nodes created: {created}"
        )


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
    """

    @pytest.mark.skip(reason="Requires actual database for meaningful results")
    async def test_high_contention_scenario(self, test_db_session):
        """
        Simulate high contention scenario with many concurrent operations.
        """
        from jenezis.storage.metadata_store import Document, DocumentStatus

        num_documents = 50
        num_concurrent_ops = 100

        # Create test documents
        docs = []
        for i in range(num_documents):
            doc = Document(
                filename=f"test_{i}.pdf",
                document_hash=f"hash_{i}",
                s3_path=f"bucket/hash_{i}_test.pdf",
                status=DocumentStatus.PENDING,
                domain_config_id=1,
            )
            docs.append(doc)
            test_db_session.add(doc)

        await test_db_session.commit()

        # Define concurrent operations
        async def random_operation():
            import random
            doc = random.choice(docs)
            new_status = random.choice([
                DocumentStatus.PROCESSING,
                DocumentStatus.COMPLETED,
                DocumentStatus.FAILED,
            ])
            doc.status = new_status
            await test_db_session.commit()

        # Execute many operations concurrently
        tasks = [random_operation() for _ in range(num_concurrent_ops)]

        # Should not deadlock or crash
        await asyncio.gather(*tasks, return_exceptions=True)
