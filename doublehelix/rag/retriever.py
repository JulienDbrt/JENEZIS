"""
Hybrid retriever combining semantic vector search with advanced, LLM-driven
graph-based reasoning.
"""
import asyncio
import logging
import json
import openai
from typing import List, Dict, Any

from doublehelix.core.config import get_settings
from doublehelix.ingestion.embedder import get_embedder
from doublehelix.storage.graph_store import GraphStore

logger = logging.getLogger(__name__)
settings = get_settings()

# --- LLM-driven Cypher Query Planner ---

CYPHER_PLANNER_PROMPT = """
You are an expert Cypher query planner. Your task is to decompose a user's natural language question into a structured JSON command that can be used to query a knowledge graph.
The graph has nodes with dynamic labels (e.g., :Risk, :Control, :Process) and relationships with dynamic types (e.g., :MITIGATES, :AFFECTS).

You must select one of the following intents:
- `find_connections`: For general questions about how entities are connected.
- `find_mitigating_controls`: For questions asking what controls mitigate a certain risk.
- `get_attributes`: For questions asking for details about a specific entity.

Then, extract the entities and their properties from the question.

Example 1:
Question: "What are the connections between the 'Insider Trading Scandal' and 'John Doe'?"
JSON:
{
  "intent": "find_connections",
  "parameters": {
    "node_labels": ["Entity"],
    "node_properties": [
      {"name": "Insider Trading Scandal"},
      {"name": "John Doe"}
    ]
  }
}

Example 2:
Question: "Show me controls that mitigate financial risks."
JSON:
{
  "intent": "find_mitigating_controls",
  "parameters": {
    "risk_label": "Risk",
    "risk_properties": {"category": "Financial"}
  }
}

Respond ONLY with the JSON object. Do not add explanations.
"""

CYPHER_TEMPLATES = {
    "find_connections": """
        // Find the nodes mentioned in the query
        UNWIND $node_properties as props
        CALL apoc.nodes.byLabel(head($node_labels), 'name', props.name) YIELD node
        WITH collect(node) as startNodes
        // Find paths between them
        CALL apoc.path.subgraphNodes(startNodes, {maxLevel: 3}) YIELD node as pathNode
        // Find the chunks that mention these path nodes
        MATCH (pathNode)<-[:MENTIONS]-(c:Chunk)
        RETURN c.id as chunk_id, c.text as text, 1 as score, LABELS(pathNode) as node_type
        LIMIT 20
    """,
    "find_mitigating_controls": """
        MATCH (r:{risk_label})<-[:MITIGATES]-(c:Control)
        WHERE all(key IN keys($risk_properties) WHERE r[key] = $risk_properties[key])
        // Once we have the controls, find the chunks that define them
        MATCH (c)<-[:MENTIONS]-(chunk:Chunk)
        RETURN chunk.id as chunk_id, chunk.text as text, 2 as score, LABELS(c) as node_type
        LIMIT 10
    """,
    "get_attributes": """
        UNWIND $node_properties as props
        MATCH (n) WHERE n.name CONTAINS props.name
        OPTIONAL MATCH (n)<-[:MENTIONS]-(c:Chunk)
        RETURN COALESCE(c.id, n.name) as chunk_id, COALESCE(c.text, apoc.convert.toJson(n)) as text, 3 as score, LABELS(n) as node_type
        LIMIT 5
    """,
}


class HybridRetriever:
    """
    Performs hybrid retrieval by combining vector search with LLM-planned graph traversal.
    """
    def __init__(self, graph_store: GraphStore):
        self.graph_store = graph_store
        self.embedder = get_embedder()
        self.llm_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.rrf_k = settings.RRF_K

    async def _plan_cypher_query(self, query: str) -> dict:
        """Uses an LLM to create a structured query plan from a natural language question."""
        try:
            response = await self.llm_client.chat.completions.create(
                model=settings.EXTRACTION_MODEL, # Use a cheaper, fast model for planning
                messages=[
                    {"role": "system", "content": CYPHER_PLANNER_PROMPT},
                    {"role": "user", "content": query}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            plan = json.loads(response.choices[0].message.content)
            logger.info(f"LLM query plan generated: {plan}")
            return plan
        except Exception as e:
            logger.error(f"Failed to generate LLM query plan: {e}")
            return {}

    async def _vector_search(self, query: str, k: int) -> List[Dict[str, Any]]:
        """Performs pure vector search."""
        query_embedding = (await self.embedder.embed_batch([query]))[0]
        return await self.graph_store.vector_search(query_embedding, top_k=k) if query_embedding else []

    async def _graph_search(self, query: str, k: int) -> List[Dict[str, Any]]:
        """Executes a high-level reasoning query on the graph based on an LLM plan."""
        plan = await self._plan_cypher_query(query)
        intent = plan.get("intent")
        params = plan.get("parameters")

        if not intent or intent not in CYPHER_TEMPLATES or not params:
            logger.warning("Could not execute graph search due to invalid or missing LLM plan.")
            return []

        cypher_query = CYPHER_TEMPLATES[intent]
        try:
            records, _, _ = await self.graph_store.driver.execute_query(
                cypher_query, **params, database_=self.graph_store.database
            )
            return [r.data() for r in records]
        except Exception as e:
            logger.error(f"Dynamic Cypher query failed: {e}", exc_info=True)
            return []

    def _reciprocal_rank_fusion(self, result_sets: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        scores, docs_by_id = {}, {}
        for results in result_sets:
            for rank, doc in enumerate(results, 1):
                doc_id = doc['chunk_id']
                if doc_id not in docs_by_id: docs_by_id[doc_id] = doc
                rrf_score = 1 / (self.rrf_k + rank)
                scores[doc_id] = scores.get(doc_id, 0) + rrf_score
        
        fused_results = [dict(docs_by_id[doc_id], score=score) for doc_id, score in scores.items()]
        return sorted(fused_results, key=lambda x: x['score'], reverse=True)

    async def retrieve(self, query: str, top_k: int = 10, search_type: str = "hybrid") -> List[Dict[str, Any]]:
        """Main retrieval method."""
        if search_type == "vector":
            return await self._vector_search(query, top_k)
        if search_type == "graph":
            return await self._graph_search(query, top_k)
        if search_type == "hybrid":
            vector_results, graph_results = await asyncio.gather(
                self._vector_search(query, top_k * 2),
                self._graph_search(query, top_k * 2)
            )
            return self._reciprocal_rank_fusion([vector_results, graph_results])[:top_k]
        
        raise ValueError(f"Unknown search type: {search_type}")
