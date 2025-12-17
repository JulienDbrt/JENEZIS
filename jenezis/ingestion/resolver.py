"""
Neuro-Symbolic Entity Resolution Service (The "Harmonizer").
Resolves extracted entity strings against the "Canonical Store" in PostgreSQL.
"""
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from pgvector.sqlalchemy import Vector

from jenezis.core.config import get_settings
from jenezis.storage.metadata_store import CanonicalNode, NodeAlias
from jenezis.ingestion.embedder import Embedder

logger = logging.getLogger(__name__)
settings = get_settings()

RESOLUTION_CONFIDENCE_THRESHOLD = 0.95 # TODO: Move to settings

class Resolver:
    """
    Orchestrates the resolution of extracted entities against the canonical store.
    Pipeline: Exact Match -> Vector Similarity -> Enrichment Queue.
    """
    def __init__(self, db: AsyncSession, embedder: Embedder):
        self.db = db
        self.embedder = embedder

    async def _find_by_exact_match(self, alias_text: str) -> Optional[int]:
        """Step 1 (Symbolic): Find a case-insensitive exact match in aliases."""
        query = (
            select(NodeAlias)
            .options(selectinload(NodeAlias.canonical_node))
            .where(NodeAlias.alias.ilike(alias_text))
        )
        result = await self.db.execute(query)
        node_alias = result.scalars().first()
        if node_alias:
            logger.info(f"Resolved '{alias_text}' via exact match to canonical node ID {node_alias.canonical_node_id}.")
            return node_alias.canonical_node_id
        return None

    async def _find_by_vector_similarity(self, name: str) -> Optional[dict]:
        """Step 2 (Neuro): Find the closest match using vector similarity search."""
        embedding = (await self.embedder.embed_batch([name]))[0]
        if not embedding:
            return None

        # Query using cosine distance (<->) from pgvector
        query = (
            select(CanonicalNode, CanonicalNode.embedding.cosine_distance(embedding).label('distance'))
            .order_by(CanonicalNode.embedding.cosine_distance(embedding))
            .limit(1)
        )
        result = await self.db.execute(query)
        match = result.first()

        if match:
            node, distance = match
            similarity = 1 - distance # Cosine distance -> similarity
            logger.info(f"Vector search for '{name}' found closest match '{node.name}' with similarity {similarity:.2f}.")
            return {"node": node, "similarity": similarity}
        return None

    async def resolve_entity(self, extracted_name: str, extracted_type: str) -> dict:
        """
        Resolves a single entity using the neuro-symbolic pipeline.
        Returns a dictionary with resolution status and data.
        """
        # 1. Exact Match
        canonical_id = await self._find_by_exact_match(extracted_name)
        if canonical_id:
            return {"status": "resolved", "canonical_id": canonical_id, "original_name": extracted_name}

        # 2. Vector Search
        vector_match = await self._find_by_vector_similarity(extracted_name)
        if vector_match and vector_match["similarity"] >= RESOLUTION_CONFIDENCE_THRESHOLD:
            return {"status": "resolved", "canonical_id": vector_match["node"].id, "original_name": extracted_name}

        # 3. Could not resolve with high confidence
        logger.info(f"Could not resolve '{extracted_name}'. Sending to Enrichment Queue.")
        return {
            "status": "unresolved",
            "name": extracted_name,
            "type": extracted_type,
            "similarity_match": {
                "node_name": vector_match["node"].name if vector_match else None,
                "similarity": vector_match["similarity"] if vector_match else 0.0,
            }
        }

    async def resolve_all(self, entities: List[Dict]) -> (List[Dict], List[Dict]):
        """
        Resolves a batch of entities.
        Returns two lists: one of resolved mappings, one of unresolved items for the enrichment queue.
        """
        resolved_map = {}
        unresolved_items = []
        
        for entity in entities:
            result = await self.resolve_entity(entity['name'], entity['type'])
            if result['status'] == 'resolved':
                # Map the temporary LLM-generated ID to the canonical ID
                resolved_map[entity['id']] = result['canonical_id']
            else:
                unresolved_items.append(result)
        
        return resolved_map, unresolved_items
