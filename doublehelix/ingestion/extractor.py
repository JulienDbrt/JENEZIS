"""
Entity and Relationship extractor using an LLM.
This module is designed to be pluggable with different models,
prioritizing cost-effectiveness.
"""
import asyncio
import logging
from typing import List, Dict, Any, Tuple

import openai
from pydantic import BaseModel, Field

from doublehelix.core.config import get_settings
from doublehelix.storage.cost_tracker import cost_tracker

logger = logging.getLogger(__name__)
settings = get_settings()

# Pydantic models for structured extraction
class ExtractedEntity(BaseModel):
    id: str = Field(description="A unique, canonical identifier for the entity, e.g., 'TESLA_MOTORS' or a Wikidata ID.")
    name: str = Field(description="The name of the entity, e.g., 'Tesla'.")
    type: str = Field(description="The type of entity, e.g., 'ORGANIZATION', 'PERSON', 'PRODUCT'.")

class ExtractedRelation(BaseModel):
    source: str = Field(description="The canonical ID of the source entity.")
    target: str = Field(description="The canonical ID of the target entity.")
    type: str = Field(description="The type of relationship, e.g., 'CEO_OF', 'PRODUCES', 'COMPETES_WITH'. Use uppercase snake_case.")

class ExtractionResult(BaseModel):
    entities: List[ExtractedEntity]
    relations: List[ExtractedRelation]

# System prompt to instruct the LLM
SYSTEM_PROMPT = f"""
You are an expert knowledge graph extractor. Your task is to identify entities and their relationships from the provided text.
You must follow these rules:
1.  **Identify Entities**: Find all significant entities (people, organizations, products, locations, concepts).
2.  **Assign Canonical IDs**: Create a unique, simple, uppercase, snake_case identifier for each entity (e.g., 'ELON_MUSK', 'TESLA_MOTORS').
3.  **Identify Relationships**: Find explicit relationships between the identified entities.
4.  **Format Output**: Respond ONLY with a valid JSON object that conforms to the following Pydantic model:
    ```json
    {{
      "entities": [{{ "id": "string", "name": "string", "type": "string" }}],
      "relations": [{{ "source": "string", "target": "string", "type": "string" }}]
    }}
    ```
5.  If no entities or relations are found, return an empty list for the corresponding key. Do not explain.
"""

class Extractor:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.model = settings.EXTRACTION_MODEL

        # Configure client based on provider
        if self.provider == 'openai':
            self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        elif self.provider == 'openrouter':
            self.client = openai.AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )
        elif self.provider == 'anthropic':
             # Anthropic uses a different client and API format
            raise NotImplementedError("Extractor not yet implemented for Anthropic.")
        else:
            raise ValueError(f"Unsupported LLM provider for extraction: {self.provider}")

    async def extract_from_chunk(self, chunk_text: str) -> ExtractionResult:
        """Extracts entities and relations from a single text chunk."""
        if not chunk_text.strip():
            return ExtractionResult(entities=[], relations=[])

        try:
            cost_tracker.estimate_cost(self.model, SYSTEM_PROMPT + chunk_text, "input")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": chunk_text}
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            
            completion = response.choices[0].message.content
            cost_tracker.estimate_cost(self.model, completion, "output")
            
            result = ExtractionResult.model_validate_json(completion)
            logger.info(f"Extracted {len(result.entities)} entities and {len(result.relations)} relations.")
            return result

        except Exception as e:
            logger.error(f"Failed during extraction from chunk. Error: {e}", exc_info=True)
            # Return empty result on failure to not block the pipeline
            return ExtractionResult(entities=[], relations=[])

    async def extract_from_all_chunks(
        self, chunks: List[Dict[str, Any]]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Processes all chunks in parallel to extract entities and relations.
        Returns a tuple of (all_entities, all_relations).
        """
        tasks = [self.extract_from_chunk(chunk['text']) for chunk in chunks]
        results = await asyncio.gather(*tasks)

        all_entities = {}
        all_relations = []

        for i, result in enumerate(results):
            chunk_id = chunks[i]['id']
            for entity in result.entities:
                if entity.id not in all_entities:
                    all_entities[entity.id] = {"id": entity.id, "name": entity.name, "type": entity.type}
            
            for relation in result.relations:
                all_relations.append({
                    "source_id": relation.source,
                    "target_id": relation.target,
                    "type": relation.type,
                    "chunk_id": chunk_id,
                })

        return list(all_entities.values()), all_relations


def get_extractor() -> Extractor:
    """Factory function to get an Extractor instance."""
    return Extractor()
