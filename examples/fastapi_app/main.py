"""
Complete FastAPI application for DoubleHelixGraphRAG.
Provides endpoints for document upload, status checking, querying, and management.
"""
import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.status import (
    HTTP_202_ACCEPTED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

import secrets
from sqlalchemy import select, func

from doublehelix.core.config import get_settings
from doublehelix.core.connections import (
    close_connections,
    get_db_session,
    get_s3_client,
    get_neo4j_driver,
    sql_engine,
)
from doublehelix.core.security import get_api_key, get_key_hash
from doublehelix.storage.metadata_store import (
    Document,
    DocumentStatus,
    get_document_by_hash,
    get_document_by_id,
    create_tables,
    APIKey,
)
from doublehelix.storage.graph_store import GraphStore
from doublehelix.rag.retriever import HybridRetriever
from doublehelix.rag.generator import Generator
from doublehelix.ingestion.extractor import get_extractor
from doublehelix.utils.logging import setup_logging
from .tasks import process_document, delete_document_task

# --- App State ---
# Using a dictionary for app state is a simple way to manage shared resources.
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("DoubleHelix API starting up...")
    
    # Initialize DB tables
    await create_tables(sql_engine)
    logger.info("SQL tables ensured.")

    # Provision initial API key if none exist
    async with get_db_session() as db:
        result = await db.execute(select(func.count(APIKey.id)))
        key_count = result.scalar_one()
        if key_count == 0:
            logger.warning("No API keys found in the database. Provisioning a new one.")
            new_key = secrets.token_hex(32)
            key_hash = get_key_hash(new_key)
            
            first_key = APIKey(
                key_hash=key_hash,
                description="Initial admin key",
                is_active=True
            )
            db.add(first_key)
            await db.commit()
            
            logger.critical("="*80)
            logger.critical("THIS IS THE ONLY TIME YOUR NEW ADMIN API KEY WILL BE SHOWN")
            logger.critical(f"  Bearer Token: {new_key}")
            logger.critical("Save this key securely. You will need it to interact with the API.")
            logger.critical("="*80)

    # Initialize graph constraints
    graph_store = GraphStore(await get_neo4j_driver())
    await graph_store.initialize_constraints_and_indexes()
    logger.info("Graph constraints and indexes ensured.")
    
    # Initialize RAG components and add to app state
    extractor = get_extractor()
    retriever = HybridRetriever(graph_store, extractor)
    app_state["generator"] = Generator(retriever)
    
    logger.info("RAG generator initialized.")
    yield
    # --- Shutdown ---
    logger.info("DoubleHelix API shutting down...")
    await close_connections()
    logger.info("All connections closed.")


app = FastAPI(
    title="DoubleHelixGraphRAG API",
    description="API for industrial-grade, adaptive GraphRAG.",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Dependency ---
def get_generator() -> Generator:
    return app_state["generator"]

# --- Endpoints ---

@app.post("/upload", status_code=HTTP_202_ACCEPTED, dependencies=[Depends(get_api_key)])
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Accepts a document, saves it, and triggers the async ingestion pipeline.
    Returns a job_id to track the document's status.
    """
    s3_client = get_s3_client()
    settings = get_settings()
    
    # Read file content and calculate hash
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    async with get_db_session() as db:
        existing_doc = await get_document_by_hash(db, file_hash)
        if existing_doc:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Document with same content already exists with ID: {existing_doc.id}",
            )

        # Upload to S3
        s3_path = f"{settings.S3_BUCKET_NAME}/{file_hash}_{file.filename}"
        bucket, key = s3_path.split('/', 1)
        s3_client.put_object(Bucket=bucket, Key=key, Body=contents)

        # Create metadata entry
        new_doc = Document(
            filename=file.filename,
            document_hash=file_hash,
            s3_path=s3_path,
            status=DocumentStatus.PENDING,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)

        # Trigger background task
        background_tasks.add_task(process_document.delay, document_id=new_doc.id)

        return {"job_id": new_doc.id, "status": "PENDING", "detail": "Document ingestion started."}

@app.get("/status/{job_id}", dependencies=[Depends(get_api_key)])
async def get_ingestion_status(job_id: int):
    """Retrieves the current status of a document ingestion job."""
    async with get_db_session() as db:
        doc = await get_document_by_id(db, job_id)
        if not doc:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Job ID not found.")
        
        return {
            "job_id": doc.id,
            "filename": doc.filename,
            "status": doc.status.value,
            "last_updated": doc.updated_at,
            "error": doc.error_log
        }

@app.post("/query", dependencies=[Depends(get_api_key)])
async def query_rag(
    query: str,
    generator: Generator = Depends(get_generator)
):
    """
    Accepts a query, performs RAG, and streams the response.
    Source documents are included in the 'X-Sources' header.
    """
    streamer, sources = await generator.rag_query_with_sources(query)
    
    # Format sources for header
    source_header = []
    for src in sources:
        source_header.append({
            "document_id": src.get("document_id"),
            "chunk_id": src.get("chunk_id"),
            "score": src.get("score"),
        })

    headers = {"X-Sources": json.dumps(source_header)}
    return StreamingResponse(streamer, media_type="text/plain", headers=headers)

@app.delete("/documents/{document_id}", status_code=HTTP_202_ACCEPTED, dependencies=[Depends(get_api_key)])
async def delete_document(document_id: int, background_tasks: BackgroundTasks):
    """
    Triggers the asynchronous deletion of a document and all its associated data.
    """
    async with get_db_session() as db:
        doc = await get_document_by_id(db, document_id)
        if not doc:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Document ID not found.")
        
    background_tasks.add_task(delete_document_task.delay, document_id=document_id)
    return {"job_id": document_id, "status": "DELETING", "detail": "Document deletion process initiated."}

@app.put("/documents/{document_id}", status_code=HTTP_202_ACCEPTED, dependencies=[Depends(get_api_key)])
async def update_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Updates a document by deleting the old one and ingesting the new one.
    This is a simple implementation; a more sophisticated one might do an in-place update.
    """
    async with get_db_session() as db:
        doc = await get_document_by_id(db, document_id)
        if not doc:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Document ID not found.")

    # 1. Trigger deletion of the old document
    background_tasks.add_task(delete_document_task.delay, document_id=document_id)
    
    # 2. Ingest the new document (similar to /upload)
    # A small delay might be needed to let the delete task start, or use Celery chains.
    await asyncio.sleep(1) 
    
    s3_client = get_s3_client()
    settings = get_settings()
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    async with get_db_session() as db:
        # Check if this content hash already exists under a different ID
        existing_doc = await get_document_by_hash(db, file_hash)
        if existing_doc:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"New document content is identical to existing document ID: {existing_doc.id}",
            )
        
        s3_path = f"{settings.S3_BUCKET_NAME}/{file_hash}_{file.filename}"
        bucket, key = s3_path.split('/', 1)
        s3_client.put_object(Bucket=bucket, Key=key, Body=contents)

        new_doc = Document(
            filename=file.filename,
            document_hash=file_hash,
            s3_path=s3_path,
            status=DocumentStatus.PENDING,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)
        
        background_tasks.add_task(process_document.delay, document_id=new_doc.id)
    
    return {
        "detail": "Document update process initiated.",
        "old_document_id": document_id,
        "new_job_id": new_doc.id
    }
