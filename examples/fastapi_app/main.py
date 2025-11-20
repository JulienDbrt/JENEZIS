"""
Complete FastAPI application for DoubleHelixGraphRAG.
Provides endpoints for document upload, status checking, querying, and management.
"""
import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from typing import List, Any

from celery import chain
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Body
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.status import (
    HTTP_202_ACCEPTED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

import secrets
from sqlalchemy import select, func
from sqlalchemy.future import select

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
    APIKey,
    Ontology,
)
from doublehelix.storage.graph_store import GraphStore
from doublehelix.rag.retriever import HybridRetriever
from doublehelix.rag.generator import Generator
from doublehelix.ingestion.extractor import get_extractor
from doublehelix.utils.logging import setup_logging
from .tasks import process_document, delete_document_task

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
    logger.info("DoubleHelix API starting up...")
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
    graph_store = GraphStore(await get_neo4j_driver())
    await graph_store.initialize_constraints_and_indexes()
    logger.info("Graph constraints and indexes ensured.")
    extractor = get_extractor()
    retriever = HybridRetriever(graph_store, extractor)
    app_state["generator"] = Generator(retriever)
    logger.info("RAG generator initialized.")
    yield
    logger.info("DoubleHelix API shutting down...")
    await close_connections()
    logger.info("All connections closed.")

app = FastAPI(title="DoubleHelixGraphRAG API", version="1.0.0", lifespan=lifespan)

# --- Dependencies ---
def get_generator() -> Generator:
    return app_state["generator"]

# --- Ontology Endpoints ---
@app.post("/ontologies", response_model=OntologyResponse, status_code=201, dependencies=[Depends(get_api_key)])
async def create_ontology(ontology_data: OntologySchema, db: AsyncSession = Depends(get_db_session)):
    new_ontology = Ontology(name=ontology_data.name, schema_json=ontology_data.schema_json)
    db.add(new_ontology)
    await db.commit()
    await db.refresh(new_ontology)
    return new_ontology

@app.get("/ontologies", response_model=List[OntologyResponse], dependencies=[Depends(get_api_key)])
async def list_ontologies(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(Ontology))
    return result.scalars().all()

@app.get("/ontologies/{ontology_id}", response_model=OntologyResponse, dependencies=[Depends(get_api_key)])
async def get_ontology(ontology_id: int, db: AsyncSession = Depends(get_db_session)):
    ontology = await db.get(Ontology, ontology_id)
    if not ontology:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Ontology not found.")
    return ontology

# --- Document & RAG Endpoints ---
@app.post("/upload", status_code=HTTP_202_ACCEPTED, dependencies=[Depends(get_api_key)])
async def upload_document(
    ontology_id: int | None = None,
    file: UploadFile = File(...)
):
    s3_client = get_s3_client()
    settings = get_settings()
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    async with get_db_session() as db:
        if await get_document_by_hash(db, file_hash):
            raise HTTPException(status_code=HTTP_409_CONFLICT, detail="Document with same content already exists.")
        if ontology_id and not await db.get(Ontology, ontology_id):
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Ontology with id {ontology_id} not found.")
        
        s3_path = f"{settings.S3_BUCKET_NAME}/{file_hash}_{file.filename}"
        bucket, key = s3_path.split('/', 1)
        s3_client.put_object(Bucket=bucket, Key=key, Body=contents)

        new_doc = Document(
            filename=file.filename,
            document_hash=file_hash,
            s3_path=s3_path,
            status=DocumentStatus.PENDING,
            ontology_id=ontology_id,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)

        process_document.delay(document_id=new_doc.id)
        return {"job_id": new_doc.id, "status": "PENDING", "detail": "Document ingestion started."}

@app.put("/documents/{document_id}", status_code=HTTP_202_ACCEPTED, dependencies=[Depends(get_api_key)])
async def update_document(
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
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    async with get_db_session() as db:
        new_doc = Document(
            filename=file.filename,
            document_hash=file_hash,
            s3_path=f"{settings.S3_BUCKET_NAME}/{file_hash}_{file.filename}",
            status=DocumentStatus.PENDING,
            ontology_id=ontology_id,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)
        
        s3_client.put_object(Bucket=settings.S3_BUCKET_NAME, Key=f"{file_hash}_{file.filename}", Body=contents)
        
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
        return {"job_id": doc.id, "filename": doc.filename, "status": doc.status.value, "last_updated": doc.updated_at, "error": doc.error_log, "ontology_id": doc.ontology_id}

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
