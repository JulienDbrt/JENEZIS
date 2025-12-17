# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JENEZIS is a neuro-symbolic GraphRAG framework implementing the "Jenezis" architecture. It combines a **Canonical Store** (PostgreSQL+pgvector for source of truth) with a **Projection Graph** (Neo4j for reasoning) orchestrated by LLM-driven extraction and resolution.

## Commands

### Development Setup
```bash
cp .env.example .env  # Configure INITIAL_ADMIN_KEY, OPENAI_API_KEY, POSTGRES_*, NEO4J_PASSWORD
docker-compose -f docker/docker-compose.yml up --build -d
```

### Run Tests
```bash
# Unit tests (fast, no services required)
pytest tests/unit/ -v

# Adversarial security tests
pytest tests/adversarial/ -v

# Integration tests (requires Docker stack)
pytest tests/integration/ -v

# All tests with coverage (80% minimum)
pytest tests/unit/ tests/adversarial/ --cov=jenezis --cov-fail-under=80

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
# Run Locust load tests (requires running stack)
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Headless mode (CI)
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
    --users=100 --spawn-rate=10 --run-time=5m --headless
```

### Security Scanning
```bash
# Static analysis with Bandit
bandit -r jenezis/ -ll -ii

# Dependency vulnerability check
poetry export -f requirements.txt --without-hashes | safety check --stdin
```

### Database Migrations
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations (automatically run on API startup in Docker)
alembic upgrade head
```

### Local Development (without Docker)
```bash
poetry install
poetry shell  # Activate virtualenv before running commands

# API server
uvicorn examples.fastapi_app.main:app --reload

# Celery worker (separate terminal)
celery -A examples.fastapi_app.celery_config worker --loglevel=INFO
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

Neo4j requires the Enterprise edition with APOC plugin for dynamic label/relationship creation. See `docker/docker-compose.yml` for full stack configuration.

## Known Vulnerabilities (xfail tests)

The adversarial test suite documents security vulnerabilities that are marked `xfail` (expected failure) to allow CI to pass while tracking issues. **These MUST be fixed before production deployment.**

### Critical - Input Validation (FIXED)

| Vulnerability | File | Status | Fix |
|--------------|------|--------|-----|
| **Path Traversal in S3 keys** | `main.py` | **FIXED** | `sanitize_filename()` strips path components |
| **Null byte injection** | `main.py` | **FIXED** | `sanitize_filename()` removes null bytes |
| **Protocol injection** | `main.py` | **FIXED** | `sanitize_filename()` rejects protocol prefixes |
| **URL-encoded traversal** | `main.py` | **FIXED** | Double URL-decode before validation |
| **File size DoS** | `main.py` | **FIXED** | `validate_upload_size()` with 50MB limit |

### Critical - Prompt Injection (FIXED)

| Vulnerability | File | Status | Fix |
|--------------|------|--------|-----|
| **Ontology schema injection** | `extractor.py` | **FIXED** | `sanitize_ontology_schema()` strips dangerous chars |
| **Retriever query injection** | `retriever.py` | **FIXED** | `validate_llm_json_output()` validates planner output |
| **Generator context injection** | `generator.py` | **FIXED** | `sanitize_context_for_generation()` filters patterns |

See `jenezis/core/prompt_security.py` for the security module.

### High - State Management (FIXED)

| Vulnerability | File | Status | Fix |
|--------------|------|--------|-----|
| **Invalid status transitions** | `metadata_store.py` | **FIXED** | `validate_status_transition()` enforces state machine |
| **Missing error_message for FAILED** | `metadata_store.py` | **FIXED** | `update_document_status()` requires error_message for FAILED |
| **Race condition in canonical nodes** | `metadata_store.py` | **FIXED** | `get_or_create_canonical_node()` handles IntegrityError |

### High - Cypher Injection (FIXED)

| Vulnerability | File | Status | Fix |
|--------------|------|--------|-----|
| **Dynamic label injection** | `graph_store.py` | **FIXED** | `sanitize_label()` validates alphanumeric pattern |
| **Relationship type injection** | `graph_store.py` | **FIXED** | `sanitize_relations()` rejects dangerous characters |

### High - Resource Exhaustion (FIXED)

| Vulnerability | File | Status | Fix |
|--------------|------|--------|-----|
| **No file size limit** | `main.py` | **FIXED** | `validate_upload_size()` checks Content-Length header |
| **Content-Length mismatch** | `main.py` | **FIXED** | Chunked reading enforces actual size limit |

### Medium - Data Integrity

| Vulnerability | File | Test | Fix Required |
|--------------|------|------|--------------|
| **EnrichmentQueueItem lacks error field** | `metadata_store.py` | `test_orphan_creation.py` | Add `error_message` column |
| **Timing attack on auth** | `security.py` | `test_security.py` | Use constant-time comparison |

### Medium - Infrastructure Security (FIXED)

| Vulnerability | File | Status | Fix |
|--------------|------|--------|-----|
| **Passwords in env vars** | `docker-compose.yml` | **FIXED** | Docker secrets at `/run/secrets/` |
| **API keys in docker inspect** | `docker-compose.yml` | **FIXED** | Secrets mounted as files |

See `docker/docker-compose.yml` for Docker secrets configuration.
Secrets files are stored in `secrets/` directory (gitignored).

### Recommended Fixes Priority

1. ~~**Immediate**: Path traversal, file size limits (DoS vectors)~~ **DONE**
2. ~~**Before beta**: State machine validation, race conditions, Cypher injection~~ **DONE**
3. ~~**Before production**: Prompt injection hardening, Docker secrets~~ **DONE**

**Remaining items (Low priority):**
- Timing attack on auth (constant-time comparison)
- EnrichmentQueueItem error field

### Running Only Passing Tests

```bash
# Skip xfail tests to see only real failures
pytest tests/unit/ tests/adversarial/ --ignore-glob="*xfail*" -v

# Run xfail tests to check if fixes work (strict mode fails if xfail passes)
pytest tests/unit/ tests/adversarial/ --runxfail -v
```
