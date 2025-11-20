"""API Key security for FastAPI applications."""

import logging
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

from doublehelix.core.config import get_settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=False)

async def get_api_key(api_key_header: str = Security(API_KEY_HEADER)):
    """
    FastAPI dependency to validate the API key from the Authorization header.
    Expects the header in the format: "Bearer <your-secret-key>".
    """
    settings = get_settings()
    
    if not api_key_header:
        logger.warning("Missing Authorization header.")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Not authenticated: Missing API key."
        )

    try:
        scheme, _, api_key = api_key_header.partition(' ')
        if scheme.lower() != 'bearer':
            logger.warning("Authorization scheme is not 'Bearer'.")
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, detail="Invalid authentication scheme."
            )
    except ValueError:
        logger.warning("Could not parse Authorization header.")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid Authorization header format."
        )

    if api_key != settings.API_SECRET_KEY:
        logger.warning("Invalid API key provided.")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid API Key"
        )
    
    return api_key
