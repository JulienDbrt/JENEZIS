"""
Hybrid retriever combining semantic vector search with LLM-driven
graph-based reasoning.

JENEZIS FalkorDB Implementation
-------------------------------
This retriever uses FalkorDB's native vector indexes for semantic search
and standard Cypher (no APOC) for graph traversal. The hybrid search
combines both in a single database round-trip where possible.

SECURITY: Uses prompt_security module to validate LLM query planner output
and sanitize user queries before processing.

Copyright (c) 2025 Sigilum - BSL 1.1 License
"""

import asyncio
import json
import logging
from typing import Any

import openai

from jenezis.core.config import get_settings
from jenezis.core.prompt_security import (
    sanitize_for_prompt,
    validate_llm_json_output,
)
from jenezis.ingestion.embedder import get_embedder
from jenezis.storage.graph_store import GraphStore, sanitize_label

logger = logging.getLogger(__name__)
settings = get_settings()

# Allowed intents for the Cypher query planner
ALLOWED_INTENTS = ["find_connections", "find_mitigating_controls", "get_attributes", "semantic_search"]


# --- LLM-driven Query Planner ---

QUERY_PLANNER_PROMPT = """
You are an expert knowledge graph query planner. Your task is to decompose a user's natural language question into a structured JSON command.

The graph has:
- Entity nodes with properties: id, name, type (e.g., type="Risk", type="Control", type="Person")
- Relationship types: MITIGATES, AFFECTS, WORKS_FOR, MENTIONS, etc.
- Chunk nodes containing source text
- Document nodes

Select one of the following intents:
- `semantic_search`: For general questions that need semantic similarity. Best for most queries.
- `find_connections`: For questions about how specific named entities are related.
- `find_mitigating_controls`: For questions about what controls mitigate risks.
- `get_attributes`: For questions asking for details about a specific named entity.

Extract relevant parameters:
- For semantic_search: optional entity_type filter
- For find_connections: list of entity names
- For find_mitigating_controls: risk category/name
- For get_attributes: entity name

Example 1:
Question: "Tell me about financial risks"
JSON:
{
  "intent": "semantic_search",
  "parameters": {
    "entity_type": "Risk"
  }
}

Example 2:
Question: "What are the connections between 'Insider Trading' and 'John Doe'?"
JSON:
{
  "intent": "find_connections",
  "parameters": {
    "entity_names": ["Insider Trading", "John Doe"]
  }
}

Example 3:
Question: "What controls mitigate fraud risk?"
JSON:
{
  "intent": "find_mitigating_controls",
  "parameters": {
    "risk_name": "fraud"
  }
}

Respond ONLY with the JSON object. No explanations.
"""


class HybridRetriever:
    """
    Performs hybrid retrieval by combining vector search with graph traversal.

    FalkorDB Architecture
    ---------------------
    Unlike the Neo4j implementation that used APOC for dynamic operations,
    this version uses:
    1. Native FalkorDB vector indexes for semantic search
    2. Standard Cypher for graph traversal
    3. Hybrid search combining both in efficient queries

    Attributes
    ----------
    graph_store : GraphStore
        The FalkorDB-backed graph store
    embedder : Embedder
        Embedding model for query vectorization
    llm_client : AsyncOpenAI
        LLM client for query planning
    rrf_k : int
        RRF constant for result fusion
    """

    def __init__(self, graph_store: GraphStore):
        """
        Initialize the retriever.

        Parameters
        ----------
        graph_store : GraphStore
            FalkorDB-backed graph store instance
        """
        self.graph_store = graph_store
        self.embedder = get_embedder()
        self.llm_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.rrf_k = settings.RRF_K

    async def _plan_query(self, query: str) -> dict:
        """
        Uses an LLM to create a structured query plan from natural language.

        SECURITY: Sanitizes user query and validates LLM output.

        Parameters
        ----------
        query : str
            User's natural language question

        Returns
        -------
        dict
            Query plan with 'intent' and 'parameters' keys
        """
        # SECURITY: Sanitize the user query before including in prompt
        sanitized_query = sanitize_for_prompt(query, "user query")

        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.EXTRACTION_MODEL,
                messages=[
                    {"role": "system", "content": QUERY_PLANNER_PROMPT},
                    {"role": "user", "content": sanitized_query}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            raw_plan = json.loads(response.choices[0].message.content)

            # SECURITY: Validate LLM output
            plan = validate_llm_json_output(raw_plan, allowed_intents=ALLOWED_INTENTS)
            if not plan:
                logger.warning("LLM query plan rejected due to validation failure")
                return {"intent": "semantic_search", "parameters": {}}

            logger.info(f"LLM query plan: {plan}")
            return plan

        except Exception as e:
            logger.error(f"Failed to generate query plan: {e}")
            # Fallback to semantic search
            return {"intent": "semantic_search", "parameters": {}}

    async def _vector_search(self, query: str, k: int) -> list[dict[str, Any]]:
        """
        Pure vector search on chunk embeddings.

        Parameters
        ----------
        query : str
            Search query
        k : int
            Number of results

        Returns
        -------
        list[dict]
            Results with chunk_id, text, score, document_id
        """
        embeddings = await self.embedder.embed_batch([query])
        if not embeddings or not embeddings[0]:
            return []

        query_embedding = embeddings[0]
        return await self.graph_store.vector_search(query_embedding, top_k=k)

    async def _hybrid_entity_search(
        self,
        query: str,
        entity_type: str | None = None,
        k: int = 10
    ) -> list[dict[str, Any]]:
        """
        Hybrid search on entities combining vector + graph context.

        This is the primary search method - it finds semantically similar
        entities and enriches them with graph neighbors.

        Parameters
        ----------
        query : str
            Search query
        entity_type : str, optional
            Filter by entity type
        k : int
            Number of results

        Returns
        -------
        list[dict]
            Rich results with entity data and neighbors
        """
        embeddings = await self.embedder.embed_batch([query])
        if not embeddings or not embeddings[0]:
            return []

        query_embedding = embeddings[0]
        return await self.graph_store.hybrid_search(
            query_embedding=query_embedding,
            entity_type_filter=entity_type,
            top_k=k,
            expand_neighbors=True
        )

    async def _find_connections(
        self,
        entity_names: list[str],
        k: int = 10
    ) -> list[dict[str, Any]]:
        """
        Find connections between named entities.

        Uses graph traversal to find paths and related chunks.

        Parameters
        ----------
        entity_names : list[str]
            Names of entities to connect
        k : int
            Max results

        Returns
        -------
        list[dict]
            Chunks mentioning entities on connection paths
        """
        if not entity_names:
            return []

        # Build query to find entities and their shared connections
        cypher = """
            UNWIND $names AS name
            MATCH (e:Entity)
            WHERE e.name CONTAINS name
            WITH collect(DISTINCT e) AS entities
            UNWIND entities AS e1
            UNWIND entities AS e2
            WHERE id(e1) < id(e2)
            MATCH path = shortestPath((e1)-[*..3]-(e2))
            UNWIND nodes(path) AS node
            MATCH (c:Chunk)-[:MENTIONS]->(node)
            RETURN DISTINCT c.id AS chunk_id,
                   c.text AS text,
                   1.0 AS score,
                   node.name AS mentioned_entity
            LIMIT $k
        """

        try:
            result = self.graph_store.engine.query(cypher, {"names": entity_names, "k": k})
            return [
                {
                    "chunk_id": row[0],
                    "text": row[1],
                    "score": row[2],
                    "mentioned_entity": row[3]
                }
                for row in result.result_set
            ]
        except Exception as e:
            logger.error(f"Connection search failed: {e}")
            return []

    async def _find_mitigating_controls(
        self,
        risk_name: str,
        k: int = 10
    ) -> list[dict[str, Any]]:
        """
        Find controls that mitigate a specific risk.

        Parameters
        ----------
        risk_name : str
            Name or category of risk
        k : int
            Max results

        Returns
        -------
        list[dict]
            Chunks describing mitigating controls
        """
        if not risk_name:
            return []

        cypher = """
            MATCH (r:Entity {type: 'Risk'})<-[:MITIGATES]-(c:Entity {type: 'Control'})
            WHERE r.name CONTAINS $risk_name
            MATCH (chunk:Chunk)-[:MENTIONS]->(c)
            RETURN chunk.id AS chunk_id,
                   chunk.text AS text,
                   2.0 AS score,
                   c.name AS control_name,
                   r.name AS risk_name
            LIMIT $k
        """

        try:
            result = self.graph_store.engine.query(cypher, {"risk_name": risk_name, "k": k})
            return [
                {
                    "chunk_id": row[0],
                    "text": row[1],
                    "score": row[2],
                    "control_name": row[3],
                    "risk_name": row[4]
                }
                for row in result.result_set
            ]
        except Exception as e:
            logger.error(f"Mitigation search failed: {e}")
            return []

    async def _get_entity_attributes(
        self,
        entity_name: str,
        k: int = 5
    ) -> list[dict[str, Any]]:
        """
        Get detailed attributes of a specific entity.

        Parameters
        ----------
        entity_name : str
            Name of entity to look up
        k : int
            Max results

        Returns
        -------
        list[dict]
            Chunks mentioning the entity
        """
        if not entity_name:
            return []

        cypher = """
            MATCH (e:Entity)
            WHERE e.name CONTAINS $name
            OPTIONAL MATCH (c:Chunk)-[:MENTIONS]->(e)
            RETURN COALESCE(c.id, e.id) AS chunk_id,
                   COALESCE(c.text, e.name + ': ' + COALESCE(e.type, 'Entity')) AS text,
                   3.0 AS score,
                   e.type AS entity_type
            LIMIT $k
        """

        try:
            result = self.graph_store.engine.query(cypher, {"name": entity_name, "k": k})
            return [
                {
                    "chunk_id": row[0],
                    "text": row[1],
                    "score": row[2],
                    "entity_type": row[3]
                }
                for row in result.result_set
            ]
        except Exception as e:
            logger.error(f"Attribute search failed: {e}")
            return []

    async def _graph_search(self, query: str, k: int) -> list[dict[str, Any]]:
        """
        Execute graph search based on LLM-planned intent.

        Routes to appropriate search method based on query analysis.

        Parameters
        ----------
        query : str
            User query
        k : int
            Max results

        Returns
        -------
        list[dict]
            Search results
        """
        plan = await self._plan_query(query)
        intent = plan.get("intent", "semantic_search")
        params = plan.get("parameters", {})

        if intent == "semantic_search":
            entity_type = params.get("entity_type")
            if entity_type:
                try:
                    sanitize_label(entity_type, "entity type")
                except Exception:
                    entity_type = None
            return await self._hybrid_entity_search(query, entity_type=entity_type, k=k)

        elif intent == "find_connections":
            entity_names = params.get("entity_names", [])
            return await self._find_connections(entity_names, k=k)

        elif intent == "find_mitigating_controls":
            risk_name = params.get("risk_name", "")
            return await self._find_mitigating_controls(risk_name, k=k)

        elif intent == "get_attributes":
            entity_name = params.get("entity_name", "")
            return await self._get_entity_attributes(entity_name, k=k)

        else:
            # Fallback to hybrid entity search
            return await self._hybrid_entity_search(query, k=k)

    def _reciprocal_rank_fusion(
        self,
        result_sets: list[list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """
        Fuse multiple result sets using Reciprocal Rank Fusion.

        Parameters
        ----------
        result_sets : list[list[dict]]
            Multiple ranked result lists

        Returns
        -------
        list[dict]
            Fused and re-ranked results
        """
        scores: dict[str, float] = {}
        docs_by_id: dict[str, dict] = {}

        for results in result_sets:
            for rank, doc in enumerate(results, 1):
                doc_id = doc.get('chunk_id', str(rank))
                if doc_id not in docs_by_id:
                    docs_by_id[doc_id] = doc

                rrf_score = 1 / (self.rrf_k + rank)
                scores[doc_id] = scores.get(doc_id, 0) + rrf_score

        fused_results = [
            dict(docs_by_id[doc_id], score=score)
            for doc_id, score in scores.items()
        ]
        return sorted(fused_results, key=lambda x: x['score'], reverse=True)

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        search_type: str = "hybrid"
    ) -> list[dict[str, Any]]:
        """
        Main retrieval method.

        Parameters
        ----------
        query : str
            User query
        top_k : int
            Number of results to return
        search_type : str
            One of: "vector", "graph", "hybrid"

        Returns
        -------
        list[dict]
            Retrieved chunks/entities with scores

        Raises
        ------
        ValueError
            If search_type is unknown
        """
        if search_type == "vector":
            return await self._vector_search(query, top_k)

        if search_type == "graph":
            return await self._graph_search(query, top_k)

        if search_type == "hybrid":
            # Run both searches in parallel
            vector_results, graph_results = await asyncio.gather(
                self._vector_search(query, top_k * 2),
                self._graph_search(query, top_k * 2)
            )
            # Fuse results using RRF
            return self._reciprocal_rank_fusion([vector_results, graph_results])[:top_k]

        raise ValueError(f"Unknown search type: {search_type}")

    async def retrieve_fast(
        self,
        query: str,
        top_k: int = 10,
        entity_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Fast retrieval path using hybrid search in a single query.

        This method bypasses LLM planning for lower latency when
        you know the entity type or want pure semantic results.

        Parameters
        ----------
        query : str
            User query
        top_k : int
            Number of results
        entity_type : str, optional
            Filter by entity type

        Returns
        -------
        list[dict]
            Retrieved results
        """
        return await self._hybrid_entity_search(query, entity_type=entity_type, k=top_k)
