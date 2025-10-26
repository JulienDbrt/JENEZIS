"""
Authentication middleware for securing admin endpoints.
"""

import os
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

# Security scheme for Bearer token
security = HTTPBearer()


class AuthMiddleware:
    """Authentication middleware for protecting admin endpoints."""

    def __init__(self) -> None:
        """Initialize the auth middleware with token from environment."""
        self.auth_token = os.getenv("API_AUTH_TOKEN")
        self.is_enabled = bool(self.auth_token)

    def verify_token(self, credentials: HTTPAuthorizationCredentials) -> bool:
        """
        Verify the provided Bearer token against the configured token.

        Args:
            credentials: The HTTP authorization credentials

        Returns:
            True if token is valid, False otherwise
        """
        if not self.is_enabled:
            # Auth is disabled if no token is configured
            return True

        if not credentials:
            return False

        return bool(credentials.credentials == self.auth_token)

    def require_auth(
        self, credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
    ) -> None:
        """
        Dependency function to require authentication for an endpoint.

        Args:
            credentials: The HTTP authorization credentials

        Raises:
            HTTPException: If authentication fails
        """
        if not self.is_enabled:
            # Auth is disabled if no token is configured (development mode)
            return

        if not credentials:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not self.verify_token(credentials):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Invalid authentication credentials",
            )


# Global auth middleware instance
auth = AuthMiddleware()


def get_auth_status() -> dict[str, bool]:
    """Get the current authentication status."""
    return {
        "auth_enabled": auth.is_enabled,
        "token_configured": bool(auth.auth_token),
    }


# Export the dependency function for use in routes
require_auth = auth.require_auth
