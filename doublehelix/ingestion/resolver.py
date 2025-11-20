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
    entities to find canonical matches.
    """
    def __init__(self, driver: AsyncDriver):
        self.driver = driver
        self.database = settings.NEO4J_DATABASE
        self.matching_threshold = settings.ENTITY_RESOLUTION_THRESHOLD

    async def _get_all_existing_entities(self) -> List[Dict[str, Any]]:
        """Fetches all entities from the graph for local processing."""
        query = "MATCH (e:Entity) RETURN e.canonical_id as id, e.name as name"
        records, _, _ = await self.driver.execute_query(query, database_=self.database)
        return [record.data() for record in records]

    async def resolve_and_map(self, new_entities: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Resolves a list of new entities against the existing graph entities.

        Args:
            new_entities: A list of dicts, each with {'id', 'name', 'type'}.

        Returns:
            A mapping dictionary from the new entity's temporary ID to the
            canonical ID (either existing or the new one if no match is found).
            Example: {'ELON_MUSK_1': 'ELON_MUSK', 'TESLA': 'TESLA_MOTORS'}
        """
        if not new_entities:
            return {}

        existing_entities = await self._get_all_existing_entities()
        id_map = {}

        if not existing_entities:
            # No existing entities, so all new ones are canonical
            return {entity['id']: entity['id'] for entity in new_entities}

        # Create a choices dictionary for fuzzywuzzy: {name: id}
        choices = {entity['name']: entity['id'] for entity in existing_entities}
        
        for new_entity in new_entities:
            new_id = new_entity['id']
            new_name = new_entity['name']

            # Use fuzzywuzzy to find the best match above a threshold
            best_match = process.extractOne(new_name, choices.keys(), score_cutoff=self.matching_threshold)

            if best_match:
                matched_name, score = best_match
                canonical_id = choices[matched_name]
                id_map[new_id] = canonical_id
                logger.info(f"Resolved '{new_name}' -> '{matched_name}' (score: {score}). Mapping '{new_id}' -> '{canonical_id}'.")
            else:
                # No suitable match found, the new entity becomes canonical
                id_map[new_id] = new_id
                # Add it to the choices for subsequent resolutions in the same batch
                choices[new_name] = new_id

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
