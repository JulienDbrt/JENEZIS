"""LLM-agnostic client for generating text embeddings.
Supports multiple providers like OpenAI, Anthropic (if they provide embeddings),
and OpenRouter.
"""
import asyncio
import logging
from typing import List

import openai
from jenezis.core.config import get_settings
from jenezis.storage.cost_tracker import cost_tracker

logger = logging.getLogger(__name__)
settings = get_settings()

class Embedder:
    """
    A unified interface for creating embeddings from different providers.
    """
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.model = settings.EMBEDDING_MODEL
        self.batch_size = settings.EMBEDDING_BATCH_SIZE

        if self.provider == 'openai':
            self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        elif self.provider == 'openrouter':
            self.client = openai.AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )
        elif self.provider == 'anthropic':
            # Anthropic does not have a dedicated embedding API as of last check.
            # This is a placeholder for if they release one or for custom models.
            raise NotImplementedError("Anthropic does not currently offer a public embedding API.")
        else:
            raise ValueError(f"Unsupported LLM provider for embeddings: {self.provider}")

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a batch of texts.
        """
        if not texts:
            return []

        # OpenAI API recommends replacing newlines for better performance.
        cleaned_texts = [text.replace("\n", " ") for text in texts]
        
        try:
            cost_tracker.estimate_cost(self.model, cleaned_texts, "input")
            
            response = await self.client.embeddings.create(
                model=self.model,
                input=cleaned_texts,
                dimensions=settings.EMBEDDING_DIMENSIONS if "3-large" in self.model else None
            )
            
            embeddings = [item.embedding for item in response.data]
            logger.info(f"Successfully generated {len(embeddings)} embeddings.")
            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings. Error: {e}", exc_info=True)
            raise

    async def embed_all(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a large list of texts by processing them in batches.
        """
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_embeddings = await self.embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
            
            # Small delay to avoid hitting rate limits on aggressive plans
            await asyncio.sleep(0.1)

        return all_embeddings


def get_embedder() -> Embedder:
    """Factory function to get an Embedder instance."""
    return Embedder()
