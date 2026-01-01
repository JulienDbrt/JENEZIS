"""
Unit Tests for GraphStore - FalkorDB Facade

Targets: jenezis/storage/graph_store.py
Coverage: 23% -> 90%+
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from jenezis.storage.graph_store import (
    GraphStore,
    sanitize_label,
    sanitize_entities,
    sanitize_relations,
    get_graph_store,
    InvalidLabelError,
    SAFE_LABEL_PATTERN,
    MAX_LABEL_LENGTH,
)

pytestmark = pytest.mark.unit


class TestSanitizeLabel:
    """Tests for label sanitization."""

    def test_valid_label_passes(self):
        """Valid labels pass through unchanged."""
        assert sanitize_label("Person") == "Person"
        assert sanitize_label("WORKS_FOR") == "WORKS_FOR"
        assert sanitize_label("Entity123") == "Entity123"
        assert sanitize_label("A_B_C") == "A_B_C"

    def test_empty_label_raises(self):
        """Empty label raises InvalidLabelError."""
        with pytest.raises(InvalidLabelError, match="Empty"):
            sanitize_label("")

    def test_none_label_raises(self):
        """None label raises InvalidLabelError."""
        with pytest.raises(InvalidLabelError):
            sanitize_label(None)

    def test_too_long_label_raises(self):
        """Label exceeding MAX_LABEL_LENGTH raises error."""
        long_label = "A" * (MAX_LABEL_LENGTH + 1)
        with pytest.raises(InvalidLabelError, match="exceeds maximum length"):
            sanitize_label(long_label)

    def test_exactly_max_length_passes(self):
        """Label at exactly MAX_LABEL_LENGTH passes."""
        label = "A" * MAX_LABEL_LENGTH
        assert sanitize_label(label) == label

    def test_starts_with_number_raises(self):
        """Label starting with number raises error."""
        with pytest.raises(InvalidLabelError, match="Must start with a letter"):
            sanitize_label("123Entity")

    def test_contains_special_chars_raises(self):
        """Label with special characters raises error."""
        invalid_labels = [
            "Entity-Type",
            "Entity.Type",
            "Entity Type",
            "Entity@Type",
        ]
        for label in invalid_labels:
            with pytest.raises(InvalidLabelError):
                sanitize_label(label)

    @pytest.mark.parametrize("dangerous_char", [
        "`", "'", '"',  # Quote escapes
        "[", "]",       # Array manipulation
        "(", ")",       # Function/grouping
        ";", "//",      # Statement terminator, comments
        "\n", "\r",     # Newlines
    ])
    def test_dangerous_characters_raise(self, dangerous_char):
        """Known dangerous characters raise error."""
        # These chars are caught by the regex pattern check, not the explicit char check
        with pytest.raises(InvalidLabelError):
            sanitize_label(f"Entity{dangerous_char}Type")

    def test_null_bytes_stripped(self):
        """Null bytes are stripped before validation."""
        # Null byte is stripped, making "EntityType" which is valid
        result = sanitize_label("Entity\x00Type")
        assert result == "EntityType"

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped."""
        assert sanitize_label("  Person  ") == "Person"

    def test_custom_label_kind_in_error(self):
        """Custom label_kind appears in error message."""
        with pytest.raises(InvalidLabelError, match="relationship type"):
            sanitize_label("", "relationship type")


class TestSanitizeEntities:
    """Tests for entity list sanitization."""

    def test_valid_entities_pass(self):
        """Valid entities pass through."""
        entities = [
            {"id": "e1", "name": "John", "type": "Person"},
            {"id": "e2", "name": "Acme", "type": "Organization"}
        ]
        result = sanitize_entities(entities)
        assert len(result) == 2

    def test_invalid_entity_type_raises(self):
        """Invalid entity type raises error."""
        entities = [{"id": "e1", "type": "Invalid;Type"}]
        with pytest.raises(InvalidLabelError):
            sanitize_entities(entities)

    def test_missing_type_raises(self):
        """Missing type field raises error."""
        entities = [{"id": "e1", "name": "John"}]
        with pytest.raises(InvalidLabelError, match="Empty"):
            sanitize_entities(entities)


class TestSanitizeRelations:
    """Tests for relation list sanitization."""

    def test_valid_relations_pass(self):
        """Valid relations pass through."""
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "WORKS_FOR"}
        ]
        result = sanitize_relations(relations)
        assert len(result) == 1

    def test_invalid_relation_type_raises(self):
        """Invalid relation type raises error."""
        relations = [{"source_id": "e1", "target_id": "e2", "type": "BAD`TYPE"}]
        with pytest.raises(InvalidLabelError):
            sanitize_relations(relations)


class TestGraphStoreInit:
    """Tests for GraphStore initialization."""

    def test_init_with_engine(self):
        """GraphStore accepts pre-configured engine."""
        mock_engine = MagicMock()
        store = GraphStore(engine=mock_engine)
        assert store.engine == mock_engine

    @patch("jenezis.storage.graph_store.FalkorEngine")
    def test_init_without_engine_creates_one(self, mock_engine_class):
        """GraphStore creates engine from settings if not provided."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        store = GraphStore()

        mock_engine_class.assert_called_once()
        assert store.engine == mock_engine


class TestGraphStoreOperations:
    """Tests for GraphStore async operations."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock FalkorEngine."""
        engine = MagicMock()
        engine.query.return_value = MagicMock(result_set=[])
        return engine

    @pytest.fixture
    def store(self, mock_engine):
        """Create GraphStore with mock engine."""
        return GraphStore(engine=mock_engine)

    async def test_initialize_constraints_and_indexes(self, store, mock_engine):
        """Initialize schema calls engine."""
        await store.initialize_constraints_and_indexes()
        mock_engine.initialize_schema.assert_called_once()

    async def test_add_document_node(self, store, mock_engine):
        """Add document node calls engine."""
        await store.add_document_node(document_id=1, filename="test.pdf")
        mock_engine.upsert_document.assert_called_once_with(1, "test.pdf")

    async def test_add_chunks(self, store, mock_engine):
        """Add chunks calls engine."""
        chunks = [{"id": "c1", "text": "content"}]
        await store.add_chunks(document_id=1, chunks=chunks)
        mock_engine.upsert_chunks.assert_called_once_with(1, chunks)

    async def test_add_entities_and_relations(self, store, mock_engine):
        """Add entities and relations with sanitization."""
        entities = [{"id": "e1", "name": "John", "type": "Person"}]
        relations = [{"source_id": "e1", "target_id": "e1", "type": "SELF_REF", "chunk_id": "c1"}]

        await store.add_entities_and_relations(entities, relations)

        mock_engine.upsert_entities.assert_called_once()
        mock_engine.upsert_relations.assert_called_once()
        mock_engine.link_entities_to_chunk.assert_called()

    async def test_add_entities_only(self, store, mock_engine):
        """Add entities without relations."""
        entities = [{"id": "e1", "name": "John", "type": "Person"}]

        await store.add_entities_and_relations(entities, [])

        mock_engine.upsert_entities.assert_called_once()
        mock_engine.upsert_relations.assert_not_called()

    async def test_add_entities_invalid_type_raises(self, store):
        """Invalid entity type raises error."""
        entities = [{"id": "e1", "type": "Bad;Type"}]

        with pytest.raises(InvalidLabelError):
            await store.add_entities_and_relations(entities, [])

    async def test_delete_document(self, store, mock_engine):
        """Delete document calls engine."""
        await store.delete_document_and_associated_data(document_id=123)
        mock_engine.delete_document.assert_called_once_with(123)

    async def test_garbage_collect(self, store, mock_engine):
        """Garbage collection calls engine."""
        mock_engine.garbage_collect_orphans.return_value = 5

        await store.garbage_collect_orphaned_entities()

        mock_engine.garbage_collect_orphans.assert_called_once()


class TestGraphStoreVectorSearch:
    """Tests for vector search operations."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock FalkorEngine with query results."""
        engine = MagicMock()
        return engine

    @pytest.fixture
    def store(self, mock_engine):
        """Create GraphStore with mock engine."""
        return GraphStore(engine=mock_engine)

    async def test_vector_search_success(self, store, mock_engine):
        """Vector search returns formatted results."""
        mock_engine.query.return_value = MagicMock(
            result_set=[
                ["chunk1", "text content", 0.95, 1],
                ["chunk2", "more content", 0.85, 1]
            ]
        )

        results = await store.vector_search([0.1] * 1536, top_k=5)

        assert len(results) == 2
        assert results[0]["chunk_id"] == "chunk1"
        assert results[0]["score"] == 0.95
        assert results[1]["text"] == "more content"

    async def test_vector_search_fallback_on_error(self, store, mock_engine):
        """Vector search falls back on error."""
        # First call fails, second (fallback) succeeds
        mock_engine.query.side_effect = [
            Exception("Vector index not found"),
            MagicMock(result_set=[["c1", "fallback", 0.5, 1]])
        ]

        results = await store.vector_search([0.1] * 1536, top_k=5)

        assert len(results) == 1
        assert results[0]["score"] == 0.5


class TestGraphStoreHybridSearch:
    """Tests for hybrid search operations."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock FalkorEngine."""
        engine = MagicMock()
        engine.hybrid_search.return_value = [
            {"entity_id": "e1", "name": "Test", "score": 0.9}
        ]
        return engine

    @pytest.fixture
    def store(self, mock_engine):
        """Create GraphStore with mock engine."""
        return GraphStore(engine=mock_engine)

    async def test_hybrid_search_without_filter(self, store, mock_engine):
        """Hybrid search without type filter."""
        results = await store.hybrid_search([0.1] * 1536, top_k=10)

        assert len(results) == 1
        mock_engine.hybrid_search.assert_called_once()

    async def test_hybrid_search_with_filter(self, store, mock_engine):
        """Hybrid search with entity type filter."""
        await store.hybrid_search(
            [0.1] * 1536,
            entity_type_filter="Person",
            top_k=10
        )

        call_args = mock_engine.hybrid_search.call_args
        assert "Person" in call_args.kwargs.get("cypher_filter", "")

    async def test_hybrid_search_invalid_filter_raises(self, store):
        """Invalid entity type filter raises error."""
        with pytest.raises(InvalidLabelError):
            await store.hybrid_search(
                [0.1] * 1536,
                entity_type_filter="Bad;Type",
                top_k=10
            )


class TestGraphStoreContextMethods:
    """Tests for context retrieval methods."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock FalkorEngine."""
        engine = MagicMock()
        engine.get_entity_by_id.return_value = {"id": "e1", "name": "Test"}
        engine.get_chunk_context.return_value = {"id": "c1", "text": "Content"}
        return engine

    @pytest.fixture
    def store(self, mock_engine):
        """Create GraphStore with mock engine."""
        return GraphStore(engine=mock_engine)

    async def test_get_entity_context(self, store, mock_engine):
        """Get entity context calls engine."""
        result = await store.get_entity_context("e1")

        assert result["id"] == "e1"
        mock_engine.get_entity_by_id.assert_called_once_with("e1")

    async def test_get_chunk_with_entities(self, store, mock_engine):
        """Get chunk context calls engine."""
        result = await store.get_chunk_with_entities("c1")

        assert result["id"] == "c1"
        mock_engine.get_chunk_context.assert_called_once_with("c1")


class TestGetGraphStoreFactory:
    """Tests for factory function."""

    @patch("jenezis.storage.graph_store.FalkorEngine")
    async def test_get_graph_store_returns_instance(self, mock_engine_class):
        """Factory returns GraphStore instance."""
        mock_engine_class.return_value = MagicMock()

        store = await get_graph_store()

        assert isinstance(store, GraphStore)


class TestSafeLabelPattern:
    """Tests for SAFE_LABEL_PATTERN regex."""

    @pytest.mark.parametrize("valid_label", [
        "A",
        "Person",
        "WORKS_FOR",
        "Entity123",
        "A_B_C_D",
        "aLowerStart",
    ])
    def test_valid_patterns_match(self, valid_label):
        """Valid labels match the pattern."""
        assert SAFE_LABEL_PATTERN.match(valid_label)

    @pytest.mark.parametrize("invalid_label", [
        "123Start",
        "_underscore_start",
        "-dash",
        "has space",
        "has-dash",
        "has.dot",
        "",
    ])
    def test_invalid_patterns_no_match(self, invalid_label):
        """Invalid labels don't match the pattern."""
        assert not SAFE_LABEL_PATTERN.match(invalid_label)
