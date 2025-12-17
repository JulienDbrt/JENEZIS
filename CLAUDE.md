# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JENEZIS is a neuro-symbolic GraphRAG framework combining a **Canonical Store** (PostgreSQL+pgvector) with a **Projection Graph** (Neo4j) orchestrated by LLM-driven extraction and resolution.

## Commands

### Development Setup
```bash
cp .env.example .env  # Configure INITIAL_ADMIN_KEY, OPENAI_API_KEY, POSTGRES_*, NEO4J_PASSWORD
docker-compose -f docker/docker-compose.yml up --build -d
```

### Run Tests
```bash
# Start test PostgreSQL (required for adversarial tests)
docker run -d --name jenezis-test-postgres \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test \
  -p 5433:5432 pgvector/pgvector:pg16
docker exec jenezis-test-postgres psql -U test -d test -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Unit tests
pytest tests/unit/ -v

# Adversarial security tests (requires test postgres on port 5433)
pytest tests/adversarial/ -v

# Integration tests (requires full Docker stack)
pytest tests/integration/ -v

# All tests with coverage
pytest tests/unit/ tests/adversarial/ --cov=jenezis

# Cleanup test postgres
docker stop jenezis-test-postgres && docker rm jenezis-test-postgres

# Single test file
pytest tests/adversarial/test_cypher_injection.py -v

# Parallel execution
pytest tests/unit/ -n 4

# By marker
pytest -m adversarial  # Security tests
pytest -m slow         # Long-running tests
pytest -m evaluation   # RAGAS evaluation (requires running stack)
```

### Load Testing
```bash
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Headless mode (CI)
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
    --users=100 --spawn-rate=10 --run-time=5m --headless
```

### Security Scanning
```bash
bandit -r jenezis/ -ll -ii
poetry export -f requirements.txt --without-hashes | safety check --stdin
```

### Database Migrations
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head  # Auto-run on API startup in Docker
```

### Local Development (without Docker)
```bash
poetry install
poetry shell  # Activate virtualenv before running commands

uvicorn examples.fastapi_app.main:app --reload
celery -A examples.fastapi_app.celery_config worker --loglevel=INFO  # Separate terminal
```

## Architecture

### Neuro-Symbolic Pipeline ("Harmonizer")
The ingestion flow in `jenezis/ingestion/`:
1. **Parser** (`parser.py`) → **Chunker** (`chunker.py`) → **Embedder** (`embedder.py`)
2. **Extractor** (`extractor.py`): LLM extracts entities/relations constrained by `DomainConfig` ontology
3. **Validator** (`validator.py`): Filters extracted data against ontology rules
4. **Resolver** (`resolver.py`): Maps entities to canonical store (exact match → vector similarity → enrichment queue)

### Data Stores
- **PostgreSQL+pgvector** (`jenezis/storage/metadata_store.py`): Canonical nodes, aliases, domain configs, documents, API keys, enrichment queue
- **Neo4j** (`jenezis/storage/graph_store.py`): Projection graph with Document→Chunk→Entity relationships, uses APOC for dynamic labels
- **MinIO/S3**: Raw document storage
- **Redis**: Celery message broker

### Key SQLAlchemy Models (`metadata_store.py`)
- `DomainConfig`: User-defined ontology (entity_types, relation_types)
- `CanonicalNode`: Canonical entity with embedding
- `NodeAlias`: Maps raw text to canonical nodes
- `EnrichmentQueueItem`: Unresolved entities queued for async learning
- `Document`: Tracks ingestion status

### Celery Tasks (`examples/fastapi_app/tasks.py`)
- `process_document`: Main ingestion pipeline
- `enrich_unresolved_entity`: Active learning for new entities
- `delete_document_task`: Cascading deletion
- `run_garbage_collection`: Orphan entity cleanup

### RAG Pipeline (`jenezis/rag/`)
- **Retriever** (`retriever.py`): Hybrid search combining vector similarity with LLM-planned Cypher queries, fused via Reciprocal Rank Fusion
- **Generator** (`generator.py`): Streaming LLM responses with source citations

### API Endpoints (`examples/fastapi_app/main.py`)
- `POST /domain-configs`: Create domain config (ontology)
- `POST /upload?domain_config_id=N`: Ingest document
- `POST /query`: RAG query with streaming response
- `GET /status/{job_id}`: Check ingestion status

## Configuration

All settings in `jenezis/core/config.py` via Pydantic Settings. Key env vars:
- `LLM_PROVIDER`: "openai" | "anthropic" | "openrouter"
- `EXTRACTION_MODEL`: Model for entity extraction (default: gpt-3.5-turbo)
- `GENERATOR_MODEL`: Model for RAG generation (default: gpt-4-turbo)
- `ENTITY_RESOLUTION_THRESHOLD`: Fuzzy matching score 0-100

## Dependencies

- **Python**: 3.11+
- **Neo4j**: Enterprise edition with APOC plugin (required for dynamic label/relationship creation)
- See `docker/docker-compose.yml` for full stack configuration

## Testing Notes

- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` - no need for `@pytest.mark.asyncio` decorators
- Security hardening modules: `jenezis/core/prompt_security.py` (prompt injection), `graph_store.py` (Cypher injection)
- Docker secrets stored in `secrets/` directory (gitignored)

## Future Enhancements (Low Priority)

| Enhancement | Location | Notes |
|-------------|----------|-------|
| EnrichmentQueueItem error field | `metadata_store.py` | Add `error_message` column for failed items |

All security tests pass. Run `pytest tests/unit/ tests/adversarial/ -v` for full coverage.
