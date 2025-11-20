"""
RAG generator that takes a query, retrieves context, and streams a
response from an LLM, including source citations.
"""
import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Tuple

import openai
from doublehelix.core.config import get_settings
from doublehelix.rag.retriever import HybridRetriever
from doublehelix.storage.cost_tracker import cost_tracker

logger = logging.getLogger(__name__)
settings = get_settings()

GENERATOR_SYSTEM_PROMPT = """
You are an expert Question-Answering assistant named "DoubleHelix".
Your task is to answer the user's question based *only* on the provided context.
Follow these rules strictly:
1.  Analyze the provided context documents carefully.
2.  Synthesize an answer that directly addresses the user's question.
3.  Your answer MUST be based exclusively on the information within the context. Do not use any external knowledge.
4.  If the context does not contain the information needed to answer the question, you MUST state: "I am sorry, but the provided context does not contain enough information to answer this question."
5.  Do not make up facts or elaborate beyond the provided text.
6.  Be concise and to the point.
"""

class Generator:
    """
    Handles the final generation step of the RAG pipeline.
    """
    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever
        self.provider = settings.LLM_PROVIDER
        self.model = settings.GENERATOR_MODEL

        # Configure client based on provider
        if self.provider == 'openai':
            self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        elif self.provider == 'openrouter':
            self.client = openai.AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )
        elif self.provider == 'anthropic':
            # Not implemented in this example
            raise NotImplementedError("Generator not yet implemented for Anthropic.")
        else:
            raise ValueError(f"Unsupported LLM provider for generation: {self.provider}")

    async def rag_query_with_sources(
        self, query: str
    ) -> Tuple[AsyncGenerator[str, None], List[Dict[str, Any]]]:
        """
        Performs the full RAG pipeline: retrieve, augment, and generate.

        Returns:
            A tuple containing:
            - An async generator that yields the response tokens.
            - A list of source documents used for the generation.
        """
        # 1. Retrieve context
        logger.info(f"Retrieving context for query: '{query}'")
        sources = await self.retriever.retrieve(query, top_k=5, search_type="hybrid")

        if not sources:
            async def empty_generator():
                yield "I am sorry, but I could not find any relevant information to answer this question."
            return empty_generator(), []

        # 2. Augment (create the prompt)
        context_str = ""
        for i, source in enumerate(sources):
            context_str += f"--- Context Document {i+1} (Source ID: doc-{source['document_id']}/chunk-{source['chunk_id']}) ---"\n"
            context_str += source['text']
            context_str += "\n\n"

        prompt = f"User Question: {query}\n\n--- Context ---\n{context_str}"
        
        logger.debug(f"Generated prompt for LLM. Length: {len(prompt)}")
        cost_tracker.estimate_cost(self.model, GENERATOR_SYSTEM_PROMPT + prompt, "input")

        # 3. Generate (stream response)
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                stream=True,
            )
            
            # Create a new async generator to yield content and track output cost
            async def response_generator():
                full_response = ""
                async for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    full_response += content
                    yield content
                
                # After stream is complete, calculate output cost
                cost_tracker.estimate_cost(self.model, full_response, "output")

            return response_generator(), sources

        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            async def error_generator():
                yield "An error occurred while generating the response."
            return error_generator(), []
