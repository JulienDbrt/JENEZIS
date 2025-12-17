"""
Path Traversal Tests - S3 Key Manipulation

These tests verify that the sanitize_filename() function correctly
blocks all path traversal attacks before filenames are used in S3 paths.

Target files:
- examples/fastapi_app/main.py:sanitize_filename()
"""
import pytest
from fastapi import HTTPException

from examples.fastapi_app.main import sanitize_filename


pytestmark = [pytest.mark.adversarial, pytest.mark.unit]


class TestPathTraversalInS3Keys:
    """
    Tests for path traversal attacks via malicious filenames.

    The fix: sanitize_filename() extracts only the basename and removes
    all directory traversal sequences before the filename is used.
    """

    # Basic directory traversal payloads
    BASIC_TRAVERSAL_PAYLOADS = [
        ("../../../etc/passwd", "basic_unix_traversal"),
        ("..\\..\\..\\windows\\system32\\config\\sam", "basic_windows_traversal"),
        ("....//....//....//etc/passwd", "double_dot_slash"),
        ("..././..././etc/passwd", "triple_dot_traversal"),
        ("./.././.././../etc/passwd", "mixed_traversal"),
    ]

    @pytest.mark.parametrize("filename,attack_name", BASIC_TRAVERSAL_PAYLOADS)
    def test_basic_traversal_blocked(self, filename: str, attack_name: str):
        """Verify that basic path traversal sequences are stripped."""
        result = sanitize_filename(filename)

        # The result should not contain any traversal sequences
        assert ".." not in result, f"Attack {attack_name}: traversal not blocked"
        assert "/" not in result, f"Attack {attack_name}: slash not removed"
        assert "\\" not in result, f"Attack {attack_name}: backslash not removed"

    # URL-encoded traversal payloads
    URL_ENCODED_PAYLOADS = [
        ("%2e%2e%2f%2e%2e%2fetc/passwd", "url_encoded"),
        ("..%252f..%252fetc/passwd", "double_url_encoded"),
        ("%252e%252e%252f%252e%252e%252fetc/passwd", "triple_url_encoded"),
        ("%2e%2e%5c%2e%2e%5cwindows", "url_encoded_backslash"),
    ]

    @pytest.mark.parametrize("filename,attack_name", URL_ENCODED_PAYLOADS)
    def test_url_encoded_traversal_blocked(self, filename: str, attack_name: str):
        """Verify that URL-encoded path traversal is decoded and blocked."""
        result = sanitize_filename(filename)

        # After URL decoding and sanitization, no traversal should remain
        assert ".." not in result, f"Attack {attack_name}: encoded traversal not blocked"

    # Unicode normalization attacks
    UNICODE_PAYLOADS = [
        ("..%c0%af..%c0%afetc/passwd", "utf8_overlong_slash"),
        ("\u002e\u002e/\u002e\u002e/etc/passwd", "unicode_dots"),
        ("．．/．．/etc/passwd", "fullwidth_dots"),  # Fullwidth periods
        ("‥/‥/etc/passwd", "two_dot_leader"),  # U+2025
    ]

    @pytest.mark.parametrize("filename,attack_name", UNICODE_PAYLOADS)
    def test_unicode_traversal_blocked(self, filename: str, attack_name: str):
        """Verify that Unicode-based path traversal is blocked."""
        result = sanitize_filename(filename)

        # The result should be safe (only basename kept)
        assert "/" not in result, f"Attack {attack_name}: slash still present"
        assert "\\" not in result


class TestS3KeyManipulation:
    """Tests for S3 key manipulation beyond simple traversal."""

    # Bucket escape attempts
    BUCKET_ESCAPE_PAYLOADS = [
        ("file.pdf/../../other-bucket/secret", "bucket_escape_slash"),
        ("file.pdf/../../../other-bucket/data", "deep_bucket_escape"),
    ]

    @pytest.mark.parametrize("filename,attack_name", BUCKET_ESCAPE_PAYLOADS)
    def test_cannot_escape_bucket(self, filename: str, attack_name: str):
        """Verify that bucket escape attempts are blocked."""
        result = sanitize_filename(filename)

        # Only the final basename should remain
        assert "/" not in result
        assert "other-bucket" not in result

    # Null byte injection
    NULL_BYTE_PAYLOADS = [
        ("file.pdf\x00.exe", "null_byte_extension"),
        ("legit\x00../../../etc/passwd", "null_byte_traversal"),
    ]

    @pytest.mark.parametrize("filename,attack_name", NULL_BYTE_PAYLOADS)
    def test_null_byte_injection_blocked(self, filename: str, attack_name: str):
        """Verify that null byte injection is blocked."""
        result = sanitize_filename(filename)

        # Null bytes should be stripped
        assert "\x00" not in result, f"Attack {attack_name}: null byte not stripped"


class TestProtocolInjection:
    """Tests for protocol injection via filenames."""

    PROTOCOL_PAYLOADS = [
        ("s3://other-bucket/secret.pdf", "s3_protocol"),
        ("file:///etc/passwd", "file_protocol"),
        ("http://evil.com/malware.exe", "http_protocol"),
        ("ftp://attacker.com/data", "ftp_protocol"),
    ]

    @pytest.mark.parametrize("filename,attack_name", PROTOCOL_PAYLOADS)
    def test_protocol_injection_blocked(self, filename: str, attack_name: str):
        """Verify that protocol prefixes in filenames are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename(filename)

        assert exc_info.value.status_code == 400
        assert "Protocol" in exc_info.value.detail


class TestFilenameValidation:
    """Tests for comprehensive filename validation."""

    SAFE_FILENAMES = [
        "document.pdf",
        "my_file_2024.docx",
        "report-final-v2.txt",
        "data.json",
        "test123.md",
    ]

    @pytest.mark.parametrize("filename", SAFE_FILENAMES)
    def test_safe_filenames_accepted(self, filename: str):
        """Verify that safe filenames are accepted."""
        result = sanitize_filename(filename)
        assert result == filename

    REJECTED_FILENAMES = [
        "",  # Empty
        ".",  # Current directory
        "..",  # Parent directory
        "/",  # Root
        "\\",  # Windows root
    ]

    @pytest.mark.parametrize("filename", REJECTED_FILENAMES)
    def test_dangerous_filenames_rejected(self, filename: str):
        """Verify that dangerous filenames are rejected."""
        with pytest.raises(HTTPException):
            sanitize_filename(filename)

    def test_whitespace_only_filename_allowed(self):
        """Whitespace-only filename is allowed (spaces are valid in filenames)."""
        result = sanitize_filename(" ")
        # Space is allowed in filenames
        assert result == " "


class TestS3PathConstruction:
    """Tests for the S3 path construction logic."""

    def test_path_split_with_slashes_in_filename(self):
        """Verify that slashes in filename are stripped."""
        filename = "path/to/file.pdf"
        result = sanitize_filename(filename)

        # Only "file.pdf" should remain
        assert result == "file.pdf"
        assert "/" not in result

    def test_bucket_name_validation(self):
        """Verify that filenames don't affect bucket handling."""
        # This tests that even weird filenames are sanitized properly
        weird_filename = "weird/bucket/name/file.pdf"
        result = sanitize_filename(weird_filename)

        # Only the basename should be kept
        assert result == "file.pdf"
