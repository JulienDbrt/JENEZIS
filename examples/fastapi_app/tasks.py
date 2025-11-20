"""
Celery tasks for the asynchronous ingestion and processing pipeline.
"""
import logging
import hashlib
from tempfile import NamedTemporaryFile
from typing import IO

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from doublehelix.core.connections import get_db_session, get_neo4j_driver, get_s3_client
from doublehelix.storage.metadata_store import DocumentStatus, update_document_status, get_document_by_id
from doublehelix.storage.graph_store import GraphStore
from doublehelix.ingestion import parser, chunker, embedder, extractor, resolver

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def get_file_from_s3(s3_path: str, temp_file: IO[bytes]):
    """Downloads a file from S3 to a temporary file."""
    s3 = get_s3_client()
    bucket, key = s3_path.split('/', 1)
    s3.download_fileobj(bucket, key, temp_file)
    temp_file.seek(0)

# --- Dead Letter Queue Handler ---

@shared_task(name="tasks.handle_dead_letter")
def handle_dead_letter(request, exc, traceback):
    """
    Handles tasks that have failed permanently.
    It logs the failure and updates the document status to FAILED.
    """
    task_name = request.kwargs.get('task_name')
    doc_id = request.kwargs.get('doc_id')
    
    error_message = f"Task {task_name} failed permanently for document {doc_id}. Error: {exc}"
    logger.critical(error_message, extra={'traceback': traceback})

    if doc_id:
        async def update_status():
            async with get_db_session() as db:
                await update_document_status(db, doc_id, DocumentStatus.FAILED, error_message)
        
        import asyncio
        asyncio.run(update_status())

# --- Main Ingestion Task ---

@shared_task(
    name="tasks.process_document",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60
)
def process_document(self, document_id: int):
    """
    The main asynchronous task for ingesting a single document.
    Orchestrates parsing, chunking, embedding, extraction, and storage.
    """
    logger.info(f"Starting ingestion process for document_id: {document_id}")

    try:
        # These instances are created inside the task to ensure they are
        # process-safe and connections are handled correctly by Celery forks.
        graph_store = GraphStore(get_neo4j_driver())
        doc_parser = parser.parse_document
        doc_chunker = chunker.get_chunker()
        doc_embedder = embedder.get_embedder()
        doc_extractor = extractor.get_extractor()
        doc_resolver = resolver.EntityResolver(get_neo4j_driver())

        async def run_async_pipeline():
            async with get_db_session() as db:
                # 1. Fetch metadata and update status
                doc = await get_document_by_id(db, document_id)
                if not doc:
                    raise ValueError(f"Document with ID {document_id} not found.")
                await update_document_status(db, document_id, DocumentStatus.PROCESSING)

                # 2. Get file from S3
                with NamedTemporaryFile(suffix=f"_{doc.filename}") as temp_file:
                    get_file_from_s3(doc.s3_path, temp_file)
                    
                    # 3. Parse and Chunk
                    text_content = doc_parser(temp_file, doc.filename)
                    chunks = doc_chunker.chunk(text_content)
                    
                    if not chunks:
                        logger.warning(f"No chunks were created for document {document_id}. Skipping.")
                        await update_document_status(db, document_id, DocumentStatus.COMPLETED)
                        return

                    # 4. Embed Chunks
                    chunk_texts = [c['text'] for c in chunks]
                    embeddings = await doc_embedder.embed_all(chunk_texts)
                    for i, c in enumerate(chunks):
                        c['embedding'] = embeddings[i]

                    # 5. Extract Entities & Relations
                    entities, relations = await doc_extractor.extract_from_all_chunks(chunks)
                    
                    # 6. Resolve Entities
                    id_map = await doc_resolver.resolve_and_map(entities)
                    resolved_relations = doc_resolver.remap_relations(relations, id_map)
                    
                    # Create a set of unique canonical entities to add to the graph
                    canonical_entities = []
                    seen_ids = set()
                    for entity in entities:
                        canonical_id = id_map.get(entity['id'])
                        if canonical_id not in seen_ids:
                             canonical_entities.append({"id": canonical_id, "name": entity['name'], "type": entity['type']})
                             seen_ids.add(canonical_id)

                    # 7. Store in Graph
                    await graph_store.add_document_node(doc.id, doc.filename)
                    await graph_store.add_chunks(doc.id, chunks)
                    if canonical_entities and resolved_relations:
                        await graph_store.add_entities_and_relations(canonical_entities, resolved_relations)

                # 8. Final status update
                await update_document_status(db, document_id, DocumentStatus.COMPLETED)
                logger.info(f"Successfully completed ingestion for document_id: {document_id}")

        import asyncio
        asyncio.run(run_async_pipeline())

    except Exception as exc:
        logger.error(f"Ingestion failed for document {document_id}. Error: {exc}", exc_info=True)
        try:
            # If max retries are exceeded, move to dead letter queue
            self.retry(exc=exc, link_error=handle_dead_letter.s(kwargs={'task_name': self.name, 'doc_id': document_id}))
        except MaxRetriesExceededError:
            # This block is executed locally if retries are exhausted
            # The DLQ task will be called by Celery broker
            pass


@shared_task(name="tasks.delete_document")
def delete_document_task(document_id: int):
    """
    Asynchronous task to delete a document and its direct associations (chunks).
    Orphaned entities are handled by a separate garbage collection task.
    """
    logger.info(f"Starting deletion process for document_id: {document_id}")
    try:
        async def run_async_delete():
            # 1. Update status to DELETING
            async with get_db_session() as db:
                await update_document_status(db, document_id, DocumentStatus.DELETING)

            # 2. Delete from graph (docs and chunks only)
            graph_store = GraphStore(get_neo4j_driver())
            await graph_store.delete_document_and_associated_data(document_id)

            # 3. Delete from metadata DB and S3
            async with get_db_session() as db:
                doc = await get_document_by_id(db, document_id)
                if doc:
                    # Delete from S3
                    s3 = get_s3_client()
                    bucket, key = doc.s3_path.split('/', 1)
                    s3.delete_object(Bucket=bucket, Key=key)
                    logger.info(f"Deleted {doc.s3_path} from S3.")

                    # Delete from SQL
                    await db.delete(doc)
                    await db.commit()
                    logger.info(f"Deleted document {document_id} from metadata store.")

        import asyncio
        asyncio.run(run_async_delete())
        
    except Exception as e:
        logger.error(f"Deletion failed for document {document_id}. Error: {e}", exc_info=True)
        async def update_status_on_fail():
            async with get_db_session() as db:
                await update_document_status(db, document_id, DocumentStatus.FAILED, f"Deletion failed: {e}")
        import asyncio
        asyncio.run(update_status_on_fail())
        raise

@shared_task(name="tasks.run_garbage_collection")
def run_garbage_collection():
    """
    Periodically runs the garbage collection process for orphaned entities in the graph.
    """
    logger.info("Starting orphaned entity garbage collection task...")
    try:
        async def run_async_gc():
            graph_store = GraphStore(get_neo4j_driver())
            await graph_store.garbage_collect_orphaned_entities()
        
        import asyncio
        asyncio.run(run_async_gc())
        logger.info("Garbage collection task finished successfully.")
    except Exception as e:
        logger.error(f"Garbage collection task failed: {e}", exc_info=True)
        raise

