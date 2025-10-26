# JENEZIS Architecture Documentation

**Project:** JENEZIS - Knowledge Graph System
**Company:** Sigilum EURL
**Author:** Julien DABERT
**Last Updated:** 2025-10-26

## System Versioning

- **v3.3:** Current production (PostgreSQL + SQLite hybrid)
- **Genesis v2.0:** Future universal domain-agnostic system (in development)

## Database Architecture

### Active Schema (Production)
- **File:** `src/db/postgres_models.py` (v1.x)
- **Database:** PostgreSQL 16 with pgvector extension
- **Connection:** Port 5433 (Docker) / 5432 (Local)
- **Main Tables:**
  - `skills` - Canonical skill names
  - `aliases` - Skill variations and mappings
  - `hierarchy` - Parent-child relationships
  - `canonical_entities` - Companies and schools
  - `entity_aliases` - Entity name variations
  - `enrichment_queue` - Async processing queue
  - `async_tasks` - Celery task tracking

### Future Schema (Genesis v2.0)
- **File:** `docs/migration_scripts/genesis_models.py.v2_not_deployed`
- **Status:** Archived for future universal system
- **Design:** Domain-agnostic with configurable node types
- **Tables:**
  - `domain_configs` - Domain configuration
  - `canonical_nodes` - Universal nodes (replaces skills + entities)
  - `node_aliases` - Universal aliases
  - `node_relationships` - Flexible relationships

## Service Architecture

### Core APIs

1. **Harmonizer API** (Port 8000)
   - Entry: `src/api/main.py`
   - Purpose: Skill normalization and canonicalization
   - Features: In-memory caching, LLM suggestions
   - Endpoints: `/harmonize`, `/suggest`, `/stats`, `/health`, `/admin/reload`

2. **Entity Resolver API** (Port 8001)
   - Entry: `src/entity_resolver/api.py`
   - Purpose: Company/school name resolution
   - Features: Fuzzy matching, auto-enrichment queue
   - Endpoints: `/resolve`, `/stats`, `/enrichment/queue`, `/admin/add_entity`

### Background Services

- **Celery Workers**
  - Broker: Redis (port 6379)
  - Tasks: `src/tasks/enrichment.py`, `src/tasks/suggestions.py`
  - Processing: LLM enrichment, Wikipedia enrichment

- **Docker Services**
  - `jenezis-postgres`: PostgreSQL database
  - `jenezis-redis`: Redis cache/broker
  - `jenezis-harmonizer-api`: Harmonizer service
  - `jenezis-entity-resolver-api`: Entity resolver service
  - `jenezis-nginx`: Reverse proxy (production profile)
  - `jenezis-prometheus`: Metrics collection (monitoring profile)
  - `jenezis-grafana`: Dashboards (monitoring profile)

## Domain Configuration

### Extensible YAML System
- Location: `domains/`
- Active: `it_skills.yaml`, `medical_diagnostics.yaml`, `product_catalog.yaml`
- Loader: `src/domain/config_loader.py`
- Features: Jinja2 templates, validation rules, LLM prompts

## Data Pipeline

### CV to Knowledge Graph
1. Parse CV JSON (example: `data/examples/cv_example.json`)
2. Call Harmonizer API → Canonical skills
3. Call Entity Resolver API → Canonical entities
4. Generate Cypher queries → `data/output/cypher_queries.txt`
5. Load to Neo4j (`cypher-shell < data/output/cypher_queries.txt`)

### Enrichment Pipeline
1. Identify unmapped items (`analyze_unmapped.py`)
2. LLM enrichment (`densify_ontology.py`)
3. Human review (`export_human_review.py`)
4. Import approved (`import_approved.py`)
5. Reload cache (`/admin/reload`)

## Performance Optimizations

### Caching Strategy
- In-memory caches loaded at startup
- Zero-downtime reload via `/admin/reload`
- 95%+ cache hit rate

### Database Optimizations
- Connection pooling: 20 base + 40 overflow
- WAL mode for SQLite (legacy)
- 9 indexes on ontology tables
- 10 indexes on entity tables
- pgvector for semantic search

### API Performance
- Harmonizer: <10ms for cached skills
- Entity Resolver: <5ms for cached entities
- LLM enrichment: ~2s per skill
- Batch processing: ~100 skills in 5-6 minutes

## Security Measures

- Bearer token authentication (`API_AUTH_TOKEN`)
- Environment variables for credentials
- CORS whitelist configuration
- SQL injection protection
- Non-root Docker containers
- Rate limiting via nginx

## Testing Infrastructure

### Test Categories
- Unit tests: `@pytest.mark.unit`
- Integration tests: `@pytest.mark.integration`
- API tests: `@pytest.mark.api`
- Coverage target: 80%+

### Quality Tools
- Black (formatting)
- Ruff (linting)
- MyPy (type checking)
- Bandit (security)
- Pre-commit hooks

## Migration Status

### Completed
- SQLite → PostgreSQL migration
- Docker containerization
- Redis/Celery integration
- Prometheus metrics

### In Progress
- Genesis v2.0 universal schema
- Domain-agnostic architecture
- Multi-tenancy support

### Future
- GraphQL API
- Neo4j GDS integration
- ML-based matching
- Real-time synchronization

## Deployment

### Local Development
```bash
docker-compose up -d postgres redis
poetry run uvicorn src.api.main:app --reload
```

### Production
```bash
docker-compose --profile production up -d
```

### Monitoring
```bash
docker-compose --profile monitoring up -d
```

## Contact

- **Project:** JENEZIS
- **Company:** Sigilum EURL
- **Author:** Julien DABERT
- **Email:** jdabert@sigilum.fr