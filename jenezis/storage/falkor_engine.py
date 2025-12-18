"""
JENEZIS FalkorEngine - Sovereign Clean Room Implementation.

This module provides a graph database engine built on FalkorDB using only:
- Official FalkorDB Python client (MIT License)
- Public FalkorDB documentation (https://docs.falkordb.com/)

No third-party graph abstraction libraries were referenced.

Architecture
------------
FalkorDB is a Redis-based graph database supporting OpenCypher queries.
Data organization:

    Redis Instance
    └── Graph (Redis key = "jenezis")
        ├── Nodes (:Entity, :Document, :Chunk)
        │   └── Properties (id, name, type, embedding, etc.)
        └── Relationships (typed, directed)
            └── Properties (chunk_id, created_at, etc.)

Key Features
------------
- OpenCypher query execution
- Native HNSW vector indexing for semantic search
- Hybrid search: vector similarity + graph traversal in one query
- Batch upsert operations with UNWIND
- Input sanitization against Cypher injection

Copyright (c) 2025 Sigilum - BSL 1.1 License
"""

import logging
import math
import re
from collections import defaultdict
from typing import Any

from falkordb import FalkorDB

logger = logging.getLogger(__name__)


# Valid identifier pattern for Cypher labels/relationship types
VALID_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class FalkorEngine:
    """
    Sovereign graph engine for JENEZIS built on FalkorDB.

    Thread Safety
    -------------
    This class is NOT thread-safe. Each thread/async task should
    use its own instance or implement connection pooling.

    Attributes
    ----------
    client : FalkorDB
        FalkorDB client instance
    graph : Graph
        Selected graph for query execution
    graph_name : str
        Name of the active graph
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
        graph_name: str = "jenezis"
    ):
        """
        Initialize FalkorDB connection.

        Parameters
        ----------
        host : str
            Redis/FalkorDB host (default: localhost)
        port : int
            Redis/FalkorDB port (default: 6379)
        password : str, optional
            Redis AUTH password
        graph_name : str
            Name of the graph to use (default: jenezis)
        """
        self.client = FalkorDB(host=host, port=port, password=password)
        self.graph = self.client.select_graph(graph_name)
        self.graph_name = graph_name
        logger.info(f"FalkorEngine connected to {host}:{port}, graph='{graph_name}'")

    def close(self):
        """Close the connection (cleanup reference)."""
        self.graph = None
        self.client = None

    # -------------------------------------------------------------------------
    # Query Execution
    # -------------------------------------------------------------------------

    def query(self, cypher: str, params: dict[str, Any] | None = None):
        """
        Execute a Cypher query against the graph.

        Parameters are safely injected via FalkorDB's parameterized queries
        to prevent injection attacks.

        Parameters
        ----------
        cypher : str
            OpenCypher query string with $param placeholders
        params : dict, optional
            Query parameters

        Returns
        -------
        QueryResult
            FalkorDB result with result_set and statistics
        """
        try:
            result = self.graph.query(cypher, params)
            return result
        except Exception as e:
            logger.error(f"FalkorDB query error: {e}\nQuery: {cypher}\nParams: {params}")
            raise

    # -------------------------------------------------------------------------
    # Schema & Index Management
    # -------------------------------------------------------------------------

    def create_vector_index(
        self,
        label: str,
        property_name: str = "embedding",
        dimensions: int = 1536,
        similarity: str = "cosine"
    ):
        """
        Create an HNSW vector index on a node label.

        FalkorDB vector index documentation:
        https://docs.falkordb.com/commands/graph.query.html#vector-indexing

        Parameters
        ----------
        label : str
            Node label (e.g., "Entity", "Chunk")
        property_name : str
            Property containing the vector (default: "embedding")
        dimensions : int
            Vector dimensions (default: 1536 for OpenAI embeddings)
        similarity : str
            Similarity function: "cosine", "euclidean", "ip" (default: cosine)
        """
        self._validate_identifier(label, "label")
        self._validate_identifier(property_name, "property")

        # FalkorDB vector index creation syntax (v4.0+)
        # https://docs.falkordb.com/cypher/indexing/vector-index
        cypher = (
            f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.{property_name}) "
            f"OPTIONS {{dimension:{dimensions}, similarityFunction:'{similarity}'}}"
        )
        try:
            self.query(cypher)
            logger.info(f"Vector index created: :{label}({property_name})")
        except Exception as e:
            err_str = str(e).lower()
            if "already exists" in err_str or "already indexed" in err_str or "index already" in err_str:
                logger.debug(f"Vector index already exists: :{label}({property_name})")
            else:
                raise

    def create_property_index(self, label: str, property_name: str):
        """
        Create a standard property index for faster lookups.

        Parameters
        ----------
        label : str
            Node label
        property_name : str
            Property to index
        """
        self._validate_identifier(label, "label")
        self._validate_identifier(property_name, "property")

        cypher = f"CREATE INDEX FOR (n:{label}) ON (n.{property_name})"
        try:
            self.query(cypher)
            logger.info(f"Property index created: :{label}({property_name})")
        except Exception as e:
            err_str = str(e).lower()
            if "already exists" in err_str or "already indexed" in err_str or "index already" in err_str:
                logger.debug(f"Property index already exists: :{label}({property_name})")
            else:
                raise

    def initialize_schema(self):
        """
        Initialize the JENEZIS graph schema with required indexes.

        Creates:
        - Vector index on :Entity(embedding) for semantic search
        - Vector index on :Chunk(embedding) for document retrieval
        - Property indexes for fast lookups
        """
        # Vector indexes for semantic search
        self.create_vector_index("Entity", "embedding")
        self.create_vector_index("Chunk", "embedding")

        # Property indexes for fast lookups
        self.create_property_index("Entity", "id")
        self.create_property_index("Entity", "canonical_id")
        self.create_property_index("Chunk", "id")
        self.create_property_index("Document", "id")

        logger.info("JENEZIS schema initialized")

    # -------------------------------------------------------------------------
    # Vector Search
    # -------------------------------------------------------------------------

    def vector_search(
        self,
        query_vector: list[float],
        label: str = "Entity",
        property_name: str = "embedding",
        top_k: int = 10
    ) -> list[dict]:
        """
        Perform pure vector similarity search.

        Parameters
        ----------
        query_vector : list[float]
            Query embedding vector
        label : str
            Node label to search (default: Entity)
        property_name : str
            Property containing embeddings (default: embedding)
        top_k : int
            Number of results to return

        Returns
        -------
        list[dict]
            Results with keys: id, name, type, score
        """
        self._validate_identifier(label, "label")

        # FalkorDB requires vecf32() wrapper for vector queries
        # We inject the vector directly into the query as vecf32([...])
        vec_str = ", ".join(str(v) for v in query_vector)

        cypher = f"""
            CALL db.idx.vector.queryNodes('{label}', '{property_name}', {top_k}, vecf32([{vec_str}]))
            YIELD node, score
            RETURN node.id AS id,
                   node.name AS name,
                   node.type AS type,
                   score
            ORDER BY score DESC
        """

        result = self.query(cypher)
        return [
            {"id": row[0], "name": row[1], "type": row[2], "score": row[3]}
            for row in result.result_set
        ]

    def hybrid_search(
        self,
        query_vector: list[float],
        label: str = "Entity",
        cypher_filter: str = "",
        top_k: int = 10,
        expand_neighbors: bool = True
    ) -> list[dict]:
        """
        Hybrid search combining vector similarity with graph filtering.

        This is the core retrieval method - it performs vector search
        then optionally expands to include graph neighbors.

        Parameters
        ----------
        query_vector : list[float]
            Query embedding vector
        label : str
            Node label to search
        cypher_filter : str
            Additional WHERE clause (e.g., "WHERE node.type = 'Risk'")
            Must be pre-validated by caller!
        top_k : int
            Number of results
        expand_neighbors : bool
            If True, include 1-hop neighbors in results

        Returns
        -------
        list[dict]
            Results with context from graph structure
        """
        self._validate_identifier(label, "label")

        # Phase 1: Vector search with optional filter
        # FalkorDB requires vecf32() wrapper for vector queries
        vec_str = ", ".join(str(v) for v in query_vector)

        vector_cypher = f"""
            CALL db.idx.vector.queryNodes('{label}', 'embedding', {top_k * 2}, vecf32([{vec_str}]))
            YIELD node, score
            {cypher_filter}
            RETURN node, score
            ORDER BY score DESC
            LIMIT {top_k}
        """

        vector_results = self.query(vector_cypher)

        results = []
        for row in vector_results.result_set:
            node = row[0]
            score = row[1]

            node_data = {
                "id": node.properties.get("id"),
                "name": node.properties.get("name"),
                "type": node.properties.get("type"),
                "score": score,
                "neighbors": []
            }

            # Phase 2: Expand to neighbors if requested
            if expand_neighbors and node_data["id"]:
                neighbor_cypher = """
                    MATCH (n {id: $node_id})-[r]-(m)
                    RETURN type(r) AS rel_type,
                           m.id AS neighbor_id,
                           m.name AS neighbor_name,
                           m.type AS neighbor_type
                    LIMIT 10
                """
                neighbor_results = self.query(neighbor_cypher, {"node_id": node_data["id"]})
                node_data["neighbors"] = [
                    {
                        "rel_type": nr[0],
                        "id": nr[1],
                        "name": nr[2],
                        "type": nr[3]
                    }
                    for nr in neighbor_results.result_set
                ]

            results.append(node_data)

        return results

    # -------------------------------------------------------------------------
    # Document & Chunk Operations
    # -------------------------------------------------------------------------

    def upsert_document(self, document_id: int, filename: str):
        """
        Create or update a Document node.

        Parameters
        ----------
        document_id : int
            Unique document identifier
        filename : str
            Original filename
        """
        cypher = """
            MERGE (d:Document {id: $doc_id})
            ON CREATE SET d.filename = $filename, d.created_at = timestamp()
            ON MATCH SET d.filename = $filename, d.updated_at = timestamp()
        """
        self.query(cypher, {"doc_id": document_id, "filename": filename})

    def upsert_chunks(self, document_id: int, chunks: list[dict]):
        """
        Batch upsert chunks and link to document.

        Parameters
        ----------
        document_id : int
            Parent document ID
        chunks : list[dict]
            Chunks with keys: id, text, embedding
        """
        if not chunks:
            return

        # Sanitize chunks
        sanitized = [self._sanitize_document(c, ["id"]) for c in chunks]

        # FalkorDB requires embeddings to be stored using vecf32() for vector index
        # We process chunks one at a time to use the vecf32() function
        for chunk in sanitized:
            vec_str = ", ".join(str(v) for v in chunk.get("embedding", []))
            cypher = f"""
                MATCH (d:Document {{id: $doc_id}})
                MERGE (c:Chunk {{id: $chunk_id}})
                ON CREATE SET c.text = $text,
                              c.embedding = vecf32([{vec_str}]),
                              c.created_at = timestamp()
                ON MATCH SET c.text = $text,
                             c.embedding = vecf32([{vec_str}]),
                             c.updated_at = timestamp()
                MERGE (d)-[:HAS_CHUNK]->(c)
            """
            self.query(cypher, {
                "doc_id": document_id,
                "chunk_id": chunk.get("id"),
                "text": chunk.get("text", "")
            })

    # -------------------------------------------------------------------------
    # Entity & Relation Operations
    # -------------------------------------------------------------------------

    def upsert_entities(self, entities: list[dict]):
        """
        Batch upsert entities.

        Since FalkorDB doesn't support dynamic labels in MERGE without APOC,
        we store the entity type as a property and use a generic :Entity label.

        Parameters
        ----------
        entities : list[dict]
            Entities with keys: id, name, type, embedding (optional)
        """
        if not entities:
            return

        # Sanitize entities
        sanitized = [self._sanitize_document(e, ["id"]) for e in entities]

        cypher = """
            UNWIND $batch AS row
            MERGE (e:Entity {id: row.id})
            ON CREATE SET e.name = row.name,
                          e.type = row.type,
                          e.canonical_id = row.canonical_id,
                          e.embedding = row.embedding,
                          e.created_at = timestamp()
            ON MATCH SET e.name = row.name,
                         e.type = row.type,
                         e.canonical_id = row.canonical_id,
                         e.embedding = row.embedding,
                         e.updated_at = timestamp()
        """
        self.query(cypher, {"batch": sanitized})

    def upsert_relations(self, relations: list[dict]):
        """
        Batch upsert relations between entities.

        Since Cypher doesn't allow parameterized relationship types,
        we group by type and execute separate queries.

        Parameters
        ----------
        relations : list[dict]
            Relations with keys: source_id, target_id, type, chunk_id (optional)
        """
        if not relations:
            return

        # Group relations by type
        grouped: dict[str, list[dict]] = defaultdict(list)
        for rel in relations:
            rel_type = rel.get("type", "RELATED_TO")
            self._validate_identifier(rel_type, "relationship type")
            grouped[rel_type].append(rel)

        # Execute batch upsert per relationship type
        for rel_type, batch in grouped.items():
            cypher = f"""
                UNWIND $batch AS row
                MATCH (s:Entity {{id: row.source_id}})
                MATCH (t:Entity {{id: row.target_id}})
                MERGE (s)-[r:{rel_type}]->(t)
                ON CREATE SET r.chunk_id = row.chunk_id, r.created_at = timestamp()
                ON MATCH SET r.chunk_id = row.chunk_id, r.updated_at = timestamp()
            """
            self.query(cypher, {"batch": batch})

    def link_entities_to_chunk(self, chunk_id: str, entity_ids: list[str]):
        """
        Create MENTIONS relationships between chunk and entities.

        Parameters
        ----------
        chunk_id : str
            Chunk identifier
        entity_ids : list[str]
            Entity identifiers mentioned in chunk
        """
        if not entity_ids:
            return

        cypher = """
            MATCH (c:Chunk {id: $chunk_id})
            UNWIND $entity_ids AS eid
            MATCH (e:Entity {id: eid})
            MERGE (c)-[:MENTIONS]->(e)
        """
        self.query(cypher, {"chunk_id": chunk_id, "entity_ids": entity_ids})

    # -------------------------------------------------------------------------
    # Deletion & Cleanup
    # -------------------------------------------------------------------------

    def delete_document(self, document_id: int):
        """
        Delete a document and all its chunks.

        Note: Entities are NOT deleted - they may be referenced by other docs.
        Use garbage_collect_orphans() to clean up orphaned entities.

        Parameters
        ----------
        document_id : int
            Document to delete
        """
        # Delete chunks and their relationships first
        cypher = """
            MATCH (d:Document {id: $doc_id})-[:HAS_CHUNK]->(c:Chunk)
            DETACH DELETE c
        """
        self.query(cypher, {"doc_id": document_id})

        # Delete document
        cypher = "MATCH (d:Document {id: $doc_id}) DETACH DELETE d"
        self.query(cypher, {"doc_id": document_id})

        logger.info(f"Deleted document {document_id} and its chunks")

    def garbage_collect_orphans(self) -> int:
        """
        Delete entities that are no longer mentioned by any chunk.

        Returns
        -------
        int
            Number of entities deleted
        """
        # Find and delete orphaned entities
        cypher = """
            MATCH (e:Entity)
            WHERE NOT (e)<-[:MENTIONS]-()
            WITH e, e.id AS deleted_id
            DETACH DELETE e
            RETURN count(deleted_id) AS deleted_count
        """
        result = self.query(cypher)
        count = result.result_set[0][0] if result.result_set else 0
        logger.info(f"Garbage collected {count} orphaned entities")
        return count

    def clear_graph(self):
        """Delete all nodes and relationships. Use with caution!"""
        self.query("MATCH (n) DETACH DELETE n")
        logger.warning(f"Cleared all data from graph '{self.graph_name}'")

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def get_entity_by_id(self, entity_id: str) -> dict | None:
        """Fetch a single entity by ID."""
        cypher = """
            MATCH (e:Entity {id: $eid})
            RETURN e.id AS id, e.name AS name, e.type AS type,
                   e.canonical_id AS canonical_id
        """
        result = self.query(cypher, {"eid": entity_id})
        if result.result_set:
            row = result.result_set[0]
            return {"id": row[0], "name": row[1], "type": row[2], "canonical_id": row[3]}
        return None

    def get_chunk_context(self, chunk_id: str) -> dict | None:
        """
        Get chunk with its mentioned entities for RAG context.

        Returns
        -------
        dict
            Chunk data with 'entities' list
        """
        cypher = """
            MATCH (c:Chunk {id: $cid})
            OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
            RETURN c.id AS chunk_id,
                   c.text AS text,
                   collect({id: e.id, name: e.name, type: e.type}) AS entities
        """
        result = self.query(cypher, {"cid": chunk_id})
        if result.result_set:
            row = result.result_set[0]
            return {
                "chunk_id": row[0],
                "text": row[1],
                "entities": [e for e in row[2] if e.get("id")]  # Filter nulls
            }
        return None

    def count_nodes(self, label: str | None = None) -> int:
        """Count nodes, optionally by label."""
        if label:
            self._validate_identifier(label, "label")
            cypher = f"MATCH (n:{label}) RETURN count(n)"
        else:
            cypher = "MATCH (n) RETURN count(n)"

        result = self.query(cypher)
        return result.result_set[0][0] if result.result_set else 0

    # -------------------------------------------------------------------------
    # Input Sanitization
    # -------------------------------------------------------------------------

    def _validate_identifier(self, value: str, context: str):
        """
        Validate that a string is safe for use as Cypher identifier.

        Prevents injection via label/relationship type names.

        Raises
        ------
        ValueError
            If identifier contains invalid characters
        """
        if not VALID_IDENTIFIER_PATTERN.match(value):
            raise ValueError(
                f"Invalid {context}: '{value}'. "
                f"Must match pattern: {VALID_IDENTIFIER_PATTERN.pattern}"
            )

    def _sanitize_document(
        self,
        doc: dict,
        required_keys: list[str] | None = None
    ) -> dict:
        """
        Sanitize a document for safe insertion.

        - Filters non-string keys
        - Removes NaN/Inf float values
        - Strips null bytes from strings
        - Validates required keys

        Parameters
        ----------
        doc : dict
            Document to sanitize
        required_keys : list[str], optional
            Keys that must be present

        Returns
        -------
        dict
            Sanitized document

        Raises
        ------
        ValueError
            If required key is missing or None
        """
        sanitized = {}

        for key, value in doc.items():
            # Skip non-string keys
            if not isinstance(key, str):
                logger.warning(f"Skipping non-string key: {key!r}")
                continue

            # Skip invalid float values
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                logger.warning(f"Skipping invalid float for key '{key}': {value}")
                continue

            # Sanitize strings (remove null bytes)
            if isinstance(value, str) and "\x00" in value:
                value = value.replace("\x00", "")
                logger.warning(f"Removed null bytes from key '{key}'")

            sanitized[key] = value

        # Validate required keys
        if required_keys:
            for key in required_keys:
                if key not in sanitized or sanitized[key] is None:
                    raise ValueError(f"Required key '{key}' missing or None in: {doc}")

        return sanitized
