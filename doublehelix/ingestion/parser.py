"""Document parser using the 'docling' library for various file types."""
import logging
import tempfile
from pathlib import Path
from typing import BinaryIO

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

        # For text-based formats, read directly
        if file_ext in [".txt", ".md"]:
            content = file_stream.read()
            if isinstance(content, bytes):
                text_content = content.decode("utf-8")
            else:
                text_content = content
            logger.info(f"Successfully parsed '{filename}'. Extracted {len(text_content)} characters.")
            return text_content

        # For complex formats (PDF, DOCX), use docling's DocumentConverter
        from docling.document_converter import DocumentConverter

        # Write to a temp file because docling v2 needs a file path
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
            content = file_stream.read()
            temp_file.write(content if isinstance(content, bytes) else content.encode("utf-8"))
            temp_path = temp_file.name

        try:
            converter = DocumentConverter()
            result = converter.convert(temp_path)
            text_content = result.document.export_to_text()
        finally:
            Path(temp_path).unlink(missing_ok=True)

        logger.info(f"Successfully parsed '{filename}'. Extracted {len(text_content)} characters.")
        return text_content

    except Exception as e:
        logger.error(f"Failed to parse document '{filename}'. Error: {e}", exc_info=True)
        raise RuntimeError(f"Could not parse file: {filename}") from e
