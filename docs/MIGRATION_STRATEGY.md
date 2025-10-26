# Migration Strategy: JENEZIS → Ontology Genesis Engine

**Document Version:** 1.0
**Date:** 2025-10-25
**Status:** 🔥 **CRITICAL - ARCHITECTURAL PIVOT**

---

## Executive Summary

This document outlines the strategy to transform JENEZIS (domain-specific IT skills ontology) into the **Ontology Genesis Engine** (universal, domain-agnostic ontology framework).

**The Problem:** Current system is hardcoded for IT skills. Cannot be reused for product catalogs, medical diagnostics, or any other domain without complete rewrite.

**The Solution:** Generic node/relationship architecture with domain-driven configuration files.

**Timeline:** Phased migration over 4-6 weeks, maintaining backward compatibility during transition.

---

## Phase 1: Foundation (Week 1-2)

### ✅ Completed
- [x] Design universal domain configuration schema (`domain_config_schema.yaml`)
- [x] Create 3 reference domain configurations (IT Skills, Product Catalog, Medical Diagnostics)
- [x] New PostgreSQL schema (`genesis_models.py`):
  - `domain_configs` table
  - `canonical_nodes` table (replaces `skills` + `canonical_entities`)
  - `node_aliases` table (replaces `aliases` + `entity_aliases`)
  - `node_relationships` table (replaces `hierarchy`)
  - `enrichment_queue` (domain-aware)
  - `human_validations` (replaces CSV workflow)
- [x] Domain configuration loader with Jinja2 prompt templating
- [x] Add dependencies: `pyyaml`, `jinja2`

### 🔨 TODO
- [ ] **Alembic Migration Script:**
  - Create new tables (`domain_configs`, `canonical_nodes`, etc.)
  - Migrate existing `skills` → `canonical_nodes` (domain_id='it_skills', node_type='skill')
  - Migrate existing `aliases` → `node_aliases`
  - Migrate existing `hierarchy` → `node_relationships` (relationship_type='is_subtype_of')
  - Insert default domain config for IT Skills
  - ⚠️ **Critical:** Preserve all existing data (329 skills, 1,678 aliases, 844 relations)

- [ ] **Database Migration Script:**
  ```bash
  poetry run alembic revision --autogenerate -m "genesis_architecture_v2"
  poetry run alembic upgrade head
  ```

- [ ] **Validation:**
  - Run test suite against migrated database
  - Verify data integrity (counts match legacy)
  - Test backward compatibility with existing API

---

## Phase 2: API Transformation (Week 2-3)

### Goal
Transform FastAPI services to support domain-driven architecture.

### Changes Required

#### 2.1 Harmonizer API (`src/api/main.py`)

**Current State:**
- Hardcoded `ALIAS_CACHE`, `SKILLS_CACHE`, `HIERARCHY_CACHE`
- Endpoints: `/harmonize`, `/suggest`, `/stats`

**Target State:**
- Load domain config from `DOMAIN_CONFIG_PATH` environment variable
- Generic cache: `NODE_CACHE`, `ALIAS_CACHE`, `RELATIONSHIP_CACHE`
- Domain-aware endpoints:
  - `/harmonize` → `/nodes/harmonize` (generic term)
  - `/suggest` → `/nodes/suggest`
  - `/stats` → `/domain/stats`
- Multi-domain support (future): `/api/{domain_id}/nodes/harmonize`

**Implementation:**
```python
# src/api/genesis_main.py (new file)
from domain import DomainConfigManager

config_manager = DomainConfigManager.from_env("DOMAIN_CONFIG_PATH")
domain_config = config_manager.get_domain(...)  # Load active domain

@app.on_event("startup")
def startup_event():
    load_node_cache(domain_config.metadata.domain_id)

@app.post("/nodes/harmonize")
def harmonize_nodes(request: HarmonizationRequest):
    # Generic harmonization using domain-aware cache
    ...
```

**Migration Strategy:**
1. Create `genesis_main.py` alongside `main.py`
2. Implement all endpoints with domain support
3. Add feature flag: `USE_GENESIS_API=true` in `.env`
4. Run both APIs in parallel during transition
5. Switch default to Genesis API
6. Deprecate `main.py` after 2 weeks

#### 2.2 Entity Resolver API (`src/entity_resolver/api.py`)

**Current State:**
- Separate service for companies/schools
- Hardcoded `COMPANY`/`SCHOOL` enum

**Target State:**
- **MERGE** into Genesis API
- Companies/schools become regular node types in domain config
- Same harmonization logic applies

**Action:**
- Deprecate separate entity resolver
- Add company/school node types to IT Skills domain config
- Existing entity resolution endpoints become `/nodes/harmonize` with `node_type` filter

---

## Phase 3: CLI Modernization (Week 3-4)

### Goal
Make all CLI tools domain-agnostic with `--domain-config` parameter.

### Changes Required

#### 3.1 `analyze_unmapped.py` → `analyze_nodes.py`

**Before:**
```bash
poetry run python src/cli/analyze_unmapped.py
# Hardcoded: reads data/candidats_competences.csv
```

**After:**
```bash
poetry run python src/cli/analyze_nodes.py --domain-config domains/it_skills.yaml
# Reads data source from domain config's data_sources section
```

**Implementation:**
```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain-config", required=True, help="Path to domain YAML")
    args = parser.parse_args()

    config = DomainConfigLoader(args.domain_config).load()

    # Get active data sources from config
    for data_source in config.get_active_data_sources():
        if data_source.type == "csv":
            analyze_csv_source(data_source, config)
```

#### 3.2 `densify_ontology.py` → `densify_domain.py`

**Before:**
- Hardcoded prompts from `prompts.py`
- Hardcoded skill/alias/hierarchy logic

**After:**
- Load prompt templates from domain config
- Generic node/alias/relationship logic
- Respect domain validation rules

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain-config", required=True)
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    config = DomainConfigLoader(args.domain_config).load()

    # Render LLM prompt using Jinja2
    prompt = config.get_prompt(
        "densification",
        node_name=unmapped_node,
        existing_nodes_sample=existing_nodes
    )

    # Call LLM with domain-specific prompt
    response = call_llm(prompt, config.llm)
```

#### 3.3 New CLI Tools

**`export_domain.py`:**
```bash
poetry run python src/cli/export_domain.py \
    --domain-config domains/product_catalog.yaml \
    --format cypher \
    --output neo4j_import.txt
```

**`validate_domain.py`:**
```bash
poetry run python src/cli/validate_domain.py domains/medical_diagnostics.yaml
# Validates YAML syntax, schema, and relationships
```

---

## Phase 4: Testing & Documentation (Week 4-5)

### Test Suite Updates

1. **Unit Tests:**
   - Test domain config loader with all 3 example domains
   - Test node/alias/relationship creation
   - Test Jinja2 prompt rendering

2. **Integration Tests:**
   - Full workflow: analyze → densify → validate → export
   - Multi-domain database isolation
   - API backward compatibility

3. **Performance Tests:**
   - Benchmark cache loading for large ontologies
   - Test concurrent domain operations

### Documentation Updates

- [ ] Rewrite `README.md` with new product positioning
- [ ] Update `CLAUDE.md` with Genesis architecture
- [ ] Create `docs/USER_GUIDE.md` for domain creators
- [ ] Create `docs/API_REFERENCE.md` for Genesis API
- [ ] Video walkthrough: "Create Your First Domain in 10 Minutes"

---

## Phase 5: Deprecation & Cleanup (Week 5-6)

### Files to Deprecate

| Old File | Status | Replacement |
|----------|--------|-------------|
| `src/db/postgres_models.py` | Deprecate | `src/db/genesis_models.py` |
| `src/api/main.py` | Deprecate | `src/api/genesis_main.py` |
| `src/entity_resolver/api.py` | Remove | Merged into genesis_main.py |
| `src/cli/prompts.py` | Remove | Domain YAML prompts section |
| `src/graph_ingestion/ingest.py` | Refactor | Domain-driven ingestion |
| `data/candidats_competences.csv` | Move | `domains/it_skills/data/` |

### Cleanup Steps

1. Add deprecation warnings to old endpoints
2. Update all internal imports to use genesis modules
3. Remove hardcoded domain logic
4. Archive legacy code in `legacy/` directory

---

## Risk Mitigation

### Backward Compatibility

**Strategy:** Dual-mode operation during transition.

```python
# src/api/compatibility_layer.py
if os.getenv("USE_LEGACY_API", "false") == "true":
    from api.main import app as legacy_app
else:
    from api.genesis_main import app
```

### Data Loss Prevention

- **Full database backup before migration**
- **Parallel databases during testing:** `jenezis` (legacy) + `jenezis_genesis` (new)
- **Data validation scripts:** Compare counts and relationships
- **Rollback procedure documented**

### User Communication

- **Changelog:** Detailed changes for each release
- **Migration guide:** Step-by-step instructions for existing users
- **Support window:** 30 days of dual API support

---

## Success Criteria

### Functional Requirements
- [ ] All 3 example domains load and validate successfully
- [ ] IT Skills domain produces identical results to legacy system
- [ ] Full workflow (analyze → enrich → validate → export) works for each domain
- [ ] API endpoints respond <100ms for cached queries

### Data Integrity
- [ ] Zero data loss during migration
- [ ] All existing skills/aliases/hierarchy preserved
- [ ] New system produces byte-identical Neo4j Cypher output for test CV

### Performance
- [ ] Cache load time <5 seconds for 10K nodes
- [ ] LLM enrichment throughput ≥15 nodes/minute
- [ ] Database query performance maintained or improved

### User Experience
- [ ] Domain creation tutorial <10 minutes
- [ ] Clear error messages for invalid configs
- [ ] Web UI supports domain selection dropdown

---

## Post-Migration Roadmap

### Q1 2026: Ecosystem Expansion
- Public domain registry (community-contributed configs)
- Domain versioning and compatibility checks
- Import/export between domain formats (GraphML, RDF, OWL)

### Q2 2026: Intelligence Layer
- Auto-suggest node types from data samples
- Anomaly detection for ontology quality
- Relationship inference using graph algorithms

### Q3 2026: Enterprise Features
- Multi-tenancy with domain isolation
- Role-based access control per domain
- Audit logging and compliance reporting

---

## Contact & Support

**Migration Lead:** Julien Dabert (jdabert@sigilum.fr)
**Repository:** `JENEZIS` (private)
**Slack Channel:** #ontology-genesis-migration
**Office Hours:** Tuesdays 2-4 PM CET

---

*This is a living document. Update after each phase completion.*
*Last Updated: 2025-10-25 by Claude (AI Assistant)*
