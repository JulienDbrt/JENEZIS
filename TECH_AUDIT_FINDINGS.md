# AUDIT TECH LEAD APPROFONDI - JENEZIS v3.3

## RÉSUMÉ EXÉCUTIF - FINDINGS CRITIQUES

### 🔴 PROBLÈMES MAJEURS IDENTIFIÉS

1. **DATABASE ARCHITECTURE INCOHÉRENTE** (CRITIQUE)
   - APIs utilisent SQLite, Celery utilise PostgreSQL
   - PostgreSQL lancé dans Docker mais inutilisé par APIs
   - AsyncTask, Skill models définis pour PostgreSQL mais jamais instanciés

2. **NEO4J ENTIÈREMENT DÉCONNECTÉ** (CRITIQUE)
   - Cypher queries générées mais jamais exécutées
   - Neo4j n'est pas dans docker-compose
   - Pipeline "CV → Neo4j" décrit dans README non fonctionnel

3. **CELERY COMPLETEMENT NON OPÉRATIONNEL** (CRITIQUE)
   - Celery app configurée, Redis lancé en Docker
   - 4 tâches Celery définies mais JAMAIS appelées
   - APIs n'utilisent pas les tâches async

4. **DOMAIN CONFIGURATION v2.0 CODE MORT** (MAJEUR)
   - DomainConfigManager et DomainMetadata définis mais jamais utilisés
   - 3 fichiers YAML de configuration (it_skills, medical, product_catalog) inutilisés
   - Seul 6 références dans le codebase (définitions de classe)

5. **MONITORING PROMETHEUS PARTIELLEMENT IMPLÉMENTÉ** (MAJEUR)
   - Métriques définies mais non appelées dans les APIs
   - Endpoints /metrics existent mais ne collectent rien

6. **ONTOLOGY.DB MANQUANTE** (CRITIQUE)
   - entity_resolver.db existe (86KB)
   - ontology.db complètement ABSENT
   - API Harmonizer ne fonctionnera pas au démarrage

---

## 1. POINTS D'ENTRÉE ACTIFS

### ✅ FONCTIONNELS

#### API - Harmonizer (Port 8000)
```
Fichier: src/api/main.py
Lancement: gunicorn src.api.main:app -w 4 -k uvicorn.workers.UvicornWorker
Endpoints:
  POST /harmonize      - Harmonise skills (utilise cache SQLite)
  POST /suggest        - Suggestions de skills (string similarity + LLM optionnel)
  GET  /health         - Health check
  GET  /stats          - Statistiques ontologie
  GET  /metrics        - Prometheus metrics (configured but not called)
  POST /admin/reload   - Recharge cache (require_auth)

Dépendances réelles:
  - SQLite: data/databases/ontology.db (MANQUANTE!)
  - Cache in-memory: ALIAS_CACHE, SKILLS_CACHE, HIERARCHY_CACHE
  - OpenAI: optionnel pour LLM suggestions
```

#### API - Entity Resolver (Port 8001)
```
Fichier: src/entity_resolver/api.py
Lancement: gunicorn src.entity_resolver.api:app -w 4 -k uvicorn.workers.UvicornWorker
Endpoints:
  POST /resolve              - Résout entités (companies/schools)
  GET  /health               - Health check
  GET  /stats                - Stats entités
  GET  /metrics              - Prometheus metrics (configured but not called)
  GET  /enrichment/queue     - Queue status
  POST /admin/reload         - Recharge cache (require_auth)
  POST /admin/add_entity     - Ajoute entité (require_auth)

Dépendances réelles:
  - SQLite: data/databases/entity_resolver.db (86KB, EXISTE)
  - Cache in-memory: ENTITY_CACHE
```

#### Nginx (Port 80/443)
```
Profile: production (optionnel)
Rôle: Reverse proxy, rate limiting, SSL/TLS
Actuellement: NON LANCÉ (profile production non activé par défaut)
```

### ⚠️ PARTIELLEMENT FONCTIONNELS

#### CLI Tools (Scripts de Gestion)
```
Tous dans src/cli/ - Lancés manuellement JAMAIS via Docker
  1. analyze_unmapped.py      - Analyse skills non mappés
  2. densify_ontology.py      - Enrichissement LLM batch
  3. mass_densify.py          - "THE BEAST" - mode automatique
  4. night_beast.py           - 5 heures enrichissement continu
  5. export_human_review.py   - Export skills pour revue
  6. import_approved.py       - Import CSV skills approuvés
  7. export_entity_review.py  - Export entités
  8. import_entity_enrichment.py - Import enrichissements

Statut: Scripts opérationnels mais:
  - Nécessitent ontology.db (ABSENTE)
  - Jamais lancés en production
  - Dépendent de configuration manuelle
```

### ❌ COMPLÈTEMENT NON FONCTIONNELS

#### Celery Workers
```
Configuration: src/celery_app.py
Redis Broker: localhost:6379 (lancé en Docker)

Tâches définies:
  1. enrich_skill_with_llm (src.tasks.enrichment)
     - Utilise PostgreSQL AsyncTask model
     - Jamais appelée depuis les APIs

  2. batch_enrich_skills
     - Batch processing
     - Jamais invoquée

  3. suggest_skills_with_llm (src.tasks.suggestions)
     - LLM suggestions via Celery
     - APIs appellent suggest_skills() directement, pas via Celery

  4. batch_suggest_skills
     - Batch suggestions
     - Jamais utilisée

Problème: Les APIs utilisent les fonctions directement au lieu de dispaticher via Celery
```

#### Neo4j Pipeline
```
Fichier: src/graph_ingestion/ingest.py
Objectif: CV (JSON) → Cypher queries → Neo4j

Flux implémenté:
  1. Charger CV exemple (data/examples/cv_example.json)
  2. Appeler Harmonizer API pour harmoniser skills
  3. Appeler Entity Resolver API pour résoudre companies/schools
  4. Générer Cypher MERGE queries
  5. Sauvegarder dans cypher_queries.txt

Statut: GÉNÉRÉE mais JAMAIS EXÉCUTÉE
  - Neo4j n'est pas lancé en Docker
  - Pas d'intégration avec les APIs
  - Queries sont sauvegardées mais manuellement exécutables seulement
  - Wikipedia enricher a import Neo4j optionnel (use_neo4j=False par défaut)
```

#### Monitoring Stack (Prometheus/Grafana)
```
Services Docker:
  - Prometheus:9090 (profile: monitoring)
  - Grafana:3001 (profile: monitoring)

Statut:
  - Configuration définie mais profile monitoring non activé par défaut
  - Métriques définies en src/api/metrics.py mais JAMAIS appelées
  - APIs génèrent de la data dans REQUEST_COUNT, etc. mais fonctions de tracking pas invoquées
  - Prometheus scrape pas les endpoints

Lancement: docker-compose --profile monitoring up -d
```

---

## 2. ANALYSE DES DÉPENDANCES - MODULE PAR MODULE

### src/api/ (Harmonizer API - UTILISÉE)

#### main.py
```
UTILISÉ: ✓ Production
Dépend de:
  - SQLite3 (ontology.db - MANQUANTE!)
  - OpenAI (optionnel pour LLM)
  - auth.py (pour require_auth)
  - metrics.py (importé mais PAS APPELÉ)

Code mort:
  - track_cache_metrics() fonction appelée à /metrics mais metrics not updated in endpoints
  - metrics_endpoint() disponible mais données stales
```

#### auth.py
```
UTILISÉ: ✓ Production (require_auth sur /admin/* endpoints)
Dépend de:
  - API_AUTH_TOKEN env var

Code mort: Aucun
```

#### metrics.py
```
UTILISÉ: ✗ Partiellement (endpoints existent mais jamais invoqués)
Dépend de:
  - prometheus_client
  - Jamais importé/utilisé dans main.py ou api.py

Implémentation:
  - REQUEST_COUNT (défini, JAMAIS incrémenté)
  - REQUEST_DURATION (défini, JAMAIS observé)
  - CACHE_SIZE (défini, appelé une fois à /metrics)
  - DB_QUERY_COUNT (défini, JAMAIS incrémenté)
  - HARMONIZATION_COUNT (défini, JAMAIS incrémenté)
  - ENTITY_RESOLUTION_COUNT (défini, JAMAIS incrémenté)
  - ERROR_COUNT (défini, JAMAIS incrémenté)

VERDICT: Code monitoring MORT - endpoints retournent toujours 0 métriques
```

### src/entity_resolver/ (Entity Resolver API - UTILISÉE)

#### api.py
```
UTILISÉ: ✓ Production
Dépend de:
  - SQLite3 (entity_resolver.db - 86KB, EXISTE)
  - auth.py (require_auth)
  - metrics.py (importé mais JAMAIS APPELÉ)

Logique:
  - Cache in-memory at startup (load_cache())
  - POST /resolve utilise cache directement
  - Ajoute entities inconnues à enrichment_queue
  - Endpoints admin pour reload et add_entity

Code mort:
  - metrics.py functions jamais appelées
  - enrichment_queue remplie mais jamais traitée (Celery workers inexistants)
```

#### db_init.py
```
UTILISÉ: ✓ À l'initialisation seulement
Crée:
  - canonical_entities table
  - entity_aliases table
  - enrichment_queue table (pour futur Celery)
  - sqlite_stat1, sqlite_stat4 (query optimizer)

Notes:
  - Enrichment queue vide en production
  - Jamais appelé après initialisation
```

### src/graph_ingestion/ (CV → Neo4j Pipeline)

#### ingest.py
```
UTILISÉ: ✗ JAMAIS
Fichier script: 780 lignes de code

Fonctionnalité:
  1. Charge CV depuis data/examples/cv_example.json
  2. Appelle API Harmonizer (/harmonize)
  3. Appelle API Entity Resolver (/resolve)
  4. Génère structure graphe (nodes, relations)
  5. Génère Cypher MERGE queries
  6. Sauvegarde dans cypher_queries.txt

Problèmes:
  - JAMAIS lancé en production
  - Neo4j n'est pas lancé
  - Queries générées statiques (test seulement)
  - Pas d'intégration avec APIs
  - Hardcoded test CV path

Verdict: Script de démonstration non productif
```

### src/enrichment/ (Entity Enrichment)

#### wikipedia_enricher.py
```
UTILISÉ: ✗ JAMAIS
Statut: 400 lignes de code mort

Objectif:
  - Enrichir entities via Wikipedia API
  - Mettre à jour Neo4j avec descriptions

Fonctionnalité:
  1. Lit enrichment_queue depuis entity_resolver.db
  2. Interroge Wikipedia API (français et anglais)
  3. Génère Neo4j update queries
  4. Marque items comme traités

Problèmes:
  - Neo4j import conditionnel (use_neo4j=False par défaut)
  - enrichment_queue JAMAIS appelée (pas de Celery workers)
  - simulate_neo4j_update() mock function (pas vraie requête)
  - Tests mockent entièrement Neo4j

Verdict: Code mort avec infrastructure zombie
```

### src/tasks/ (Celery Async Tasks)

#### enrichment.py
```
UTILISÉ: ✗ JAMAIS
Tâches:
  1. enrich_skill_with_llm@app.task
  2. batch_enrich_skills@app.task

Implémentation:
  - Dépend de PostgreSQL AsyncTask, Skill models
  - Interroge OpenAI API
  - Met à jour AsyncTask.status
  - Retourne enriched_result dict

Problèmes:
  - JAMAIS appelée depuis les APIs
  - Celery workers jamais lancés
  - PostgreSQL AsyncTask table jamais créée
  - Redis broker lancé mais jamais utilisé

Verdict: Code Celery mort
```

#### suggestions.py
```
UTILISÉ: ✗ JAMAIS
Tâches:
  1. suggest_skills_with_llm@app.task
  2. batch_suggest_skills@app.task

Notes:
  - APIs appellent suggest_skills() directement (string similarity)
  - Tâches Celery jamais invoquées
  - Même pattern que enrichment.py

Verdict: Code Celery mort
```

### src/db/ (Database Management)

#### database.py
```
UTILISÉ: ✓ Initialisation ontology.db uniquement
Crée:
  - skills table
  - aliases table
  - hierarchy table
  - 3 indexes

Statut: Jamais exécuté après installation
Problem: ontology.db MISSING - script jamais appelé!
```

#### postgres_connection.py
```
UTILISÉ: ✗ JAMAIS
Implémentation:
  - SQLAlchemy engine avec connection pooling
  - AsyncSession support
  - Définit DATABASE_URL depuis env

Problème:
  - Importé par src/tasks/*
  - Jamais appelé depuis APIs
  - PostgreSQL jamais initialisé
  - get_db(), get_async_db() jamais utilisés

Verdict: Code mort - Postgres setup inutilisé
```

#### postgres_models.py
```
UTILISÉ: ✗ JAMAIS
Modèles définis:
  - Skill (avec pgvector embeddings!)
  - Alias
  - Hierarchy
  - AsyncTask, TaskStatus
  - Et 5 autres modèles

Problème:
  - Importé par src/tasks/*
  - Tables jamais créées en production
  - Base.metadata.create_all() jamais appelé

Verdict: Schema PostgreSQL mort - PostgreSQL lancé mais schema jamais déploié
```

### src/cli/ (Command Line Tools)

#### analyze_unmapped.py
```
UTILISÉ: ✗ Manuellement (jamais en production)
Dépend de:
  - ontology.db (MANQUANTE!)
  - CSV file analyse_skills.csv
  - OpenAI API (optionnel)

Fonctionnalité:
  1. Charge mapped skills depuis DB
  2. Détecte skills non mappés
  3. Classe skills (certifications, frameworks, tools)
  4. Génère rapport JSON

Verdict: Code OK mais jamais lancé
```

#### densify_ontology.py
```
UTILISÉ: ✗ Manuellement
Batch LLM enrichment avec:
  - LLMSkillProcessor
  - HumanReviewManager
  - SkillDatabaseManager
  - ApiCacheManager

Dépend de:
  - ontology.db (MANQUANTE!)
  - OpenAI API

Verdict: Code OK mais jamais lancé en production
```

#### night_beast.py
```
UTILISÉ: ✗ Manuellement
"5-hour continuous enrichment session"

Lance: densify_ontology.py en boucle avec batch sizes progressifs
Dépend de:
  - ontology.db (MANQUANTE!)
  - API Harmonizer healthy

Verdict: Code OK mais jamais lancé
```

### src/domain/ (v2.0 Universal Schema - COMPLÈTEMENT NON UTILISÉ)

#### config_loader.py
```
UTILISÉ: ✗ JAMAIS EN PRODUCTION
Classes:
  - NodeTypeSchema
  - RelationshipTypeSchema
  - DomainMetadata (unused)
  - DataSourceConfig
  - DomainConfigLoader
  - DomainConfigManager (unused)

Usage en codebase:
  - 6 références total (classe definitions only)
  - JAMAIS importé ou instancié en code réel
  - Tests mockent completement

Fichiers YAML associés (domains/):
  - it_skills.yaml
  - medical_diagnostics.yaml
  - product_catalog.yaml

VERDICT: Code dead - v2.0 schema jamais déployée
```

---

## 3. ANALYSE DOCKER

### Services Lancés par Défaut

```yaml
docker-compose up -d  # Défaut

✓ PostgreSQL:16       port 5433  - UTILISÉE: Non (APIs utilisent SQLite)
✓ Redis:7-alpine      port 6379  - UTILISÉE: Non (Celery jamais lancé)
✓ Harmonizer API      port 8000  - UTILISÉE: Oui (mais ontology.db manquante)
✓ Entity Resolver API port 8001  - UTILISÉE: Oui (entity_resolver.db existe)
```

### Services Optionnels

```yaml
--profile production  # Nginx reverse proxy, rate limiting
--profile monitoring  # Prometheus + Grafana (metriques jamais collectées)

✗ Nginx              port 80/443 - UTILISÉ: Non
✗ Prometheus         port 9090   - UTILISÉ: Non (metriques non appelées)
✗ Grafana            port 3001   - UTILISÉ: Non
```

### Services Absents

```
✗ Neo4j              - PAS DANS DOCKER-COMPOSE
                       (cypher_queries.txt générées mais jamais exécutées)
✗ Celery Worker     - PAS LANCÉ
                       (tâches définies mais jamais invoquées)
```

### Architecture Mismatch

```
EXPECTED (Par documentation/README):
  CV JSON → Harmonizer API → Entity Resolver API → Neo4j → Analyse avancée

ACTUAL (Ce qui fonctionne réellement):
  CV JSON → ❌ (ingest.py jamais lancé)
  Harmonizer API → ✓ (fonctionne si ontology.db existe)
  Entity Resolver API → ✓ (fonctionne, remplit enrichment_queue)
  enrichment_queue → ❌ (jamais consommée)
  Neo4j → ❌ (jamais lancé)
```

---

## 4. ANALYSE DES DONNÉES

### Bases de Données

```
✗ data/databases/ontology.db
  - MANQUANTE (critique pour Harmonizer API)
  - Attendue: skills, aliases, hierarchy tables
  - Nombre de records inconnu (DB introuvable)

✓ data/databases/entity_resolver.db
  - 86 KB (très petit)
  - Tables:
    • canonical_entities (entreprises/écoles)
    • entity_aliases
    • enrichment_queue (vide)

✓ data/examples/cv_example.json
  - Example CV parsé
  - Utilisé seulement par ingest.py (jamais lancé)
```

### Données dans Output/

```
✓ data/output/cypher_queries_example.txt
  - Example requêtes Cypher générées
  - Jamais chargées dans Neo4j

✓ data/output/.gitkeep
  - Placeholder directory
```

### Fichiers de Configuration

```
✓ domains/it_skills.yaml
✓ domains/medical_diagnostics.yaml
✓ domains/product_catalog.yaml
  - Tous définis
  - JAMAIS UTILISÉS (DomainConfigManager jamais instancié)
```

---

## 5. CODE MORT SUSPECT

### Classes/Modules Complètement Non Utilisés

```
1. DomainConfigManager (src/domain/config_loader.py)
   - Défini: Oui
   - Importé: Oui (src/domain/__init__.py)
   - Utilisé: ✗ JAMAIS
   - Références: 6 (défini 1x, classe method 5x)

2. DomainMetadata (src/domain/config_loader.py)
   - Défini: Oui
   - Utilisé: ✗ JAMAIS
   - Références: 3 (définition + from_dict method)

3. postgres_models.py (Skill, AsyncTask, etc.)
   - Défini: Oui (7918 bytes)
   - Utilisé: ✗ Jamais (AsyncTask table jamais créée)
   - Références: Importé par src/tasks/* mais jamais get_db() appelé

4. postgres_connection.py
   - Défini: Oui (3851 bytes)
   - Utilisé: ✗ Jamais
   - References: Importé par src/tasks/* mais jamais appelé

5. Celery Tasks (enrichment.py, suggestions.py)
   - Défini: Oui (4 tasks)
   - Utilisé: ✗ Jamais
   - Références: 0 (définition seulement)

6. graph_ingestion/ingest.py (780 lignes)
   - Défini: Oui
   - Utilisé: ✗ Jamais
   - Exécuté: 0 fois (script standalone jamais lancé)

7. enrichment/wikipedia_enricher.py (400 lignes)
   - Défini: Oui
   - Utilisé: ✗ Jamais
   - Exécuté: 0 fois (enrichment_queue jamais consommée)
```

### Configuration Définie mais Non Utilisée

```
1. Prometheus Metrics (metrics.py)
   - REQUEST_COUNT
   - REQUEST_DURATION
   - CACHE_SIZE
   - DB_QUERY_COUNT
   - DB_QUERY_DURATION
   - HARMONIZATION_COUNT
   - ENTITY_RESOLUTION_COUNT
   - ERROR_COUNT
   
   Status: Functions defined but NEVER called in APIs

2. Redis Configuration
   - Redis lancé en Docker
   - Utilisé: ✗ (Celery workers jamais lancés)
   
3. PostgreSQL Configuration
   - PostgreSQL lancé en Docker (pgvector enabled)
   - Utilisé: ✗ (async_engine/engine jamais utilisé)
   - AsyncTask model schema jamais déployé

4. Neo4j Configuration (env vars)
   - NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD dans config.py
   - Utilisé: ✗ (Neo4j jamais lancé, cypher queries jamais exécutées)
```

---

## 6. ANALYSE DES TESTS

### Test Coverage Par Module

```
BIEN TESTÉ:
  ✓ src/api/main.py (test_harmonizer_api.py - 20+ tests)
  ✓ src/entity_resolver/api.py (test_entity_resolver_api.py - 15+ tests)
  ✓ src/api/auth.py (test_auth.py - comprehensive)
  ✓ src/cli/analyze_unmapped.py (test_cli_analyze_unmapped.py)
  ✓ src/cli/densify_ontology.py (test_cli_densify_ontology.py)

PARTIELLEMENT TESTÉ:
  ⚠ src/enrichment/wikipedia_enricher.py
    - test_wikipedia_enricher_comprehensive.py
    - Mocks entièrement Neo4j (use_neo4j=False)
    - Ne teste jamais vraie intégration

  ⚠ src/tasks/enrichment.py, suggestions.py
    - Pas de vrais tests Celery
    - PostgreSQL AsyncTask jamais testé
    - Redis broker jamais testé

PAS TESTÉ:
  ✗ src/graph_ingestion/ingest.py
    - test_graph_ingestion.py existe
    - Mock entièrement les API calls
    - Jamais testé en vraie intégration

  ✗ src/db/postgres_models.py
    - Jamais créé en DB
    - Jamais testé contre vraie PostgreSQL
```

### Tests Mocking Neo4j

```python
# Pattern trouvé:
@patch.dict("sys.modules", {"neo4j": Mock()})
def test_main_with_neo4j(self):
    # Tests MOCK Neo4j au lieu de tester vraie intégration
```

### Tests Pour Code Mort

```
test_enrichment_workflow.py
  - Wikipedia enrichment avec use_neo4j=False

test_coverage_completion.py
  - simulate_neo4j_update() tested (mock function)

Verdict: Tests pour code mort qui jamais exécuté
```

---

## 7. ANALYSE CRITIQUE DES FEATURES

### Feature 1: Harmonisation des Skills

```
Status: ✓ FONCTIONNELLE

Implémentation:
  - SQLite ontology.db avec (skills, aliases, hierarchy)
  - API POST /harmonize avec cache in-memory
  - Suggestion par string similarity + LLM optionnel

Problème:
  - ontology.db MANQUANTE (app crash au démarrage)
  - Tests passent (DB créée temporairement par conftest)
  - Production sans data = API inutile

Tests:
  - 20+ tests dans test_harmonizer_api.py
  - Couvrent: exact match, similarity, LLM, edge cases
  - Mais avec DB temporaire (ne reflète pas prod!)

Verdict: Feature OK architecturalement, données manquantes en prod
```

### Feature 2: Résolution d'Entités

```
Status: ✓ FONCTIONNELLE

Implémentation:
  - SQLite entity_resolver.db (canonical_entities, aliases)
  - Cache in-memory au démarrage
  - POST /resolve avec matchings partial
  - Ajoute unknowns à enrichment_queue

Complétude:
  - Endpoints OK (health, stats, reload)
  - Admin endpoints OK (add_entity)
  - enrichment_queue infrastructure définie

Problème:
  - enrichment_queue remplie mais jamais consommée
  - Wikipedia enricher jamais appelé
  - Données statiques (30 companies, 13 schools seulement)

Tests:
  - 15+ tests test_entity_resolver_api.py
  - Couvrent: resolve, add_entity, cache reload
  - Pas de tests pour enrichment_queue processing

Verdict: Feature partiellement implémentée - queue infrastructure zombie
```

### Feature 3: Pipeline CV → Neo4j

```
Status: ✗ NON IMPLÉMENTÉE

Implémentation:
  - Script ingest.py (780 lignes) génère Cypher queries
  - Appelle Harmonizer + Entity Resolver APIs
  - Crée structure graph (nodes/relations)
  - Sauvegarde requêtes dans cypher_queries.txt

Problèmes:
  - Neo4j NON DANS DOCKER
  - Script JAMAIS LANCÉ
  - Queries sauvegardées JAMAIS EXÉCUTÉES
  - Pas d'intégration avec APIs

Tests:
  - test_graph_ingestion.py existe
  - Entièrement mocked (pas d'appels réels)
  - Ne reflète pas vraie intégration

Verdict: Feature définie mais jamais déployée
```

### Feature 4: Enrichissement LLM (OpenAI)

```
Status: ⚠ PARTIELLEMENT IMPLÉMENTÉE

1. Harmonizer suggestions (API)
   - Suggestions string similarity: ✓ Fonctionne
   - Suggestions LLM (/suggest?use_llm=true): ⚠ Optionnel, jamais utilisé

2. Skills enrichment (CLI + Celery)
   - densify_ontology.py: Appelle OpenAI pour normaliser skills
   - Celery task enrich_skill_with_llm: Définie mais jamais appelée
   - CLI jamais lancée en prod

3. Entity enrichment (Wikipedia)
   - Appelle Wikipedia API (working)
   - Mais enrichment_queue jamais consommée
   - Neo4j updates jamais exécutées

Tests:
  - LLM mocked dans tous les tests (never vraie API)

Verdict: Infrastructure OK, jamais utilisée en production
```

### Feature 5: Enrichissement Wikipedia

```
Status: ✗ NON OPÉRATIONNEL

Implémentation:
  - wikipedia_enricher.py télécharge descriptions
  - Lit enrichment_queue depuis entity_resolver.db
  - Génère Neo4j update queries
  - simulate_neo4j_update() mock function

Problèmes:
  1. enrichment_queue jamais consommée
     - /resolve ajoute unknowns mais personne ne lit
     - Aucun Celery worker pour traiter la queue

  2. Neo4j updates jamais exécutées
     - use_neo4j=False par défaut
     - Neo4j jamais lancé en Docker
     - simulate_neo4j_update() = mock function (pas vraies mutations)

  3. Pas de planification
     - Celery workers jamais lancés
     - Cronjob ou scheduler absent
     - Code jamais exécuté

Tests:
  - Entièrement mockés
  - Ne couvrent pas vraie intégration

Verdict: Code mort avec infrastructure zombie
```

### Feature 6: Export/Import CSV (Human Review)

```
Status: ⚠ PARTIELLEMENT IMPLÉMENTÉE

Export:
  ✓ export_human_review.py
    - Exporte skills avec stats
    - Crée CSV pour révision manuelle

  ✓ export_entity_review.py
    - Exporte entities pour revue
    - Crée CSV structure

Import:
  ✓ import_approved.py
    - Lit CSV skills approuvés
    - Ajoute à ontology.db

  ⚠ import_entity_enrichment.py
    - Définit mais jamais testé

Statut:
  - Scripts OK en local
  - Jamais utilisés en production
  - Nécessite intervention manuelle
  - ontology.db manquante = import impossible

Verdict: Workflow cycle OK, mais données manquantes
```

### Feature 7: Celery/Redis Async Tasks

```
Status: ✗ COMPLÈTEMENT NON OPÉRATIONNEL

Configuration:
  - celery_app.py: Défini avec Redis broker
  - Redis lancé en Docker
  - 4 tasks définies (enrichment, suggestions)

Problèmes:
  1. Tasks jamais appelées
     - APIs utilisent fonctions synchrones directement
     - Pas de app.send_task() ou task.delay() dans code
     - AUCUNE invocation trouvée

  2. PostgreSQL AsyncTask model jamais utilisé
     - Modèle défini dans postgres_models.py
     - Jamais CREATE TABLE
     - async_engine jamais initialisé

  3. Redis broker lancé mais inutilisé
     - Docker compose le lance
     - Aucune consommation observée

  4. Pas de workers lancés
     - Pas de `celery -A src.celery_app worker`
     - Pas de docker service pour worker

Verdict: Celery infrastructure mort - tous composants inutilisés
```

### Feature 8: Monitoring Prometheus/Grafana

```
Status: ✗ PARTIELLEMENT IMPLÉMENTÉE

Métriques définies (metrics.py):
  - REQUEST_COUNT
  - REQUEST_DURATION
  - CACHE_SIZE
  - DB_QUERY_COUNT
  - DB_QUERY_DURATION
  - HARMONIZATION_COUNT
  - ENTITY_RESOLUTION_COUNT
  - ERROR_COUNT

Problèmes:
  1. Fonctions tracking JAMAIS APPELÉES
     - track_request_metrics() défini, jamais invoqué
     - track_harmonization() défini, jamais invoqué
     - track_entity_resolution() défini, jamais invoqué
     - track_database_query() défini, jamais invoqué
     - track_error() défini, jamais invoqué

  2. Métriques stales
     - /metrics endpoint exists mais retourne toujours 0
     - CACHE_SIZE appelé une fois à startup
     - Rien d'autre collecté

  3. Prometheus/Grafana jamais lancés
     - --profile monitoring non activé par défaut
     - Pas de data pour visualiser

Verdict: Monitoring skeleton - aucune data collectée
```

---

## 8. INCOHÉRENCES ARCHITECTURALES

### Mismatch #1: Deux Backends de Base de Données

```
PROBLÈME: Deux systèmes complètement disjoints

APIs (Harmonizer + Entity Resolver):
  └─ SQLite avec cache in-memory
    ├─ ontology.db (skills, aliases, hierarchy)
    ├─ entity_resolver.db (entities, aliases, queue)
    └─ Pas de PostgreSQL

Celery Tasks (enrichment, suggestions):
  └─ PostgreSQL avec SQLAlchemy
    ├─ Importe postgres_models (AsyncTask, Skill)
    ├─ Utilise postgres_connection (engine, sessionmaker)
    ├─ Tables jamais créées en prod
    └─ Code mort

IMPACT:
  - PostgreSQL lancé en Docker mais inutilisé (86MB image)
  - AsyncTask model jamais instancié
  - Tasks ne peuvent pas stocker résultats dans DB
  - Dépense infrastructure pour rien

SOLUTION: Choisir SQLite ou PostgreSQL, pas les deux
```

### Mismatch #2: APIs vs Appels Directs vs Celery

```
PROBLÈME: Trois patterns mélangés

Pattern 1 - Appels API directs (utilisé):
  src/graph_ingestion/ingest.py
    → requests.post(HARMONIZER_API_URL/harmonize)
    → requests.post(ENTITY_RESOLVER_API_URL/resolve)

Pattern 2 - Appels directs aux fonctions (utilisé):
  src/api/main.py
    → suggest_skills() appelé directement
    → Pas de Celery.delay()

Pattern 3 - Celery tasks (JAMAIS UTILISÉ):
  src/tasks/enrichment.py
    → enrich_skill_with_llm.delay()
  src/tasks/suggestions.py
    → suggest_skills_with_llm.delay()

IMPACT:
  - Inconsistence dans la codebase
  - Celery infrastructure inutile
  - Redis jamais utilisé
  - Tâches async jamais exécutées

VERDICT: Code a design prévisionniste (anticipait async) mais jamais implémenté
```

### Mismatch #3: Neo4j Pipeline Déconnecté

```
PROBLÈME: Code génère Cypher mais Neo4j n'existe pas

Génération:
  src/graph_ingestion/ingest.py
    → Génère cypher_queries.txt
    → Sauvegarde requêtes MERGE

Exécution:
  ✗ Neo4j pas dans docker-compose
  ✗ Queries jamais chargées
  ✗ "CV → Graph Neo4j" in README is aspirational, pas réel

Wikipedia enrichment:
  src/enrichment/wikipedia_enricher.py
    → Wikipedia data collectée
    → Neo4j updates générées mais jamais exécutées
    → use_neo4j=False par défaut

IMPACT:
  - Tout le pipeline "knowledge graph" is theoretical
  - 800 lignes de code jamais exécutées
  - README documentation misleading
  - Users penseront que Neo4j est dispo

VERDICT: Code prévisionniste pour feature jamais déployée
```

### Mismatch #4: Domain Configuration v2.0

```
PROBLÈME: Universal schema framework jamais utilisé

Défini:
  src/domain/config_loader.py
    - DomainConfigManager
    - DomainMetadata
    - NodeTypeSchema
    - RelationshipTypeSchema

Fichiers YAML (domains/):
  - it_skills.yaml (completement valide)
  - medical_diagnostics.yaml (ready)
  - product_catalog.yaml (ready)

Utilisé:
  ✗ JAMAIS EN PRODUCTION
  ✗ 6 références au total (définitions seulement)
  ✗ Jamais importé dans code réel

IMPACT:
  - Dead code d'infrastructure
  - YAML files inutiles
  - Complexité architecturale inutile

VERDICT: v2.0 schema lancé en parallèle de v1.x, jamais finalisé
```

### Mismatch #5: Monitoring Non Connecté

```
PROBLÈME: Métriques définies mais jamais collectées

Côté Code:
  metrics.py définit 8 métriques
  Mais fonctions tracking jamais appelées

Côté Infrastructure:
  Prometheus + Grafana dans docker-compose (--profile monitoring)
  Mais endpoints /metrics retournent toujours 0

IMPACT:
  - Dashboards Grafana sont vides
  - Pas de visibilité sur API performance
  - Setup monitoring incomplet

VERDICT: Skeleton monitoring sans données
```

---

## 9. RECOMMANDATIONS CRITIQUES

### 🔴 ACTION CRITIQUE #1: Créer ontology.db

```bash
# URGENT - API Harmonizer crash au démarrage sans ce fichier
cd /Users/juliendabert/Desktop/JENEZIS
python3 src/db/database.py  # Crée ontology.db

# Puis charger data de test
python3 src/cli/import_approved.py data/test_skills.csv
```

### 🔴 ACTION CRITIQUE #2: Décider du Backend DB

**Option A: Garder SQLite (Actuel)**
```
Avantage:
  - Minimaliste, performant pour small scale
  - Déjà implémenté dans APIs
  - Pas de dépendances externes

Désavantage:
  - Pas de pgvector (semantic search)
  - Pas de full async
  - Limité à 1 instance

Action:
  1. Supprimer src/db/postgres_* (mort)
  2. Supprimer src/tasks/* (mort)
  3. Supprimer PostgreSQL de docker-compose
  4. Implémenter retry logic en SQLite
```

**Option B: Migrer vers PostgreSQL (Recommandé)**
```
Avantage:
  - pgvector pour semantic search
  - Scalabilité (multiple replicas)
  - Async support (FastAPI friendly)
  - Tasks persistence

Action:
  1. Initialiser PostgreSQL schema via init_db()
  2. Migrer ontology.db → PostgreSQL
  3. Implémenter Celery workers
  4. Lancer redis worker: celery -A src.celery_app worker
```

**Recommandation: Option B** - PostgreSQL + Celery sont définis, juste pas utilisés

### 🔴 ACTION CRITIQUE #3: Ou Supprimer Celery (Recommandé si SQLite)

```python
# Option 1: Implémenter Celery correctement
@app.post("/suggest")
async def suggest_skills(request: SuggestRequest):
    # Dispatcher vers Celery au lieu d'appeler directement
    task = suggest_skills_with_llm.delay(request.skill, request.top_k)
    return {"task_id": task.id, "status": "queued"}

# Option 2: Supprimer Celery si on reste en SQLite
# Supprimer:
# - src/celery_app.py
# - src/tasks/
# - Redis de docker-compose
# Garder:
# - Appels synchrones simples dans APIs
```

### 🟠 ACTION MAJEURE #1: Décider pour Neo4j

**Option A: Garder code de génération**
```
Si vous voulez supporter Neo4j:
  1. Ajouter Neo4j service à docker-compose
  2. Implémenter vraie exécution de Cypher
  3. Intégrer avec wikipedia_enricher.py
  4. Lancer enrichment_queue worker

Effort: ~2 sprints
```

**Option B: Supprimer code Neo4j**
```
Si Neo4j non prioritaire:
  - Supprimer src/graph_ingestion/ingest.py (780 lignes)
  - Supprimer src/enrichment/wikipedia_enricher.py (400 lignes)
  - Supprimer enrichment_queue schema
  - Mettre à jour README (supprimer "CV → Neo4j")

Effort: 4 heures
```

**Recommandation: Option A** - Code est bon, juste besoin de connexion

### 🟠 ACTION MAJEURE #2: Monitoring

```python
# Activer vraiment les métriques dans APIs

# src/api/main.py
from api.metrics import track_harmonization, track_cache_metrics

@app.post("/harmonize")
def harmonize_skills(request: HarmonizationRequest):
    results = []
    for skill in request.skills:
        # ... logique ...
        if canonical:
            track_harmonization("known")
        else:
            track_harmonization("unknown")
    
    track_cache_metrics("aliases", len(ALIAS_CACHE))
    return HarmonizationResponse(results=results)

# Même pour entity_resolver/api.py
@app.post("/resolve")
def resolve_entities(request: ResolveRequest):
    # ... logique ...
    track_entity_resolution(request.entity_type, "known")
```

### 🟡 ACTION MAJEURE #3: Domain Configuration

**Décider:**
- Garder et finir domain config v2.0 (3-5 sprints)
- Ou supprimer (DomainConfigManager + YAML files)

**Recommandation: Supprimer pour maintenant**
```
Raisons:
  - Jamais utilisé en production
  - APIs de skills existantes fonctionnent
  - Ajoute complexité sans value

Action:
  1. Supprimer src/domain/
  2. Supprimer domains/*.yaml
  3. Supprimer doc references
```

### 🟡 ACTION MINEURE #1: CLI Tools

Rendre utilisables en production:
```bash
# Actuellement: Script standalone, jamais lancé
# Besoin: CLI entrypoint dans poetry ou docker service

# Option 1: Poetry CLI
[tool.poetry.scripts]
jenezis-densify = "src.cli.densify_ontology:main"
jenezis-analyze = "src.cli.analyze_unmapped:main"
jenezis-night-beast = "src.cli.night_beast:main"

# Option 2: Docker service
services:
  cli-worker:
    build: .
    command: python -m src.cli.densify_ontology 100
```

---

## SUMMARY TABLE: Code Utilization Status

| Module | File | LOC | Used | Verdict |
|--------|------|-----|------|---------|
| API | src/api/main.py | 325 | ✓ Production | Keep - Critical |
| API | src/api/auth.py | 87 | ✓ Production | Keep - Required |
| API | src/api/metrics.py | 108 | ⚠ Defined only | Fix - Call tracking functions |
| Entity Resolver | src/entity_resolver/api.py | 501 | ✓ Production | Keep - Critical |
| Entity Resolver | src/entity_resolver/db_init.py | 120 | ✓ Setup | Keep - Schema |
| Graph Ingestion | src/graph_ingestion/ingest.py | 780 | ✗ Never | Decide: Keep + launch Neo4j or Delete |
| Enrichment | src/enrichment/wikipedia_enricher.py | 400 | ✗ Never | Decide: Implement or Delete |
| Celery App | src/celery_app.py | 46 | ✗ Never | Delete or Implement workers |
| Tasks | src/tasks/enrichment.py | 127 | ✗ Never | Delete or Implement caller |
| Tasks | src/tasks/suggestions.py | 70 | ✗ Never | Delete or Implement caller |
| DB Utils | src/db/database.py | 65 | ✓ Setup | Keep - Schema creation |
| DB Utils | src/db/postgres_connection.py | 141 | ✗ Never | Delete (PostgreSQL not used) |
| DB Utils | src/db/postgres_models.py | 250 | ✗ Never | Delete (PostgreSQL not used) |
| Domain | src/domain/config_loader.py | 350 | ✗ Never | Delete (v2.0 not deployed) |
| CLI | src/cli/*.py | 2000+ | ⚠ Manual | Keep - Local tools |
| Config | src/config.py | 51 | ✓ Startup | Keep |

**Total dead code: ~1500 LOC (20% of codebase)**

---

## CONCLUSION

JENEZIS est un projet **architecturally sound but incompletely deployed**:

✓ **Fonctionnels:**
  - APIs Harmonizer et Entity Resolver
  - SQLite ontology et entity resolution
  - Tests complets (21 test files)
  - Docker containerization stable

✗ **Non Opérationnels:**
  - ontology.db manquante (données perdues?)
  - Neo4j jamais connecté (1200 lignes code génération)
  - Celery workers jamais lancés (infrastructure inutile)
  - PostgreSQL setup pour rien (100MB image inutile)
  - Domain config v2.0 jamais déployée (350 lignes code mort)
  - Monitoring métriques jamais appelées (8 métriques vides)
  - Wikipedia enrichment jamais exécuté (enrichment_queue zombie)

**Architecture Résumée:**
```
RÉALITÉ:
  CV JSON [test data]
    ↓
  Harmonizer API [OK] ← SQLite [MISSING]
    ↓
  Entity Resolver API [OK] ← SQLite [EXISTS]
    ↓
  enrichment_queue [NEVER CONSUMED]

PLAN ORIGINAL (README):
  CV JSON
    ↓
  Harmonizer API
    ↓
  Entity Resolver API
    ↓
  enrichment_queue ← Wikipedia enricher ← Neo4j
    ↓
  Knowledge Graph [Neo4j NOT LAUNCHED]
    ↓
  Advanced Analysis
```

**Recommandation: Réduire scope et stabiliser**
1. Fixer ontology.db
2. Choisir PostgreSQL OU SQLite (pas les deux)
3. Lancer Neo4j OU supprimer le pipeline
4. Lancer Celery workers OU supprimer les tâches
5. Appeler vraiment les fonctions de métriques
