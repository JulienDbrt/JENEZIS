"""API Key security for FastAPI applications."""

import logging
import hashlib
import hmac
from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_403_FORBIDDEN

from jenezis.core.connections import get_db_session_dep
from jenezis.storage.metadata_store import get_all_active_api_keys, APIKey

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=False)

def get_key_hash(api_key: str) -> str:
    """Hashes the API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()

async def get_api_key(
    api_key_header: str = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db_session_dep)
):
    """
    FastAPI dependency that validates a bearer token against a database of hashed keys.
    """
    if not api_key_header:
        logger.warning("Missing Authorization header.")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Not authenticated: Missing API key."
        )

    try:
        scheme, _, api_key = api_key_header.partition(' ')
        if scheme.lower() != 'bearer' or not api_key:
            logger.warning("Invalid authentication scheme or empty key.")
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, detail="Invalid authentication credentials."
            )
    except ValueError:
        logger.warning("Could not parse Authorization header.")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid Authorization header format."
        )

    # SECURITY: Use a constant-time comparison to mitigate timing attacks.
    key_hash = get_key_hash(api_key)
    active_keys: list[APIKey] = await get_all_active_api_keys(db)

    # Iterate through all active keys and compare hashes in constant time
    matched_key = None
    for db_key in active_keys:
        if hmac.compare_digest(db_key.key_hash, key_hash):
            matched_key = db_key
            break # Found a match

    if not matched_key:
        logger.warning("Invalid or inactive API key provided.")
        # We still raise a generic error to avoid leaking information
        # about whether the key exists but is inactive vs. doesn't exist at all.
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid or inactive API Key."
        )

    # The key is valid. Return its ID for potential use in downstream logic.
    return matched_key.id

