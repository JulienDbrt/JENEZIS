# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**JENEZIS** - Knowledge Graph System by **Sigilum EURL**
**Created by Julien DABERT**

JENEZIS is a comprehensive Knowledge Graph system for talent intelligence that harmonizes skills, resolves entities (companies/schools), and ingests CV data into Neo4j. It consists of multiple FastAPI services, CLI tools, and a robust enrichment pipeline.

**Key Metrics:**
- 329 canonical skills + 1,678 aliases
- 30 companies + 13 schools in entity resolver
- PostgreSQL with pgvector for embeddings
- Redis/Celery for async task processing

## Development Commands

### Setup & Installation

```bash
# Install dependencies
poetry install --with dev

# Setup pre-commit hooks
poetry run pre-commit install

# Environment configuration
cp .env.example .env
# Edit .env with your credentials
```

### Running Services

```bash
# Development mode (with hot reload)
poetry run uvicorn src.api.main:app --reload --port 8000  # Harmonizer API
poetry run uvicorn src.entity_resolver.api:app --reload --port 8001  # Entity Resolver

# Production mode with Docker
docker-compose up -d  # Development profile
docker-compose --profile production --profile monitoring up -d  # Full production

# Background tasks (Celery)
poetry run celery -A src.celery_app worker --loglevel=info
```

### Database Management

```bash
# PostgreSQL migrations (production path)
poetry run alembic upgrade head  # Apply migrations
poetry run alembic revision --autogenerate -m "description"  # Create new migration

# SQLite mode (development/legacy)
poetry run python src/db/database.py  # Initialize SQLite databases
poetry run python src/db/optimize_indexes.py  # Optimize indexes

# Database validation
poetry run python scripts/validate_migration.py --database jenezis_genesis_test
```

### Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test categories
poetry run pytest -m unit  # Unit tests only
poetry run pytest -m integration  # Integration tests
poetry run pytest -m api  # API tests

# Run single test file
poetry run pytest tests/unit/test_harmonizer_api.py -v

# Run pre-commit checks
poetry run pre-commit run --all-files
```

### Code Quality

```bash
# Format code
poetry run black src/ tests/

# Lint code
poetry run ruff check src/ tests/

# Type checking
poetry run mypy src/

# Security scan
poetry run bandit -r src/
```

### CLI Tools

```bash
# Skill enrichment pipeline
poetry run python src/cli/analyze_unmapped.py  # Analyze unmapped skills
poetry run python src/cli/densify_ontology.py 100  # Enrich 100 skills
poetry run python src/cli/mass_densify.py --auto  # NIGHT BEAST mode
poetry run python src/cli/export_human_review.py  # Export for validation
poetry run python src/cli/import_approved.py  # Import validated skills

# Entity enrichment
poetry run python src/enrichment/wikipedia_enricher.py  # Auto-enrich entities
poetry run python src/cli/export_entity_review.py  # Export entities for review

# Graph ingestion
poetry run python src/graph_ingestion/ingest.py  # Process CV to Cypher
```

## Architecture Overview

### Service Architecture

The system uses a microservices architecture with two main APIs:

1. **Harmonizer API (port 8000)**: Normalizes skill names to canonical forms
   - Uses in-memory caching for performance (<10ms latency)
   - Supports LLM-based suggestions via OpenAI
   - Entry point: `src/api/main.py`

2. **Entity Resolver API (port 8001)**: Resolves company/school names
   - Auto-queues unknown entities for enrichment
   - Fuzzy matching with alias support
   - Entry point: `src/entity_resolver/api.py`

### Database Strategy

**PostgreSQL Mode (Production)**:
- Models: `src/db/postgres_models.py`
- Connection pooling: `src/db/postgres_connection.py`
- pgvector extension for semantic search
- Alembic migrations in `alembic/`

**SQLite Mode (Development/Legacy)**:
- Schema: `src/db/database.py`
- Two databases: `ontology.db` and `entity_resolver.db`
- WAL mode with optimized indexes

### Background Processing

Uses Celery with Redis broker for async tasks:
- LLM enrichment: `src/tasks/enrichment.py`
- Suggestion pre-computation: `src/tasks/suggestions.py`
- Wikipedia enrichment: `src/enrichment/wikipedia_enricher.py`

### Domain Configuration

YAML-based extensible domain system in `domains/`:
- `it_skills.yaml` - IT/Software skills
- `medical_diagnostics.yaml` - Medical domain
- `product_catalog.yaml` - Product catalog

Loader: `src/domain/config_loader.py`

### Graph Pipeline

CV → Neo4j ingestion flow:
1. Parse CV JSON (example: `data/examples/cv_example.json`)
2. Call Harmonizer API for skill canonicalization
3. Call Entity Resolver API for company/school normalization
4. Generate Cypher queries (output: `data/output/cypher_queries.txt`)
5. Load into Neo4j: `cypher-shell < data/output/cypher_queries.txt`

## Important Patterns

### Cache-First Architecture
- All APIs load caches at startup for performance
- Use `/admin/reload` endpoint for zero-downtime cache refresh
- Reduces database hits by 95%+

### Two-Phase Enrichment
1. **Automatic**: LLM (OpenAI) or Wikipedia API enrichment
2. **Human Review**: CSV export → manual validation → import

### Error Handling
- Graceful degradation (fallback to string similarity if LLM fails)
- Automatic canonical ID generation for unknown entities
- Comprehensive health checks on all services

### Security
- Bearer token authentication for admin endpoints
- Environment variables for all credentials (no hardcoding)
- CORS whitelist configuration
- SQL injection protection via parameterized queries

## Key Files & Directories

```
src/
├── api/main.py              # Harmonizer API
├── entity_resolver/api.py   # Entity Resolver API
├── db/                      # Database models & connections
├── graph_ingestion/         # CV → Neo4j pipeline
├── cli/                     # CLI enrichment tools
├── tasks/                   # Celery async tasks
├── enrichment/              # Wikipedia enricher
└── domain/                  # Domain configuration loader

data/
├── databases/               # SQLite DB files
│   ├── ontology.db         # Skills ontology
│   └── entity_resolver.db  # Companies/schools
└── output/                  # Generated exports

domains/                     # YAML domain configs
tests/unit/                  # 308+ test files
```

## Environment Variables

Required in `.env`:
```bash
# OpenAI (required for LLM features)
OPENAI_API_KEY=sk-...

# PostgreSQL (production) - JENEZIS database
DATABASE_URL=postgresql://jenezis:jenezis@localhost:5433/jenezis

# Redis (for Celery)
REDIS_URL=redis://localhost:6379/0

# API Security
API_AUTH_TOKEN=your-secure-token

# Neo4j (for graph ingestion)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

## Common Workflows

### Adding New Skills to Ontology
1. Run `analyze_unmapped.py` to identify missing skills
2. Use `densify_ontology.py N` to enrich N skills via LLM
3. Review `needs_human_review.csv` and mark approvals
4. Import with `import_approved.py`
5. Reload API cache: `curl -X POST localhost:8000/admin/reload`

### Processing New CVs
1. Place CV JSON in expected format (see `data/examples/cv_example.json`)
2. Run `python src/graph_ingestion/ingest.py`
3. Load generated Cypher into Neo4j from `data/output/cypher_queries.txt`
4. Unknown entities automatically queued for enrichment

### Monitoring & Debugging
- Health checks: `GET /health` on both APIs
- Metrics: `GET /metrics` (Prometheus format)
- Logs: Docker containers write to `/app/logs/`
- Database stats: `GET /stats` on both APIs

## Testing Philosophy

- **Always** write tests for new features
- Use pytest markers (`@pytest.mark.unit`, `@pytest.mark.integration`)
- Mock external services (OpenAI, Wikipedia) in tests
- Target 80%+ code coverage
- Pre-commit hooks enforce code quality

## Performance Considerations

- Harmonizer API: <10ms latency for cached skills
- Batch processing: ~100 skills in 5-6 minutes via LLM
- Connection pooling: 20 base + 40 overflow connections
- Database indexes: 9 on ontology.db, 10 on entity_resolver.db
- Use WAL mode for SQLite databases



## Docker Services

The project uses Docker Compose for orchestration:

### Containers
- `jenezis-postgres`: PostgreSQL 16 with pgvector extension (port 5433)
- `jenezis-redis`: Redis 7 Alpine (port 6379)
- `jenezis-harmonizer-api`: Harmonizer API service (port 8000)
- `jenezis-entity-resolver-api`: Entity Resolver API service (port 8001)
- `jenezis-nginx`: Nginx reverse proxy (ports 80/443) - production profile
- `jenezis-prometheus`: Prometheus monitoring (port 9090) - monitoring profile
- `jenezis-grafana`: Grafana dashboards (port 3001) - monitoring profile

### Quick Start with Docker
```bash
# Start core services (PostgreSQL + Redis)
docker-compose up -d postgres redis

# Start all API services
docker-compose up -d

# Start with production profile (includes nginx)
docker-compose --profile production up -d

# Start with monitoring (includes Prometheus + Grafana)
docker-compose --profile monitoring up -d

# View logs
docker-compose logs -f harmonizer-api

# Stop all services
docker-compose down

# Stop and remove volumes (fresh start)
docker-compose down -v
```

## Project Information

- **Project**: JENEZIS
- **Company**: Sigilum EURL
- **Author**: Julien DABERT
- **Contact**: jdabert@sigilum.fr
- **Documentation**: This file (CLAUDE.md)
- **Architecture**: Microservices with Knowledge Graph

## Project Structure (Post-Cleanup)

### Key Documentation
- `README.md` - Main project documentation
- `CLAUDE.md` - This file, guidance for Claude Code
- `docs/ARCHITECTURE.md` - System architecture details
- `docs/AUDIT_COMPLET.md` - Latest audit report
- `docs/CLEANUP_CHECKLIST.md` - Maintenance checklist
- `docs/migration_scripts/` - Archived migration scripts

### Active Database Schema
- Production uses `src/db/postgres_models.py` (v1.x)
- Genesis v2.0 schema archived in `docs/migration_scripts/genesis_models.py.v2_not_deployed`
- Migrations managed by Alembic

### Recent Cleanup (2025-10-26)
- Removed obsolete files (COUNTDOWN.md, README_GENESIS.md, erwin-harmonizer.conf)
- Consolidated duplicate tests (_refactored versions kept)
- Archived unused migration scripts
- Updated all references from Erwin to JENEZIS
- Added PostgreSQL datasource for Grafana