# JENEZIS Cleanup Checklist - Actions Concrètes

**Généré:** 26 octobre 2025
**Audit complet:** Voir `docs/AUDIT_COMPLET.md`

---

## PHASE 1: SUPPRESSION IMMÉDIATE (30 min)

### Fichiers à supprimer

```bash
# 1. Fichier nginx avec ancien nom du projet
rm /Users/juliendabert/Desktop/JENEZIS/docker/nginx/sites-enabled/erwin-harmonizer.conf

# 2. Documentation obsolète (Genesis non-implémenté)
rm /Users/juliendabert/Desktop/JENEZIS/README_GENESIS.md

# 3. Checklist temporaire du 48H sprint
rm /Users/juliendabert/Desktop/JENEZIS/COUNTDOWN.md

# 4. Cache Python (régénéré automatiquement)
find /Users/juliendabert/Desktop/JENEZIS -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find /Users/juliendabert/Desktop/JENEZIS -name "*.pyc" -delete 2>/dev/null
```

**Impact:** +0.2 MB libérés, zéro impact fonctionnel

---

## PHASE 2: SCRIPT DE MIGRATION À ARCHIVER (10 min)

### Action: Archiver plutôt que supprimer

```bash
# Créer dossier archive
mkdir -p /Users/juliendabert/Desktop/JENEZIS/docs/migration_scripts

# Archiver le script de migration SQLite → PostgreSQL
mv /Users/juliendabert/Desktop/JENEZIS/temp_scripts/migrate_sqlite_to_postgres.py \
   /Users/juliendabert/Desktop/JENEZIS/docs/migration_scripts/

# Documenter
cat > /Users/juliendabert/Desktop/JENEZIS/docs/migration_scripts/README.md << 'EOFMIG'
# Migration Scripts Archive

## migrate_sqlite_to_postgres.py
- **Contexte:** Migration JENEZIS v1.x (SQLite) → v2.0 (PostgreSQL)
- **Date:** 2025-10-26
- **Status:** Supposément complétée - archivé pour référence
- **Utilisation future:** Non prévue (migration one-time)
EOFMIG

# Supprimer le dossier temp vide si c'était le seul fichier
rmdir /Users/juliendabert/Desktop/JENEZIS/temp_scripts 2>/dev/null || true
```

---

## PHASE 3: DÉTERMINE SCHÉMA BD ACTIF (CRITIQUE!)

### Diagnostic: Lequel est utilisé en production?

```bash
# Chercher les imports actuels
echo "=== Imports de genesis_models ==="
grep -r "from.*genesis_models\|import.*genesis_models" /Users/juliendabert/Desktop/JENEZIS/src --include="*.py"

echo -e "\n=== Imports de postgres_models ==="
grep -r "from.*postgres_models\|import.*postgres_models" /Users/juliendabert/Desktop/JENEZIS/src --include="*.py"

echo -e "\n=== Dans les migrations Alembic ==="
grep -r "from.*models\|import.*models" /Users/juliendabert/Desktop/JENEZIS/alembic --include="*.py"
```

### Décision basée sur résultats:

- **Si genesis_models est actif:**
  - Archiver postgres_models.py → `/docs/migration_scripts/postgres_models.py.legacy`
  - Documenter la migration dans `/docs/DATABASE_SCHEMA.md`

- **Si postgres_models est encore actif:**
  - Mettre à jour le docstring: "for Erwin Harmonizer" → "for JENEZIS - Ontology Engine"
  - Vérifier pourquoi genesis_models n'est pas en production
  - Documenter la stratégie de transition

---

## PHASE 4: FUSION DES TESTS DUPLIQUÉS (2-3 heures)

### Tests à fusionner:

| Feature | Fichiers | Action |
|---------|----------|--------|
| **analyze_unmapped** | `test_cli_analyze_unmapped.py` (249 L) + `test_cli_analyze_unmapped_refactored.py` (374 L) | Fusionner en 1 fichier, supprimer "_refactored" |
| **densify_ontology** | `test_cli_densify_ontology.py` (332 L) + `test_cli_densify_ontology_refactored.py` (657 L) | Fusionner en 1 fichier, supprimer "_refactored" |
| **night_beast** | `test_night_beast.py` + `test_night_beast_comprehensive.py` | Fusionner en 1 fichier, supprimer "_comprehensive" |
| **mass_densify** | `test_mass_densify.py` + `test_mass_densify_comprehensive.py` | Fusionner en 1 fichier, supprimer "_comprehensive" |
| **metrics** | `test_metrics.py` + `test_metrics_direct.py` | Fusionner ou décider lequel garder |

### Script de fusion:

```bash
#!/bin/bash
# AVANT de fusionner:
# 1. Vérifier quels cas de test sont dans chaque fichier
# 2. Identifier les doublons
# 3. Merger les cas de test pertinents de "_refactored"/comprehensive" dans la version principale

# Exemple pour analyze_unmapped:
cd /Users/juliendabert/Desktop/JENEZIS/tests/unit

# Backup des originaux
cp test_cli_analyze_unmapped.py test_cli_analyze_unmapped.py.backup
cp test_cli_analyze_unmapped_refactored.py test_cli_analyze_unmapped_refactored.py.backup

# Analyser les deux fichiers
echo "=== Cas de test dans version originale ==="
grep "^def test_" test_cli_analyze_unmapped.py | wc -l

echo "=== Cas de test dans version refactored ==="
grep "^def test_" test_cli_analyze_unmapped_refactored.py | wc -l

# Différences:
echo "=== Cas de test UNIQUEMENT dans refactored ==="
comm -13 <(grep "^def test_" test_cli_analyze_unmapped.py | sort) \
         <(grep "^def test_" test_cli_analyze_unmapped_refactored.py | sort)
```

### Actions spécifiques:

```bash
# APRÈS fusion (exemple):
rm /Users/juliendabert/Desktop/JENEZIS/tests/unit/test_cli_analyze_unmapped_refactored.py
rm /Users/juliendabert/Desktop/JENEZIS/tests/unit/test_cli_densify_ontology_refactored.py
# ... etc pour tous les "_refactored" et "_comprehensive"
```

**Gain:** 1,612 lignes de test consolidées, maintenabilité améliorée

---

## PHASE 5: METTRE À JOUR RÉFÉRENCES "ERWIN"

### Fichiers à modifier:

#### 1. `/src/db/postgres_models.py` (ligne 2)

**Avant:**
```python
"""
PostgreSQL SQLAlchemy models for Erwin Harmonizer.
```

**Après:**
```python
"""
PostgreSQL SQLAlchemy models for JENEZIS - Ontology Genesis Engine.

Legacy schema v1.x - See genesis_models.py for v2.0+ universal schema.
```

#### 2. `/EXECUTION_48H.md` (lignes 15, 38)

**Avant:**
```bash
pg_dump -U erwin -d erwin_harmonizer > backups/pre_genesis_$(date +%Y%m%d_%H%M%S).sql
DATABASE_URL="postgresql://erwin:erwin@localhost:5433/erwin_genesis_test"
```

**Après:**
```bash
pg_dump -U jenezis -d jenezis > backups/pre_genesis_$(date +%Y%m%d_%H%M%S).sql
DATABASE_URL="postgresql://jenezis:jenezis@localhost:5433/jenezis_test"
```

---

## PHASE 6: CONSOLIDATION DOCUMENTATION

### Objectif: UN SEUL README clair

#### Option A: Garder `README.md` (recommandé)

```bash
# Supprimer les doublons
rm /Users/juliendabert/Desktop/JENEZIS/README_JENEZIS.md
rm /Users/juliendabert/Desktop/JENEZIS/QUICK_START_LOCAL.md

# Archiver si utile pour référence
mkdir -p /Users/juliendabert/Desktop/JENEZIS/docs/deprecated_docs
mv /Users/juliendabert/Desktop/JENEZIS/QUICK_START_LOCAL.md \
   /Users/juliendabert/Desktop/JENEZIS/docs/deprecated_docs/
```

#### Option B: Créer une nouvelle version

Si vous préférez réécrire le README depuis zéro:

```bash
# Renommer temporairement
mv README.md README_v3.3_backup.md
mv README_JENEZIS.md README.md

# Éditer le nouveau README.md avec:
# - Version clairement indiquée (v3.3 ou Genesis v2.0)
# - Table des matières
# - Installation simple (Docker vs Local)
# - Premiers pas rapides
# - Liens vers docs détaillées
```

---

## PHASE 7: CRÉER DOCUMENTATION ARCHITECTURE

### Créer `/docs/ARCHITECTURE.md`

```markdown
# JENEZIS Architecture Documentation

## Versioning

- **v3.3:** Current production (SQLite + PostgreSQL hybrid)
- **Genesis v2.0:** In-progress universal domain-agnostic system

## Database Schema

### Active Schema
- **File:** `src/db/postgres_models.py` (v1.x)
- **Tables:** Skills, Aliases, Hierarchy, CanonicalEntity, EntityAlias, EnrichmentQueue
- **Database:** PostgreSQL 16 + pgvector

### Migration Path (v2.0)
- **File:** `src/db/genesis_models.py` (not yet deployed)
- **Tables:** DomainConfig, CanonicalNode, NodeAlias, NodeRelationship, EnrichmentQueue
- **Status:** In review - will replace above schema

## CLI Conventions

...
```

---

## PHASE 8: VÉRIFICATION SÉCURITÉ

### Vérifier `.gitignore`

```bash
cat /Users/juliendabert/Desktop/JENEZIS/.gitignore | grep -E "\.env|\.pyc|__pycache__|\.sqlite"
```

**Attendu:**
```
.env
.env.production
*.pyc
__pycache__/
*.db
*.sqlite3
```

### Vérifier que `.env.production` n'est pas committé

```bash
cd /Users/juliendabert/Desktop/JENEZIS
git ls-files --cached | grep "\.env"
```

---

## PHASE 9: VÉRIFIER GRAFANA CONFIG

### Décider du sort de SQLite datasource

```bash
# Vérifier si utilisé
grep -r "sqlite" /Users/juliendabert/Desktop/JENEZIS/grafana-provisioning/

# Si non-utilisé après migration PostgreSQL:
rm /Users/juliendabert/Desktop/JENEZIS/grafana-provisioning/datasources/sqlite.yml

# Ajouter PostgreSQL datasource si absent:
# (Vérifier qu'il existe dans docker-compose ou file provisioning)
```

---

## CHECKLIST DE VALIDATION

Après chaque phase, vérifier:

- [ ] Tests passent toujours: `pytest /Users/juliendabert/Desktop/JENEZIS/tests`
- [ ] Pas d'imports cassés après suppression de fichiers
- [ ] Git status montre les changements attendus uniquement
- [ ] Documentation reste à jour
- [ ] Pas de références cassées dans README

---

## COMMANDES DE VALIDATION GLOBALES

```bash
# 1. Vérifier qu'aucun fichier supprimé n'est importé
echo "=== Vérifier genesis_models ==="
python -c "from src.db.genesis_models import Base" && echo "✓" || echo "✗"

echo "=== Vérifier postgres_models ==="
python -c "from src.db.postgres_models import Base" && echo "✓" || echo "✗"

# 2. Lancer les tests
cd /Users/juliendabert/Desktop/JENEZIS
poetry run pytest tests/ -v --tb=short

# 3. Vérifier liens dans documentation
grep -r "README_GENESIS\|COUNTDOWN" /Users/juliendabert/Desktop/JENEZIS/docs
grep -r "README_GENESIS\|COUNTDOWN" /Users/juliendabert/Desktop/JENEZIS/README.md

# 4. Vérifier que les domaines sont accessibles
poetry run python -c "from src.domain.config_loader import load_domain_config; load_domain_config('it_skills')"
```

---

## TIMING ESTIMÉ

| Phase | Temps | Cumulé |
|-------|-------|--------|
| 1. Suppression immédiate | 30 min | 30 min |
| 2. Archivage script migration | 10 min | 40 min |
| 3. Diagnostic BD (CRITIQUE) | 30 min | 1h 10min |
| 4. Fusion tests | 2-3 h | 4-5h |
| 5. Mettre à jour références | 30 min | 4h 30min-5h 30min |
| 6. Consolidation docs | 1h | 5h 30min-6h 30min |
| 7. Documentation architecture | 1h | 6h 30min-7h 30min |
| 8. Sécurité / Grafana | 30 min | 7h-8h |

**Total:** 1-2 jours de travail ciblé

---

## NOTES IMPORTANTES

1. **AVANT DE SUPPRIMER:** Committer l'état actuel dans git
   ```bash
   git add -A && git commit -m "backup: pre-cleanup state"
   ```

2. **TESTER APRÈS CHAQUE PHASE** - Ne pas faire toutes les suppressions d'un coup

3. **UTILISER GIT POUR TRACKING:**
   ```bash
   git status
   git diff
   ```

4. **GARDER LES BACKUPS:** Les fichiers archivés dans `/docs/migration_scripts/` peuvent être utiles pour audit

5. **DOCUMENTER LES DÉCISIONS:** Surtout la #3 (lequel des schémas BD est actif!)

---

**Généré par:** Audit JENEZIS
**Date:** 2025-10-26
**Voir aussi:** `docs/AUDIT_COMPLET.md`
