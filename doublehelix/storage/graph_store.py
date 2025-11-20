"""
Interface for all Neo4j graph operations, including ingestion, updates,
deletions, and search. It handles the creation of nodes, relationships,
vector indexes, and the clean purging of orphaned data.
"""
import logging
from typing import List, Dict, Any

from neo4j import AsyncDriver

from doublehelix.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

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
                logger.error(f"Failed to create vector index 'chunk_embeddings'. Your Neo4j version might not support it. Error: {e}")

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
        Idempotently adds entities and relationships extracted from text.
        - entities: [{'id', 'name', 'type'}]
        - relations: [{'source_id', 'target_id', 'type', 'chunk_id'}]
        """
        # Batch-add entities
        entity_query = """
        UNWIND $entities as entity_data
        MERGE (e:Entity {canonical_id: entity_data.id})
        ON CREATE SET
            e.name = entity_data.name,
            e.type = entity_data.type,
            e.created_at = datetime()
        """
        await self.driver.execute_query(entity_query, entities=entities, database_=self.database)

        # Batch-add relationships and link to chunks
        relation_query = """
        UNWIND $relations as rel_data
        MATCH (source:Entity {canonical_id: rel_data.source_id})
        MATCH (target:Entity {canonical_id: rel_data.target_id})
        MATCH (chunk:Chunk {id: rel_data.chunk_id})
        // Create the dynamic relationship between entities
        CALL apoc.create.relationship(source, rel_data.type, {}, target) YIELD rel
        // Link the chunk to the entities it mentions
        MERGE (chunk)-[:MENTIONS]->(source)
        MERGE (chunk)-[:MENTIONS]->(target)
        """
        # Note: apoc.create.relationship requires the APOC plugin to be installed in Neo4j.
        try:
            await self.driver.execute_query(relation_query, relations=relations, database_=self.database)
        except Exception as e:
            logger.error(f"Failed to create relationships. Ensure APOC plugin is installed. Error: {e}")
            # Provide a fallback or raise the error
            raise

    async def delete_document_and_associated_data(self, document_id: int):
        """
        Deletes a document, its chunks, and any entities that become orphaned
        as a result of this deletion.
        """
        # This is a complex, multi-step transaction.
        query = """
        MATCH (d:Document {id: $document_id})-[r_has_chunk:HAS_CHUNK]->(c:Chunk)
        // Collect chunks and the document for deletion
        WITH d, collect(c) as chunks_to_delete
        // Find all entities mentioned in these chunks
        OPTIONAL MATCH (c_to_del)-[:MENTIONS]->(e:Entity)
        WHERE c_to_del in chunks_to_delete
        WITH d, chunks_to_delete, collect(DISTINCT e) as mentioned_entities
        // For each mentioned entity, check if it has relationships to other chunks
        // not in the deletion list.
        UNWIND mentioned_entities as entity
        OPTIONAL MATCH (entity)<-[:MENTIONS]-(other_chunk:Chunk)
        WHERE NOT other_chunk in chunks_to_delete
        WITH d, chunks_to_delete, entity, count(other_chunk) as other_connections
        // Collect orphaned entities (those with no other connections)
        WITH d, chunks_to_delete, collect(CASE WHEN other_connections = 0 THEN entity ELSE null END) as orphaned_entities
        // Delete the document, its chunks, and the orphaned entities
        DETACH DELETE d
        FOREACH (c IN chunks_to_delete | DETACH DELETE c)
        FOREACH (e IN [o IN orphaned_entities WHERE o IS NOT NULL] | DETACH DELETE e)
        """
        await self.driver.execute_query(query, document_id=document_id, database_=self.database)
        logger.info(f"Successfully deleted document {document_id} and cleaned up orphaned entities.")

    async def vector_search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Performs a vector similarity search on chunk embeddings."""
        query = """
        CALL db.index.vector.queryNodes('chunk_embeddings', $top_k, $embedding) YIELD node, score
        MATCH (node)-<-[:HAS_CHUNK]-(d:Document)
        RETURN
            node.id as chunk_id,
            node.text as text,
            score,
            d.id as document_id
        """
        records, _, _ = await self.driver.execute_query(
            query,
            top_k=top_k,
            embedding=query_embedding,
            database_=self.database
        )
        return [record.data() for record in records]
