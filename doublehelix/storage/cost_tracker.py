"""
Cost tracking for LLM operations using tiktoken and known model prices.
"""
import logging
from typing import Literal, List

import tiktoken

logger = logging.getLogger(__name__)

# Prices per 1 million tokens in USD
# Keep this updated with the latest pricing from providers.
MODEL_PRICES = {
    "text-embedding-3-small": {"input": 0.02},
    "text-embedding-3-large": {"input": 0.13},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}

class CostTracker:
    """
    A utility class to estimate the cost of LLM API calls.
    """
    def __init__(self):
        self._encodings = {}

    def _get_encoder(self, model_name: str):
        """Lazily gets a tiktoken encoder for a given model."""
        if model_name not in self._encodings:
            try:
                self._encodings[model_name] = tiktoken.encoding_for_model(model_name)
            except KeyError:
                logger.warning(f"No tiktoken encoder found for model '{model_name}'. Using 'cl100k_base'.")
                self._encodings[model_name] = tiktoken.get_encoding("cl100k_base")
        return self._encodings[model_name]

    def estimate_cost(
        self,
        model_name: str,
        text: str | List[str],
        token_type: Literal["input", "output"] = "input"
    ) -> float:
        """
        Estimates the cost of processing text with a given model.

        Args:
            model_name: The name of the LLM or embedding model.
            text: The text string or list of strings to process.
            token_type: 'input' for prompts/embeddings, 'output' for completions.

        Returns:
            The estimated cost in USD.
        """
        if model_name not in MODEL_PRICES:
            logger.warning(f"Pricing for model '{model_name}' not found. Returning cost of 0.")
            return 0.0

        if not text:
            return 0.0

        encoder = self._get_encoder(model_name)
        
        if isinstance(text, list):
            # The token-counting API is slow for many small strings.
            # It's faster to join them and count once.
            num_tokens = len(encoder.encode("".join(text)))
        else:
            num_tokens = len(encoder.encode(text))
            
        price_per_million_tokens = MODEL_PRICES[model_name].get(token_type)
        if price_per_million_tokens is None:
            logger.warning(f"'{token_type}' pricing for model '{model_name}' not found. Using input price.")
            price_per_million_tokens = MODEL_PRICES[model_name].get("input", 0.0)

        cost = (num_tokens / 1_000_000) * price_per_million_tokens
        
        logger.debug(
            "Cost estimation",
            extra={
                "model": model_name,
                "tokens": num_tokens,
                "type": token_type,
                "cost_usd": cost,
            },
        )
        return cost

# Singleton instance for easy access
cost_tracker = CostTracker()
