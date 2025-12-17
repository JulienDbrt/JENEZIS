"""
Token-based text chunker using tiktoken for accurate token counting.
"""
import logging
import uuid
from typing import List, Dict, Any

import tiktoken

from jenezis.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class Chunker:
    """
    Splits text into chunks based on token count, with configurable overlap.
    """
    def __init__(self, chunk_size: int, chunk_overlap: int, model_name: str = "gpt-4"):
        if chunk_overlap >= chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")
            
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        try:
            self.encoder = tiktoken.encoding_for_model(model_name)
        except KeyError:
            logger.warning(f"No tiktoken encoder found for model '{model_name}'. Using 'cl100k_base'.")
            self.encoder = tiktoken.get_encoding("cl100k_base")

    def chunk(self, document_text: str) -> List[Dict[str, Any]]:
        """
        Splits a single document's text into a list of chunk dictionaries.
        Each chunk has a unique ID, the text content, and its token count.
        """
        if not document_text:
            return []

        tokens = self.encoder.encode(document_text)
        
        chunks = []
        start_index = 0
        chunk_seq_num = 0
        
        while start_index < len(tokens):
            end_index = start_index + self.chunk_size
            chunk_tokens = tokens[start_index:end_index]
            
            if not chunk_tokens:
                break

            chunk_text = self.encoder.decode(chunk_tokens)
            
            # Generate a unique, deterministic ID for the chunk if needed,
            # but for this project, we'll use a simple UUID.
            # In a real system, a hash of content + doc_id + seq_num might be better.
            chunk_id = str(uuid.uuid4())

            chunks.append({
                "id": chunk_id,
                "text": chunk_text,
                "token_count": len(chunk_tokens),
                "sequence_num": chunk_seq_num
            })
            
            chunk_seq_num += 1
            start_index += self.chunk_size - self.chunk_overlap

        logger.info(f"Split text into {len(chunks)} chunks.")
        return chunks

def get_chunker() -> Chunker:
    """Factory function to get a Chunker instance based on global settings."""
    return Chunker(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        model_name=settings.GENERATOR_MODEL # Use generator model for more conservative chunking
    )

