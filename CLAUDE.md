# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DoubleHelixGraphRAG is a neuro-symbolic GraphRAG framework implementing the "Jenezis" architecture. It combines a **Canonical Store** (PostgreSQL+pgvector for source of truth) with a **Projection Graph** (Neo4j for reasoning) orchestrated by LLM-driven extraction and resolution.

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
pytest tests/unit/ tests/adversarial/ --cov=doublehelix --cov-fail-under=80

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
bandit -r doublehelix/ -ll -ii

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
poetry run uvicorn examples.fastapi_app.main:app --reload
poetry run celery -A examples.fastapi_app.celery_config worker --loglevel=INFO
```

## Architecture

### Neuro-Symbolic Pipeline ("Harmonizer")
The ingestion flow in `doublehelix/ingestion/`:
1. **Parser** (`parser.py`) → **Chunker** (`chunker.py`) → **Embedder** (`embedder.py`)
2. **Extractor** (`extractor.py`): LLM extracts entities/relations constrained by `DomainConfig` ontology
3. **Validator** (`validator.py`): Filters extracted data against ontology rules
4. **Resolver** (`resolver.py`): Maps entities to canonical store (exact match → vector similarity → enrichment queue)

### Data Stores
- **PostgreSQL+pgvector** (`doublehelix/storage/metadata_store.py`): Canonical nodes, aliases, domain configs, documents, API keys, enrichment queue
- **Neo4j** (`doublehelix/storage/graph_store.py`): Projection graph with Document→Chunk→Entity relationships, uses APOC for dynamic labels
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

### RAG Pipeline (`doublehelix/rag/`)
- **Retriever** (`retriever.py`): Hybrid search combining vector similarity with LLM-planned Cypher queries, fused via Reciprocal Rank Fusion
- **Generator** (`generator.py`): Streaming LLM responses with source citations

### API Endpoints (`examples/fastapi_app/main.py`)
- `POST /ontologies`: Create domain config
- `POST /upload?ontology_id=N`: Ingest document
- `POST /query`: RAG query with streaming response
- `GET /status/{job_id}`: Check ingestion status

## Configuration

All settings in `doublehelix/core/config.py` via Pydantic Settings. Key env vars:
- `LLM_PROVIDER`: "openai" | "anthropic" | "openrouter"
- `EXTRACTION_MODEL`: Model for entity extraction (default: gpt-3.5-turbo)
- `GENERATOR_MODEL`: Model for RAG generation (default: gpt-4-turbo)
- `ENTITY_RESOLUTION_THRESHOLD`: Fuzzy matching score 0-100

## Dependencies

Neo4j requires the Enterprise edition with APOC plugin for dynamic label/relationship creation. See `docker/docker-compose.yml` for full stack configuration.

## Known Vulnerabilities (xfail tests)

The adversarial test suite documents security vulnerabilities that are marked `xfail` (expected failure) to allow CI to pass while tracking issues. **These MUST be fixed before production deployment.**

### Critical - Input Validation

| Vulnerability | File | Test | Fix Required |
|--------------|------|------|--------------|
| **Path Traversal in S3 keys** | `main.py:138` | `test_path_traversal.py` | Sanitize filenames before S3 path construction |
| **Null byte injection** | `main.py:138` | `test_path_traversal.py` | Strip null bytes from filenames |
| **Protocol injection** | `main.py:138` | `test_path_traversal.py` | Block `s3://`, `file://`, `http://` in filenames |
| **URL-encoded traversal** | `main.py:138` | `test_path_traversal.py` | Decode and validate after URL decoding |

### Critical - Prompt Injection

| Vulnerability | File | Test | Fix Required |
|--------------|------|------|--------------|
| **Ontology schema injection** | `extractor.py` | `test_prompt_injection.py` | Sanitize entity/relation types in prompts |
| **Retriever query injection** | `retriever.py` | `test_prompt_injection.py` | Sandbox LLM query planner output |
| **Generator context injection** | `generator.py` | `test_prompt_injection.py` | Filter dangerous patterns from context |

### High - State Management

| Vulnerability | File | Test | Fix Required |
|--------------|------|------|--------------|
| **Invalid status transitions** | `metadata_store.py:107` | `test_state_machine_violations.py` | Add state machine validation to `update_document_status()` |
| **Missing error_message for FAILED** | `metadata_store.py` | `test_state_machine_violations.py` | Require error_message when status=FAILED |
| **Race condition in canonical nodes** | `resolver.py` | `test_race_conditions.py` | Use `INSERT ... ON CONFLICT` or distributed lock |

### High - Resource Exhaustion

| Vulnerability | File | Test | Fix Required |
|--------------|------|------|--------------|
| **No file size limit** | `main.py:129` | `test_file_upload_dos.py` | Check Content-Length before `await file.read()` |
| **Content-Length mismatch** | `main.py:129` | `test_file_upload_dos.py` | Validate actual vs claimed size |

### Medium - Data Integrity

| Vulnerability | File | Test | Fix Required |
|--------------|------|------|--------------|
| **EnrichmentQueueItem lacks error field** | `metadata_store.py` | `test_orphan_creation.py` | Add `error_message` column |
| **Timing attack on auth** | `security.py` | `test_security.py` | Use constant-time comparison |

### Recommended Fixes Priority

1. **Immediate**: Path traversal, file size limits (DoS vectors)
2. **Before beta**: State machine validation, race conditions
3. **Before production**: Prompt injection hardening, timing attacks

### Running Only Passing Tests

```bash
# Skip xfail tests to see only real failures
pytest tests/unit/ tests/adversarial/ --ignore-glob="*xfail*" -v

# Run xfail tests to check if fixes work (strict mode fails if xfail passes)
pytest tests/unit/ tests/adversarial/ --runxfail -v
```
