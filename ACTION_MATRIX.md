# AUDIT ACTION MATRIX - Quoi faire et quand

## PRIORISATION PAR IMPACT & EFFORT

```
IMPACT
  ^
  |  [Q2] HIGH IMPACT      [Q1] QUICK WINS (DO FIRST!)
  |      MEDIUM EFFORT           EASY WINS
  |
  |      - Neo4j setup      - Create ontology.db
  |      - Postgres/Celery  - Call metrics functions
  |      - Wikipedia enrich - Update README
  |      - Monitoring full  - Delete domain config
  |
  |  [Q3] LOW IMPACT        [Q4] RECONSIDER
  |      MEDIUM EFFORT           HARD TO JUSTIFY
  |
  |      - Refactor CLI     - Implement v2.0 schema
  |      - Add more tests   - Full Prometheus setup
  +-----------------------------------> EFFORT
```

---

## ACTIONABLE ITEMS (Par sévérité)

### 🔴 CRITIQUE (Jour 1 - 1-2 heures total)

| # | Tâche | Effort | Impact | Action |
|---|-------|--------|--------|--------|
| 1 | Créer ontology.db | 5 min | CRITIQUE | `python3 src/db/database.py` |
| 2 | Tester Harmonizer API | 30 min | CRITIQUE | Lancer docker, POST /harmonize |
| 3 | Documenter statut réel | 30 min | CRITIQUE | Créer fichier de status |

**Pourquoi:** Sans ontology.db, API Harmonizer crash au démarrage  
**Preuve:** `src/api/main.py:151` - `if not ALIAS_CACHE` → fail

---

### 🟠 MAJEUR (Semaine 1 - 2 sprints max)

#### Décision A: Database Architecture

| Option | SQLite | PostgreSQL |
|--------|--------|------------|
| Garder APIs | ✓ Unchanged | ✓ Migrate |
| Utiliser Celery | ✗ No async | ✓ Yes (enrich, suggest) |
| Scalabilité | ⭐ Limited | ⭐⭐⭐⭐ |
| Effort | 2h cleanup | 1-2 sprints |
| Coût | $0 extra | $25-40€/month |
| **Recommandation** | ← Pas recommandé | **← DO THIS** |

**Action:** 1 heure meeting pour décider

#### Décision B: Neo4j

| Option | Garder | Supprimer |
|--------|--------|-----------|
| Pipeline | ✓ Complet | ✗ None |
| Code génération | 780 lines | Delete |
| Wikipedia enrich | ✓ Actif | ✗ None |
| Effort | 2 sprints | 4h delete |
| **Recommandation** | **← DO THIS (if time)** | ← Good if urgent |

**Action:** Décider après décision Database

#### Décision C: Domain Config v2.0

| Option | Garder | Supprimer |
|--------|--------|-----------|
| YAML files | 3 files ready | Delete |
| Code | 350 lines | Delete |
| Effort | 3-5 sprints finish | 4h delete |
| Utilité | Future multidomains | N/A - not used |
| **Recommandation** | ← Maybe future | **← Delete now** |

**Action:** Delete (reduce technical debt)

---

### 🟡 IMPORTANT (Semaine 2 - 1 sprint)

| # | Tâche | Effort | Status | Fix |
|---|-------|--------|--------|-----|
| 1 | Enable Monitoring | 4h | Partial | Call track_* functions in APIs |
| 2 | CLI Tools docs | 2h | Missing | Document how to run |
| 3 | Docker cleanup | 2h | Bloated | Remove unused services |
| 4 | README sync | 2h | Misleading | Match features vs reality |

---

### 🟢 NICE TO HAVE (Sprint +2)

- [ ] Full Prometheus + Grafana integration
- [ ] Celery workers with proper scaling
- [ ] Neo4j GraphQL API
- [ ] Advanced semantic search with pgvector

---

## IMPLEMENTATION CHECKLIST

### Week 1: Stabilize

- [ ] Day 1
  - [ ] Create ontology.db (5 min)
  - [ ] Test API health (15 min)
  - [ ] Document findings (30 min)
  
- [ ] Day 2-3: Decision meeting
  - [ ] SQLite vs PostgreSQL (1h discussion)
  - [ ] Neo4j in scope? (30 min decision)
  - [ ] Domain config decision (30 min)
  
- [ ] Day 4-5: Quick wins
  - [ ] Update README (delete non-existent features)
  - [ ] Delete domain config code (if decided)
  - [ ] Document decisions in ADR

### Week 2: Implement

**If PostgreSQL chosen:**
- [ ] Initialize postgres schema (init_db)
- [ ] Implement Celery workers
- [ ] Write migration script for ontology.db
- [ ] Implement metrics collection

**If SQLite kept:**
- [ ] Delete src/db/postgres_*
- [ ] Delete src/tasks/*
- [ ] Remove PostgreSQL from docker-compose
- [ ] Remove Redis from docker-compose

**Parallel tasks:**
- [ ] Enable monitoring (call track_* functions)
- [ ] Add CLI documentation
- [ ] Update docker-compose (remove unused services)

### Week 3+: Optional

**If Neo4j in scope:**
- [ ] Add Neo4j to docker-compose
- [ ] Implement cypher execution in ingest.py
- [ ] Implement wikipedia enricher worker
- [ ] Test full pipeline

---

## RISK ASSESSMENT

### High Risk (Do Not Skip)

| Risk | Mitigation |
|------|-----------|
| ontology.db missing | Create it Day 1, test immediately |
| Tests ≠ Production | Add integration tests with real DB |
| Undefined architecture | Make SQLite vs PG decision immediately |

### Medium Risk

| Risk | Mitigation |
|------|-----------|
| Celery code unused | Document decision (keep or delete) |
| Neo4j unfinished | Decide (launch or delete) |
| Metrics not collected | Add function calls (1-2h) |

### Low Risk

| Risk | Mitigation |
|------|-----------|
| Domain config unused | Delete it (reduce complexity) |
| Monitoring profiles | Keep optional, not critical |
| CLI tools not in Docker | Document local usage |

---

## EFFORT ESTIMATION

### Minimal Path (3-5 days)

```
- Create ontology.db              5 min
- Choose database architecture    2 hours (meeting)
- Delete unused code              4 hours
- Update documentation            2 hours
- Enable monitoring calls         2 hours
- Test everything                 4 hours

Total: 14 hours ~ 2 person-days
```

### Recommended Path (1-2 sprints)

```
- All of Minimal Path            14 hours
- Implement Celery workers       20 hours
- Test Celery integration        8 hours
- Migrate ontology to Postgres   8 hours
- Prometheus/Grafana setup       12 hours

Total: 62 hours ~ 1.5 sprints (2 people)
```

### Full Implementation (3-4 sprints)

```
- All of Recommended Path        62 hours
- Neo4j integration             40 hours
- Wikipedia enricher            20 hours
- Full monitoring dashboard     16 hours
- Advanced features (GQL API)   24 hours

Total: 162 hours ~ 4 sprints (2 people)
```

---

## GO/NO-GO DECISION MATRIX

### By Monday (End of Audit)

**Decision:** SQLite vs PostgreSQL

- [ ] PostgreSQL (recommended) → Go with Celery path
- [ ] SQLite (simpler) → Delete Celery/Postgres code

**Decision:** Neo4j Scope

- [ ] Include in scope → Plan 2 extra sprints
- [ ] Defer to future → Delete code, document ADR

**Decision:** Domain Config v2.0

- [ ] Keep & finish → Plan 3-5 sprints future
- [ ] Delete now → Execute cleanup (4h)

---

## SUCCESS METRICS

After Week 1:
- [ ] Harmonizer API boots and responds (ontology.db exists)
- [ ] All tests pass against real databases
- [ ] Architecture decisions documented in ADRs

After Week 2:
- [ ] Monitoring metrics actually collected
- [ ] Unused code either deleted or scheduled
- [ ] Docker services appropriate to scope

After Sprint +1:
- [ ] Database architecture consistent
- [ ] All Celery tasks either working or removed
- [ ] Code quality metrics improve (less dead code)
- [ ] Technical debt reduced by 25%+

---

## OWNER ASSIGNMENTS

Suggestion (adjust by team):

| Area | Owner | Time |
|------|-------|------|
| ontology.db creation | Junior | 15 min |
| Architecture decision | Tech Lead | 2h |
| Database migration | Mid-level | 1 sprint |
| Neo4j implementation | Senior | 2 sprints |
| Testing & QA | QA Engineer | 1 sprint |
| Documentation | Tech Writer | 1 week |

---

## REFERENCE DOCUMENTS

- **Full Audit:** TECH_AUDIT_FINDINGS.md (1300 lines)
- **This Summary:** AUDIT_EXECUTIVE_SUMMARY.md
- **This Matrix:** ACTION_MATRIX.md

---

## QUESTIONS TO ASK LEADERSHIP

1. **Database choice:** Do you want scalability (PG) or simplicity (SQLite)?
2. **Neo4j:** Is knowledge graph a core feature or nice-to-have?
3. **Timeline:** 1 week stabilize + optional extended? Or full cleanup now?
4. **Team:** Who's available for this? Senior needed for PG/Celery?

---

**Last updated:** 26 October 2025  
**Status:** Awaiting decision on critical items
