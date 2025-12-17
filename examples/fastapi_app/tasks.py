"""
Celery tasks for the asynchronous ingestion and processing pipeline.
"""
import logging
import hashlib
import json
from tempfile import NamedTemporaryFile
from typing import IO

import openai
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from jenezis.core.config import get_settings
from jenezis.core.connections import get_db_session, get_neo4j_driver, get_s3_client
from jenezis.storage.metadata_store import (
    Document, DocumentStatus, update_document_status, get_document_by_id,
    EnrichmentQueueItem, EnrichmentStatus, CanonicalNode, NodeAlias,
    get_or_create_canonical_node, InvalidStatusTransitionError
)
from jenezis.storage.graph_store import GraphStore
from jenezis.ingestion import parser, chunker, embedder, extractor
from jenezis.ingestion.resolver import Resolver

logger = logging.getLogger(__name__)
settings = get_settings()

# --- Helper & DLQ Functions ---
def get_file_from_s3(s3_path: str, temp_file: IO[bytes]):
    s3 = get_s3_client(); bucket, key = s3_path.split('/', 1)
    s3.download_fileobj(bucket, key, temp_file); temp_file.seek(0)

@shared_task(name="tasks.handle_dead_letter")
def handle_dead_letter(request, exc, traceback):
    doc_id = request.kwargs.get('doc_id')
    error_message = f"Task {request.kwargs.get('task_name')} failed for doc {doc_id}. Error: {exc}"
    logger.critical(error_message, extra={'traceback': traceback})
    if doc_id:
        async def update_status():
            async with get_db_session() as db:
                try:
                    # SECURITY: Now requires error_message for FAILED status
                    await update_document_status(db, doc_id, DocumentStatus.FAILED, error_message)
                except InvalidStatusTransitionError as e:
                    # Document may already be in a terminal state
                    logger.warning(f"Cannot mark doc {doc_id} as FAILED: {e}")
        import asyncio; asyncio.run(update_status())

# --- Main Ingestion & Learning Loop Tasks ---

@shared_task(name="tasks.process_document", bind=True, autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
def process_document(self, document_id: int):
    """Main task for ingesting a document with the neuro-symbolic 'Harmonizer' pipeline."""
    logger.info(f"Starting ingestion for document_id: {document_id}")
    try:
        doc_embedder = embedder.get_embedder()
        async def run_async_pipeline():
            graph_store = GraphStore(await get_neo4j_driver())
            async with get_db_session() as db:
                doc = (await db.execute(select(Document).options(selectinload(Document.domain_config)).filter(Document.id == document_id))).scalars().one_or_none()
                if not doc: raise ValueError(f"Doc {document_id} not found.")
                await update_document_status(db, document_id, DocumentStatus.PROCESSING)
                domain_config = doc.domain_config.schema_json if doc.domain_config else None
                if not domain_config: raise ValueError(f"Doc {document_id} has no DomainConfig.")

                with NamedTemporaryFile(suffix=f"_{doc.filename}") as temp_file:
                    get_file_from_s3(doc.s3_path, temp_file)
                    chunks = chunker.get_chunker().chunk(parser.parse_document(temp_file, doc.filename))
                    if not chunks: await update_document_status(db, document_id, DocumentStatus.COMPLETED, "Doc was empty."); return

                    embeddings = await doc_embedder.embed_all([c['text'] for c in chunks])
                    for i, c in enumerate(chunks): c['embedding'] = embeddings[i]
                    await graph_store.add_document_node(doc.id, doc.filename); await graph_store.add_chunks(doc.id, chunks)

                    entities, relations = await extractor.get_extractor().extract_from_all_chunks(chunks, domain_config)
                    from jenezis.ingestion.validator import Validator
                    validated_entities, validated_relations = Validator(domain_config).validate_and_filter(entities, relations)
                    if not validated_entities: await update_document_status(db, document_id, DocumentStatus.COMPLETED, "No valid entities extracted."); return
                    
                    resolver = Resolver(db, doc_embedder)
                    resolved_map, unresolved_items = await resolver.resolve_all(validated_entities)

                    if unresolved_items:
                        logger.warning(f"Queueing {len(unresolved_items)} unresolved entities for enrichment.")
                        for item in unresolved_items:
                            context_chunk_text = next((c['text'] for c in chunks if item['name'] in c['text']), chunks[0]['text'])
                            db.add(EnrichmentQueueItem(name=item['name'], entity_type=item['type'], context_chunk=context_chunk_text))
                        await db.flush()

                    remapped_relations = []
                    for rel in validated_relations:
                        source_id, target_id = resolved_map.get(rel.get("source_id")), resolved_map.get(rel.get("target_id"))
                        if source_id and target_id and source_id != target_id:
                            remapped_relations.append({**rel, "source_id": source_id, "target_id": target_id})
                    
                    await graph_store.add_entities_and_relations(validated_entities, remapped_relations)
                await update_document_status(db, document_id, DocumentStatus.COMPLETED)
        import asyncio; asyncio.run(run_async_pipeline())
    except Exception as exc:
        logger.error(f"Ingestion failed for doc {document_id}: {exc}", exc_info=True)
        try: self.retry(exc=exc, link_error=handle_dead_letter.s(kwargs={'task_name': self.name, 'doc_id': document_id}))
        except MaxRetriesExceededError: pass

@shared_task(name="tasks.enrich_unresolved_entity")
def enrich_unresolved_entity(item_id: int):
    """Processes one item from the enrichment queue to learn a new entity."""
    logger.info(f"Starting enrichment for item {item_id}.")
    async def run_enrichment():
        async with get_db_session() as db:
            item = await db.get(EnrichmentQueueItem, item_id)
            if not item or item.status != EnrichmentStatus.PENDING: return
            item.status = EnrichmentStatus.PROCESSING; await db.commit()
            try:
                client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                prompt = f'Given the entity name "{item.name}" of approx. type "{item.entity_type}" found in context: "{item.context_chunk}", provide its canonical name. Respond ONLY with JSON: {{"canonical_name": "Canonical Name"}}'
                response = await client.chat.completions.create(model=settings.EXTRACTION_MODEL, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}, temperature=0.0)
                canonical_name = json.loads(response.choices[0].message.content)['canonical_name']

                embedding = (await embedder.get_embedder().embed_batch([canonical_name]))[0]

                # SECURITY: Use atomic get_or_create to prevent race conditions
                # This handles the case where two concurrent enrichment tasks
                # try to create the same canonical node simultaneously
                node, created = await get_or_create_canonical_node(
                    db, name=canonical_name, node_type=item.entity_type, embedding=embedding
                )

                if created:
                    logger.info(f"Created new canonical node '{canonical_name}'.")
                else:
                    logger.info(f"Found existing canonical node '{canonical_name}'.")

                # Add the alias mapping (this may also race, but alias uniqueness is less critical)
                existing_alias = await db.execute(
                    select(NodeAlias).where(NodeAlias.alias == item.name)
                )
                if not existing_alias.scalars().first():
                    db.add(NodeAlias(alias=item.name, canonical_node_id=node.id, confidence_score=0.98))

                item.status = EnrichmentStatus.COMPLETED; await db.commit()
                logger.info(f"Successfully enriched '{item.name}' as canonical node '{canonical_name}'.")
            except Exception as e:
                logger.error(f"Enrichment failed for item {item_id}: {e}", exc_info=True)
                item.status = EnrichmentStatus.FAILED; await db.commit()
    import asyncio; asyncio.run(run_enrichment())

@shared_task(name="tasks.schedule_enrichment")
def schedule_enrichment():
    """Periodically dispatches enrichment tasks for PENDING items."""
    logger.info("Scheduler looking for items to enrich.")
    async def find_and_dispatch():
        async with get_db_session() as db:
            item_ids = (await db.execute(select(EnrichmentQueueItem.id).where(EnrichmentQueueItem.status == EnrichmentStatus.PENDING).limit(100))).scalars().all()
            for item_id in item_ids: enrich_unresolved_entity.delay(item_id)
    import asyncio; asyncio.run(find_and_dispatch())

@shared_task(name="tasks.delete_document")
def delete_document_task(document_id: int):
    logger.info(f"Starting deletion for doc {document_id}")
    try:
        async def run_async_delete():
            async with get_db_session() as db:
                try:
                    await update_document_status(db, document_id, DocumentStatus.DELETING)
                except InvalidStatusTransitionError as e:
                    # Document is in a state that doesn't allow deletion
                    logger.warning(f"Cannot delete doc {document_id}: {e}")
                    raise

            await GraphStore(await get_neo4j_driver()).delete_document_and_associated_data(document_id)
            async with get_db_session() as db:
                doc = await get_document_by_id(db, document_id)
                if doc:
                    s3 = get_s3_client(); bucket, key = doc.s3_path.split('/', 1)
                    s3.delete_object(Bucket=bucket, Key=key)
                    await db.delete(doc); await db.commit()
        import asyncio; asyncio.run(run_async_delete())
    except InvalidStatusTransitionError:
        # Don't mark as failed for invalid transitions - just re-raise
        raise
    except Exception as e:
        logger.error(f"Deletion failed for doc {document_id}: {e}", exc_info=True)
        async def update_status_on_fail():
            async with get_db_session() as db:
                try:
                    await update_document_status(db, document_id, DocumentStatus.FAILED, f"Deletion failed: {e}")
                except InvalidStatusTransitionError:
                    # Already in a terminal state, can't mark as failed
                    logger.warning(f"Cannot mark doc {document_id} as FAILED - invalid transition")
        import asyncio; asyncio.run(update_status_on_fail()); raise

@shared_task(name="tasks.run_garbage_collection")
def run_garbage_collection():
    logger.info("Starting garbage collection task...")
    try:
        async def run_async_gc(): await GraphStore(await get_neo4j_driver()).garbage_collect_orphaned_entities()
        import asyncio; asyncio.run(run_async_gc())
    except Exception as e:
        logger.error(f"Garbage collection task failed: {e}", exc_info=True); raise

