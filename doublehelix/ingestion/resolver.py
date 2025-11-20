"""
Entity resolver to merge new entities with existing ones in the graph,
preventing duplicates. Uses fuzzy string matching.
"""
import logging
from typing import List, Dict, Any, Optional

from fuzzywuzzy import process
from neo4j import AsyncDriver

from doublehelix.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class EntityResolver:
    """
    Resolves newly extracted entities against a knowledge base of existing
    entities to find canonical matches, using a full-text index for scalability.
    """
    def __init__(self, driver: AsyncDriver):
        self.driver = driver
        self.database = settings.NEO4J_DATABASE
        self.matching_threshold = settings.ENTITY_RESOLUTION_THRESHOLD

    async def _find_candidates_in_graph(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        Uses the full-text index to find candidate entities in the graph.
        """
        # The query uses a fuzzy match operator `~` if desired, or a standard search.
        # For broader matches, we can add a similarity threshold.
        query = """
        CALL db.index.fulltext.queryNodes('entity_names_ft_index', $entity_name + '~0.8')
        YIELD node, score
        RETURN node.canonical_id as id, node.name as name, score
        LIMIT 10
        """
        try:
            records, _, _ = await self.driver.execute_query(
                query, entity_name=entity_name, database_=self.database
            )
            return [record.data() for record in records]
        except Exception as e:
            # This can happen if the index is not ready yet.
            logger.warning(f"Could not query full-text index (it might still be populating). Falling back to non-indexed search for '{entity_name}'. Error: {e}")
            return []


    async def resolve_and_map(self, new_entities: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Resolves a list of new entities against the existing graph entities using
        an indexed search approach.

        Returns:
            A mapping dictionary from the new entity's temporary ID to the
            canonical ID (either existing or the new one if no match is found).
        """
        if not new_entities:
            return {}

        id_map = {}
        
        for new_entity in new_entities:
            new_id = new_entity['id']
            new_name = new_entity['name']

            # Find candidates using the efficient, indexed graph search
            candidates = await self._find_candidates_in_graph(new_name)
            
            if not candidates:
                # No candidates found, this is a new entity
                id_map[new_id] = new_id
                continue

            # Use fuzzywuzzy on the small set of candidates
            choices = {c['name']: c['id'] for c in candidates}
            best_match = process.extractOne(new_name, choices.keys(), score_cutoff=self.matching_threshold)

            if best_match:
                matched_name, score = best_match
                canonical_id = choices[matched_name]
                id_map[new_id] = canonical_id
                logger.info(f"Resolved '{new_name}' -> '{matched_name}' (score: {score}). Mapping '{new_id}' -> '{canonical_id}'.")
            else:
                # No suitable match found among candidates, the new entity becomes canonical
                id_map[new_id] = new_id

        return id_map

    def remap_relations(self, relations: List[Dict[str, Any]], id_map: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Updates the source and target IDs in relations based on the resolution map.
        """
        remapped_relations = []
        for rel in relations:
            source_id = rel.get("source_id")
            target_id = rel.get("target_id")
            
            remapped_source = id_map.get(source_id)
            remapped_target = id_map.get(target_id)

            if remapped_source and remapped_target:
                # Avoid self-referential loops which are usually not meaningful
                if remapped_source == remapped_target:
                    continue

                new_rel = rel.copy()
                new_rel["source_id"] = remapped_source
                new_rel["target_id"] = remapped_target
                remapped_relations.append(new_rel)
            else:
                logger.warning(f"Could not remap relation: {rel}. Source or target ID missing from map.")
                
        return remapped_relations
