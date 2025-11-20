"""Document parser using the 'docling' library for various file types."""
import logging
from pathlib import Path
from typing import BinaryIO

import docling

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = [".pdf", ".docx", ".txt", ".md"]

def parse_document(file_stream: BinaryIO, filename: str) -> str:
    """
    Parses the content of a file-like object into raw text.
    It uses the filename's extension to determine the parsing strategy.
    
    Args:
        file_stream: A binary file-like object containing the document content.
        filename: The original name of the file, used for its extension.

    Returns:
        The extracted raw text from the document.
        
    Raises:
        ValueError: If the file format is not supported.
        Exception: If parsing fails for any reason.
    """
    file_ext = Path(filename).suffix.lower()

    if file_ext not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported file format: '{file_ext}'. Supported formats are: {SUPPORTED_FORMATS}")

    try:
        logger.info(f"Parsing document '{filename}' with format '{file_ext}'.")
        
        # Docling's `read` function can handle various formats
        # We pass the file stream and hint at the format with the extension
        document = docling.read(file_stream, source_filename=filename)
        
        text_content = document.text
        
        logger.info(f"Successfully parsed '{filename}'. Extracted {len(text_content)} characters.")
        return text_content
    
    except Exception as e:
        logger.error(f"Failed to parse document '{filename}'. Error: {e}", exc_info=True)
        raise RuntimeError(f"Could not parse file: {filename}") from e

