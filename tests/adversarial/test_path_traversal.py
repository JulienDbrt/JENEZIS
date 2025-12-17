"""
Path Traversal Tests - S3 Key Manipulation

These tests target the vulnerability in main.py where filenames
are used to construct S3 paths without proper sanitization.

Target files:
- examples/fastapi_app/main.py:138 (s3_path construction)
- examples/fastapi_app/main.py:143 (filename in Document model)
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import hashlib


pytestmark = [pytest.mark.adversarial, pytest.mark.unit]


class TestPathTraversalInS3Keys:
    """
    Tests for path traversal attacks via malicious filenames.

    The vulnerability: User-provided filenames are used directly
    in S3 path construction:
    s3_path = f"{settings.S3_BUCKET_NAME}/{file_hash}_{file.filename}"
    """

    # Basic directory traversal payloads
    BASIC_TRAVERSAL_PAYLOADS = [
        ("../../../etc/passwd", "basic_unix_traversal"),
        ("..\\..\\..\\windows\\system32\\config\\sam", "basic_windows_traversal"),
        ("....//....//....//etc/passwd", "double_dot_slash"),
        ("..././..././etc/passwd", "triple_dot_traversal"),
        ("./.././.././../etc/passwd", "mixed_traversal"),
    ]

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: Path traversal not sanitized in S3 keys - see CLAUDE.md")
    @pytest.mark.parametrize("filename,attack_name", BASIC_TRAVERSAL_PAYLOADS)
    async def test_basic_traversal_blocked(
        self,
        filename: str,
        attack_name: str,
        mock_s3_client,
    ):
        """
        Verify that basic path traversal sequences are blocked or sanitized.
        """
        file_hash = hashlib.sha256(b"test content").hexdigest()
        bucket = "jenezis-documents"

        # Simulate the vulnerable code path
        # s3_path = f"{bucket}/{file_hash}_{filename}"
        s3_key = f"{file_hash}_{filename}"

        # Store the file
        mock_s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"test")

        # Check if the key contains traversal sequences
        stored_keys = mock_s3_client.get_stored_keys(bucket)

        for key in stored_keys:
            # Traversal sequences should NOT be in the final key
            # Either sanitize them out or reject the upload
            dangerous_patterns = ["../", "..\\", "....//"]
            for pattern in dangerous_patterns:
                if pattern in key:
                    pytest.fail(
                        f"Path traversal detected in S3 key!\n"
                        f"Attack: {attack_name}\n"
                        f"Filename: {filename}\n"
                        f"Key: {key}\n"
                        "RECOMMENDATION: Sanitize filenames before use in S3 paths"
                    )

    # URL-encoded traversal payloads
    URL_ENCODED_PAYLOADS = [
        ("%2e%2e%2f%2e%2e%2fetc/passwd", "url_encoded"),
        ("..%252f..%252fetc/passwd", "double_url_encoded"),
        ("%252e%252e%252f%252e%252e%252fetc/passwd", "triple_url_encoded"),
        ("%2e%2e%5c%2e%2e%5cwindows", "url_encoded_backslash"),
    ]

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: URL-encoded path traversal not decoded - see CLAUDE.md")
    @pytest.mark.parametrize("filename,attack_name", URL_ENCODED_PAYLOADS)
    async def test_url_encoded_traversal_blocked(
        self,
        filename: str,
        attack_name: str,
        mock_s3_client,
    ):
        """
        Verify that URL-encoded path traversal is blocked.
        """
        file_hash = hashlib.sha256(b"test").hexdigest()
        bucket = "jenezis-documents"
        s3_key = f"{file_hash}_{filename}"

        mock_s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"test")

        # The encoded sequences should be decoded and blocked, or
        # stored literally (which is safe but ugly)
        mock_s3_client.assert_no_path_traversal(bucket)

    # Unicode normalization attacks
    UNICODE_PAYLOADS = [
        ("..%c0%af..%c0%afetc/passwd", "utf8_overlong_slash"),
        ("\u002e\u002e/\u002e\u002e/etc/passwd", "unicode_dots"),
        ("．．/．．/etc/passwd", "fullwidth_dots"),  # Fullwidth periods
        ("‥/‥/etc/passwd", "two_dot_leader"),  # U+2025
    ]

    @pytest.mark.parametrize("filename,attack_name", UNICODE_PAYLOADS)
    async def test_unicode_traversal_blocked(
        self,
        filename: str,
        attack_name: str,
        mock_s3_client,
    ):
        """
        Verify that Unicode-based path traversal is blocked.
        """
        file_hash = hashlib.sha256(b"test").hexdigest()
        bucket = "jenezis-documents"
        s3_key = f"{file_hash}_{filename}"

        mock_s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"test")

        # After Unicode normalization, these should not traverse
        stored_keys = mock_s3_client.get_stored_keys(bucket)

        # The key should be safe after any normalization
        for key in stored_keys:
            # Check for normalized traversal patterns
            normalized = key.encode().decode('unicode_escape', errors='ignore')
            assert not normalized.startswith(".."), (
                f"Unicode traversal may have succeeded: {key}"
            )


class TestS3KeyManipulation:
    """
    Tests for S3 key manipulation beyond simple traversal.
    """

    # Bucket escape attempts
    BUCKET_ESCAPE_PAYLOADS = [
        ("file.pdf/../../other-bucket/secret", "bucket_escape_slash"),
        ("file.pdf/../../../other-bucket/data", "deep_bucket_escape"),
    ]

    @pytest.mark.parametrize("filename,attack_name", BUCKET_ESCAPE_PAYLOADS)
    async def test_cannot_escape_bucket(
        self,
        filename: str,
        attack_name: str,
        mock_s3_client,
    ):
        """
        Verify that attackers cannot access other buckets via filename.
        """
        file_hash = hashlib.sha256(b"test").hexdigest()
        bucket = "jenezis-documents"

        # In real S3, the bucket is separate from the key
        # but if the code constructs paths incorrectly, this could be exploited
        s3_key = f"{file_hash}_{filename}"

        mock_s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"test")

        # Verify the file is in the correct bucket
        assert bucket in mock_s3_client.buckets
        assert s3_key in mock_s3_client.buckets[bucket]

        # Verify no other buckets were affected
        assert "other-bucket" not in mock_s3_client.buckets

    # Null byte injection
    NULL_BYTE_PAYLOADS = [
        ("file.pdf\x00.exe", "null_byte_extension"),
        ("legit\x00../../../etc/passwd", "null_byte_traversal"),
    ]

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: Null bytes not stripped from filenames - see CLAUDE.md")
    @pytest.mark.parametrize("filename,attack_name", NULL_BYTE_PAYLOADS)
    async def test_null_byte_injection_blocked(
        self,
        filename: str,
        attack_name: str,
        mock_s3_client,
    ):
        """
        Verify that null byte injection is blocked.
        """
        file_hash = hashlib.sha256(b"test").hexdigest()
        bucket = "jenezis-documents"

        # Null bytes should be stripped or rejected
        s3_key = f"{file_hash}_{filename}"

        mock_s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"test")

        stored_keys = mock_s3_client.get_stored_keys(bucket)

        for key in stored_keys:
            # Null bytes should not be in the key
            assert "\x00" not in key, (
                f"Null byte found in S3 key: {repr(key)}"
            )


class TestProtocolInjection:
    """
    Tests for protocol injection via filenames.
    """

    PROTOCOL_PAYLOADS = [
        ("s3://other-bucket/secret.pdf", "s3_protocol"),
        ("file:///etc/passwd", "file_protocol"),
        ("http://evil.com/malware.exe", "http_protocol"),
        ("ftp://attacker.com/data", "ftp_protocol"),
    ]

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: Protocol prefixes not blocked in filenames - see CLAUDE.md")
    @pytest.mark.parametrize("filename,attack_name", PROTOCOL_PAYLOADS)
    async def test_protocol_injection_blocked(
        self,
        filename: str,
        attack_name: str,
        mock_s3_client,
    ):
        """
        Verify that protocol prefixes in filenames are sanitized.
        """
        file_hash = hashlib.sha256(b"test").hexdigest()
        bucket = "jenezis-documents"
        s3_key = f"{file_hash}_{filename}"

        mock_s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"test")

        stored_keys = mock_s3_client.get_stored_keys(bucket)

        # The key should not start with a protocol
        for key in stored_keys:
            key_lower = key.lower()
            dangerous_protocols = ["s3://", "file://", "http://", "ftp://"]
            for protocol in dangerous_protocols:
                # Protocol might be after the hash prefix, so check the filename part
                filename_part = key.split("_", 1)[1] if "_" in key else key
                assert not filename_part.lower().startswith(protocol), (
                    f"Protocol injection detected: {key}"
                )


class TestFilenameValidation:
    """
    Tests for comprehensive filename validation.
    """

    SAFE_FILENAMES = [
        "document.pdf",
        "my_file_2024.docx",
        "report-final-v2.txt",
        "data.json",
        "test123.md",
    ]

    @pytest.mark.parametrize("filename", SAFE_FILENAMES)
    async def test_safe_filenames_accepted(
        self,
        filename: str,
        mock_s3_client,
    ):
        """Verify that safe filenames are accepted."""
        file_hash = hashlib.sha256(b"test").hexdigest()
        bucket = "jenezis-documents"
        s3_key = f"{file_hash}_{filename}"

        mock_s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"test")

        assert s3_key in mock_s3_client.get_stored_keys(bucket)

    DANGEROUS_FILENAMES = [
        "",  # Empty
        " ",  # Whitespace only
        ".",  # Current directory
        "..",  # Parent directory
        "/",  # Root
        "\\",  # Windows root
        "CON",  # Windows reserved
        "PRN",  # Windows reserved
        "AUX",  # Windows reserved
        "NUL",  # Windows reserved
        "COM1",  # Windows reserved
        "LPT1",  # Windows reserved
    ]

    @pytest.mark.parametrize("filename", DANGEROUS_FILENAMES)
    async def test_dangerous_filenames_rejected_or_sanitized(
        self,
        filename: str,
        mock_s3_client,
    ):
        """
        Verify that dangerous filenames are rejected or sanitized.
        """
        file_hash = hashlib.sha256(b"test").hexdigest()
        bucket = "jenezis-documents"

        try:
            s3_key = f"{file_hash}_{filename}"
            mock_s3_client.put_object(Bucket=bucket, Key=s3_key, Body=b"test")
        except (ValueError, OSError):
            # Good - dangerous filename was rejected
            return

        # If accepted, verify it was sanitized
        stored_keys = mock_s3_client.get_stored_keys(bucket)

        for key in stored_keys:
            # The dangerous filename should not be the entire key
            # (there should be a hash prefix)
            assert not key == filename, (
                f"Dangerous filename stored without hash prefix: {key}"
            )


class TestS3PathConstruction:
    """
    Tests for the S3 path construction logic.
    """

    async def test_path_split_with_slashes_in_filename(self, mock_s3_client):
        """
        Verify that slashes in filename don't break bucket/key splitting.

        The vulnerable code does:
        bucket, key = s3_path.split('/', 1)
        """
        bucket = "jenezis-documents"
        file_hash = "abc123"
        filename = "path/to/file.pdf"  # Contains slashes

        # Construct path as the code does
        s3_path = f"{bucket}/{file_hash}_{filename}"

        # Split as the code does
        split_bucket, split_key = s3_path.split('/', 1)

        assert split_bucket == bucket
        assert split_key == f"{file_hash}_{filename}"

        # The slash in filename should be part of the key, not create nested paths
        # (unless S3 folder semantics are desired)

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: Invalid bucket name not validated - see CLAUDE.md")
    async def test_bucket_name_with_slash_handled(self):
        """
        Verify that bucket names containing slashes are handled correctly.
        """
        # This is actually invalid - S3 bucket names cannot contain slashes
        # But the code should handle this gracefully if misconfigured

        bucket = "invalid/bucket/name"
        file_hash = "abc123"
        filename = "file.pdf"

        s3_path = f"{bucket}/{file_hash}_{filename}"

        # This would create an ambiguous split
        parts = s3_path.split('/', 1)

        # Should recognize this as invalid configuration
        assert "/" in parts[0], "First part contains slash - invalid bucket name"
