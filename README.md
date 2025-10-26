# JENEZIS - Knowledge Graph System v3.3 🚀

Système complet de construction et d'exploitation de graphe de connaissances pour l'analyse avancée des talents. De l'harmonisation des compétences à la détection de profils stratégiques via Neo4j.

## 🐳 Déploiement Docker Production-Ready

Le système est désormais **100% containerisé** avec une architecture Docker sécurisée et stable :

### Déploiement Rapide

```bash
# Configuration sécurisée
cp .env.production .env
# Éditer .env avec vos credentials

# Développement (avec hot reload)
docker-compose up -d

# Production (avec nginx + monitoring)
docker-compose --profile production --profile monitoring up -d

# APIs disponibles:
# - Harmonizer API: http://localhost:8000/docs
# - Entity Resolver API: http://localhost:8001/docs
# - Monitoring: http://localhost:3000 (Grafana)
```

### Architecture Docker

- **Multi-stage builds** optimisés pour la production
- **Gunicorn + Uvicorn workers** pour la haute disponibilité
- **Nginx reverse proxy** avec rate limiting et SSL/TLS ready
- **Health checks** intégrés pour orchestration
- **Volumes persistants** pour bases de données SQLite
- **Prometheus + Grafana** pour monitoring complet
- **Authentication Bearer token** pour endpoints admin

### Sécurité Renforcée

✅ **Zero hardcoded credentials** - Variables d'environnement obligatoires
✅ **CORS configuré** par environnement (pas de wildcard)
✅ **Non-root containers** - Sécurité par défaut
✅ **Rate limiting** nginx pour protection API
✅ **Security headers** complets
✅ **SQL injection** protection intégrée

## 📊 État actuel du système

### Ontologie de compétences
- **329 compétences canoniques** (+22% depuis documentation)
- **1,678 aliases mappés** (+165% croissance massive!)
- **843 relations hiérarchiques** (+122% depuis v1)
- **87,793 compétences non mappées identifiées** (conquête active via NIGHT BEAST)

### Base d'entités
- **30 entreprises** françaises et internationales
- **13 écoles/universités** prestigieuses
- **174 alias d'entités**
- **File d'enrichissement automatique** via Wikipedia

### Pipeline complet
- **CV → Graph Neo4j** opérationnel
- **Enrichissement automatique** des entités
- **Résolution d'entités** en temps réel

## 🏗️ Architecture

```
JENEZIS/
├── src/
│   ├── api/                      # API FastAPI Harmonizer
│   │   └── main.py              # Endpoints: /harmonize, /suggest, /stats
│   ├── cli/                     # Outils CLI
│   │   ├── analyze_unmapped.py  # Analyse des skills non mappés
│   │   ├── densify_ontology.py  # Enrichissement par LLM
│   │   ├── mass_densify.py      # THE BEAST - Mode automatique
│   │   ├── export_entity_review.py # Export entités pour revue humaine
│   │   └── import_entity_enrichment.py # Import enrichissements validés
│   ├── db/                      # Gestion base de données
│   │   ├── database.py          # Schéma SQLite
│   │   └── optimize_indexes.py  # Optimisation des performances
│   ├── entity_resolver/         # Service de résolution d'entités
│   │   ├── api.py              # API FastAPI (port 8001)
│   │   └── db_init.py          # Initialisation base entités
│   ├── graph_ingestion/         # Pipeline d'ingestion graphe
│   │   └── ingest.py           # Pipeline CV → Neo4j
│   ├── enrichment/              # Enrichissement des entités
│   │   └── wikipedia_enricher.py # Enrichissement via Wikipedia
│   └── config.py                # Configuration centralisée
├── data/
│   ├── databases/               # Bases de données
│   │   ├── ontology.db         # Base skills SQLite (WAL mode, 9 index)
│   │   └── entity_resolver.db  # Base entités SQLite (WAL mode, 10 index)
│   ├── candidats_competences.csv # 623K relations candidat-compétence
│   └── output/                  # Exports générés
└── data/
    ├── examples/
    │   └── cv_example.json     # Exemple de CV parsé
    └── output/
        └── cypher_queries_example.txt  # Requêtes générées pour Neo4j
```

## 🚀 Installation

### Option 1: Docker (Recommandé)

```bash
# Cloner le repo
git clone <repo-url>
cd JENEZIS

# Configuration
cp .env.production .env
# Générer token sécurisé
echo "API_AUTH_TOKEN=$(openssl rand -hex 32)" >> .env
# Éditer .env avec vos credentials

# Déploiement
docker-compose build
docker-compose up -d

# Vérifier la santé
curl http://localhost:8000/health
curl http://localhost:8001/health
```

### Option 2: Développement Local

```bash
# Installer les dépendances avec Poetry
poetry install

# Configuration environnement
cp .env.example .env
# Éditer .env avec vos credentials:
# - OPENAI_API_KEY (requis pour enrichissement LLM)
# - NEO4J_PASSWORD (requis pour graph ingestion)
# - API_AUTH_TOKEN (pour sécurité admin endpoints)

# Initialiser la base de données
poetry run python src/db/database.py

# Optimiser les index pour la performance
poetry run python src/db/optimize_indexes.py
```

## 🔥 Démarrage rapide

### 1. Lancer les services

#### Avec Docker (Production)
```bash
# Déploiement complet avec monitoring
docker-compose --profile production --profile monitoring up -d

# Vérification
docker-compose ps
curl http://localhost:8000/health
```

#### Développement Local
```bash
# Terminal 1: API Harmonizer (port 8000)
poetry run uvicorn src.api.main:app --reload

# Terminal 2: API Entity Resolver (port 8001)
poetry run uvicorn src.entity_resolver.api:app --reload --port 8001

# APIs disponibles:
# - Harmonizer: http://127.0.0.1:8000/docs
# - Entity Resolver: http://127.0.0.1:8001/docs
```

### 2. Pipeline CV vers Neo4j

```bash
# Traiter un CV et générer les requêtes Cypher
poetry run python src/graph_ingestion/ingest.py

# Enrichir automatiquement les entités nouvelles
poetry run python src/enrichment/wikipedia_enricher.py

# Export des entités nécessitant validation manuelle
poetry run python src/cli/export_entity_review.py

# Import des enrichissements validés
poetry run python src/cli/import_entity_enrichment.py

# Charger dans Neo4j
cypher-shell < cypher_queries.txt
```

### 3. Enrichir l'ontologie (THE BEAST MODE)

```bash
# Analyse des skills non mappés
poetry run python src/cli/analyze_unmapped.py

# Densification par batch
poetry run python src/cli/densify_ontology.py 100

# Mode BEAST - Automatique progressif
poetry run python src/cli/mass_densify.py --auto

# Monitoring en temps réel
./monitor.sh
```

## 📡 API Endpoints

### `POST /harmonize`
Harmonise une liste de compétences brutes vers leur forme canonique.

```bash
curl -X POST "http://127.0.0.1:8000/harmonize" \
  -H "Content-Type: application/json" \
  -d '{"skills": ["react.js", "node js", "typescript"]}'
```

### `POST /suggest` [NEW v2]
Suggère les N skills canoniques les plus proches pour un skill inconnu.

```bash
curl -X POST "http://127.0.0.1:8000/suggest" \
  -H "Content-Type: application/json" \
  -d '{"skill": "machine learning", "top_k": 3, "use_llm": false}'
```

### `GET /stats`
Retourne les métriques de l'ontologie en temps réel.

### `POST /admin/reload`
Recharge le cache après enrichissement (zero-downtime).

## 🔧 Pipeline d'enrichissement

### Workflow Skills

```
1. ANALYZE → analyze_unmapped.py
   ↓ Génère: unmapped_skills_analysis.csv (87K skills)

2. DENSIFY → densify_ontology.py N
   ↓ Auto-approve si fréquence > 1000
   ↓ Génère: needs_human_review.csv

3. EXPORT → export_human_review.py (automatique)
   ↓ Génère: human_review_YYYY-MM-DD_HH-MM-SS.csv

4. VALIDATE → Validation manuelle Excel
   ↓ Marquer approve=OUI/NON

5. IMPORT → import_approved.py
   ↓ Importe les skills approuvés

6. RELOAD → curl -X POST /admin/reload
   ↓ Active les changements
```

### Workflow Entités (Companies/Schools)

```
1. RESOLVE → Entity Resolver API détecte les nouvelles entités
   ↓ Status: PENDING dans enrichment_queue

2. ENRICH → wikipedia_enricher.py
   ↓ Trouve sur Wikipedia → COMPLETED
   ↓ Pas trouvé → NEEDS_REVIEW

3. EXPORT → export_entity_review.py
   ↓ Génère: entity_review_YYYY-MM-DD_HH-MM-SS.csv

4. VALIDATE → Recherche manuelle Wikipedia + validation
   ↓ Remplir wikipedia_url, description, approve=OUI

5. IMPORT → import_entity_enrichment.py
   ↓ Met à jour les métadonnées

6. UPDATE NEO4J → wikipedia_enricher.py (sans --simulate)
   ↓ Propage les enrichissements au graphe
```

## 🧠 Human Review - Guide d'audit stratégique

### Principes de validation

L'enrichissement par LLM génère 80% de propositions correctes, mais nécessite une **validation architecturale** pour garantir la cohérence de l'ontologie.

### Erreurs communes à corriger

#### 1. **Parents incohérents**
```
❌ dev front-end → backend
✅ dev front-end → frontend, javascript

Règle: Un skill ne peut pas être enfant de son opposé sémantique
```

#### 2. **Confusion rôle/outil/concept**
```
❌ webdesigner → adobe_photoshop
✅ webdesign → ui_ux, design

Règle: Les rôles ne sont pas des sous-catégories d'outils
```

#### 3. **Manque d'abstraction**
```
❌ ansible → administrateur_systeme, ci_cd, cloud
✅ ansible → configuration_management, automation

Règle: Privilégier les catégories conceptuelles sur les usages
```

#### 4. **Duplications conceptuelles**
```
❌ ui_design, ux_design, design_ux_ui (3 entrées)
✅ ui_ux (1 entrée canonique, les autres en alias)

Règle: Fusionner les concepts identiques
```

### Grille de validation

| Critère | Question de validation | Exemple |
|---------|------------------------|---------|
| **Cohérence sémantique** | Le parent est-il logiquement supérieur? | `bootstrap` est un framework CSS, pas un build_tool |
| **Niveau d'abstraction** | Le parent est-il assez abstrait? | `pl_sql` → `sql` plutôt que `backend` |
| **Unicité** | Ce concept existe-t-il déjà sous un autre nom? | Fusionner `ui_design` et `ux_design` |
| **Nature vs Usage** | Ai-je classé par nature ou par usage? | `confluence` est un `collaboration_tool`, pas un `project_management_tool` |

### Process de validation Excel

1. Ouvrir `human_review_YYYY-MM-DD_HH-MM-SS.csv`
2. Pour chaque ligne:
   - **OUI** : La proposition est correcte ou acceptable
   - **NON** : À rejeter (incohérent, doublon, etc.)
   - **Vide** : À revoir plus tard
3. Sauvegarder et importer: `poetry run python src/cli/import_approved.py`

## 📈 Métriques de performance

- **API Latency**: <10ms pour les skills en cache
- **Enrichissement LLM**: ~2s par skill
- **Batch processing**: ~100 skills en 5-6 minutes
- **Taux d'auto-approbation**: ~40% (skills > 1000 occurrences)
- **Précision après validation**: >95%

## 🧪 Tests & Qualité de Code

### Infrastructure de Test Complète ✅

```bash
# Installation des dépendances de développement
poetry install --with dev

# Configuration des pre-commit hooks (formatage, linting, sécurité)
poetry run pre-commit install

# Lancer tous les tests avec couverture
poetry run pytest --cov=src --cov-report=html

# Tests par catégorie
poetry run pytest -m unit        # Tests unitaires
poetry run pytest -m integration # Tests d'intégration
poetry run pytest -m api         # Tests API

# Rapport de couverture
open htmlcov/index.html  # Ouvre le rapport HTML
```

### Outils de Qualité de Code

```bash
# Formatage automatique (Black)
poetry run black src/ tests/

# Linting (Ruff - ultra rapide)
poetry run ruff check src/ tests/

# Type checking (MyPy)
poetry run mypy src/

# Scan de sécurité (Bandit)
poetry run bandit -r src/

# Tout vérifier avant commit
poetry run pre-commit run --all-files
```

### CI/CD avec GitHub Actions

Le pipeline CI/CD automatique inclut:
- ✅ Tests sur Python 3.9-3.13
- ✅ Support multi-OS (Linux, macOS, Windows)
- ✅ Vérification de qualité du code
- ✅ Scan de sécurité
- ✅ Rapport de couverture (minimum 80%)
- ✅ Build et validation du package

## 🧠 Exploitation Avancée du Graphe Neo4j

### Requêtes Cypher Stratégiques pour l'Analyse des Talents

Une fois vos données ingérées dans Neo4j, le vrai pouvoir commence. Voici comment transformer votre graphe en intelligence actionnable :

#### 1. **Détecte les Ponts Technologiques** 🌉

Identifiez les candidats qui maîtrisent plusieurs écosystèmes techniques - ces profils rares qui peuvent faire le lien entre équipes.

```cypher
// Trouve les candidats qui maîtrisent à la fois Java et Python
MATCH (c:Candidat)-[:A_TRAVAILLE]->(:Experience)-[:A_UTILISE]->(tech1:Competence)
WHERE tech1.name = 'java' OR
      EXISTS((tech1)-[:EST_UN_TYPE_DE*]->(:Competence {name: 'java'}))
WITH c
MATCH (c)-[:A_TRAVAILLE]->(:Experience)-[:A_UTILISE]->(tech2:Competence)
WHERE tech2.name = 'python' OR
      EXISTS((tech2)-[:EST_UN_TYPE_DE*]->(:Competence {name: 'python'}))
RETURN c.id, c.firstName, c.lastName, c.email
```

#### 2. **Identifie les Experts Trans-sectoriels** 🏢

Découvrez les talents qui ont navigué entre différents secteurs - excellents pour l'innovation cross-industry.

```cypher
// Candidats avec expérience dans plusieurs secteurs
// (Nécessite l'enrichissement des entreprises avec propriété 'sector')
MATCH (c:Candidat)-[:A_TRAVAILLE]->(:Experience)-[:CHEZ]->(e:Entreprise)
WHERE e.sector IS NOT NULL
WITH c, COUNT(DISTINCT e.sector) AS nb_secteurs,
     COLLECT(DISTINCT e.sector) AS secteurs,
     COLLECT(DISTINCT e.name) AS entreprises
WHERE nb_secteurs > 1
RETURN c.id, c.firstName, c.lastName,
       nb_secteurs, secteurs, entreprises
ORDER BY nb_secteurs DESC
```

#### 3. **Calcule les Scores de Centralité** ⭐

Utilisez Neo4j Graph Data Science pour identifier les candidats "hub" de votre écosystème.

```cypher
// Créer une projection pour l'analyse (nécessite Neo4j GDS)
CALL gds.graph.project(
  'talent-network',
  ['Candidat', 'Competence', 'Entreprise'],
  {
    A_UTILISE: {orientation: 'UNDIRECTED'},
    A_TRAVAILLE: {orientation: 'UNDIRECTED'},
    CHEZ: {orientation: 'UNDIRECTED'}
  }
)

// Calculer la centralité de degré
CALL gds.degree.stream('talent-network')
YIELD nodeId, score
MATCH (n) WHERE id(n) = nodeId AND labels(n) = ['Candidat']
RETURN n.firstName, n.lastName, score
ORDER BY score DESC
LIMIT 10
```

#### 4. **Détecte les Parcours d'Excellence** 🎓

Trouvez les candidats avec formation prestigieuse ET expérience dans des entreprises leaders.

```cypher
// Candidats Polytechnique + Experience Big Tech
MATCH (c:Candidat)-[:A_SUIVI]->(:Formation)-[:DELIVREE_PAR]->(ecole:Ecole)
WHERE ecole.name CONTAINS 'Polytechnique' OR
      ecole.name CONTAINS 'Centrale' OR
      ecole.name CONTAINS 'HEC'
WITH c, ecole.name AS formation_prestigieuse
MATCH (c)-[:A_TRAVAILLE]->(:Experience)-[:CHEZ]->(e:Entreprise)
WHERE e.name IN ['Google', 'Amazon', 'Microsoft', 'BNP Paribas', 'Total']
RETURN c.firstName, c.lastName, formation_prestigieuse,
       COLLECT(DISTINCT e.name) AS entreprises_prestigieuses
```

#### 5. **Analyse les Trajectoires de Carrière** 📈

Comprenez les patterns de progression professionnelle.

```cypher
// Evolution temporelle des compétences
MATCH (c:Candidat)-[:A_TRAVAILLE]->(exp:Experience)
WHERE exp.startDate IS NOT NULL
WITH c, exp ORDER BY exp.startDate
MATCH (exp)-[:A_UTILISE]->(comp:Competence)
RETURN c.firstName, c.lastName,
       exp.startDate, exp.title, exp.company,
       COLLECT(comp.name) AS competences_acquises
ORDER BY c.id, exp.startDate
```

#### 6. **Recommandation de Compétences** 🎯

Suggérez les prochaines compétences à acquérir basées sur les parcours similaires.

```cypher
// Pour un candidat donné, trouve les compétences communes
// chez des profils similaires
MATCH (target:Candidat {email: 'john.doe@email.com'})
      -[:A_UTILISE]->(skill:Competence)
WITH target, COLLECT(skill) AS targetSkills
MATCH (other:Candidat)-[:A_UTILISE]->(commonSkill:Competence)
WHERE other <> target AND commonSkill IN targetSkills
WITH target, other, COUNT(commonSkill) AS commonCount
ORDER BY commonCount DESC
LIMIT 5
MATCH (other)-[:A_UTILISE]->(suggestedSkill:Competence)
WHERE NOT (target)-[:A_UTILISE]->(suggestedSkill)
RETURN suggestedSkill.name, COUNT(*) AS frequency
ORDER BY frequency DESC
LIMIT 10
```

#### 7. **Score de Polyvalence** 🔄

Mesurez la diversité des compétences d'un candidat.

```cypher
// Score basé sur le nombre de domaines couverts
MATCH (c:Candidat)-[:A_TRAVAILLE]->(:Experience)-[:A_UTILISE]->(comp:Competence)
WITH c, COUNT(DISTINCT comp) AS nb_competences
MATCH (c)-[:A_TRAVAILLE]->(:Experience)-[:CHEZ]->(e:Entreprise)
WITH c, nb_competences, COUNT(DISTINCT e) AS nb_entreprises
MATCH (c)-[:A_OBTENU]->(cert:Certification)
WITH c, nb_competences, nb_entreprises, COUNT(cert) AS nb_certifications
RETURN c.firstName, c.lastName,
       nb_competences * 0.5 + nb_entreprises * 2 + nb_certifications * 3 AS score_polyvalence
ORDER BY score_polyvalence DESC
```

### Configuration Neo4j GDS (Graph Data Science)

Pour les analyses avancées, installez l'extension GDS :

```bash
# Télécharger depuis Neo4j Download Center
# Copier dans le dossier plugins/ de Neo4j
# Ajouter dans neo4j.conf:
dbms.security.procedures.unrestricted=gds.*
dbms.security.procedures.allowlist=gds.*
```

## 📚 Documentation complète

Voir [`CLAUDE.md`](./CLAUDE.md) pour la documentation technique détaillée et les directives opérationnelles.

## 🔒 Sécurité & Performance

### Améliorations de Sécurité Récentes
- ✅ Migration des credentials vers variables d'environnement
- ✅ Correction des risques SQL injection
- ✅ Politique CORS restrictive (whitelist des origines)
- ✅ Validation des labels Neo4j contre injection
- ✅ Documentation complète du schéma DB (`DATABASE_SCHEMA.md`)

### Optimisations de Performance
- ✅ Mode WAL (Write-Ahead Logging) pour concurrence
- ✅ 9 index optimisés sur ontology.db
- ✅ 10 index optimisés sur entity_resolver.db
- ✅ Cache mémoire de 10MB/5MB configuré
- ✅ Script d'optimisation automatique

## 🚧 Roadmap

### ✅ Réalisé
- [x] Endpoint `/suggest` avec similarité
- [x] Mass densification automatique
- [x] Export/import pour validation humaine
- [x] Pipeline CV → Neo4j opérationnel
- [x] Résolution d'entités (entreprises/écoles)
- [x] Enrichissement automatique via Wikipedia
- [x] Requêtes Cypher avancées documentées
- [x] Sécurisation complète (credentials, CORS, SQL)
- [x] Optimisation des performances DB

### Court terme (Q1 2025)
- [ ] Atteindre 1000 skills (objectif: 50% de couverture)
- [ ] Interface web de validation
- [ ] Intégration LinkedIn/Crunchbase pour enrichissement
- [ ] Dashboard de monitoring du graphe

### Moyen terme (Q2-Q3 2025)
- [ ] Migration PostgreSQL pour scalabilité
- [ ] Export GraphML pour visualisation avancée
- [ ] Multi-tenancy (ontologies par domaine)
- [ ] API GraphQL pour requêtes flexibles
- [ ] ML Pipeline pour matching automatique

### Long terme (2026)
- [ ] Apprentissage actif depuis l'usage
- [ ] Fédération inter-organisations
- [ ] Prediction de trajectoires de carrière
- [ ] Recommandation de formations personnalisées

## 📊 Statut actuel

```
🔹 Système de Graphe de Connaissances v3.2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ontologie Skills    : 329 canoniques | 1,678 aliases | 843 relations
Base Entités        : 30 entreprises | 13 écoles | 174 aliases
Pipeline            : CV → Harmonisation → Résolution → Neo4j ✅
Enrichissement      : NIGHT BEAST mode - 5h sessions automatiques
Processing          : 87,793 skills identifiés → Conquête active
Croissance          : +22% skills, +165% aliases via enrichissement
Tests & CI/CD       : 308 tests ✅ (284 passing, 24 skipped) | Coverage 80% | Pre-commit hooks
Sécurité           : Credentials .env | CORS sécurisé | SQL injection fix
Performance        : WAL mode | 19 index optimisés | Cache 15MB
Qualité            : 95% précision après validation humaine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📄 License

Ce logiciel est **propriétaire** et appartient à **Sigilum EURL**.
Voir le fichier [LICENSE](LICENSE) pour plus de détails.

Tous droits réservés © 2025 Sigilum EURL - Julien DABERT

---

**JENEZIS by Sigilum EURL** - *The Knowledge Graph System*
**Created by Julien DABERT**

Pour toute question technique, consulter `CLAUDE.md` ou contacter l'équipe engineering.
