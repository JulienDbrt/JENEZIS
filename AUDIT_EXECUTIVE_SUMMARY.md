# AUDIT TECH LEAD - RÉSUMÉ EXÉCUTIF

**Date:** 26 Octobre 2025  
**Codebase:** JENEZIS v3.3  
**Statut:** Production-like Docker setup avec code mort critique

---

## TABLEAU DE BORD - FINDINGS CRITIQUES

| Catégorie | Problème | Sévérité | Impact |
|-----------|----------|----------|---------|
| **Database** | APIs utilisent SQLite, Celery use PostgreSQL | 🔴 CRITIQUE | Deux backends disjoints |
| **Database** | ontology.db MANQUANTE | 🔴 CRITIQUE | API Harmonizer crash at startup |
| **Neo4j** | Pipeline CV→Neo4j jamais exécuté | 🔴 CRITIQUE | 1200 lignes code mort |
| **Celery** | 4 tâches définies mais JAMAIS appelées | 🔴 CRITIQUE | Infrastructure inutile (Redis) |
| **Monitoring** | Métriques définies mais jamais collectées | 🟠 MAJEUR | Aucune visibilité |
| **Domain Config** | v2.0 schema jamais utilisé | 🟠 MAJEUR | 350 lignes code mort |

---

## CODE AUDIT SUMMARY

```
Total fichiers Python:    37
Total lignes de code:     ~8000
Code potentiellement mort: ~1500 lignes (18.75%)

CODE MORT PAR MODULE:
  ❌ src/graph_ingestion/ingest.py         780 lignes (jamais lancé)
  ❌ src/enrichment/wikipedia_enricher.py  400 lignes (jamais lancé)
  ❌ src/tasks/*.py                        197 lignes (jamais invoqué)
  ❌ src/db/postgres_*.py                  195 lignes (jamais utilisé)
  ❌ src/domain/config_loader.py           350 lignes (jamais utilisé)
  ❌ src/api/metrics.py                    108 lignes (endpoints stale)
```

---

## POINTS D'ENTRÉE ACTUELS

### ✅ FONCTIONNELS (En production)

```
✓ Harmonizer API (8000)
  - POST /harmonize     - Cache SQLite (ontology.db MANQUANTE!)
  - POST /suggest       - String similarity + LLM optionnel
  
✓ Entity Resolver API (8001)
  - POST /resolve       - Cache SQLite (entity_resolver.db 86KB)
  - enrichment_queue    - Remplie mais jamais consommée
```

### ⚠️ PARTIELLEMENT FONCTIONNELS

```
⚠ CLI Tools (src/cli/*.py)
  - analyze_unmapped.py, densify_ontology.py, night_beast.py, etc.
  - Scripts opérationnels mais jamais lancés en production
  - Dépendent de ontology.db (MANQUANTE)
```

### ❌ COMPLÈTEMENT NON FONCTIONNELS

```
✗ Celery Workers
  - Config définie, Redis lancé, 4 tasks, JAMAIS appelées
  
✗ Neo4j Pipeline
  - 1200 lignes code génération Cypher, jamais exécuté
  - Neo4j pas dans docker-compose
  
✗ Wikipedia Enricher
  - enrichment_queue remplie mais jamais traitée
  - Neo4j updates simulées (use_neo4j=False)
  
✗ Monitoring Prometheus/Grafana
  - Métriques définies, jamais collectées
  - Endpoints existent mais retournent 0
```

---

## DATABASE ARCHITECTURE MISMATCH

```
RÉALITÉ ACTUELLE:

APIs (src/api/main.py, src/entity_resolver/api.py)
  └─ SQLite + in-memory cache
     ├─ ontology.db (MANQUANTE!)
     └─ entity_resolver.db (86KB)

Celery Tasks (src/tasks/*.py)
  └─ PostgreSQL (jamais utilisé)
     ├─ postgres_models.py (tables jamais créées)
     ├─ postgres_connection.py (engine jamais init)
     └─ AsyncTask (jamais instancié)

Docker Services:
  ✓ PostgreSQL:16 (lancé mais inutilisé)
  ✓ Redis:7 (lancé mais inutilisé)
  ✗ Neo4j (pas lancé)


PLAN ORIGINAL (README):
  CV → API → API → Neo4j → Graph Analysis

RÉALITÉ:
  CV → API [OK] → API [OK] → ❌ (jamais appelée)
                                ↓
                           enrichment_queue [vide]
                                ↓
                           Wikipedia enricher [jamais lancé]
                                ↓
                           Neo4j [n'existe pas]
```

---

## RECOMMENDATIONS

### 🔴 CRITIQUE - RÉSOUDRE IMMÉDIATEMENT

#### 1. Créer ontology.db
```bash
python3 src/db/database.py
```
**Pourquoi:** API Harmonizer crash au démarrage sans ce fichier  
**Effort:** 5 minutes

#### 2. Choisir backend DB (SQLite OU PostgreSQL)
**Option A: SQLite** (actuel)
- Garder APIs unchanged
- Supprimer src/db/postgres_*, src/tasks/*, Celery
- Effort: 2 heures

**Option B: PostgreSQL** (recommandé)
- Initialiser postgres schema via init_db()
- Implémenter Celery workers
- Migrer ontology.db → PostgreSQL
- Effort: 1-2 sprints

### 🟠 MAJEUR - RÉSOUDRE DANS LE SPRINT

#### 3. Neo4j: Garder ou Supprimer?
- **Garder:** Ajouter Neo4j à docker-compose, implémenter exécution Cypher (2 sprints)
- **Supprimer:** Delete src/graph_ingestion + src/enrichment (4 heures)

#### 4. Monitoring: Appeler réellement les fonctions
```python
# Dans src/api/main.py et src/entity_resolver/api.py
@app.post("/harmonize")
def harmonize_skills(request):
    # Ajouter tracking calls
    track_harmonization("known" if canonical else "unknown")
    track_cache_metrics("aliases", len(ALIAS_CACHE))
    return response
```

#### 5. Domain Config v2.0: Finir ou Supprimer?
- **Finir:** Intégrer dans APIs (3-5 sprints)
- **Supprimer:** Delete src/domain/ + domains/*.yaml (4 heures) ← RECOMMANDÉ

---

## QUICK WINS (1-2 heures chacun)

1. **Créer ontology.db** - API crash fix
2. **Appeler metrics functions** - Enable monitoring
3. **Mettre à jour README** - Enlever features non déployées
4. **Supprimer domain config** - Réduire complexité
5. **Clarifier Neo4j strategy** - Documenter décision

---

## TESTS STATUS

✓ **21 test files** - Coverage bon pour APIs
✓ **Tests passent** - Avec test databases temporaires
✗ **Tests ≠ Production** - conftest crée DB temp, production crash
✗ **Pas de tests Celery** - AsyncTask jamais testé
✗ **Pas de tests Neo4j** - Entièrement mockés

---

## ARCHITECTURE QUALITY

| Aspect | Rating | Notes |
|--------|--------|-------|
| API Design | ⭐⭐⭐⭐ | FastAPI well-structured, endpoints clear |
| Database | ⭐⭐ | Mismatch (SQLite vs PostgreSQL) |
| Async | ⭐ | Celery defined but not used |
| Testing | ⭐⭐⭐ | Good coverage for used code |
| Documentation | ⭐⭐ | README describes undeployed features |
| DevOps | ⭐⭐⭐ | Docker solid but unnecessary services |

---

## COÛT DE INACTION

**Monthly Infrastructure Cost (Approx):**
- PostgreSQL (unused): ~20-30€
- Redis (unused): ~5-10€
- **Total waste: 25-40€/month** ← Can eliminate with small refactor

**Development Cost:**
- 1500 LOC code mort = 10-15% more complexity for devs
- Unclear status (working vs dead) = confusion, slower debugging
- Extra test maintenance for dead code

---

## NEXT STEPS (Prioritized)

### Week 1
- [ ] Créer ontology.db (5 min)
- [ ] Tester APIs avec DB (30 min)
- [ ] Décider SQLite vs PostgreSQL (1h meeting)
- [ ] Mettre à jour README avec réalité (2h)

### Week 2
- [ ] Supprimer ou finaliser domain config (4h)
- [ ] Implémenter monitoring metrics calls (4h)
- [ ] Nettoyer docker-compose (unused services) (2h)

### Sprint suivant
- [ ] Implémenter Neo4j OU supprimer pipeline (sprint-length decision)
- [ ] Finir PostgreSQL migration OU enlever Celery (sprint-length decision)

---

## CONCLUSION

Le projet a une **base solide** (2 APIs fonctionnelles, tests) mais souffre d'une **déploiement incomplet** (code prévisionniste jamais finalisé).

**Recommandation:** Faire un sprint de "technical cleanup" pour:
1. Fixer données manquantes (ontology.db)
2. Simplifier architecture (choisir 1 DB, 1 async pattern)
3. Nettoyer code mort (supprimer ou finir)
4. Clarifier documentation (réalité vs aspiration)

Effort estimé: **3-5 jours pour réduire technicaldebt de 25%**

---

**Rapport complet:** Voir TECH_AUDIT_FINDINGS.md (1300+ lignes d'analyse détaillée)
