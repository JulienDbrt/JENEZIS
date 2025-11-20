"""API Key security for FastAPI applications."""

import logging
import hashlib
from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_403_FORBIDDEN

from doublehelix.core.connections import get_db_session
from doublehelix.storage.metadata_store import get_api_key_by_hash

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=False)

def get_key_hash(api_key: str) -> str:
    """Hashes the API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()

async def get_api_key(
    api_key_header: str = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db_session)
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

    # Hash the provided key and check against the database
    key_hash = get_key_hash(api_key)
    db_api_key = await get_api_key_by_hash(db, key_hash)

    if not db_api_key:
        logger.warning("Invalid or inactive API key provided.")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid or inactive API Key."
        )
    
    # The key is valid, but we don't return it.
    # The dependency is just for validation.
    return db_api_key.id

