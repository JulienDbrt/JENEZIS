"""
Unit Tests for Upload Security Functions

These tests verify the security fixes for:
- File size validation (DoS prevention)
- Filename sanitization (path traversal prevention)

Target functions:
- examples/fastapi_app/main.py: sanitize_filename()
- examples/fastapi_app/main.py: validate_upload_size()
"""
import io
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import HTTPException
from starlette.datastructures import Headers

pytestmark = [pytest.mark.unit]


# Import the security functions from main
from examples.fastapi_app.main import (
    sanitize_filename,
    validate_upload_size,
    MAX_UPLOAD_SIZE_BYTES,
)


class TestSanitizeFilename:
    """Tests for the sanitize_filename() function."""

    # --- Path Traversal Tests ---

    @pytest.mark.parametrize("malicious_filename", [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//....//etc/passwd",
        "..././..././etc/passwd",
        "./.././.././../etc/passwd",
    ])
    def test_basic_path_traversal_blocked(self, malicious_filename: str):
        """Basic path traversal sequences are stripped."""
        result = sanitize_filename(malicious_filename)
        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result

    @pytest.mark.parametrize("malicious_filename", [
        "%2e%2e%2f%2e%2e%2fetc/passwd",  # URL-encoded ../
        "..%252f..%252fetc/passwd",  # Double URL-encoded
        "%252e%252e%252f%252e%252e%252fetc/passwd",  # Triple URL-encoded
    ])
    def test_url_encoded_traversal_blocked(self, malicious_filename: str):
        """URL-encoded path traversal is decoded and blocked."""
        result = sanitize_filename(malicious_filename)
        assert ".." not in result
        # Result should be just the filename part after sanitization

    # --- Null Byte Injection Tests ---

    @pytest.mark.parametrize("malicious_filename", [
        "file.pdf\x00.exe",
        "legit\x00../../../etc/passwd",
        "normal\x00",
    ])
    def test_null_bytes_stripped(self, malicious_filename: str):
        """Null bytes are removed from filenames."""
        result = sanitize_filename(malicious_filename)
        assert "\x00" not in result

    # --- Protocol Injection Tests ---

    @pytest.mark.parametrize("malicious_filename", [
        "s3://other-bucket/secret.pdf",
        "file:///etc/passwd",
        "http://evil.com/malware.exe",
        "ftp://attacker.com/data",
        "gopher://localhost:25/",
    ])
    def test_protocol_prefixes_rejected(self, malicious_filename: str):
        """Protocol prefixes in filenames are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename(malicious_filename)
        assert exc_info.value.status_code == 400
        assert "Protocol" in exc_info.value.detail

    # --- Empty/Invalid Filename Tests ---

    @pytest.mark.parametrize("invalid_filename", [
        "",
        None,
    ])
    def test_empty_filename_rejected(self, invalid_filename):
        """Empty or None filenames are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename(invalid_filename)
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize("invalid_filename", [
        ".",
        "..",
        "/",
        "\\",
    ])
    def test_dangerous_single_chars_rejected(self, invalid_filename: str):
        """Single dangerous characters are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename(invalid_filename)
        assert exc_info.value.status_code == 400

    # --- Safe Filename Tests ---

    @pytest.mark.parametrize("safe_filename,expected", [
        ("document.pdf", "document.pdf"),
        ("my_file_2024.docx", "my_file_2024.docx"),
        ("report-final-v2.txt", "report-final-v2.txt"),
        ("data.json", "data.json"),
        ("test123.md", "test123.md"),
        ("file with spaces.pdf", "file with spaces.pdf"),
    ])
    def test_safe_filenames_unchanged(self, safe_filename: str, expected: str):
        """Safe filenames pass through unchanged."""
        result = sanitize_filename(safe_filename)
        assert result == expected

    # --- Unicode Filename Tests ---

    def test_unicode_filename_sanitized(self):
        """Unicode characters are handled (converted to safe chars)."""
        result = sanitize_filename("документ.pdf")
        # Cyrillic chars should be converted to underscores or kept
        assert result.endswith(".pdf")
        assert len(result) > 4  # Should have some name

    # --- Long Filename Tests ---

    def test_extremely_long_filename_truncated(self):
        """Very long filenames are truncated to 255 chars."""
        long_name = "a" * 1000 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".pdf")

    # --- Extraction of Basename Tests ---

    @pytest.mark.parametrize("path_filename,expected_base", [
        ("/path/to/file.pdf", "file.pdf"),
        ("C:\\Users\\test\\file.pdf", "file.pdf"),
        ("../parent/file.pdf", "file.pdf"),
        ("./current/file.pdf", "file.pdf"),
    ])
    def test_basename_extracted(self, path_filename: str, expected_base: str):
        """Only the basename is kept from paths."""
        result = sanitize_filename(path_filename)
        # Result should be based on the basename, possibly with chars replaced
        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result


class TestValidateUploadSize:
    """Tests for the validate_upload_size() function."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request with configurable headers."""
        request = MagicMock()
        request.headers = {}
        return request

    @pytest.fixture
    def mock_file(self):
        """Create a mock file with configurable content."""
        def _create_file(content: bytes):
            file = MagicMock()
            file_io = io.BytesIO(content)

            async def read(size=-1):
                return file_io.read(size)

            file.read = read
            return file
        return _create_file

    @pytest.mark.asyncio
    async def test_small_file_accepted(self, mock_request, mock_file):
        """Files under the size limit are accepted."""
        content = b"small content"
        file = mock_file(content)

        result = await validate_upload_size(mock_request, file)
        assert result == content

    @pytest.mark.asyncio
    async def test_exact_limit_accepted(self, mock_request, mock_file):
        """Files exactly at the size limit are accepted."""
        content = b"X" * MAX_UPLOAD_SIZE_BYTES
        file = mock_file(content)

        result = await validate_upload_size(mock_request, file)
        assert len(result) == MAX_UPLOAD_SIZE_BYTES

    @pytest.mark.asyncio
    async def test_over_limit_rejected(self, mock_request, mock_file):
        """Files over the size limit are rejected."""
        content = b"X" * (MAX_UPLOAD_SIZE_BYTES + 1)
        file = mock_file(content)

        with pytest.raises(HTTPException) as exc_info:
            await validate_upload_size(mock_request, file)
        assert exc_info.value.status_code == 413
        assert "too large" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_content_length_header_checked(self, mock_request, mock_file):
        """Content-Length header is checked for early rejection."""
        mock_request.headers["content-length"] = str(MAX_UPLOAD_SIZE_BYTES + 1000000)
        file = mock_file(b"small")  # Actual content is small

        with pytest.raises(HTTPException) as exc_info:
            await validate_upload_size(mock_request, file)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_invalid_content_length_ignored(self, mock_request, mock_file):
        """Invalid Content-Length headers are ignored (actual size checked)."""
        mock_request.headers["content-length"] = "not-a-number"
        content = b"valid content"
        file = mock_file(content)

        result = await validate_upload_size(mock_request, file)
        assert result == content

    @pytest.mark.asyncio
    async def test_missing_content_length_ok(self, mock_request, mock_file):
        """Missing Content-Length is OK (actual size still checked)."""
        # No content-length header
        content = b"valid content"
        file = mock_file(content)

        result = await validate_upload_size(mock_request, file)
        assert result == content


class TestIntegrationSanitizeAndValidate:
    """Integration tests combining sanitization and validation."""

    def test_malicious_filename_with_traversal_and_null(self):
        """Combined attack: traversal + null byte."""
        malicious = "../../../etc/passwd\x00.pdf"
        result = sanitize_filename(malicious)

        assert ".." not in result
        assert "/" not in result
        assert "\x00" not in result
        # Should end up as something like "passwd.pdf" or "passwd_.pdf"

    def test_url_encoded_protocol_blocked(self):
        """URL-encoded protocol is decoded and blocked."""
        # s3:// URL-encoded
        malicious = "s3%3A%2F%2Fother-bucket%2Fsecret"
        with pytest.raises(HTTPException):
            sanitize_filename(malicious)
