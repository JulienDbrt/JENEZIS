"""
Symbolic validator for ensuring LLM outputs conform to the defined ontology.
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class Validator:
    """
    Validates extracted graph data against a given ontology schema.
    """
    def __init__(self, ontology_schema: Dict[str, Any]):
        self.ontology_schema = ontology_schema
        self.valid_entity_types = set(ontology_schema.get("entity_types", []))
        self.valid_relation_types = set(ontology_schema.get("relation_types", []))

    def validate_and_filter(
        self,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]]
    ) -> (List[Dict[str, Any]], List[Dict[str, Any]]):
        """
        Filters entities and relations to ensure they conform to the ontology.
        """
        if not self.ontology_schema:
            logger.warning("Validator has no ontology schema. Passing through all data.")
            return entities, relations

        # Validate Entities
        valid_entities = []
        invalid_entity_count = 0
        for entity in entities:
            if entity.get("type") in self.valid_entity_types:
                valid_entities.append(entity)
            else:
                invalid_entity_count += 1
        
        if invalid_entity_count > 0:
            logger.warning(f"Filtered out {invalid_entity_count} entities not conforming to ontology types: {self.valid_entity_types}")

        # Validate Relations
        valid_relations = []
        invalid_relation_count = 0
        valid_entity_ids = {e['id'] for e in valid_entities}

        for relation in relations:
            # Check if relation type is valid
            if relation.get("type") not in self.valid_relation_types:
                invalid_relation_count += 1
                continue
            # Check if source and target entities are valid
            if relation.get("source_id") not in valid_entity_ids or relation.get("target_id") not in valid_entity_ids:
                invalid_relation_count += 1
                continue
            valid_relations.append(relation)

        if invalid_relation_count > 0:
            logger.warning(f"Filtered out {invalid_relation_count} relations not conforming to ontology.")
            
        return valid_entities, valid_relations
