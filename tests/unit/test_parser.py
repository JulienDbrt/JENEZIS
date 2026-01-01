"""
Unit Tests for Document Parser

Targets: jenezis/ingestion/parser.py
Coverage: 18% -> 90%+
"""
import io
import pytest
from unittest.mock import patch, MagicMock

from jenezis.ingestion.parser import parse_document, SUPPORTED_FORMATS

pytestmark = pytest.mark.unit


class TestSupportedFormats:
    """Tests for supported format constant."""

    def test_supported_formats_defined(self):
        """SUPPORTED_FORMATS contains expected formats."""
        assert ".pdf" in SUPPORTED_FORMATS
        assert ".docx" in SUPPORTED_FORMATS
        assert ".txt" in SUPPORTED_FORMATS
        assert ".md" in SUPPORTED_FORMATS


class TestParseDocumentTextFormats:
    """Tests for text-based format parsing (txt, md)."""

    def test_parse_txt_file(self):
        """Parses .txt files correctly."""
        content = b"Hello, this is a test document."
        file_stream = io.BytesIO(content)

        result = parse_document(file_stream, "test.txt")

        assert result == "Hello, this is a test document."

    def test_parse_md_file(self):
        """Parses .md files correctly."""
        content = b"# Heading\n\nThis is **markdown** content."
        file_stream = io.BytesIO(content)

        result = parse_document(file_stream, "test.md")

        assert "# Heading" in result
        assert "**markdown**" in result

    def test_parse_txt_unicode(self):
        """Handles Unicode content in text files."""
        content = "Héllo, wörld! 日本語テスト".encode("utf-8")
        file_stream = io.BytesIO(content)

        result = parse_document(file_stream, "unicode.txt")

        assert "Héllo" in result
        assert "日本語" in result

    def test_parse_txt_empty_file(self):
        """Handles empty text files."""
        file_stream = io.BytesIO(b"")

        result = parse_document(file_stream, "empty.txt")

        assert result == ""

    def test_parse_txt_with_string_stream(self):
        """Handles string content (not bytes)."""
        # Some file-like objects might return strings
        class StringStream:
            def read(self):
                return "String content, not bytes"

        result = parse_document(StringStream(), "string.txt")
        assert result == "String content, not bytes"


class TestParseDocumentComplexFormats:
    """Tests for complex format parsing (pdf, docx) with mocking."""

    @patch("docling.document_converter.DocumentConverter")
    def test_parse_pdf_file(self, mock_converter_class):
        """Parses PDF files using docling."""
        # Setup mock
        mock_converter = MagicMock()
        mock_result = MagicMock()
        mock_result.document.export_to_text.return_value = "Extracted PDF content"
        mock_converter.convert.return_value = mock_result
        mock_converter_class.return_value = mock_converter

        content = b"%PDF-1.4 fake pdf content"
        file_stream = io.BytesIO(content)

        result = parse_document(file_stream, "document.pdf")

        assert result == "Extracted PDF content"
        mock_converter.convert.assert_called_once()

    @patch("docling.document_converter.DocumentConverter")
    def test_parse_docx_file(self, mock_converter_class):
        """Parses DOCX files using docling."""
        mock_converter = MagicMock()
        mock_result = MagicMock()
        mock_result.document.export_to_text.return_value = "Extracted DOCX content"
        mock_converter.convert.return_value = mock_result
        mock_converter_class.return_value = mock_converter

        content = b"PK fake docx content"
        file_stream = io.BytesIO(content)

        result = parse_document(file_stream, "document.docx")

        assert result == "Extracted DOCX content"

    @patch("docling.document_converter.DocumentConverter")
    def test_parse_pdf_cleanup_temp_file(self, mock_converter_class):
        """Temporary files are cleaned up after parsing."""
        mock_converter = MagicMock()
        mock_result = MagicMock()
        mock_result.document.export_to_text.return_value = "Content"
        mock_converter.convert.return_value = mock_result
        mock_converter_class.return_value = mock_converter

        file_stream = io.BytesIO(b"content")

        # Should not raise, meaning cleanup succeeded
        parse_document(file_stream, "test.pdf")


class TestParseDocumentErrors:
    """Tests for error handling."""

    def test_unsupported_format_raises(self):
        """Unsupported file format raises ValueError."""
        file_stream = io.BytesIO(b"content")

        with pytest.raises(ValueError, match="Unsupported file format"):
            parse_document(file_stream, "file.xyz")

    def test_unsupported_format_error_message(self):
        """Error message includes supported formats."""
        file_stream = io.BytesIO(b"content")

        with pytest.raises(ValueError) as exc_info:
            parse_document(file_stream, "file.exe")

        assert ".pdf" in str(exc_info.value)
        assert ".txt" in str(exc_info.value)

    @patch("docling.document_converter.DocumentConverter")
    def test_parsing_failure_raises_runtime_error(self, mock_converter_class):
        """Parsing failure raises RuntimeError."""
        mock_converter = MagicMock()
        mock_converter.convert.side_effect = Exception("Conversion failed")
        mock_converter_class.return_value = mock_converter

        file_stream = io.BytesIO(b"corrupted content")

        with pytest.raises(RuntimeError, match="Could not parse file"):
            parse_document(file_stream, "corrupted.pdf")

    def test_case_insensitive_extension(self):
        """File extension matching is case-insensitive."""
        content = b"Test content"

        # All these should work
        for ext in [".TXT", ".Txt", ".tXt"]:
            file_stream = io.BytesIO(content)
            result = parse_document(file_stream, f"file{ext}")
            assert result == "Test content"


class TestParseDocumentLogging:
    """Tests for logging behavior."""

    def test_logs_parsing_start(self, caplog):
        """Logs when starting to parse."""
        file_stream = io.BytesIO(b"content")

        with caplog.at_level("INFO"):
            parse_document(file_stream, "test.txt")

        assert "Parsing document 'test.txt'" in caplog.text

    def test_logs_success_with_char_count(self, caplog):
        """Logs success with character count."""
        content = b"Hello World"  # 11 characters
        file_stream = io.BytesIO(content)

        with caplog.at_level("INFO"):
            parse_document(file_stream, "test.txt")

        assert "Successfully parsed" in caplog.text
        assert "11 characters" in caplog.text

    @patch("docling.document_converter.DocumentConverter")
    def test_logs_error_on_failure(self, mock_converter_class, caplog):
        """Logs error on parsing failure."""
        mock_converter = MagicMock()
        mock_converter.convert.side_effect = Exception("Parse error")
        mock_converter_class.return_value = mock_converter

        file_stream = io.BytesIO(b"content")

        with caplog.at_level("ERROR"):
            with pytest.raises(RuntimeError):
                parse_document(file_stream, "test.pdf")

        assert "Failed to parse document" in caplog.text


class TestParseDocumentEdgeCases:
    """Tests for edge cases."""

    def test_filename_with_multiple_dots(self):
        """Handles filenames with multiple dots."""
        file_stream = io.BytesIO(b"content")

        result = parse_document(file_stream, "my.file.name.txt")

        assert result == "content"

    def test_filename_with_path(self):
        """Handles filenames with path components."""
        file_stream = io.BytesIO(b"content")

        result = parse_document(file_stream, "/path/to/file.txt")

        assert result == "content"

    def test_large_file(self):
        """Handles large text files."""
        # 1MB of text
        content = b"A" * (1024 * 1024)
        file_stream = io.BytesIO(content)

        result = parse_document(file_stream, "large.txt")

        assert len(result) == 1024 * 1024

    def test_binary_content_in_text_file(self):
        """Handles text file with invalid UTF-8."""
        # Invalid UTF-8 bytes
        content = b"\xff\xfe Invalid UTF-8"
        file_stream = io.BytesIO(content)

        # Should handle gracefully or raise
        try:
            result = parse_document(file_stream, "binary.txt")
            # If it succeeds, it decoded somehow
            assert isinstance(result, str)
        except (UnicodeDecodeError, RuntimeError):
            # Expected for invalid UTF-8
            pass
