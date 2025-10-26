# ORDRE D'EXÉCUTION 48 HEURES - JENEZIS GENESIS v2.0

**Mission:** Transformer JENEZIS en Ontology Genesis Engine opérationnel.
**Deadline:** 48 heures à partir de MAINTENANT.
**Status:** 🔥 **OPÉRATION ACTIVE**

---

## HEURE 0-4: MIGRATION DATABASE (CRITIQUE)

### H+0:00 - Backup Complet

```bash
# 1. Backup PostgreSQL
pg_dump -U jenezis -d jenezis > backups/pre_genesis_$(date +%Y%m%d_%H%M%S).sql

# 2. Backup SQLite (legacy)
cp data/databases/ontology.db backups/ontology_pre_genesis_$(date +%Y%m%d_%H%M%S).db

# 3. Snapshot Docker volume (si applicable)
docker-compose stop postgres
docker run --rm -v jenezis_postgres_data:/source -v $(pwd)/backups:/backup \
    alpine tar czf /backup/postgres_volume_$(date +%Y%m%d_%H%M%S).tar.gz -C /source .
docker-compose start postgres
```

**Checkpoint:** Backups vérifiés et datés.

---

### H+0:30 - Test Migration sur DB Clone

```bash
# 1. Créer une DB de test
createdb -U jenezis jenezis_genesis_test

# 2. Restaurer le backup dedans
psql -U jenezis -d jenezis_genesis_test < backups/pre_genesis_*.sql

# 3. Lancer la migration sur la DB test
export DATABASE_URL="postgresql://jenezis:jenezis@localhost:5433/jenezis_genesis_test"
poetry run alembic upgrade head

# 4. Vérifier l'intégrité
poetry run python scripts/validate_migration.py --database jenezis_genesis_test
```

**Checkpoint:** Migration test réussie, counts validés.

---

### H+1:30 - Migration Production

**⚠️ POINT DE NON-RETOUR ⚠️**

```bash
# 1. Arrêter l'API (si en production)
docker-compose stop api celery_worker

# 2. Lancer migration production
export DATABASE_URL="postgresql://jenezis:jenezis@localhost:5433/jenezis_harmonizer"
poetry run alembic upgrade head

# 3. Validation immédiate
poetry run python scripts/validate_migration.py

# Expected output:
# ✅ domain_configs: 1 row (it_skills)
# ✅ canonical_nodes: 329 rows (migrated from skills)
# ✅ node_aliases: 1,678 rows (migrated from aliases)
# ✅ node_relationships: 844 rows (migrated from hierarchy)
# ✅ Data integrity: 100%
```

**Checkpoint:** Production migrée, données validées, rollback disponible.

---

### H+2:00 - Tests API Legacy

```bash
# 1. Restart API (legacy mode)
export USE_GENESIS_API=false
poetry run uvicorn src.api.main:app --reload --port 8000 &

# 2. Test endpoints critiques
curl http://localhost:8000/stats
# Expected: {"total_skills": 329, "total_aliases": 1678, "total_relations": 844}

curl -X POST http://localhost:8000/harmonize \
  -H "Content-Type: application/json" \
  -d '{"skills": ["python", "javascript", "react"]}'
# Expected: All 3 skills mapped correctly

# 3. Kill test server
kill %1
```

**Checkpoint:** API legacy fonctionne avec nouveau schema.

---

## HEURE 4-12: GENESIS API (CONSTRUCTION)

### H+4:00 - Créer genesis_main.py

```bash
# Fichier: src/api/genesis_main.py
# Voir template ci-dessous
```

**Implémentation critique:**

```python
# src/api/genesis_main.py
from fastapi import FastAPI, Depends, HTTPException
from domain import DomainConfigManager
from db.genesis_models import CanonicalNode, NodeAlias, NodeRelationship
import os

app = FastAPI(title="JENEZIS Genesis API v2.0")

# Load domain from environment
config_manager = DomainConfigManager.from_env("DOMAIN_CONFIG_PATH")
current_domain = None

@app.on_event("startup")
def startup_event():
    global current_domain
    domain_path = os.getenv("DOMAIN_CONFIG_PATH", "domains/it_skills.yaml")
    current_domain = config_manager.load_domain(domain_path)
    print(f"✅ Loaded domain: {current_domain.metadata.name}")
    load_cache(current_domain.metadata.domain_id)

@app.post("/nodes/harmonize")
def harmonize_nodes(request: HarmonizationRequest):
    # Use domain-aware cache
    results = []
    for node_name in request.nodes:
        canonical = NODE_CACHE.get((current_domain.metadata.domain_id, node_name.lower()))
        if canonical:
            results.append({
                "original": node_name,
                "canonical": canonical["name"],
                "node_type": canonical["type"],
                "is_known": True
            })
        else:
            results.append({
                "original": node_name,
                "canonical": node_name.lower(),
                "node_type": "unknown",
                "is_known": False
            })
    return {"results": results}

# ... autres endpoints
```

**Checkpoint:** Genesis API démarre sans erreur.

---

### H+6:00 - Tests Multi-Domaines

```bash
# 1. Test domain IT Skills
export DOMAIN_CONFIG_PATH=domains/it_skills.yaml
poetry run uvicorn src.api.genesis_main:app --reload --port 8001 &
sleep 5

curl http://localhost:8001/domain/stats
# Expected: {"domain_id": "it_skills", "nodes": 329, ...}

kill %1

# 2. Test domain Product Catalog
export DOMAIN_CONFIG_PATH=domains/product_catalog.yaml
poetry run uvicorn src.api.genesis_main:app --reload --port 8001 &
sleep 5

curl http://localhost:8001/domain/stats
# Expected: {"domain_id": "product_catalog", "nodes": 0, ...}

kill %1
```

**Checkpoint:** API change de domaine dynamiquement.

---

### H+8:00 - Refactor CLI Tools

```bash
# 1. Créer analyze_nodes.py (remplace analyze_unmapped.py)
# Voir template ci-dessous

# 2. Créer densify_domain.py (remplace densify_ontology.py)
# Voir template ci-dessous

# 3. Tests
poetry run python src/cli/analyze_nodes.py --domain-config domains/it_skills.yaml
poetry run python src/cli/densify_domain.py --domain-config domains/it_skills.yaml --batch-size 5
```

**Checkpoint:** CLI tools fonctionnent avec domain configs.

---

## HEURE 12-24: PROOF OF CONCEPT (VALIDATION)

### H+12:00 - Scénario 1: IT Skills (Existant)

```bash
# 1. Analyser data existante
export DOMAIN_CONFIG_PATH=domains/it_skills.yaml
poetry run python src/cli/analyze_nodes.py --domain-config $DOMAIN_CONFIG_PATH

# Expected output:
# Domain: IT Skills & Competencies Ontology
# Data source: data/candidats_competences.csv
# Total raw nodes: 623,029
# Unique nodes: 87,793
# Already mapped: 87,124 (99.2%)
# Unmapped: 669 (0.8%)

# 2. Enrichir 10 nouveaux skills
poetry run python src/cli/densify_domain.py \
    --domain-config $DOMAIN_CONFIG_PATH \
    --batch-size 10

# Expected: 6-8 auto-approved, 2-4 queued for validation
```

**Checkpoint:** IT Skills domain operational.

---

### H+14:00 - Scénario 2: Product Catalog (Nouveau)

```bash
# 1. Créer données de test
cat > data/test_products.csv << EOF
product_name
iPhone 14 Pro Max
Apple iPhone14ProMax
i phone 14 pro max
Samsung Galaxy S23
Galaxy S23 Ultra Samsung
USB-C Cable 2m
USB-C charging cable
USBC cable 2 meters
EOF

# 2. Configurer data source
# Éditer domains/product_catalog.yaml:
# data_sources:
#   - name: "test_products"
#     type: "csv"
#     path: "data/test_products.csv"
#     enabled: true

# 3. Analyser
export DOMAIN_CONFIG_PATH=domains/product_catalog.yaml
poetry run python src/cli/analyze_nodes.py --domain-config $DOMAIN_CONFIG_PATH

# Expected: 8 raw products, ~3-4 unique after dedup

# 4. Enrichir
poetry run python src/cli/densify_domain.py \
    --domain-config $DOMAIN_CONFIG_PATH \
    --batch-size 10

# Expected:
# - "iphone_14_pro_max" canonical node
# - 3 aliases: ["iphone 14 pro max", "apple iphone14promax", "i phone 14 pro max"]
# - relationship: belongs_to_category → "smartphones"
```

**Checkpoint:** Product catalog domain créé from scratch en <1h.

---

### H+18:00 - Scénario 3: API Multi-Domain

```bash
# 1. Démarrer instance IT Skills
export DOMAIN_CONFIG_PATH=domains/it_skills.yaml
poetry run uvicorn src.api.genesis_main:app --port 8001 &

# 2. Démarrer instance Product Catalog (autre port)
export DOMAIN_CONFIG_PATH=domains/product_catalog.yaml
poetry run uvicorn src.api.genesis_main:app --port 8002 &

# 3. Tester les 2 en parallèle
curl http://localhost:8001/nodes/harmonize \
  -H "Content-Type: application/json" \
  -d '{"nodes": ["python", "react"]}'

curl http://localhost:8002/nodes/harmonize \
  -H "Content-Type: application/json" \
  -d '{"nodes": ["iPhone 14", "Galaxy S23"]}'

# Both should work independently

# 4. Kill servers
killall uvicorn
```

**Checkpoint:** Multi-domain confirmed operational.

---

## HEURE 24-36: DOCUMENTATION & DÉMO

### H+24:00 - Vidéo Proof of Concept

**Script vidéo (5 minutes):**

1. **Intro (30s):** "JENEZIS: Du chaos au graphe en 24h. Regardez."

2. **Démo IT Skills (2min):**
   - Montrer `data/candidats_competences.csv` (623K lignes)
   - Lancer analyze_nodes.py → 87,793 unique skills
   - Lancer densify_domain.py --batch-size 20
   - Montrer LLM en action (logs en temps réel)
   - Résultat: 15 skills canoniques créés en 2 minutes

3. **Démo Product Catalog (2min):**
   - Créer `test_products.csv` (8 lignes de chaos)
   - Éditer `product_catalog.yaml` (10 secondes)
   - Lancer densify → 3 produits canoniques + hiérarchie
   - Export Neo4j: montrer les requêtes Cypher générées

4. **Outro (30s):** "Même code. Domaines différents. Configuration = superpouvoir."

**Checkpoint:** Vidéo enregistrée, uploadée sur Loom/YouTube.

---

### H+28:00 - README Final

```bash
# 1. Remplacer README.md par README_GENESIS.md
mv README.md README_LEGACY.md
mv README_GENESIS.md README.md

# 2. Ajouter badges
# - Build status
# - Test coverage
# - License

# 3. Screenshots
# - API docs (http://localhost:8000/docs)
# - Domain config YAML
# - CLI output

# 4. Quick start video embed
```

**Checkpoint:** README production-ready.

---

## HEURE 36-48: DÉPLOIEMENT & VALIDATION

### H+36:00 - Docker Compose Multi-Domain

```yaml
# docker-compose.yml updates
version: '3.8'

services:
  postgres:
    # ... existing config

  redis:
    # ... existing config

  api-it-skills:
    build: .
    environment:
      DOMAIN_CONFIG_PATH: /app/domains/it_skills.yaml
    ports:
      - "8001:8000"

  api-products:
    build: .
    environment:
      DOMAIN_CONFIG_PATH: /app/domains/product_catalog.yaml
    ports:
      - "8002:8000"

  celery-it-skills:
    build: .
    environment:
      DOMAIN_CONFIG_PATH: /app/domains/it_skills.yaml
    command: celery -A src.celery_app worker
```

```bash
# Test deployment
docker-compose up -d
docker-compose ps  # Should show 5 services running
docker-compose logs -f api-it-skills  # Check logs

curl http://localhost:8001/health
curl http://localhost:8002/health
```

**Checkpoint:** Multi-domain déployé en Docker.

---

### H+40:00 - Tests End-to-End

```bash
# Full workflow test
export DOMAIN_CONFIG_PATH=domains/it_skills.yaml

# 1. Analyze
poetry run python src/cli/analyze_nodes.py --domain-config $DOMAIN_CONFIG_PATH

# 2. Enrich
poetry run python src/cli/densify_domain.py --domain-config $DOMAIN_CONFIG_PATH --batch-size 50

# 3. Validate (simulate human approval)
# poetry run python src/cli/approve_validations.py --approve-all

# 4. Export
poetry run python src/cli/export_domain.py \
    --domain-config $DOMAIN_CONFIG_PATH \
    --format cypher \
    --output exports/it_skills_$(date +%Y%m%d).txt

# 5. Load into Neo4j (if available)
# cypher-shell < exports/it_skills_*.txt
```

**Checkpoint:** Full pipeline validated.

---

### H+44:00 - Performance Benchmarks

```bash
# Create benchmark script
cat > scripts/benchmark.py << 'EOF'
import time
from domain import DomainConfigLoader

# Test 1: Domain config load time
start = time.time()
config = DomainConfigLoader("domains/it_skills.yaml").load()
print(f"Config load: {(time.time() - start)*1000:.2f}ms")

# Test 2: Cache load time (10K nodes)
start = time.time()
load_cache(config.metadata.domain_id)
print(f"Cache load (10K nodes): {(time.time() - start)*1000:.2f}ms")

# Test 3: API latency (cached)
# ... curl benchmark

# Test 4: LLM enrichment throughput
# ... time 100 nodes enrichment
EOF

poetry run python scripts/benchmark.py
```

**Expected results:**
- Config load: <50ms
- Cache load: <2000ms (10K nodes)
- API latency: <10ms (cached)
- LLM throughput: 15-20 nodes/min

**Checkpoint:** Performance validée.

---

### H+48:00 - GO LIVE

```bash
# 1. Tag release
git tag -a v2.0.0-genesis -m "Genesis Architecture: Universal Ontology Engine"
git push origin v2.0.0-genesis

# 2. Update CLAUDE.md
# - Version: 2.0.0
# - Architecture: Genesis (universal)
# - Domains: IT Skills (production), Product Catalog (beta), Medical (demo)

# 3. Announce
# - Internal Slack: "JENEZIS v2.0 live. Multi-domain. 100x faster setup."
# - LinkedIn post: "Rebuilt our ontology engine. What took weeks now takes hours."

# 4. Monitor
docker-compose logs -f
# Watch for errors, performance issues
```

**Mission Complete:** JENEZIS Genesis v2.0 operational.

---

## CHECKPOINTS DE VALIDATION

### Checkpoint #1 (H+4): Migration DB
- [ ] Backup complet effectué
- [ ] Migration test réussie
- [ ] Migration production validée
- [ ] Counts matches: 329 skills, 1,678 aliases, 844 relations
- [ ] Rollback testé et fonctionnel

### Checkpoint #2 (H+12): Genesis API
- [ ] genesis_main.py démarre sans erreur
- [ ] Charge domain config depuis env var
- [ ] `/nodes/harmonize` functional
- [ ] Cache invalidation works
- [ ] Swagger docs générées

### Checkpoint #3 (H+24): Multi-Domain Proof
- [ ] IT Skills domain operational (legacy data)
- [ ] Product Catalog domain créé from scratch
- [ ] 2 instances API parallèles fonctionnelles
- [ ] CLI tools acceptent --domain-config
- [ ] Vidéo POC enregistrée

### Checkpoint #4 (H+36): Production Ready
- [ ] Docker Compose multi-domain
- [ ] Tests E2E passent
- [ ] Performance benchmarks validés
- [ ] README updated
- [ ] CLAUDE.md updated

### Checkpoint #5 (H+48): LIVE
- [ ] v2.0.0 tagged
- [ ] Services deployed
- [ ] Monitoring active
- [ ] Team notified
- [ ] First prospect demo scheduled

---

## ROLLBACK PROCEDURE (Si catastrophe)

```bash
# 1. Stop all services
docker-compose down

# 2. Restore PostgreSQL
dropdb -U jenezis jenezis_harmonizer
createdb -U jenezis jenezis_harmonizer
psql -U jenezis -d jenezis_harmonizer < backups/pre_genesis_*.sql

# 3. Downgrade Alembic
poetry run alembic downgrade -1

# 4. Restart legacy API
export USE_GENESIS_API=false
docker-compose up -d

# 5. Investigate
tail -f logs/error.log
```

---

## CONTACTS D'URGENCE

**Lead:** Julien Dabert (jdabert@sigilum.fr)
**Backup:** Claude AI Assistant (cette conversation)
**Documentation:** docs/MIGRATION_STRATEGY.md

---

**STATUS FINAL:** 🔥 **EXÉCUTION EN COURS**

**Timer Start:** MAINTENANT
**Deadline:** T+48H

**LET'S FUCKING GO.**
