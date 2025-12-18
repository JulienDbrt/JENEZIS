"""
Complete FastAPI application for JENEZIS.
Provides endpoints for document upload, status checking, querying, and management.
"""
import asyncio
import hashlib
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import PurePosixPath
from typing import List, Any
from urllib.parse import unquote

from celery import chain
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Body, Request
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.status import (
    HTTP_202_ACCEPTED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_413_REQUEST_ENTITY_TOO_LARGE,
)

import secrets
from sqlalchemy import select, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from jenezis.core.config import get_settings
from jenezis.core.connections import (
    close_connections,
    get_db_session,
    get_db_session_dep,
    get_s3_client,
    sql_engine,
)
from jenezis.core.security import get_api_key, get_key_hash
from jenezis.storage.metadata_store import (
    Document,
    DocumentStatus,
    get_document_by_hash,
    get_document_by_id,
    APIKey,
    Ontology,
)
from jenezis.storage.graph_store import GraphStore
from jenezis.rag.retriever import HybridRetriever
from jenezis.rag.generator import Generator
from jenezis.utils.logging import setup_logging
from .tasks import process_document, delete_document_task

# --- Security Constants ---
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_FILENAME_PATTERN = re.compile(r'^[\w\-. ]+$')  # Alphanumeric, dash, dot, space


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and injection attacks.

    - Strips null bytes
    - URL-decodes the filename
    - Extracts only the basename (no directory components)
    - Blocks protocol prefixes (s3://, file://, http://, etc.)
    - Replaces dangerous characters with underscores
    - Limits length to 255 characters

    Returns a safe filename or raises HTTPException if filename is invalid.
    """
    if not filename:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Filename is required."
        )

    # Strip null bytes (can truncate filename in C-based systems)
    sanitized = filename.replace('\x00', '')

    # URL-decode to catch encoded traversal attempts (%2e%2e%2f = ../)
    sanitized = unquote(unquote(sanitized))  # Double decode for %252e attacks

    # Block protocol prefixes
    protocol_pattern = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', re.IGNORECASE)
    if protocol_pattern.match(sanitized):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Protocol prefixes not allowed in filename."
        )

    # Extract basename only - removes ALL directory components
    # Use PurePosixPath to handle both / and \ separators
    sanitized = PurePosixPath(sanitized.replace('\\', '/')).name

    # If after stripping path components we have nothing, reject
    if not sanitized or sanitized in ('.', '..'):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Invalid filename after sanitization."
        )

    # Replace any remaining dangerous characters with underscore
    # Keep only: alphanumeric, dash, underscore, dot, space
    sanitized = re.sub(r'[^\w\-. ]', '_', sanitized)

    # Collapse multiple underscores/dots
    sanitized = re.sub(r'[_.]{2,}', '_', sanitized)

    # Limit length
    if len(sanitized) > 255:
        name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
        max_name_len = 255 - len(ext) - 1 if ext else 255
        sanitized = f"{name[:max_name_len]}.{ext}" if ext else name[:255]

    return sanitized


async def validate_upload_size(request: Request, file: UploadFile) -> bytes:
    """
    Validate file size before fully reading into memory.

    - Checks Content-Length header first (fast rejection)
    - Reads file in chunks to enforce actual size limit
    - Returns file contents if valid

    Raises HTTPException 413 if file exceeds MAX_UPLOAD_SIZE_BYTES.
    """
    # Check Content-Length header for early rejection
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
            if declared_size > MAX_UPLOAD_SIZE_BYTES:
                raise HTTPException(
                    status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB."
                )
        except ValueError:
            pass  # Invalid Content-Length, will verify actual size

    # Read file in chunks to enforce actual size limit
    chunks = []
    total_size = 0
    chunk_size = 64 * 1024  # 64 KB chunks

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB."
            )
        chunks.append(chunk)

    return b''.join(chunks)


# --- App State & Pydantic Schemas ---
app_state = {}

class OntologySchema(BaseModel):
    name: str
    schema_json: dict[str, Any]

class OntologyResponse(OntologySchema):
    id: int

# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... (lifespan content remains the same)
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("JENEZIS API starting up...")
    settings = get_settings()
    logger.info("SQL schema management is now handled by Alembic.")
    async with get_db_session() as db:
        result = await db.execute(select(func.count(APIKey.id)))
        key_count = result.scalar_one()
        if key_count == 0:
            logger.warning("No API keys found. Attempting to provision from environment.")
            if not settings.INITIAL_ADMIN_KEY or settings.INITIAL_ADMIN_KEY == "change-me-to-a-very-secure-secret-on-first-boot":
                raise RuntimeError("FATAL: No API keys in DB and INITIAL_ADMIN_KEY is not set.")
            key_hash = get_key_hash(settings.INITIAL_ADMIN_KEY)
            first_key = APIKey(key_hash=key_hash, description="Initial admin key (provisioned from env)")
            db.add(first_key)
            await db.commit()
            logger.info("Successfully provisioned initial admin API key.")
    graph_store = GraphStore()  # Uses FalkorDB via FalkorEngine
    await graph_store.initialize_constraints_and_indexes()
    logger.info("Graph constraints and indexes ensured.")
    retriever = HybridRetriever(graph_store)
    app_state["generator"] = Generator(retriever)
    logger.info("RAG generator initialized.")
    yield
    logger.info("JENEZIS API shutting down...")
    await close_connections()
    logger.info("All connections closed.")

app = FastAPI(title="JENEZIS API", version="2.0.0", lifespan=lifespan)

# --- Dependencies ---
def get_generator() -> Generator:
    return app_state["generator"]

# --- Ontology Endpoints ---
@app.post("/ontologies", response_model=OntologyResponse, status_code=201, dependencies=[Depends(get_api_key)])
async def create_ontology(ontology_data: OntologySchema, db: AsyncSession = Depends(get_db_session_dep)):
    new_ontology = Ontology(name=ontology_data.name, schema_json=ontology_data.schema_json)
    db.add(new_ontology)
    await db.commit()
    await db.refresh(new_ontology)
    return new_ontology

@app.get("/ontologies", response_model=List[OntologyResponse], dependencies=[Depends(get_api_key)])
async def list_ontologies(db: AsyncSession = Depends(get_db_session_dep)):
    result = await db.execute(select(Ontology))
    return result.scalars().all()

@app.get("/ontologies/{ontology_id}", response_model=OntologyResponse, dependencies=[Depends(get_api_key)])
async def get_ontology(ontology_id: int, db: AsyncSession = Depends(get_db_session_dep)):
    ontology = await db.get(Ontology, ontology_id)
    if not ontology:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Ontology not found.")
    return ontology

# --- Document & RAG Endpoints ---
@app.post("/upload", status_code=HTTP_202_ACCEPTED, dependencies=[Depends(get_api_key)])
async def upload_document(
    request: Request,
    ontology_id: int | None = None,
    file: UploadFile = File(...)
):
    s3_client = get_s3_client()
    settings = get_settings()

    # SECURITY: Validate file size before loading into memory
    contents = await validate_upload_size(request, file)
    file_hash = hashlib.sha256(contents).hexdigest()

    # SECURITY: Sanitize filename to prevent path traversal
    safe_filename = sanitize_filename(file.filename)

    async with get_db_session() as db:
        if await get_document_by_hash(db, file_hash):
            raise HTTPException(status_code=HTTP_409_CONFLICT, detail="Document with same content already exists.")
        if ontology_id and not await db.get(Ontology, ontology_id):
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Ontology with id {ontology_id} not found.")

        # SECURITY: Use hash-prefixed key to prevent any filename manipulation
        s3_key = f"{file_hash}_{safe_filename}"
        s3_client.put_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key, Body=contents)

        new_doc = Document(
            filename=safe_filename,
            document_hash=file_hash,
            s3_path=f"{settings.S3_BUCKET_NAME}/{s3_key}",
            status=DocumentStatus.PENDING,
            domain_config_id=ontology_id,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)

        process_document.delay(document_id=new_doc.id)
        return {"job_id": new_doc.id, "status": "PENDING", "detail": "Document ingestion started."}

@app.put("/documents/{document_id}", status_code=HTTP_202_ACCEPTED, dependencies=[Depends(get_api_key)])
async def update_document(
    request: Request,
    document_id: int,
    file: UploadFile = File(...),
    ontology_id: int | None = None,
):
    async with get_db_session() as db:
        if not await db.get(Document, document_id):
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Document ID not found.")
        if ontology_id and not await db.get(Ontology, ontology_id):
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Ontology with id {ontology_id} not found.")

    s3_client = get_s3_client()
    settings = get_settings()

    # SECURITY: Validate file size before loading into memory
    contents = await validate_upload_size(request, file)
    file_hash = hashlib.sha256(contents).hexdigest()

    # SECURITY: Sanitize filename to prevent path traversal
    safe_filename = sanitize_filename(file.filename)

    # SECURITY: Use hash-prefixed key to prevent any filename manipulation
    s3_key = f"{file_hash}_{safe_filename}"

    async with get_db_session() as db:
        new_doc = Document(
            filename=safe_filename,
            document_hash=file_hash,
            s3_path=f"{settings.S3_BUCKET_NAME}/{s3_key}",
            status=DocumentStatus.PENDING,
            domain_config_id=ontology_id,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)

        s3_client.put_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key, Body=contents)

        update_chain = chain(delete_document_task.s(document_id=document_id), process_document.s(document_id=new_doc.id))
        update_chain.delay()

    return {"detail": "Document update process initiated.", "old_document_id": document_id, "new_job_id": new_doc.id}

@app.get("/status/{job_id}", dependencies=[Depends(get_api_key)])
async def get_ingestion_status(job_id: int):
    # ... (endpoint content remains the same)
    async with get_db_session() as db:
        doc = await get_document_by_id(db, job_id)
        if not doc:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Job ID not found.")
        return {"job_id": doc.id, "filename": doc.filename, "status": doc.status.value, "last_updated": doc.updated_at, "error": doc.error_log, "domain_config_id": doc.domain_config_id}

@app.post("/query", dependencies=[Depends(get_api_key)])
async def query_rag(query: str, generator: Generator = Depends(get_generator)):
    # ... (endpoint content remains the same)
    streamer, sources = await generator.rag_query_with_sources(query)
    source_header = [{"document_id": src.get("document_id"), "chunk_id": src.get("chunk_id"), "score": src.get("score")} for src in sources]
    headers = {"X-Sources": json.dumps(source_header)}
    return StreamingResponse(streamer, media_type="text/plain", headers=headers)

@app.delete("/documents/{document_id}", status_code=HTTP_202_ACCEPTED, dependencies=[Depends(get_api_key)])
async def delete_document(document_id: int):
    # ... (endpoint content remains the same, but remove BackgroundTasks)
    async with get_db_session() as db:
        if not await get_document_by_id(db, document_id):
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Document ID not found.")
    delete_document_task.delay(document_id=document_id)
    return {"job_id": document_id, "status": "DELETING", "detail": "Document deletion process initiated."}
