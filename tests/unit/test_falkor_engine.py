"""
FalkorEngine Unit Tests

Comprehensive tests for the FalkorDB graph engine.

Target file: jenezis/storage/falkor_engine.py
Coverage target: 80%+
"""
import math
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from jenezis.storage.falkor_engine import FalkorEngine, VALID_IDENTIFIER_PATTERN


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Mock FalkorDB Infrastructure
# ---------------------------------------------------------------------------

class MockQueryResult:
    """Mock FalkorDB query result."""

    def __init__(self, result_set=None):
        self.result_set = result_set or []


class MockNode:
    """Mock FalkorDB Node."""

    def __init__(self, properties=None):
        self.properties = properties or {}


class MockGraph:
    """Mock FalkorDB Graph."""

    def __init__(self):
        self.queries = []
        self._result_queue = []
        self._default_result = MockQueryResult([])

    def query(self, cypher, params=None):
        """Record and return mock result."""
        self.queries.append({"cypher": cypher, "params": params})
        if self._result_queue:
            return self._result_queue.pop(0)
        return self._default_result

    def set_result(self, result):
        """Set next result to return."""
        self._result_queue.append(result)

    def set_default_result(self, result):
        """Set default result."""
        self._default_result = result


class MockFalkorClient:
    """Mock FalkorDB client."""

    def __init__(self, graph=None):
        self._graph = graph or MockGraph()

    def select_graph(self, graph_name):
        """Return mock graph."""
        return self._graph


@pytest.fixture
def mock_graph():
    """Create a mock graph for testing."""
    return MockGraph()


@pytest.fixture
def mock_client(mock_graph):
    """Create a mock client with the mock graph."""
    return MockFalkorClient(mock_graph)


@pytest.fixture
def engine(mock_client, mock_graph):
    """Create a FalkorEngine with mocked FalkorDB."""
    with patch("jenezis.storage.falkor_engine.FalkorDB", return_value=mock_client):
        eng = FalkorEngine(host="localhost", port=6379, graph_name="test")
        eng.graph = mock_graph  # Ensure we use our mock
        return eng


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------

class TestFalkorEngineInit:
    """Tests for FalkorEngine initialization."""

    def test_init_default_params(self):
        """Engine should initialize with default parameters."""
        mock_client = MockFalkorClient()
        with patch("jenezis.storage.falkor_engine.FalkorDB", return_value=mock_client):
            engine = FalkorEngine()
            assert engine.graph_name == "jenezis"
            assert engine.client is not None
            assert engine.graph is not None

    def test_init_custom_params(self):
        """Engine should accept custom connection parameters."""
        mock_client = MockFalkorClient()
        with patch("jenezis.storage.falkor_engine.FalkorDB", return_value=mock_client) as mock_falkor:
            engine = FalkorEngine(
                host="192.168.1.100",
                port=6380,
                password="secret123",
                graph_name="custom_graph"
            )
            mock_falkor.assert_called_once_with(
                host="192.168.1.100",
                port=6380,
                password="secret123"
            )
            assert engine.graph_name == "custom_graph"

    def test_close(self, engine):
        """Close should clean up references."""
        engine.close()
        assert engine.graph is None
        assert engine.client is None


# ---------------------------------------------------------------------------
# Query Execution Tests
# ---------------------------------------------------------------------------

class TestQueryExecution:
    """Tests for query method."""

    def test_query_simple(self, engine, mock_graph):
        """Simple query should be executed."""
        mock_graph.set_result(MockQueryResult([["result1"]]))

        result = engine.query("MATCH (n) RETURN n")

        assert len(mock_graph.queries) == 1
        assert "MATCH (n) RETURN n" in mock_graph.queries[0]["cypher"]
        assert result.result_set == [["result1"]]

    def test_query_with_params(self, engine, mock_graph):
        """Query with parameters should pass params."""
        mock_graph.set_result(MockQueryResult([["found"]]))

        result = engine.query(
            "MATCH (n {id: $id}) RETURN n",
            {"id": "test-123"}
        )

        assert mock_graph.queries[0]["params"] == {"id": "test-123"}

    def test_query_error_logging(self, engine, mock_graph):
        """Query errors should be logged and re-raised."""
        mock_graph.query = MagicMock(side_effect=Exception("DB Error"))

        with pytest.raises(Exception, match="DB Error"):
            engine.query("INVALID CYPHER")


# ---------------------------------------------------------------------------
# Schema & Index Tests
# ---------------------------------------------------------------------------

class TestSchemaManagement:
    """Tests for index and schema creation."""

    def test_create_vector_index(self, engine, mock_graph):
        """Vector index creation should use correct syntax."""
        engine.create_vector_index("Entity", "embedding", 1536, "cosine")

        assert len(mock_graph.queries) == 1
        cypher = mock_graph.queries[0]["cypher"]
        assert "CREATE VECTOR INDEX" in cypher
        assert "Entity" in cypher
        assert "embedding" in cypher
        assert "1536" in cypher
        assert "cosine" in cypher

    def test_create_vector_index_already_exists(self, engine, mock_graph):
        """Should handle 'already exists' error gracefully."""
        mock_graph.query = MagicMock(side_effect=Exception("Index already exists"))

        # Should not raise
        engine.create_vector_index("Entity", "embedding")

    def test_create_vector_index_already_indexed(self, engine, mock_graph):
        """Should handle 'already indexed' error gracefully."""
        mock_graph.query = MagicMock(
            side_effect=Exception("Attribute 'embedding' is already indexed")
        )

        # Should not raise
        engine.create_vector_index("Chunk", "embedding")

    def test_create_vector_index_other_error(self, engine, mock_graph):
        """Should re-raise other errors."""
        mock_graph.query = MagicMock(side_effect=Exception("Connection failed"))

        with pytest.raises(Exception, match="Connection failed"):
            engine.create_vector_index("Entity", "embedding")

    def test_create_vector_index_invalid_label(self, engine):
        """Should reject invalid label names."""
        with pytest.raises(ValueError, match="Invalid label"):
            engine.create_vector_index("Entity; DROP", "embedding")

    def test_create_property_index(self, engine, mock_graph):
        """Property index creation should use correct syntax."""
        engine.create_property_index("Entity", "id")

        cypher = mock_graph.queries[0]["cypher"]
        assert "CREATE INDEX" in cypher
        assert "Entity" in cypher
        assert "id" in cypher

    def test_create_property_index_already_exists(self, engine, mock_graph):
        """Should handle 'already exists' error gracefully."""
        mock_graph.query = MagicMock(side_effect=Exception("Index already exists"))

        # Should not raise
        engine.create_property_index("Entity", "id")

    def test_create_property_index_invalid_property(self, engine):
        """Should reject invalid property names."""
        with pytest.raises(ValueError, match="Invalid property"):
            engine.create_property_index("Entity", "id; DELETE")

    def test_initialize_schema(self, engine, mock_graph):
        """Initialize schema should create all indexes."""
        engine.initialize_schema()

        # Should create 2 vector indexes + 4 property indexes
        assert len(mock_graph.queries) == 6

        cyphers = [q["cypher"] for q in mock_graph.queries]

        # Verify vector indexes
        assert any("VECTOR INDEX" in c and "Entity" in c for c in cyphers)
        assert any("VECTOR INDEX" in c and "Chunk" in c for c in cyphers)

        # Verify property indexes
        assert any("CREATE INDEX" in c and "Entity" in c and "id" in c for c in cyphers)
        assert any("CREATE INDEX" in c and "Document" in c for c in cyphers)


# ---------------------------------------------------------------------------
# Vector Search Tests
# ---------------------------------------------------------------------------

class TestVectorSearch:
    """Tests for vector search functionality."""

    def test_vector_search_basic(self, engine, mock_graph):
        """Vector search should use vecf32 wrapper."""
        mock_graph.set_result(MockQueryResult([
            ["id1", "Entity Name", "Person", 0.95],
            ["id2", "Another Entity", "Organization", 0.87]
        ]))

        query_vec = [0.1, 0.2, 0.3]
        results = engine.vector_search(query_vec, label="Entity", top_k=10)

        # Check query uses vecf32
        cypher = mock_graph.queries[0]["cypher"]
        assert "vecf32([" in cypher
        assert "0.1, 0.2, 0.3" in cypher
        assert "db.idx.vector.queryNodes" in cypher

        # Check results
        assert len(results) == 2
        assert results[0]["id"] == "id1"
        assert results[0]["score"] == 0.95

    def test_vector_search_empty_results(self, engine, mock_graph):
        """Should handle empty results."""
        mock_graph.set_result(MockQueryResult([]))

        results = engine.vector_search([0.1, 0.2, 0.3])

        assert results == []

    def test_vector_search_invalid_label(self, engine):
        """Should reject invalid labels."""
        with pytest.raises(ValueError, match="Invalid label"):
            engine.vector_search([0.1, 0.2], label="Entity`])MATCH(n)DELETE n//")


# ---------------------------------------------------------------------------
# Hybrid Search Tests
# ---------------------------------------------------------------------------

class TestHybridSearch:
    """Tests for hybrid search combining vector and graph."""

    def test_hybrid_search_basic(self, engine, mock_graph):
        """Hybrid search should return entities with neighbors."""
        # First query: vector search
        mock_node = MockNode({"id": "entity1", "name": "Test", "type": "Person"})
        mock_graph.set_result(MockQueryResult([[mock_node, 0.92]]))

        # Second query: neighbor expansion
        mock_graph._result_queue.append(MockQueryResult([
            ["WORKS_FOR", "org1", "Acme Corp", "Organization"]
        ]))

        results = engine.hybrid_search(
            [0.1, 0.2, 0.3],
            label="Entity",
            top_k=5,
            expand_neighbors=True
        )

        assert len(results) == 1
        assert results[0]["id"] == "entity1"
        assert results[0]["score"] == 0.92
        assert len(results[0]["neighbors"]) == 1
        assert results[0]["neighbors"][0]["rel_type"] == "WORKS_FOR"

    def test_hybrid_search_no_expansion(self, engine, mock_graph):
        """Hybrid search without neighbor expansion."""
        mock_node = MockNode({"id": "entity1", "name": "Test", "type": "Person"})
        mock_graph.set_result(MockQueryResult([[mock_node, 0.85]]))

        results = engine.hybrid_search(
            [0.1, 0.2],
            expand_neighbors=False
        )

        # Should only execute vector query, not neighbor query
        assert len(mock_graph.queries) == 1
        assert results[0]["neighbors"] == []

    def test_hybrid_search_with_filter(self, engine, mock_graph):
        """Hybrid search with cypher filter."""
        mock_node = MockNode({"id": "risk1", "name": "Market Risk", "type": "Risk"})
        mock_graph.set_result(MockQueryResult([[mock_node, 0.90]]))
        mock_graph._result_queue.append(MockQueryResult([]))  # No neighbors

        results = engine.hybrid_search(
            [0.1, 0.2],
            cypher_filter="WHERE node.type = 'Risk'",
            expand_neighbors=True
        )

        cypher = mock_graph.queries[0]["cypher"]
        assert "WHERE node.type = 'Risk'" in cypher

    def test_hybrid_search_invalid_label(self, engine):
        """Should reject invalid labels in hybrid search."""
        with pytest.raises(ValueError, match="Invalid label"):
            engine.hybrid_search([0.1], label="Bad;Label")


# ---------------------------------------------------------------------------
# Document & Chunk Operations Tests
# ---------------------------------------------------------------------------

class TestDocumentOperations:
    """Tests for document CRUD operations."""

    def test_upsert_document(self, engine, mock_graph):
        """Should create/update document node."""
        engine.upsert_document(123, "report.pdf")

        cypher = mock_graph.queries[0]["cypher"]
        params = mock_graph.queries[0]["params"]

        assert "MERGE (d:Document" in cypher
        assert params["doc_id"] == 123
        assert params["filename"] == "report.pdf"

    def test_upsert_chunks_empty(self, engine, mock_graph):
        """Empty chunks should not execute query."""
        engine.upsert_chunks(123, [])

        assert len(mock_graph.queries) == 0

    def test_upsert_chunks_with_embeddings(self, engine, mock_graph):
        """Chunks with embeddings should use vecf32."""
        chunks = [
            {"id": "chunk1", "text": "Hello world", "embedding": [0.1, 0.2, 0.3]},
            {"id": "chunk2", "text": "Goodbye world", "embedding": [0.4, 0.5, 0.6]}
        ]

        engine.upsert_chunks(42, chunks)

        # Should create one query per chunk (not batch due to vecf32)
        assert len(mock_graph.queries) == 2

        cypher1 = mock_graph.queries[0]["cypher"]
        assert "vecf32([0.1, 0.2, 0.3])" in cypher1
        assert "MERGE (c:Chunk" in cypher1

    def test_upsert_chunks_missing_id(self, engine):
        """Chunks without id should raise ValueError."""
        chunks = [{"text": "No ID here", "embedding": [0.1]}]

        with pytest.raises(ValueError, match="Required key 'id'"):
            engine.upsert_chunks(1, chunks)


# ---------------------------------------------------------------------------
# Entity & Relation Operations Tests
# ---------------------------------------------------------------------------

class TestEntityOperations:
    """Tests for entity CRUD operations."""

    def test_upsert_entities_empty(self, engine, mock_graph):
        """Empty entities should not execute query."""
        engine.upsert_entities([])

        assert len(mock_graph.queries) == 0

    def test_upsert_entities_batch(self, engine, mock_graph):
        """Should batch upsert entities."""
        entities = [
            {"id": "e1", "name": "John Doe", "type": "Person"},
            {"id": "e2", "name": "Acme Corp", "type": "Organization"}
        ]

        engine.upsert_entities(entities)

        cypher = mock_graph.queries[0]["cypher"]
        params = mock_graph.queries[0]["params"]

        assert "UNWIND $batch" in cypher
        assert "MERGE (e:Entity" in cypher
        assert len(params["batch"]) == 2

    def test_upsert_entities_with_embedding(self, engine, mock_graph):
        """Entities with embeddings should be stored."""
        entities = [
            {"id": "e1", "name": "Test", "type": "Person", "embedding": [0.1, 0.2]}
        ]

        engine.upsert_entities(entities)

        params = mock_graph.queries[0]["params"]
        assert params["batch"][0]["embedding"] == [0.1, 0.2]


class TestRelationOperations:
    """Tests for relation CRUD operations."""

    def test_upsert_relations_empty(self, engine, mock_graph):
        """Empty relations should not execute query."""
        engine.upsert_relations([])

        assert len(mock_graph.queries) == 0

    def test_upsert_relations_grouped_by_type(self, engine, mock_graph):
        """Relations should be grouped by type."""
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "WORKS_FOR", "chunk_id": "c1"},
            {"source_id": "e3", "target_id": "e4", "type": "WORKS_FOR", "chunk_id": "c1"},
            {"source_id": "e5", "target_id": "e6", "type": "MANAGES", "chunk_id": "c2"},
        ]

        engine.upsert_relations(relations)

        # Should create 2 queries (one per type)
        assert len(mock_graph.queries) == 2

        # Check that types are in queries
        cyphers = [q["cypher"] for q in mock_graph.queries]
        assert any("WORKS_FOR" in c for c in cyphers)
        assert any("MANAGES" in c for c in cyphers)

    def test_upsert_relations_invalid_type(self, engine):
        """Should reject invalid relation types."""
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "BAD; TYPE"}
        ]

        with pytest.raises(ValueError, match="Invalid relationship type"):
            engine.upsert_relations(relations)

    def test_link_entities_to_chunk(self, engine, mock_graph):
        """Should create MENTIONS relationships."""
        engine.link_entities_to_chunk("chunk1", ["e1", "e2", "e3"])

        cypher = mock_graph.queries[0]["cypher"]
        params = mock_graph.queries[0]["params"]

        assert "MENTIONS" in cypher
        assert params["chunk_id"] == "chunk1"
        assert params["entity_ids"] == ["e1", "e2", "e3"]

    def test_link_entities_empty(self, engine, mock_graph):
        """Empty entity list should not execute query."""
        engine.link_entities_to_chunk("chunk1", [])

        assert len(mock_graph.queries) == 0


# ---------------------------------------------------------------------------
# Deletion & Cleanup Tests
# ---------------------------------------------------------------------------

class TestDeletion:
    """Tests for deletion operations."""

    def test_delete_document(self, engine, mock_graph):
        """Should delete document and chunks."""
        engine.delete_document(123)

        # Should execute 2 queries: chunks then document
        assert len(mock_graph.queries) == 2

        cypher1 = mock_graph.queries[0]["cypher"]
        cypher2 = mock_graph.queries[1]["cypher"]

        assert "HAS_CHUNK" in cypher1 and "DELETE" in cypher1
        assert "Document" in cypher2 and "DELETE" in cypher2

    def test_garbage_collect_orphans(self, engine, mock_graph):
        """Should delete orphaned entities and return count."""
        mock_graph.set_result(MockQueryResult([[42]]))

        count = engine.garbage_collect_orphans()

        assert count == 42
        cypher = mock_graph.queries[0]["cypher"]
        assert "NOT (e)<-[:MENTIONS]-()" in cypher
        assert "DELETE" in cypher

    def test_garbage_collect_no_orphans(self, engine, mock_graph):
        """Should return 0 when no orphans."""
        mock_graph.set_result(MockQueryResult([[0]]))

        count = engine.garbage_collect_orphans()

        assert count == 0

    def test_garbage_collect_empty_result(self, engine, mock_graph):
        """Should handle empty result set."""
        mock_graph.set_result(MockQueryResult([]))

        count = engine.garbage_collect_orphans()

        assert count == 0

    def test_clear_graph(self, engine, mock_graph):
        """Should delete all nodes."""
        engine.clear_graph()

        cypher = mock_graph.queries[0]["cypher"]
        assert "MATCH (n) DETACH DELETE n" in cypher


# ---------------------------------------------------------------------------
# Utility Methods Tests
# ---------------------------------------------------------------------------

class TestUtilityMethods:
    """Tests for utility methods."""

    def test_get_entity_by_id_found(self, engine, mock_graph):
        """Should return entity when found."""
        mock_graph.set_result(MockQueryResult([
            ["e1", "John Doe", "Person", "canonical_123"]
        ]))

        result = engine.get_entity_by_id("e1")

        assert result["id"] == "e1"
        assert result["name"] == "John Doe"
        assert result["type"] == "Person"
        assert result["canonical_id"] == "canonical_123"

    def test_get_entity_by_id_not_found(self, engine, mock_graph):
        """Should return None when not found."""
        mock_graph.set_result(MockQueryResult([]))

        result = engine.get_entity_by_id("nonexistent")

        assert result is None

    def test_get_chunk_context_found(self, engine, mock_graph):
        """Should return chunk with entities."""
        mock_graph.set_result(MockQueryResult([
            ["chunk1", "Hello world text", [
                {"id": "e1", "name": "John", "type": "Person"},
                {"id": "e2", "name": "Acme", "type": "Organization"}
            ]]
        ]))

        result = engine.get_chunk_context("chunk1")

        assert result["chunk_id"] == "chunk1"
        assert result["text"] == "Hello world text"
        assert len(result["entities"]) == 2

    def test_get_chunk_context_with_null_entities(self, engine, mock_graph):
        """Should filter out null entities."""
        mock_graph.set_result(MockQueryResult([
            ["chunk1", "Text", [
                {"id": "e1", "name": "John", "type": "Person"},
                {"id": None, "name": None, "type": None}  # Null from LEFT JOIN
            ]]
        ]))

        result = engine.get_chunk_context("chunk1")

        # Should filter out entity with null id
        assert len(result["entities"]) == 1

    def test_get_chunk_context_not_found(self, engine, mock_graph):
        """Should return None when chunk not found."""
        mock_graph.set_result(MockQueryResult([]))

        result = engine.get_chunk_context("nonexistent")

        assert result is None

    def test_count_nodes_all(self, engine, mock_graph):
        """Should count all nodes."""
        mock_graph.set_result(MockQueryResult([[150]]))

        count = engine.count_nodes()

        assert count == 150
        assert "MATCH (n)" in mock_graph.queries[0]["cypher"]

    def test_count_nodes_by_label(self, engine, mock_graph):
        """Should count nodes by label."""
        mock_graph.set_result(MockQueryResult([[42]]))

        count = engine.count_nodes(label="Entity")

        assert count == 42
        assert "MATCH (n:Entity)" in mock_graph.queries[0]["cypher"]

    def test_count_nodes_invalid_label(self, engine):
        """Should reject invalid labels."""
        with pytest.raises(ValueError, match="Invalid label"):
            engine.count_nodes(label="Bad`Label")

    def test_count_nodes_empty_result(self, engine, mock_graph):
        """Should return 0 for empty result."""
        mock_graph.set_result(MockQueryResult([]))

        count = engine.count_nodes()

        assert count == 0


# ---------------------------------------------------------------------------
# Input Validation Tests
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Tests for _validate_identifier method."""

    def test_valid_identifiers(self, engine):
        """Should accept valid identifiers."""
        valid_names = [
            "Entity",
            "Person",
            "WORKS_FOR",
            "node123",
            "MyLabel_v2"
        ]

        for name in valid_names:
            # Should not raise
            engine._validate_identifier(name, "test")

    def test_invalid_identifiers(self, engine):
        """Should reject invalid identifiers."""
        invalid_names = [
            "123starts_with_number",
            "has space",
            "has-hyphen",
            "has.dot",
            "has`backtick",
            "has'quote",
            "has;semicolon",
            "",
            "has\nnewline",
        ]

        for name in invalid_names:
            with pytest.raises(ValueError, match="Invalid"):
                engine._validate_identifier(name, "test")


# ---------------------------------------------------------------------------
# Input Sanitization Tests
# ---------------------------------------------------------------------------

class TestInputSanitization:
    """Tests for _sanitize_document method."""

    def test_sanitize_basic(self, engine):
        """Should pass through clean documents."""
        doc = {"id": "test", "name": "Test Name", "value": 42}

        result = engine._sanitize_document(doc)

        assert result == doc

    def test_sanitize_nan_values(self, engine):
        """Should filter out NaN float values."""
        doc = {"id": "test", "score": float("nan"), "valid": 0.5}

        result = engine._sanitize_document(doc)

        assert "score" not in result
        assert result["valid"] == 0.5

    def test_sanitize_inf_values(self, engine):
        """Should filter out infinity values."""
        doc = {"id": "test", "pos_inf": float("inf"), "neg_inf": float("-inf")}

        result = engine._sanitize_document(doc)

        assert "pos_inf" not in result
        assert "neg_inf" not in result

    def test_sanitize_null_bytes(self, engine):
        """Should remove null bytes from strings."""
        doc = {"id": "test", "text": "Hello\x00World"}

        result = engine._sanitize_document(doc)

        assert result["text"] == "HelloWorld"
        assert "\x00" not in result["text"]

    def test_sanitize_non_string_keys(self, engine):
        """Should skip non-string keys."""
        doc = {"id": "test", 123: "numeric_key", (1, 2): "tuple_key"}

        result = engine._sanitize_document(doc)

        assert "id" in result
        assert 123 not in result
        assert (1, 2) not in result

    def test_sanitize_required_keys_present(self, engine):
        """Should pass when required keys present."""
        doc = {"id": "test", "name": "Test"}

        result = engine._sanitize_document(doc, required_keys=["id", "name"])

        assert result["id"] == "test"

    def test_sanitize_required_keys_missing(self, engine):
        """Should raise when required key missing."""
        doc = {"name": "Test"}

        with pytest.raises(ValueError, match="Required key 'id'"):
            engine._sanitize_document(doc, required_keys=["id"])

    def test_sanitize_required_keys_none(self, engine):
        """Should raise when required key is None."""
        doc = {"id": None, "name": "Test"}

        with pytest.raises(ValueError, match="Required key 'id'"):
            engine._sanitize_document(doc, required_keys=["id"])

    def test_sanitize_preserves_types(self, engine):
        """Should preserve various value types."""
        doc = {
            "string": "hello",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "list": [1, 2, 3],
            "nested": {"a": 1}
        }

        result = engine._sanitize_document(doc)

        assert result["string"] == "hello"
        assert result["int"] == 42
        assert result["float"] == 3.14
        assert result["bool"] is True
        assert result["list"] == [1, 2, 3]
        assert result["nested"] == {"a": 1}


# ---------------------------------------------------------------------------
# Security Tests (Cypher Injection)
# ---------------------------------------------------------------------------

class TestCypherInjectionPrevention:
    """Tests for Cypher injection prevention."""

    def test_vector_search_label_injection(self, engine):
        """Vector search should reject label injection attempts."""
        injection_payloads = [
            "Entity`]) MATCH (n) DELETE n //",
            "Entity}) RETURN 1; MATCH (n) DELETE n //",
            "Entity\x00]) DELETE ALL //",
        ]

        for payload in injection_payloads:
            with pytest.raises(ValueError, match="Invalid label"):
                engine.vector_search([0.1, 0.2], label=payload)

    def test_relation_type_injection(self, engine):
        """Relation upsert should reject type injection attempts."""
        relations = [
            {"source_id": "e1", "target_id": "e2", "type": "REL`]; DELETE ALL //"}
        ]

        with pytest.raises(ValueError, match="Invalid relationship type"):
            engine.upsert_relations(relations)

    def test_property_index_injection(self, engine):
        """Property index should reject injection in property name."""
        with pytest.raises(ValueError, match="Invalid property"):
            engine.create_property_index("Entity", "prop); DROP INDEX //")


# ---------------------------------------------------------------------------
# Edge Cases Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_query_vector(self, engine, mock_graph):
        """Should handle empty query vector."""
        mock_graph.set_result(MockQueryResult([]))

        results = engine.vector_search([])

        # Should execute query with empty vector
        cypher = mock_graph.queries[0]["cypher"]
        assert "vecf32([])" in cypher

    def test_large_embedding_vector(self, engine, mock_graph):
        """Should handle large embedding vectors."""
        mock_graph.set_result(MockQueryResult([]))

        large_vector = [0.1] * 1536  # OpenAI embedding size

        results = engine.vector_search(large_vector)

        # Should execute without error
        assert len(mock_graph.queries) == 1

    def test_special_characters_in_text(self, engine, mock_graph):
        """Should handle special characters in chunk text."""
        chunks = [{
            "id": "c1",
            "text": "Text with 'quotes' and \"double quotes\" and $special",
            "embedding": [0.1]
        }]

        engine.upsert_chunks(1, chunks)

        # Should use parameterized query, not inline text
        params = mock_graph.queries[0]["params"]
        assert "'quotes'" in params["text"]

    def test_unicode_in_entity_names(self, engine, mock_graph):
        """Should handle unicode in entity names."""
        entities = [
            {"id": "e1", "name": "日本語名前", "type": "Person"},
            {"id": "e2", "name": "Émile Zola", "type": "Person"},
            {"id": "e3", "name": "Владимир", "type": "Person"}
        ]

        engine.upsert_entities(entities)

        params = mock_graph.queries[0]["params"]
        assert params["batch"][0]["name"] == "日本語名前"
        assert params["batch"][1]["name"] == "Émile Zola"
        assert params["batch"][2]["name"] == "Владимир"


# ---------------------------------------------------------------------------
# Regex Pattern Tests
# ---------------------------------------------------------------------------

class TestValidIdentifierPattern:
    """Tests for the VALID_IDENTIFIER_PATTERN regex."""

    def test_pattern_accepts_valid(self):
        """Pattern should accept valid identifiers."""
        valid = ["a", "A", "ab", "Ab", "aB", "a1", "a_", "A_1", "Entity_v2"]

        for v in valid:
            assert VALID_IDENTIFIER_PATTERN.match(v), f"Should accept: {v}"

    def test_pattern_rejects_invalid(self):
        """Pattern should reject invalid identifiers."""
        invalid = ["1a", "_a", "a-b", "a.b", "a b", "", "a`b", "a'b"]

        for v in invalid:
            assert not VALID_IDENTIFIER_PATTERN.match(v), f"Should reject: {v}"
