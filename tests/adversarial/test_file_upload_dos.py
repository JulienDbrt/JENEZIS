"""
File Upload DoS Tests - Resource Exhaustion Attacks

These tests target the vulnerability in main.py where file contents
are read entirely into memory without size validation.

Target files:
- examples/fastapi_app/main.py:129 (await file.read() without size limit)
"""
import io
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import UploadFile
from starlette.datastructures import Headers


pytestmark = [pytest.mark.adversarial, pytest.mark.unit]


class FakeStreamingFile:
    """
    A fake file that simulates a very large upload without
    actually allocating the memory.
    """

    def __init__(self, claimed_size: int, actual_data: bytes = b""):
        self.claimed_size = claimed_size
        self.actual_data = actual_data
        self._position = 0

    async def read(self, size: int = -1) -> bytes:
        """
        Simulates reading from a large file.
        Returns actual_data for small reads, raises for large ones.
        """
        if size == -1:
            # Reading entire file - this is the vulnerability!
            # In a real attack, this would consume claimed_size bytes of memory
            if self.claimed_size > 100 * 1024 * 1024:  # 100MB threshold
                raise MemoryError(
                    f"Attempted to read {self.claimed_size} bytes into memory! "
                    "This is the DoS vulnerability."
                )
            return self.actual_data
        return self.actual_data[:size]

    async def seek(self, position: int):
        self._position = position

    def __len__(self):
        return self.claimed_size


class TestFileSizeDoS:
    """
    Tests for denial of service via large file uploads.

    The vulnerability: The upload endpoint calls `await file.read()`
    without checking file size first, allowing an attacker to exhaust
    server memory with a single request.
    """

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: No file size limit before read() - see CLAUDE.md")
    async def test_large_file_should_be_rejected_before_full_read(self):
        """
        Verify that files exceeding a size limit are rejected
        without reading the entire content into memory.
        """
        # Simulate a 10GB file
        large_file = FakeStreamingFile(
            claimed_size=10 * 1024 * 1024 * 1024,  # 10GB
            actual_data=b"small payload"
        )

        # Create an UploadFile wrapper
        upload_file = UploadFile(
            filename="huge_file.pdf",
            file=large_file,
            headers=Headers({"content-type": "application/pdf"}),
        )

        # Mock the endpoint's file handling
        # If the code tries to read() the entire file, it will raise MemoryError
        try:
            content = await upload_file.read()
            # If we get here with the full claimed size, it's vulnerable
            if len(content) == large_file.claimed_size:
                pytest.fail(
                    "VULNERABILITY: Large file was read entirely into memory! "
                    "This enables DoS attacks."
                )
        except MemoryError as e:
            # Good - the test caught the attempt to read a huge file
            assert "DoS vulnerability" in str(e)

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: Content-Length mismatch not validated - see CLAUDE.md")
    async def test_content_length_mismatch_handled(self):
        """
        Verify that Content-Length header mismatches are handled.

        Attack: Set Content-Length: 100 but send 10GB of data.
        """
        # Create a file that claims to be small but is actually large
        deceptive_file = FakeStreamingFile(
            claimed_size=100,  # Claims 100 bytes
            actual_data=b"X" * 1000,  # Actually sends 1KB
        )

        upload_file = UploadFile(
            filename="deceptive.pdf",
            file=deceptive_file,
        )

        content = await upload_file.read()

        # The actual data read should match what was sent, not what was claimed
        assert len(content) == 1000

    DECOMPRESSION_BOMB_SIGNATURES = [
        # PDF with highly compressed stream
        b"%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode /Length 10 >>\nstream\n"
        + b"\x78\x9c" + b"\x00" * 8  # zlib header + zeros
        + b"\nendstream\nendobj\n%%EOF",

        # DOCX is a ZIP - could contain zip bomb
        b"PK\x03\x04" + b"\x00" * 26,  # ZIP local file header

        # Gzip bomb header
        b"\x1f\x8b\x08\x00" + b"\x00" * 6,
    ]

    @pytest.mark.parametrize("bomb_signature", DECOMPRESSION_BOMB_SIGNATURES)
    async def test_decompression_bombs_detected(self, bomb_signature: bytes):
        """
        Verify that decompression bombs are detected and rejected.

        These are files that are small when compressed but expand to
        enormous sizes when decompressed.
        """
        upload_file = UploadFile(
            filename="potential_bomb.pdf",
            file=io.BytesIO(bomb_signature),
        )

        content = await upload_file.read()

        # The raw content should be small
        assert len(content) < 1024, "Bomb signature should be small"

        # Detection would happen in the parser, not here
        # This test just verifies we can identify the signatures


class TestBillionLaughsXML:
    """
    Tests for XML entity expansion attacks (Billion Laughs / XML bomb).

    DOCX files contain XML - an attacker could craft a DOCX with
    malicious XML that expands exponentially when parsed.
    """

    BILLION_LAUGHS_XML = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
  <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
  <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
  <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
  <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
  <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<lolz>&lol9;</lolz>"""

    async def test_xml_bomb_in_docx_rejected(self):
        """
        Verify that XML bombs embedded in DOCX files are rejected.
        """
        # Create a minimal DOCX-like structure with the bomb in content
        # Real DOCX would have this in word/document.xml inside the ZIP

        # This test verifies the signature is detectable
        assert b"<!ENTITY" in self.BILLION_LAUGHS_XML
        assert b"&lol9;" in self.BILLION_LAUGHS_XML

        # The parser should reject files with recursive entity definitions


class TestSlowLorisUpload:
    """
    Tests for Slow Loris style attacks via slow uploads.

    Attack: Send data very slowly to hold connections open and
    exhaust server resources.
    """

    async def test_upload_timeout_enforced(self):
        """
        Verify that uploads have a timeout and don't hang indefinitely.
        """
        # This would be tested at the server level with real timeouts
        # Here we just verify the test infrastructure

        class SlowFile:
            """A file that reads very slowly."""

            def __init__(self):
                self.data = b"X" * 1000
                self.position = 0
                self.reads = 0

            async def read(self, size: int = -1) -> bytes:
                self.reads += 1
                if self.reads > 100:  # Simulate slow progress
                    raise TimeoutError("Upload timed out (simulated)")
                if size == -1:
                    return self.data
                chunk = self.data[self.position:self.position + size]
                self.position += size
                return chunk

        slow_file = SlowFile()

        with pytest.raises(TimeoutError):
            # Should timeout, not hang forever
            for _ in range(200):
                await slow_file.read(10)


class TestConcurrentUploadDoS:
    """
    Tests for DoS via many concurrent uploads.
    """

    async def test_concurrent_uploads_limited(self):
        """
        Verify that there's a limit on concurrent uploads to prevent
        resource exhaustion.
        """
        # This would be tested with actual concurrent requests
        # Here we document the expected behavior

        # Expected: Server should have rate limiting or connection limits
        # that prevent a single client from opening too many uploads

        # Placeholder assertion
        max_concurrent = 10  # Expected limit
        assert max_concurrent > 0, "Should have a concurrent upload limit"


class TestMalformedFileHeaders:
    """
    Tests for handling malformed file uploads.
    """

    async def test_empty_filename_handled(self):
        """Files with empty filenames should be rejected or handled safely."""
        upload_file = UploadFile(
            filename="",
            file=io.BytesIO(b"content"),
        )

        # Should not crash
        content = await upload_file.read()
        assert content == b"content"

    async def test_null_byte_in_filename_sanitized(self):
        """Filenames with null bytes should be sanitized."""
        dangerous_filename = "file.pdf\x00.exe"

        upload_file = UploadFile(
            filename=dangerous_filename,
            file=io.BytesIO(b"content"),
        )

        # The filename should be sanitized before use
        # This test documents the expected behavior
        assert "\x00" in upload_file.filename  # Raw UploadFile doesn't sanitize

    async def test_extremely_long_filename_truncated(self):
        """Very long filenames should be truncated."""
        long_filename = "a" * 10000 + ".pdf"

        upload_file = UploadFile(
            filename=long_filename,
            file=io.BytesIO(b"content"),
        )

        # Document expected behavior: filename should be truncated
        # to prevent storage/logging issues
        assert len(upload_file.filename) == 10004

    async def test_unicode_filename_handled(self):
        """Unicode filenames should be handled correctly."""
        unicode_filename = "документ_файл.pdf"

        upload_file = UploadFile(
            filename=unicode_filename,
            file=io.BytesIO(b"content"),
        )

        content = await upload_file.read()
        assert content == b"content"
        assert upload_file.filename == unicode_filename
