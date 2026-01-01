# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JENEZIS is a neuro-symbolic GraphRAG framework combining a **Canonical Store** (PostgreSQL+pgvector) with a **Projection Graph** (FalkorDB) orchestrated by LLM-driven extraction and resolution.

## Commands

### Development Setup
```bash
poetry install && poetry shell  # Always activate virtualenv first
cp .env.example .env  # Configure INITIAL_ADMIN_KEY, OPENAI_API_KEY, POSTGRES_*, FALKOR_*
docker-compose -f docker/docker-compose.yml up --build -d
```

### Run Tests
```bash
# Unit tests (no external dependencies)
poetry run pytest tests/unit/ -v

# Adversarial security tests (requires test postgres on port 5433)
docker run -d --name jenezis-test-postgres \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test \
  -p 5433:5432 pgvector/pgvector:pg16
docker exec jenezis-test-postgres psql -U test -d test -c "CREATE EXTENSION IF NOT EXISTS vector;"
poetry run pytest tests/adversarial/ -v

# Integration tests (requires full Docker stack)
poetry run pytest tests/integration/ -v

# All tests with coverage
poetry run pytest tests/unit/ tests/adversarial/ --cov=jenezis

# Single test file
poetry run pytest tests/adversarial/test_cypher_injection.py -v

# By marker
poetry run pytest -m adversarial  # Security tests
poetry run pytest -m evaluation   # RAGAS evaluation (requires running stack)
```

### Local Development (without Docker)
```bash
poetry install && poetry shell
uvicorn examples.fastapi_app.main:app --reload
celery -A examples.fastapi_app.celery_config worker --loglevel=INFO  # Separate terminal
```

### Database Migrations
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head  # Auto-run on API startup in Docker
```

### Security Scanning
```bash
bandit -r jenezis/ -ll -ii
poetry export -f requirements.txt --without-hashes | safety check --stdin
```

## Architecture

### Core Principle: Canonical → Projection Separation
- **Canonical Store (PostgreSQL+pgvector)**: Source of truth for entities, aliases, ontologies
- **Projection Graph (FalkorDB)**: Derived reasoning layer, rebuildable from canonical store
- This separation enables full audit trails and prevents data drift

### Graph Database: FalkorDB (migrated from Neo4j)
The codebase uses FalkorDB as the graph database backend:
- **FalkorEngine** (`jenezis/storage/falkor_engine.py`): Core graph engine with OpenCypher support
- **GraphStore** (`jenezis/storage/graph_store.py`): Facade maintaining API compatibility
- Native HNSW vector indexing for semantic search
- No APOC dependency (dynamic labels stored as properties)
- Redis-based persistence on port 6379

### Neuro-Symbolic Pipeline ("Harmonizer")
The ingestion flow in `jenezis/ingestion/`:
1. **Parser** (`parser.py`) → **Chunker** (`chunker.py`) → **Embedder** (`embedder.py`)
2. **Extractor** (`extractor.py`): LLM extracts entities/relations constrained by `DomainConfig` ontology
3. **Validator** (`validator.py`): Filters extracted data against ontology rules
4. **Resolver** (`resolver.py`): Maps entities to canonical store (exact match → vector similarity → enrichment queue)

### Key SQLAlchemy Models (`jenezis/storage/metadata_store.py`)
- `DomainConfig`: User-defined ontology (entity_types, relation_types)
- `CanonicalNode`: Canonical entity with embedding vector
- `NodeAlias`: Maps raw text variants to canonical nodes
- `EnrichmentQueueItem`: Unresolved entities queued for async learning
- `Document`: Tracks ingestion status via state machine

### RAG Pipeline (`jenezis/rag/`)
- **Retriever** (`retriever.py`): Hybrid search (vector similarity + LLM-planned Cypher), fused via Reciprocal Rank Fusion
- **Generator** (`generator.py`): Streaming LLM responses with source citations

### Celery Tasks (`examples/fastapi_app/tasks.py`)
- `process_document`: Main ingestion pipeline
- `enrich_unresolved_entity`: Active learning for new entities
- `delete_document_task`: Cascading deletion
- `run_garbage_collection`: Orphan entity cleanup

### Security Hardening
- **Prompt injection**: `jenezis/core/prompt_security.py` - sanitizes ontology schemas and retriever outputs
- **Cypher injection**: `graph_store.py` - validates dynamic labels/relations against strict regex patterns
- **Path traversal**: Upload handler blocks `../`, null bytes, protocol injection
- **State machine**: Document status transitions enforced to prevent invalid states

## Configuration

All settings in `jenezis/core/config.py` via Pydantic Settings. Key env vars:
- `LLM_PROVIDER`: "openai" | "anthropic" | "openrouter"
- `EXTRACTION_MODEL`: Model for entity extraction (default: gpt-3.5-turbo)
- `GENERATOR_MODEL`: Model for RAG generation (default: gpt-4-turbo)
- `ENTITY_RESOLUTION_THRESHOLD`: Fuzzy matching score 0-100
- `FALKOR_HOST`, `FALKOR_PORT`, `FALKOR_GRAPH`: FalkorDB connection settings
- Docker secrets supported via `*_FILE` env vars (e.g., `OPENAI_API_KEY_FILE`)

## Docker Stack

Services defined in `docker/docker-compose.yml`:
- **falkordb** (port 6379): Graph database with native vector support
- **postgres** (port 5432): Metadata store with pgvector
- **redis** (port 6380): Celery message broker (separate from FalkorDB)
- **minio** (ports 9000/9001): S3-compatible object storage
- **api** (port 8000): FastAPI application
- **worker**: Celery worker for async tasks

## Testing Notes

- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` - no need for `@pytest.mark.asyncio` decorators
- Fixtures in `tests/conftest.py` provide mock LLM, Neo4j, and S3 clients with recording capabilities
- `CypherQueryRecorder` and `MockLLMClient` fixtures enable injection detection tests
- Adversarial tests require test PostgreSQL on port 5433 (see Run Tests section)
- Test markers: `unit`, `integration`, `adversarial`, `slow`, `evaluation`

## API Endpoints (`examples/fastapi_app/main.py`)

- `POST /domain-configs`: Create domain config (ontology)
- `POST /upload?domain_config_id=N`: Ingest document
- `POST /query`: RAG query with streaming response
- `GET /status/{job_id}`: Check ingestion status

## Dependencies

- **Python**: 3.11+
- **FalkorDB**: Redis-based graph database with OpenCypher support
