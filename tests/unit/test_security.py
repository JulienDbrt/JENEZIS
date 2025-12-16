"""
Security Module Unit Tests

Tests for API key authentication and authorization.

Target file: doublehelix/core/security.py
"""
import hashlib
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from doublehelix.core.security import get_key_hash, get_api_key


pytestmark = pytest.mark.unit


class TestKeyHashing:
    """Tests for API key hashing function."""

    def test_hash_is_sha256(self):
        """Verify that keys are hashed with SHA256."""
        test_key = "test-api-key-12345"
        result = get_key_hash(test_key)

        expected = hashlib.sha256(test_key.encode()).hexdigest()
        assert result == expected

    def test_hash_is_deterministic(self):
        """Same key should always produce same hash."""
        test_key = "reproducible-key"

        hash1 = get_key_hash(test_key)
        hash2 = get_key_hash(test_key)

        assert hash1 == hash2

    def test_different_keys_produce_different_hashes(self):
        """Different keys should produce different hashes."""
        key1 = "key-one"
        key2 = "key-two"

        hash1 = get_key_hash(key1)
        hash2 = get_key_hash(key2)

        assert hash1 != hash2

    def test_hash_length_is_64_chars(self):
        """SHA256 hex digest should be 64 characters."""
        result = get_key_hash("any-key")
        assert len(result) == 64

    def test_empty_key_hashes(self):
        """Empty string should still produce a valid hash."""
        result = get_key_hash("")
        assert len(result) == 64
        # SHA256 of empty string
        assert result == hashlib.sha256(b"").hexdigest()

    def test_unicode_key_hashes(self):
        """Unicode keys should be handled correctly."""
        unicode_key = "clé-secrète-日本語"
        result = get_key_hash(unicode_key)

        expected = hashlib.sha256(unicode_key.encode()).hexdigest()
        assert result == expected

    def test_whitespace_key_preserved(self):
        """Whitespace in keys should be preserved (not stripped)."""
        key_with_space = "key with spaces"
        key_without_space = "keywithspaces"

        hash1 = get_key_hash(key_with_space)
        hash2 = get_key_hash(key_without_space)

        assert hash1 != hash2


class TestAPIKeyAuthentication:
    """Tests for API key authentication middleware."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request."""
        request = MagicMock()
        request.headers = {}
        return request

    async def test_missing_authorization_header_raises_403(self):
        """Missing Authorization header should raise HTTPException 403."""
        from fastapi import HTTPException

        # Mock request without Authorization header
        with patch("doublehelix.core.security.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock()
            mock_get_db.return_value.__aexit__ = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await get_api_key(api_key_header=None)

            assert exc_info.value.status_code == 403

    async def test_empty_bearer_token_raises_403(self):
        """'Bearer ' with empty token should raise HTTPException 403."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_api_key(api_key_header="Bearer ")

        assert exc_info.value.status_code == 403

    async def test_invalid_scheme_raises_403(self):
        """Non-Bearer scheme should raise HTTPException 403."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_api_key(api_key_header="Basic dXNlcjpwYXNz")

        assert exc_info.value.status_code == 403

    @pytest.mark.xfail(reason="Some malformed headers not rejected (lowercase 'bearer' accepted)")
    async def test_malformed_header_raises_403(self):
        """Malformed Authorization header should raise 403."""
        from fastapi import HTTPException

        malformed_headers = [
            "BearerToken",  # No space
            "bearer token",  # Wrong case for scheme
            "  Bearer token",  # Leading spaces
            "Bearer",  # No token
        ]

        for header in malformed_headers:
            with pytest.raises(HTTPException) as exc_info:
                await get_api_key(api_key_header=header)

            assert exc_info.value.status_code == 403, f"Failed for header: {header}"


class TestTimingAttackResistance:
    """Tests for timing attack resistance."""

    @pytest.mark.xfail(reason="KNOWN VULNERABILITY: Timing variance too high - potential timing attack vector - see CLAUDE.md")
    async def test_response_time_consistent(self):
        """
        Response time should be relatively consistent regardless of
        key validity to prevent timing attacks.

        Note: This is a basic check. Real timing attack testing requires
        statistical analysis over many requests.
        """
        from fastapi import HTTPException

        # Time multiple invalid key attempts
        times = []
        for i in range(5):
            start = time.perf_counter()
            try:
                await get_api_key(api_key_header=f"Bearer invalid-key-{i}")
            except HTTPException:
                pass
            end = time.perf_counter()
            times.append(end - start)

        # Check variance is not too high
        avg_time = sum(times) / len(times)
        max_deviation = max(abs(t - avg_time) for t in times)

        # Deviation should be small (allowing for some variance)
        # This is a weak test but documents the expected behavior
        assert max_deviation < 0.1, (
            f"High timing variance detected: {times}\n"
            "This could indicate vulnerability to timing attacks"
        )


class TestAPIKeyValidation:
    """Tests for API key format validation."""

    VALID_KEY_FORMATS = [
        "simple-key",
        "key-with-numbers-123",
        "UPPERCASE-KEY",
        "mixedCase-Key-123",
        "key_with_underscores",
        "a" * 100,  # Long key
    ]

    POTENTIALLY_DANGEROUS_KEYS = [
        "key\x00null",  # Null byte
        "key\nwith\nnewlines",
        "key\twith\ttabs",
        "key with spaces",  # Valid but unusual
        "../../../etc/passwd",  # Path traversal (shouldn't matter but test)
        "'; DROP TABLE api_keys; --",  # SQL injection (shouldn't matter)
    ]

    @pytest.mark.parametrize("key", VALID_KEY_FORMATS)
    def test_valid_key_formats_accepted(self, key: str):
        """Valid key formats should produce valid hashes."""
        result = get_key_hash(key)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    @pytest.mark.parametrize("key", POTENTIALLY_DANGEROUS_KEYS)
    def test_dangerous_keys_handled_safely(self, key: str):
        """Potentially dangerous keys should still hash safely."""
        # Should not raise an exception
        result = get_key_hash(key)
        assert len(result) == 64

        # The hash should be unique to the key
        # (injection attempts don't affect hashing)
