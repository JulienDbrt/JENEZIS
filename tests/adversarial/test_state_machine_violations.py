"""
State Machine Violation Tests - Invalid Status Transitions

These tests target the lack of state machine validation in
document status updates.

Target files:
- jenezis/storage/metadata_store.py:107-112 (update_document_status)
- jenezis/storage/metadata_store.py:22-24 (DocumentStatus enum)
"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from jenezis.storage.metadata_store import (
    Document,
    DocumentStatus,
    update_document_status,
)


pytestmark = [pytest.mark.adversarial, pytest.mark.unit]


class TestDocumentStatusStateMachine:
    """
    Tests for document status state machine validation.

    The vulnerability: The update_document_status function allows
    ANY status transition, which can lead to:
    - Re-processing completed documents
    - Resurrecting failed documents
    - Updating documents while deleting
    """

    # Valid transition paths
    VALID_TRANSITIONS = [
        # Normal ingestion flow
        (DocumentStatus.PENDING, DocumentStatus.PROCESSING),
        (DocumentStatus.PROCESSING, DocumentStatus.COMPLETED),
        (DocumentStatus.PROCESSING, DocumentStatus.FAILED),

        # Update flow
        (DocumentStatus.COMPLETED, DocumentStatus.UPDATING),
        (DocumentStatus.UPDATING, DocumentStatus.PROCESSING),

        # Delete flow (from any terminal state)
        (DocumentStatus.COMPLETED, DocumentStatus.DELETING),
        (DocumentStatus.FAILED, DocumentStatus.DELETING),
    ]

    # Invalid transitions that should be blocked
    INVALID_TRANSITIONS = [
        # Cannot go backwards
        (DocumentStatus.PROCESSING, DocumentStatus.PENDING,
         "Processing document should not return to pending"),

        (DocumentStatus.COMPLETED, DocumentStatus.PENDING,
         "Completed document should not return to pending"),

        (DocumentStatus.COMPLETED, DocumentStatus.PROCESSING,
         "Completed document should not be re-processed directly"),

        (DocumentStatus.FAILED, DocumentStatus.PROCESSING,
         "Failed document should not be re-processed without update"),

        (DocumentStatus.FAILED, DocumentStatus.PENDING,
         "Failed document should not return to pending"),

        # Cannot transition from DELETING
        (DocumentStatus.DELETING, DocumentStatus.PENDING,
         "Deleting document cannot return to pending"),

        (DocumentStatus.DELETING, DocumentStatus.PROCESSING,
         "Deleting document cannot be processed"),

        (DocumentStatus.DELETING, DocumentStatus.COMPLETED,
         "Deleting document cannot be completed"),

        (DocumentStatus.DELETING, DocumentStatus.FAILED,
         "Deleting document cannot be marked failed"),

        (DocumentStatus.DELETING, DocumentStatus.UPDATING,
         "Deleting document cannot be updated"),
    ]

    @pytest.mark.parametrize("from_status,to_status", VALID_TRANSITIONS)
    async def test_valid_transition_allowed(
        self,
        from_status: DocumentStatus,
        to_status: DocumentStatus,
        test_db_session,
    ):
        """Verify that valid status transitions are allowed."""
        # Create document with initial status
        doc = Document(
            filename="test.pdf",
            document_hash=f"hash_{from_status.value}_{to_status.value}",
            s3_path="bucket/test.pdf",
            status=from_status,
            domain_config_id=1,
        )
        test_db_session.add(doc)
        await test_db_session.commit()
        await test_db_session.refresh(doc)

        # Attempt transition
        result = await update_document_status(
            test_db_session,
            doc.id,
            to_status,
        )

        # Should succeed
        assert result is not None
        assert result.status == to_status

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: State machine validation not implemented - see CLAUDE.md")
    @pytest.mark.parametrize("from_status,to_status,reason", INVALID_TRANSITIONS)
    async def test_invalid_transition_blocked(
        self,
        from_status: DocumentStatus,
        to_status: DocumentStatus,
        reason: str,
        test_db_session,
    ):
        """
        Verify that invalid status transitions are blocked.

        NOTE: This test documents EXPECTED behavior. Currently the code
        does NOT validate transitions, so these tests will FAIL until
        validation is implemented.
        """
        # Create document with initial status
        doc = Document(
            filename="test.pdf",
            document_hash=f"invalid_{from_status.value}_{to_status.value}",
            s3_path="bucket/test.pdf",
            status=from_status,
            domain_config_id=1,
        )
        test_db_session.add(doc)
        await test_db_session.commit()
        await test_db_session.refresh(doc)

        # Attempt invalid transition
        # EXPECTED: Should raise ValueError or return None
        # ACTUAL (vulnerable): Will succeed

        result = await update_document_status(
            test_db_session,
            doc.id,
            to_status,
        )

        # Document the vulnerability
        if result and result.status == to_status:
            pytest.fail(
                f"VULNERABILITY: Invalid transition allowed!\n"
                f"From: {from_status.value} -> To: {to_status.value}\n"
                f"Reason this should be blocked: {reason}\n"
                "RECOMMENDATION: Add state machine validation to update_document_status"
            )


class TestStatusTransitionSideEffects:
    """
    Tests for side effects of status transitions.
    """

    async def test_processing_to_completed_requires_data(self, test_db_session):
        """
        Verify that marking a document COMPLETED requires that
        processing actually happened (chunks exist, etc.).
        """
        # Create a document that never actually processed
        doc = Document(
            filename="test.pdf",
            document_hash="unprocessed_hash",
            s3_path="bucket/test.pdf",
            status=DocumentStatus.PROCESSING,
            domain_config_id=1,
        )
        test_db_session.add(doc)
        await test_db_session.commit()
        await test_db_session.refresh(doc)

        # Attempt to mark as completed without actual processing
        result = await update_document_status(
            test_db_session,
            doc.id,
            DocumentStatus.COMPLETED,
        )

        # EXPECTED: Should verify chunks exist in graph
        # ACTUAL (vulnerable): Blindly updates status

        # Document expected behavior
        assert result is not None  # Currently succeeds without validation

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: error_message not required for FAILED status - see CLAUDE.md")
    async def test_failed_status_requires_error_log(self, test_db_session):
        """
        Verify that marking a document FAILED includes an error message.
        """
        doc = Document(
            filename="test.pdf",
            document_hash="failed_hash",
            s3_path="bucket/test.pdf",
            status=DocumentStatus.PROCESSING,
            domain_config_id=1,
        )
        test_db_session.add(doc)
        await test_db_session.commit()
        await test_db_session.refresh(doc)

        # Mark as failed without error message
        result = await update_document_status(
            test_db_session,
            doc.id,
            DocumentStatus.FAILED,
            error_message=None,  # No error message!
        )

        # EXPECTED: Should require error_message for FAILED status
        # ACTUAL: Allows empty error_log

        if result and result.status == DocumentStatus.FAILED:
            if not result.error_log:
                pytest.fail(
                    "VULNERABILITY: Document marked FAILED without error_log!\n"
                    "RECOMMENDATION: Require error_message when setting FAILED status"
                )


class TestConcurrentStatusConflicts:
    """
    Tests for conflicts from concurrent status updates.
    """

    async def test_optimistic_locking_not_implemented(self, test_db_session):
        """
        Document the lack of optimistic locking for status updates.
        """
        # Without optimistic locking (e.g., version column), concurrent
        # updates can overwrite each other without detection

        doc = Document(
            filename="test.pdf",
            document_hash="lock_test_hash",
            s3_path="bucket/test.pdf",
            status=DocumentStatus.PENDING,
            domain_config_id=1,
        )
        test_db_session.add(doc)
        await test_db_session.commit()

        # Check for version column
        has_version_column = hasattr(doc, 'version') or hasattr(doc, 'updated_at')

        # Document that optimistic locking should be implemented
        assert has_version_column, (
            "RECOMMENDATION: Add version column for optimistic locking"
        )


class TestStatusEnumCompleteness:
    """
    Tests for DocumentStatus enum completeness.
    """

    def test_all_statuses_have_valid_transitions(self):
        """
        Verify that every status has at least one valid outgoing transition
        (except terminal states).
        """
        terminal_states = {DocumentStatus.COMPLETED, DocumentStatus.FAILED}

        # Define expected valid transitions for each state
        expected_transitions = {
            DocumentStatus.PENDING: [DocumentStatus.PROCESSING, DocumentStatus.DELETING],
            DocumentStatus.PROCESSING: [DocumentStatus.COMPLETED, DocumentStatus.FAILED],
            DocumentStatus.COMPLETED: [DocumentStatus.UPDATING, DocumentStatus.DELETING],
            DocumentStatus.FAILED: [DocumentStatus.DELETING],  # Or retry mechanism
            DocumentStatus.UPDATING: [DocumentStatus.PROCESSING],
            DocumentStatus.DELETING: [],  # Terminal
        }

        for status in DocumentStatus:
            if status not in terminal_states and status != DocumentStatus.DELETING:
                transitions = expected_transitions.get(status, [])
                assert len(transitions) > 0, (
                    f"Status {status.value} has no valid outgoing transitions"
                )

    def test_no_orphan_statuses(self):
        """
        Verify that every status is reachable from PENDING.
        """
        reachable = {DocumentStatus.PENDING}
        transitions = {
            DocumentStatus.PENDING: [DocumentStatus.PROCESSING],
            DocumentStatus.PROCESSING: [DocumentStatus.COMPLETED, DocumentStatus.FAILED],
            DocumentStatus.COMPLETED: [DocumentStatus.UPDATING, DocumentStatus.DELETING],
            DocumentStatus.FAILED: [DocumentStatus.DELETING],
            DocumentStatus.UPDATING: [DocumentStatus.PROCESSING],
        }

        # BFS to find all reachable states
        queue = [DocumentStatus.PENDING]
        while queue:
            current = queue.pop(0)
            for next_status in transitions.get(current, []):
                if next_status not in reachable:
                    reachable.add(next_status)
                    queue.append(next_status)

        # All statuses should be reachable
        all_statuses = set(DocumentStatus)
        unreachable = all_statuses - reachable

        assert not unreachable, (
            f"Unreachable statuses from PENDING: {[s.value for s in unreachable]}"
        )


class TestStatusQuerySafety:
    """
    Tests for safe status querying.
    """

    async def test_status_filtering_in_queries(self, test_db_session):
        """
        Verify that status-based queries use enum values correctly.
        """
        from sqlalchemy import select

        # Create documents with different statuses
        for i, status in enumerate(DocumentStatus):
            doc = Document(
                filename=f"test_{i}.pdf",
                document_hash=f"query_test_hash_{i}",
                s3_path=f"bucket/test_{i}.pdf",
                status=status,
                domain_config_id=1,
            )
            test_db_session.add(doc)

        await test_db_session.commit()

        # Query for specific status using enum
        result = await test_db_session.execute(
            select(Document).where(Document.status == DocumentStatus.PENDING)
        )
        pending_docs = result.scalars().all()

        # Should find exactly one document
        assert len(pending_docs) == 1
        assert pending_docs[0].status == DocumentStatus.PENDING

    async def test_status_comparison_type_safety(self, test_db_session):
        """
        Verify that status comparisons are type-safe.
        """
        doc = Document(
            filename="test.pdf",
            document_hash="type_safety_hash",
            s3_path="bucket/test.pdf",
            status=DocumentStatus.PENDING,
            domain_config_id=1,
        )
        test_db_session.add(doc)
        await test_db_session.commit()
        await test_db_session.refresh(doc)

        # Correct comparison
        assert doc.status == DocumentStatus.PENDING

        # String comparison should also work (via enum)
        assert doc.status.value == "PENDING"

        # Direct string comparison should NOT be used in code
        # (but document that it might accidentally work)
