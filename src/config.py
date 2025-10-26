"""
Configuration centralisée pour le projet JENEZIS.
Tous les chemins et paramètres globaux sont définis ici.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env
load_dotenv()

# Répertoire racine du projet
PROJECT_ROOT = Path(__file__).parent.parent

# Répertoires principaux
DATA_DIR = PROJECT_ROOT / "data"
DATABASES_DIR = DATA_DIR / "databases"
OUTPUT_DIR = DATA_DIR / "output"

# PostgreSQL Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jenezis:jenezis@localhost:5433/jenezis")

# Legacy SQLite paths (kept for compatibility - TO BE REMOVED)
# These are only used by CLI tools that haven't been migrated yet
ONTOLOGY_DB = DATABASES_DIR / "ontology.db"  # DEPRECATED - use PostgreSQL
ENTITY_RESOLVER_DB = DATABASES_DIR / "entity_resolver.db"  # DEPRECATED - use PostgreSQL

# Fichiers de données
CANDIDATS_COMPETENCES_CSV = DATA_DIR / "candidats_competences.csv"
CV_EXAMPLE_JSON = DATA_DIR / "examples" / "cv_example.json"
CYPHER_QUERIES_FILE = OUTPUT_DIR / "cypher_queries.txt"

# Configurations API
HARMONIZER_API_URL = "http://127.0.0.1:8000"
ENTITY_RESOLVER_API_URL = "http://127.0.0.1:8001"

# Configuration Neo4j (depuis variables d'environnement)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "jenezis123")  # Default for development

# Validate required configuration in production
if os.getenv("NODE_ENV") == "production":
    if not NEO4J_PASSWORD:
        raise ValueError("NEO4J_PASSWORD must be set in production environment")
    if not os.getenv("API_AUTH_TOKEN"):
        raise ValueError("API_AUTH_TOKEN must be set in production environment")

# Créer les répertoires s'ils n'existent pas
DATABASES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
