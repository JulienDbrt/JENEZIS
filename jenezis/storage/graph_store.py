"""
Interface for all Neo4j graph operations, including ingestion, updates,
deletions, and search. It handles the creation of nodes, relationships,
vector indexes, and the clean purging of orphaned data.
"""
import logging
import re
from typing import List, Dict, Any

from neo4j import AsyncDriver

from jenezis.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# --- Security: Cypher Label/Type Sanitization ---

# Pattern for valid Neo4j labels/relationship types
# Must start with letter, contain only alphanumeric and underscore
SAFE_LABEL_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')

# Maximum length for labels (Neo4j doesn't have strict limit but we impose one)
MAX_LABEL_LENGTH = 64


class InvalidLabelError(ValueError):
    """Raised when an entity type or relationship type is invalid."""
    pass


def sanitize_label(label: str, label_kind: str = "entity type") -> str:
    """
    Sanitizes a Neo4j label or relationship type to prevent Cypher injection.

    Args:
        label: The label/type string to sanitize
        label_kind: Description for error messages ("entity type" or "relationship type")

    Returns:
        The validated label string (unchanged if valid)

    Raises:
        InvalidLabelError: If the label contains dangerous characters or patterns
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


def sanitize_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sanitizes a list of entities, validating all type fields.

    Args:
        entities: List of entity dicts with 'id', 'name', 'type'

    Returns:
        The same list with validated types

    Raises:
        InvalidLabelError: If any entity has an invalid type
    """
    for entity in entities:
        entity_type = entity.get('type', '')
        sanitize_label(entity_type, "entity type")
    return entities


def sanitize_relations(relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sanitizes a list of relations, validating all type fields.

    Args:
        relations: List of relation dicts with 'source_id', 'target_id', 'type', 'chunk_id'

    Returns:
        The same list with validated types

    Raises:
        InvalidLabelError: If any relation has an invalid type
    """
    for relation in relations:
        rel_type = relation.get('type', '')
        sanitize_label(rel_type, "relationship type")
    return relations

class GraphStore:
    """
    Manages all interactions with the Neo4j graph database.
    """
    def __init__(self, driver: AsyncDriver):
        self.driver = driver
        self.database = settings.NEO4J_DATABASE

    async def initialize_constraints_and_indexes(self):
        """
        Idempotently creates necessary constraints and indexes in the graph.
        This is crucial for performance and data integrity.
        """
        async with self.driver.session(database=self.database) as session:
            # Constraints for uniqueness
            await session.run("CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
            await session.run("CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE")
            await session.run("CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.canonical_id IS UNIQUE")
            logger.info("Graph constraints ensured.")

            # Vector Index for Chunk embeddings
            try:
                await session.run("CREATE FULLTEXT INDEX entity_names_ft_index IF NOT EXISTS FOR (e:Entity) ON (e.name)")
                logger.info("Full-text index 'entity_names_ft_index' ensured.")

                await session.run(f"""
                CREATE VECTOR INDEX `chunk_embeddings` IF NOT EXISTS
                FOR (c:Chunk) ON (c.embedding)
                OPTIONS {{ indexConfig: {{
                    `vector.dimensions`: {settings.EMBEDDING_DIMENSIONS},
                    `vector.similarity_function`: 'cosine'
                }}}}
                """)
                logger.info("Vector index 'chunk_embeddings' ensured.")
            except Exception as e:
                logger.error(f"Failed to create vector index or full-text index. Your Neo4j version/edition might not support it. Error: {e}")

    async def add_document_node(self, document_id: int, filename: str):
        """Creates a 'Document' node in the graph."""
        query = """
        MERGE (d:Document {id: $document_id})
        ON CREATE SET d.filename = $filename, d.created_at = datetime()
        ON MATCH SET d.filename = $filename, d.updated_at = datetime()
        """
        await self.driver.execute_query(
            query,
            document_id=document_id,
            filename=filename,
            database_=self.database
        )

    async def add_chunks(self, document_id: int, chunks: List[Dict[str, Any]]):
        """
        Adds a batch of 'Chunk' nodes and connects them to their parent 'Document'.
        'chunks' is a list of dicts, each with 'id', 'text', and 'embedding'.
        """
        query = """
        UNWIND $chunks as chunk_data
        MATCH (d:Document {id: $document_id})
        MERGE (c:Chunk {id: chunk_data.id})
        ON CREATE SET
            c.text = chunk_data.text,
            c.embedding = chunk_data.embedding,
            c.created_at = datetime()
        MERGE (d)-[:HAS_CHUNK]->(c)
        """
        await self.driver.execute_query(
            query,
            document_id=document_id,
            chunks=chunks,
            database_=self.database
        )

    async def add_entities_and_relations(self, entities: List[Dict], relations: List[Dict]):
        """
        Idempotently adds entities and relationships using dynamic labels for nodes
        based on the entity type from the ontology.
        - entities: [{'id', 'name', 'type'}]
        - relations: [{'source_id', 'target_id', 'type', 'chunk_id'}]

        Raises:
            InvalidLabelError: If any entity type or relation type fails validation
        """
        # SECURITY: Sanitize all entity types and relation types BEFORE using in Cypher
        # This prevents Cypher injection via malicious LLM output
        sanitize_entities(entities)
        if relations:
            sanitize_relations(relations)

        # This operation is broken into two parts for clarity and robustness.

        # 1. Merge Nodes with Dynamic Labels using APOC
        # We give each node a base 'Entity' label plus its specific type label.
        # SECURITY NOTE: entity_data.type is now guaranteed to be safe (alphanumeric + underscore)
        node_query = """
        UNWIND $entities as entity_data
        // Use apoc.merge.node to handle dynamic labels from the entity type
        CALL apoc.merge.node(['Entity', entity_data.type], {canonical_id: entity_data.id}) YIELD node
        SET node.name = entity_data.name,
            node.updated_at = datetime()
        WITH node
        WHERE node.created_at IS NULL
        SET node.created_at = datetime()
        """
        try:
            await self.driver.execute_query(node_query, entities=entities, database_=self.database)
        except Exception as e:
            logger.error(f"Failed to merge nodes with dynamic labels. Ensure APOC plugin is installed. Error: {e}")
            raise

        # 2. Merge Relationships between the now-existing nodes
        if relations:
            # SECURITY NOTE: rel_data.type is now guaranteed to be safe
            relation_query = """
            UNWIND $relations as rel_data
            MATCH (source:Entity {canonical_id: rel_data.source_id})
            MATCH (target:Entity {canonical_id: rel_data.target_id})
            MATCH (chunk:Chunk {id: rel_data.chunk_id})
            // Create the dynamic relationship, also with APOC for safety
            CALL apoc.create.relationship(source, rel_data.type, {}, target) YIELD rel
            // Link the chunk to the entities it mentions
            MERGE (chunk)-[:MENTIONS]->(source)
            MERGE (chunk)-[:MENTIONS]->(target)
            """
            try:
                await self.driver.execute_query(relation_query, relations=relations, database_=self.database)
            except Exception as e:
                logger.error(f"Failed to create relationships. Error: {e}")
                raise

    async def delete_document_and_associated_data(self, document_id: int):
        """
        Deletes a document and its chunks from the graph.
        This operation is now decoupled from orphan entity cleanup.
        """
        query = """
        MATCH (d:Document {id: $document_id})
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        DETACH DELETE d, c
        """
        await self.driver.execute_query(query, document_id=document_id, database_=self.database)
        logger.info(f"Successfully deleted document {document_id} and its chunks.")

    async def garbage_collect_orphaned_entities(self):
        """
        Finds and deletes orphaned entities in batches using APOC.
        An orphan is an entity with no connections to any chunks.
        """
        # This query uses apoc.periodic.iterate for scalable batch processing.
        # It finds all entities that are not mentioned by any chunk and deletes them.
        query = """
        CALL apoc.periodic.iterate(
            "MATCH (e:Entity) WHERE NOT (e)<-[:MENTIONS]-() RETURN e",
            "DETACH DELETE e",
            {batchSize: 1000, parallel: false}
        )
        YIELD batches, total, errorMessages
        RETURN batches, total, errorMessages
        """
        try:
            result, _, _ = await self.driver.execute_query(query, database_=self.database)
            summary = result[0]
            logger.info(f"Orphaned entity garbage collection complete. "
                        f"Processed {summary['total']} entities in {summary['batches']} batches.")
            if summary['errorMessages']:
                logger.error(f"Errors during garbage collection: {summary['errorMessages']}")
        except Exception as e:
            logger.error(f"Garbage collection task failed. Ensure APOC plugin is installed. Error: {e}")
            raise

    async def vector_search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Performs a vector similarity search on chunk embeddings.
        Falls back to returning empty results if vector index doesn't exist (Community Edition).
        """
        query = """
        CALL db.index.vector.queryNodes('chunk_embeddings', $top_k, $embedding) YIELD node, score
        MATCH (node)<-[:HAS_CHUNK]-(d:Document)
        RETURN
            node.id as chunk_id,
            node.text as text,
            score,
            d.id as document_id
        """
        try:
            records, _, _ = await self.driver.execute_query(
                query,
                top_k=top_k,
                embedding=query_embedding,
                database_=self.database
            )
            return [record.data() for record in records]
        except Exception as e:
            if "vector" in str(e).lower() or "index" in str(e).lower():
                logger.warning(f"Vector search failed (likely no vector index support): {e}")
                # Fallback: return all chunks sorted by text length as a basic fallback
                fallback_query = """
                MATCH (c:Chunk)<-[:HAS_CHUNK]-(d:Document)
                RETURN c.id as chunk_id, c.text as text, 0.5 as score, d.id as document_id
                LIMIT $top_k
                """
                records, _, _ = await self.driver.execute_query(
                    fallback_query, top_k=top_k, database_=self.database
                )
                return [record.data() for record in records]
            raise
