"""
GraphStore - Unified graph database interface for JENEZIS.

This module provides a facade over the FalkorEngine, maintaining API compatibility
with the rest of the JENEZIS codebase while using FalkorDB as the backend.

Migration Note
--------------
This version replaces the Neo4j-based implementation with FalkorDB.
The interface remains identical to ensure backward compatibility.

Key Changes from Neo4j Version
------------------------------
- No APOC dependency (dynamic labels stored as properties)
- Vector search via FalkorDB native HNSW indexes
- Redis-based persistence (faster, simpler)

Copyright (c) 2025 Sigilum - BSL 1.1 License
"""

import logging
import re
from typing import Any

from jenezis.core.config import get_settings
from jenezis.storage.falkor_engine import FalkorEngine

logger = logging.getLogger(__name__)
settings = get_settings()


# --- Security: Cypher Label/Type Sanitization ---

# Pattern for valid labels/relationship types
# Must start with letter, contain only alphanumeric and underscore
SAFE_LABEL_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')

# Maximum length for labels
MAX_LABEL_LENGTH = 64


class InvalidLabelError(ValueError):
    """Raised when an entity type or relationship type is invalid."""
    pass


def sanitize_label(label: str, label_kind: str = "entity type") -> str:
    """
    Sanitizes a label or relationship type to prevent Cypher injection.

    Args:
        label: The label/type string to sanitize
        label_kind: Description for error messages

    Returns:
        The validated label string (unchanged if valid)

    Raises:
        InvalidLabelError: If the label contains dangerous characters
    """
    if not label:
        raise InvalidLabelError(f"Empty {label_kind} is not allowed")

    # Strip null bytes and control characters
    cleaned = label.replace('\x00', '').strip()

    # Check length
    if len(cleaned) > MAX_LABEL_LENGTH:
        raise InvalidLabelError(
            f"{label_kind} '{cleaned[:20]}...' exceeds maximum length of {MAX_LABEL_LENGTH}"
        )

    # Validate against safe pattern
    if not SAFE_LABEL_PATTERN.match(cleaned):
        raise InvalidLabelError(
            f"Invalid {label_kind} '{cleaned}'. "
            f"Must start with a letter and contain only letters, numbers, and underscores."
        )

    # Additional checks for known injection patterns
    dangerous_patterns = [
        '`', "'", '"',  # Quote escapes
        ']', '[',       # Array manipulation
        ')', '(',       # Function/grouping
        ';', '//',      # Statement terminator, comments
        '\n', '\r',     # Newlines
    ]
    for pattern in dangerous_patterns:
        if pattern in label:
            raise InvalidLabelError(
                f"Invalid {label_kind} '{label}': contains forbidden character '{pattern}'"
            )

    return cleaned


def sanitize_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sanitizes a list of entities, validating all type fields.
    """
    for entity in entities:
        entity_type = entity.get('type', '')
        sanitize_label(entity_type, "entity type")
    return entities


def sanitize_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sanitizes a list of relations, validating all type fields.
    """
    for relation in relations:
        rel_type = relation.get('type', '')
        sanitize_label(rel_type, "relationship type")
    return relations


class GraphStore:
    """
    Manages all interactions with the FalkorDB graph database.

    This class provides the same interface as the previous Neo4j-based
    implementation but uses FalkorDB as the backend.

    Attributes
    ----------
    engine : FalkorEngine
        The underlying FalkorDB engine
    """

    def __init__(self, engine: FalkorEngine | None = None):
        """
        Initialize GraphStore.

        Parameters
        ----------
        engine : FalkorEngine, optional
            Pre-configured engine. If None, creates one from settings.
        """
        if engine is not None:
            self.engine = engine
        else:
            # Create engine from settings
            self.engine = FalkorEngine(
                host=getattr(settings, 'FALKOR_HOST', 'localhost'),
                port=getattr(settings, 'FALKOR_PORT', 6379),
                password=getattr(settings, 'FALKOR_PASSWORD', None),
                graph_name=getattr(settings, 'FALKOR_GRAPH', 'jenezis')
            )

    async def initialize_constraints_and_indexes(self):
        """
        Idempotently creates necessary indexes in the graph.

        Note: FalkorDB doesn't have constraints like Neo4j, but we create
        property indexes and vector indexes for performance.
        """
        # FalkorEngine operations are synchronous, but we keep async interface
        # for backward compatibility
        self.engine.initialize_schema()
        logger.info("Graph schema initialized (FalkorDB)")

    async def add_document_node(self, document_id: int, filename: str):
        """Creates a 'Document' node in the graph."""
        self.engine.upsert_document(document_id, filename)

    async def add_chunks(self, document_id: int, chunks: list[dict[str, Any]]):
        """
        Adds a batch of 'Chunk' nodes and connects them to their parent 'Document'.
        """
        self.engine.upsert_chunks(document_id, chunks)

    async def add_entities_and_relations(
        self,
        entities: list[dict],
        relations: list[dict]
    ):
        """
        Idempotently adds entities and relationships.

        Unlike the Neo4j version that uses APOC for dynamic labels,
        we store the entity type as a property since FalkorDB doesn't
        support APOC procedures.

        Parameters
        ----------
        entities : list[dict]
            List of entities with keys: id, name, type
        relations : list[dict]
            List of relations with keys: source_id, target_id, type, chunk_id

        Raises
        ------
        InvalidLabelError
            If any entity type or relation type fails validation
        """
        # SECURITY: Sanitize all entity types and relation types
        sanitize_entities(entities)
        if relations:
            sanitize_relations(relations)

        # Upsert entities
        self.engine.upsert_entities(entities)

        # Upsert relations
        if relations:
            self.engine.upsert_relations(relations)

            # Link entities to their source chunks
            # Group by chunk_id for efficiency
            from collections import defaultdict
            chunk_entities: dict[str, set[str]] = defaultdict(set)

            for rel in relations:
                chunk_id = rel.get('chunk_id')
                if chunk_id:
                    chunk_entities[chunk_id].add(rel['source_id'])
                    chunk_entities[chunk_id].add(rel['target_id'])

            for chunk_id, entity_ids in chunk_entities.items():
                self.engine.link_entities_to_chunk(chunk_id, list(entity_ids))

    async def delete_document_and_associated_data(self, document_id: int):
        """
        Deletes a document and its chunks from the graph.

        Note: Entities are NOT deleted here - they may be referenced
        by other documents. Use garbage_collect_orphaned_entities()
        to clean up orphaned entities.
        """
        self.engine.delete_document(document_id)
        logger.info(f"Successfully deleted document {document_id} and its chunks.")

    async def garbage_collect_orphaned_entities(self):
        """
        Finds and deletes orphaned entities.

        An orphan is an entity with no connections to any chunks.
        """
        deleted_count = self.engine.garbage_collect_orphans()
        logger.info(f"Orphaned entity garbage collection complete. "
                    f"Deleted {deleted_count} entities.")

    async def vector_search(
        self,
        query_embedding: list[float],
        top_k: int = 5
    ) -> list[dict[str, Any]]:
        """
        Performs a vector similarity search on chunk embeddings.

        Parameters
        ----------
        query_embedding : list[float]
            The query vector
        top_k : int
            Number of results to return

        Returns
        -------
        list[dict]
            Results with keys: chunk_id, text, score, document_id
        """
        # Search chunks by embedding
        cypher = """
            CALL db.idx.vector.queryNodes('Chunk', 'embedding', $top_k, $vec)
            YIELD node, score
            MATCH (d:Document)-[:HAS_CHUNK]->(node)
            RETURN node.id AS chunk_id,
                   node.text AS text,
                   score,
                   d.id AS document_id
            ORDER BY score DESC
        """
        try:
            result = self.engine.query(cypher, {"top_k": top_k, "vec": query_embedding})
            return [
                {
                    "chunk_id": row[0],
                    "text": row[1],
                    "score": row[2],
                    "document_id": row[3]
                }
                for row in result.result_set
            ]
        except Exception as e:
            logger.warning(f"Vector search failed: {e}. Returning fallback results.")
            # Fallback: return recent chunks
            fallback_cypher = """
                MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
                RETURN c.id AS chunk_id, c.text AS text, 0.5 AS score, d.id AS document_id
                LIMIT $top_k
            """
            result = self.engine.query(fallback_cypher, {"top_k": top_k})
            return [
                {
                    "chunk_id": row[0],
                    "text": row[1],
                    "score": row[2],
                    "document_id": row[3]
                }
                for row in result.result_set
            ]

    # -------------------------------------------------------------------------
    # New Methods (FalkorDB-specific capabilities)
    # -------------------------------------------------------------------------

    async def hybrid_search(
        self,
        query_embedding: list[float],
        entity_type_filter: str | None = None,
        top_k: int = 10,
        expand_neighbors: bool = True
    ) -> list[dict[str, Any]]:
        """
        Hybrid search combining vector similarity with graph structure.

        This is the primary retrieval method for RAG - it finds relevant
        entities via embedding similarity and enriches them with graph context.

        Parameters
        ----------
        query_embedding : list[float]
            Query vector
        entity_type_filter : str, optional
            Filter by entity type (e.g., "Risk", "Person")
        top_k : int
            Number of results
        expand_neighbors : bool
            Include 1-hop neighbors in results

        Returns
        -------
        list[dict]
            Rich results with entity data and neighbor context
        """
        # Build optional filter clause
        cypher_filter = ""
        if entity_type_filter:
            sanitize_label(entity_type_filter, "entity type filter")
            cypher_filter = f"WHERE node.type = '{entity_type_filter}'"

        return self.engine.hybrid_search(
            query_vector=query_embedding,
            label="Entity",
            cypher_filter=cypher_filter,
            top_k=top_k,
            expand_neighbors=expand_neighbors
        )

    async def get_entity_context(self, entity_id: str) -> dict | None:
        """
        Get full context for an entity including its relationships.

        Useful for building rich RAG context.
        """
        return self.engine.get_entity_by_id(entity_id)

    async def get_chunk_with_entities(self, chunk_id: str) -> dict | None:
        """
        Get a chunk with all its mentioned entities.

        Useful for building grounded responses.
        """
        return self.engine.get_chunk_context(chunk_id)


# Factory function for backward compatibility
async def get_graph_store() -> GraphStore:
    """
    Factory function to create a GraphStore instance.

    This replaces the Neo4j driver-based initialization.
    """
    return GraphStore()
