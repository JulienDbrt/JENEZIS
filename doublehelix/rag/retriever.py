"""
Hybrid retriever combining vector search and graph traversal, with Reciprocal
Rank Fusion (RRF) to merge results.
"""
import asyncio
import logging
from typing import List, Dict, Any

from doublehelix.core.config import get_settings
from doublehelix.ingestion.embedder import get_embedder
from doublehelix.ingestion.extractor import get_extractor, Extractor
from doublehelix.storage.graph_store import GraphStore

logger = logging.getLogger(__name__)
settings = get_settings()

class HybridRetriever:
    """
    Performs hybrid retrieval by combining results from vector search
    (semantic similarity) and graph search (explicit connections).
    """
    def __init__(self, graph_store: GraphStore, extractor: Extractor):
        self.graph_store = graph_store
        self.embedder = get_embedder()
        self.extractor = extractor
        self.rrf_k = settings.RRF_K

    async def retrieve(self, query: str, top_k: int = 10, search_type: str = "hybrid") -> List[Dict[str, Any]]:
        """
        Main retrieval method.

        Args:
            query: The user's search query.
            top_k: The final number of documents to return.
            search_type: "hybrid", "vector", or "graph".

        Returns:
            A ranked list of context chunks.
        """
        if search_type == "vector":
            return await self._vector_search(query, top_k)
        if search_type == "graph":
            return await self._graph_search(query, top_k)
        if search_type == "hybrid":
            # Perform vector and graph search in parallel
            vector_results, graph_results = await asyncio.gather(
                self._vector_search(query, top_k * 2),
                self._graph_search(query, top_k * 2)
            )
            # Combine results using RRF
            fused_results = self._reciprocal_rank_fusion([vector_results, graph_results])
            # Sort by fused score and take top_k
            sorted_results = sorted(fused_results, key=lambda x: x['score'], reverse=True)
            return sorted_results[:top_k]
        
        raise ValueError(f"Unknown search type: {search_type}")

    async def _vector_search(self, query: str, k: int) -> List[Dict[str, Any]]:
        """Performs pure vector search."""
        query_embedding = (await self.embedder.embed_batch([query]))[0]
        if not query_embedding:
            return []
        
        results = await self.graph_store.vector_search(query_embedding, top_k=k)
        logger.info(f"Vector search found {len(results)} results for query: '{query}'")
        return results

    async def _graph_search(self, query: str, k: int) -> List[Dict[str, Any]]:
        """
        Performs true graph-based search by traversing paths between query entities.
        1. Extracts entities from the query.
        2. Finds paths (up to 2 hops) between these entities in the graph.
        3. Retrieves chunks that mention any entity along these paths.
        4. Ranks chunks based on their connection to the paths.
        """
        extraction = await self.extractor.extract_from_chunk(query)
        entity_ids = [e.id for e in extraction.entities]

        if not entity_ids or len(entity_ids) < 1:
            logger.info("Graph search requires at least one identifiable entity in the query.")
            return []

        # This query is far more powerful than co-occurrence. It finds the "connective tissue".
        cypher_query = """
        // 1. Start with the entities found in the user's query
        WITH $entity_ids as query_entity_ids
        MATCH (e:Entity)
        WHERE e.canonical_id IN query_entity_ids
        WITH collect(e) as query_entities

        // 2. If there are multiple entities, find paths between them.
        // If only one, find its neighbors.
        CALL apoc.path.subgraphNodes(query_entities, {
            maxLevel: 2,
            relationshipFilter:'>'
        }) YIELD node as path_node

        // 3. Find all chunks that mention any of these path entities
        WITH path_node, query_entities
        MATCH (path_node)<-[:MENTIONS]-(c:Chunk)

        // 4. Score the chunks. A higher score is given to chunks that
        // are mentioned by entities from the original query.
        WITH c, path_node, CASE WHEN path_node in query_entities THEN 2 ELSE 1 END as points
        WITH c, sum(points) as score

        // 5. Retrieve chunk details and return
        MATCH (c)<-[:HAS_CHUNK]-(d:Document)
        RETURN
            c.id as chunk_id,
            c.text as text,
            d.id as document_id,
            score
        ORDER BY score DESC
        LIMIT $k
        """
        try:
            records, _, _ = await self.graph_store.driver.execute_query(
                cypher_query,
                entity_ids=entity_ids,
                k=k,
                database_=self.graph_store.database
            )
            results = [r.data() for r in records]
            logger.info(f"True graph search found {len(results)} results for entities: {entity_ids}")
            return results
        except Exception as e:
            logger.error(f"Graph search query failed. Ensure APOC plugin is installed. Error: {e}")
            return []

    def _reciprocal_rank_fusion(self, result_sets: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Merges multiple ranked lists of results using RRF.
        Each result dict must have a 'chunk_id' key.
        """
        scores = {}
        # Keep track of the actual documents to avoid re-fetching
        docs_by_id = {}

        for results in result_sets:
            for rank, doc in enumerate(results, 1):
                doc_id = doc['chunk_id']
                if doc_id not in docs_by_id:
                    docs_by_id[doc_id] = doc
                
                # Calculate RRF score
                rrf_score = 1 / (self.rrf_k + rank)
                
                if doc_id not in scores:
                    scores[doc_id] = 0
                scores[doc_id] += rrf_score

        # Combine into a final list of documents with their fused scores
        fused_results = []
        for doc_id, score in scores.items():
            final_doc = docs_by_id[doc_id]
            final_doc['score'] = score
            fused_results.append(final_doc)
            
        return fused_results
