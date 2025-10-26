"""
JWT authentication implementation.

Replaces static token authentication with JWT tokens for better security.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme
security = HTTPBearer()


class Token(BaseModel):
    """Token response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data."""

    sub: str  # Subject (usually user ID or client ID)
    scopes: list[str] = []
    exp: Optional[datetime] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bool(pwd_context.verify(plain_password, hashed_password))


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return str(pwd_context.hash(password))


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data (sub, scopes, etc.)
        expires_delta: Token expiration time

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict[str, Any]) -> str:
    """
    Create a JWT refresh token.

    Args:
        data: Payload data (sub, scopes, etc.)

    Returns:
        Encoded JWT refresh token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> TokenData:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string

    Returns:
        TokenData with decoded payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        scopes: list[str] = payload.get("scopes", [])
        exp: Optional[datetime] = payload.get("exp")

        if sub is None:
            raise credentials_exception

        return TokenData(sub=sub, scopes=scopes, exp=exp)

    except JWTError:
        raise credentials_exception


async def get_current_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenData:
    """
    Dependency to extract and validate JWT from request.

    Args:
        credentials: HTTP Authorization header

    Returns:
        Decoded token data

    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    return decode_token(token)


def require_scope(required_scope: str):  # type: ignore[no-untyped-def]
    """
    Factory for scope-based authorization dependencies.

    Args:
        required_scope: The scope required to access the endpoint

    Returns:
        Dependency function that validates scope

    Example:
        @app.post("/admin/reload", dependencies=[Depends(require_scope("admin"))])
    """

    async def scope_checker(token_data: TokenData = Depends(get_current_token)) -> TokenData:
        if required_scope not in token_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required scope: {required_scope}",
            )
        return token_data

    return scope_checker


# Convenience dependencies for common scopes
async def require_admin(token_data: TokenData = Depends(get_current_token)) -> TokenData:
    """Require admin scope."""
    if "admin" not in token_data.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return token_data


async def require_write(token_data: TokenData = Depends(get_current_token)) -> TokenData:
    """Require write scope."""
    if "write" not in token_data.scopes and "admin" not in token_data.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required",
        )
    return token_data


async def require_read(token_data: TokenData = Depends(get_current_token)) -> TokenData:
    """Require read scope (most permissive)."""
    if not token_data.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required",
        )
    return token_data
