#!/usr/bin/env python3
"""
Tests for the authentication module.
"""

import os
import sys

import pytest

# Add src to path for imports
sys.path.insert(0, "/Users/juliendabert/Desktop/Erwin-Harmonizer/src")

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


class TestAuthMiddleware:
    """Test suite for AuthMiddleware class."""

    def setup_method(self):
        """Reset environment for each test."""
        # Clear any existing auth token
        if "API_AUTH_TOKEN" in os.environ:
            del os.environ["API_AUTH_TOKEN"]

    @pytest.mark.unit
    def test_auth_middleware_init_with_token(self):
        """Test AuthMiddleware initialization with token."""
        from src.api.auth import AuthMiddleware

        # Set token
        os.environ["API_AUTH_TOKEN"] = "test_token_123"

        auth = AuthMiddleware()

        assert auth.auth_token == "test_token_123"
        assert auth.is_enabled is True

    @pytest.mark.unit
    def test_auth_middleware_init_without_token(self):
        """Test AuthMiddleware initialization without token."""
        from src.api.auth import AuthMiddleware

        # Ensure no token is set
        if "API_AUTH_TOKEN" in os.environ:
            del os.environ["API_AUTH_TOKEN"]

        auth = AuthMiddleware()

        assert auth.auth_token is None
        assert auth.is_enabled is False

    @pytest.mark.unit
    def test_verify_token_valid(self):
        """Test token verification with valid token."""
        from src.api.auth import AuthMiddleware

        os.environ["API_AUTH_TOKEN"] = "valid_token"
        auth = AuthMiddleware()

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")

        assert auth.verify_token(credentials) is True

    @pytest.mark.unit
    def test_verify_token_invalid(self):
        """Test token verification with invalid token."""
        from src.api.auth import AuthMiddleware

        os.environ["API_AUTH_TOKEN"] = "valid_token"
        auth = AuthMiddleware()

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid_token")

        assert auth.verify_token(credentials) is False

    @pytest.mark.unit
    def test_verify_token_no_credentials(self):
        """Test token verification with no credentials."""
        from src.api.auth import AuthMiddleware

        os.environ["API_AUTH_TOKEN"] = "test_token"
        auth = AuthMiddleware()

        assert auth.verify_token(None) is False

    @pytest.mark.unit
    def test_verify_token_auth_disabled(self):
        """Test token verification when auth is disabled."""
        from src.api.auth import AuthMiddleware

        # No token set = auth disabled
        auth = AuthMiddleware()

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any_token")

        # Should return True when auth is disabled
        assert auth.verify_token(credentials) is True

    @pytest.mark.unit
    def test_require_auth_valid_token(self):
        """Test require_auth with valid token."""
        from src.api.auth import AuthMiddleware

        os.environ["API_AUTH_TOKEN"] = "valid_token"
        auth = AuthMiddleware()

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")

        # Should not raise exception
        auth.require_auth(credentials)

    @pytest.mark.unit
    def test_require_auth_invalid_token(self):
        """Test require_auth with invalid token."""
        from src.api.auth import AuthMiddleware

        os.environ["API_AUTH_TOKEN"] = "valid_token"
        auth = AuthMiddleware()

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid_token")

        with pytest.raises(HTTPException) as exc_info:
            auth.require_auth(credentials)

        assert exc_info.value.status_code == 403
        assert "Invalid authentication credentials" in exc_info.value.detail

    @pytest.mark.unit
    def test_require_auth_no_credentials(self):
        """Test require_auth with no credentials."""
        from src.api.auth import AuthMiddleware

        os.environ["API_AUTH_TOKEN"] = "test_token"
        auth = AuthMiddleware()

        with pytest.raises(HTTPException) as exc_info:
            auth.require_auth(None)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.unit
    def test_require_auth_disabled(self):
        """Test require_auth when authentication is disabled."""
        from src.api.auth import AuthMiddleware

        # No token = auth disabled
        auth = AuthMiddleware()

        # Should not raise exception even with no credentials
        auth.require_auth(None)

    @pytest.mark.unit
    def test_get_auth_status_enabled(self):
        """Test get_auth_status when auth is enabled."""
        from src.api.auth import get_auth_status

        os.environ["API_AUTH_TOKEN"] = "test_token"

        # Import after setting env var to get updated auth instance
        import importlib

        import src.api.auth

        importlib.reload(src.api.auth)

        status = get_auth_status()

        assert status["auth_enabled"] is True
        assert status["token_configured"] is True

    @pytest.mark.unit
    def test_get_auth_status_disabled(self):
        """Test get_auth_status when auth is disabled."""
        # Ensure no token
        if "API_AUTH_TOKEN" in os.environ:
            del os.environ["API_AUTH_TOKEN"]

        # Import after clearing env var
        import importlib

        import src.api.auth

        importlib.reload(src.api.auth)
        from src.api.auth import get_auth_status

        status = get_auth_status()

        assert status["auth_enabled"] is False
        assert status["token_configured"] is False

    @pytest.mark.unit
    def test_global_auth_instance(self):
        """Test that global auth instance is properly exported."""
        from src.api.auth import auth, require_auth

        # Should have the auth instance
        assert auth is not None
        assert hasattr(auth, "verify_token")
        assert hasattr(auth, "require_auth")

        # Should have the exported dependency
        assert require_auth is not None
        assert callable(require_auth)

    @pytest.mark.unit
    def test_auth_middleware_methods_exist(self):
        """Test that AuthMiddleware has all required methods."""
        from src.api.auth import AuthMiddleware

        auth = AuthMiddleware()

        assert hasattr(auth, "verify_token")
        assert hasattr(auth, "require_auth")
        assert hasattr(auth, "auth_token")
        assert hasattr(auth, "is_enabled")

    @pytest.mark.unit
    def test_empty_token_handling(self):
        """Test handling of empty token."""
        from src.api.auth import AuthMiddleware

        # Set empty token
        os.environ["API_AUTH_TOKEN"] = ""
        auth = AuthMiddleware()

        # Empty token should disable auth
        assert auth.auth_token == ""
        assert auth.is_enabled is False

    @pytest.mark.unit
    def test_whitespace_token_handling(self):
        """Test handling of whitespace-only token."""
        from src.api.auth import AuthMiddleware

        # Set whitespace token
        os.environ["API_AUTH_TOKEN"] = "   "
        auth = AuthMiddleware()

        # Whitespace token should still enable auth (as it's truthy)
        assert auth.auth_token == "   "
        assert auth.is_enabled is True

    @pytest.mark.unit
    def test_token_comparison_exact(self):
        """Test that token comparison is exact."""
        from src.api.auth import AuthMiddleware

        os.environ["API_AUTH_TOKEN"] = "exact_token"
        auth = AuthMiddleware()

        # Exact match
        credentials_exact = HTTPAuthorizationCredentials(scheme="Bearer", credentials="exact_token")
        assert auth.verify_token(credentials_exact) is True

        # Case sensitive
        credentials_case = HTTPAuthorizationCredentials(scheme="Bearer", credentials="EXACT_TOKEN")
        assert auth.verify_token(credentials_case) is False

        # With spaces
        credentials_spaces = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=" exact_token "
        )
        assert auth.verify_token(credentials_spaces) is False

    @pytest.mark.unit
    def test_http_exception_properties(self):
        """Test HTTPException properties for different scenarios."""
        from src.api.auth import AuthMiddleware

        os.environ["API_AUTH_TOKEN"] = "test_token"
        auth = AuthMiddleware()

        # Test 401 exception
        with pytest.raises(HTTPException) as exc_info:
            auth.require_auth(None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

        # Test 403 exception
        invalid_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="wrong_token"
        )

        with pytest.raises(HTTPException) as exc_info:
            auth.require_auth(invalid_credentials)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Invalid authentication credentials"

    @pytest.mark.unit
    def test_security_scheme_import(self):
        """Test that security scheme is properly imported."""
        from fastapi.security import HTTPBearer

        from src.api.auth import security

        assert isinstance(security, HTTPBearer)
