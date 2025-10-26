#!/usr/bin/env python3
"""
API FastAPI pour le service de résolution d'entités.
Expose la logique de résolution des noms d'entreprises et écoles.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional, Union

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from api.auth import get_auth_status, require_auth
from api.metrics import metrics_endpoint, track_cache_metrics

# Charger les variables d'environnement
load_dotenv()

# --- Configuration ---
DB_FILE = "data/databases/entity_resolver.db"

app = FastAPI(
    title="Entity Resolver API",
    description="Service de résolution et normalisation des entités (entreprises, écoles)",
    version="1.0.0",
)

# Configuration CORS sécurisée
# En production, définir CORS_ORIGINS dans .env avec les domaines autorisés
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:8000").split(",")
# Si on veut permettre tout en développement local uniquement
if os.getenv("NODE_ENV", "development") == "development" and "CORS_ORIGINS" not in os.environ:
    cors_origins = ["http://localhost:3000", "http://127.0.0.1:8000", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


# --- Modèles Pydantic ---
class ResolveRequest(BaseModel):
    """Requête de résolution d'entités."""

    entities: list[str] = Field(..., description="Liste des noms d'entités à résoudre")
    entity_type: str = Field("COMPANY", description="Type d'entité: COMPANY ou SCHOOL")

    class Config:
        schema_extra = {
            "example": {
                "entities": ["BNP P.", "Google", "École Polytechnique"],
                "entity_type": "COMPANY",
            }
        }


class ResolvedEntity(BaseModel):
    """Entité résolue avec ses informations canoniques."""

    original_name: str = Field(..., description="Nom original fourni")
    canonical_id: str = Field(..., description="Identifiant canonique unique")
    display_name: str = Field(..., description="Nom d'affichage officiel")
    is_known: bool = Field(..., description="True si l'entité est dans la base")
    entity_type: Optional[str] = Field(None, description="Type d'entité détecté")
    metadata: Optional[dict] = Field(None, description="Métadonnées additionnelles")


class ResolveResponse(BaseModel):
    """Réponse contenant les entités résolues."""

    results: list[ResolvedEntity]
    stats: dict[str, int] = Field(..., description="Statistiques de la résolution")


class AddEntityRequest(BaseModel):
    """Requête pour ajouter une nouvelle entité."""

    canonical_id: str = Field(..., description="Identifiant unique (ex: 'bnp_paribas')")
    display_name: str = Field(..., description="Nom officiel (ex: 'BNP Paribas')")
    aliases: list[str] = Field(..., description="Liste des variations du nom")
    entity_type: str = Field("COMPANY", description="COMPANY ou SCHOOL")
    metadata: Optional[dict] = Field(None, description="Informations supplémentaires")


# --- Cache en mémoire ---
ENTITY_CACHE: dict[str, dict[str, Any]] = {}


def load_cache() -> None:
    """Charge toutes les entités en mémoire pour des performances optimales."""
    global ENTITY_CACHE
    ENTITY_CACHE = {}

    if not Path(DB_FILE).exists():
        print(f"⚠️  Base de données '{DB_FILE}' introuvable. Cache vide.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Charger toutes les correspondances alias -> entité canonique
    cursor.execute(
        """
        SELECT
            ea.alias_name,
            ce.canonical_id,
            ce.display_name,
            ce.entity_type,
            ce.metadata
        FROM entity_aliases ea
        JOIN canonical_entities ce ON ea.canonical_id = ce.id
    """
    )

    for row in cursor.fetchall():
        alias, can_id, display_name, entity_type, metadata = row
        ENTITY_CACHE[alias.lower().strip()] = {
            "canonical_id": can_id,
            "display_name": display_name,
            "entity_type": entity_type,
            "metadata": json.loads(metadata) if metadata else {},
        }

    conn.close()
    print(f"✅ Cache chargé avec {len(ENTITY_CACHE)} alias")


# Charger le cache au démarrage
load_cache()


# --- Logique de résolution ---
def resolve_entity(entity_name: str, preferred_type: Optional[str] = None) -> dict[str, Any]:
    """
    Résout un nom d'entité en utilisant le cache.

    Args:
        entity_name: Le nom à résoudre
        preferred_type: Type préféré si ambigu (COMPANY ou SCHOOL)

    Returns:
        Dictionnaire avec les informations canoniques
    """
    # Normaliser le nom pour la recherche
    normalized = entity_name.lower().strip()

    # Recherche exacte dans le cache
    if normalized in ENTITY_CACHE:
        result = ENTITY_CACHE[normalized]
        # Check if preferred_type matches if specified
        if preferred_type and result["entity_type"] != preferred_type:
            # Type mismatch - treat as unknown
            pass
        else:
            return {
                "canonical_id": result["canonical_id"],
                "display_name": result["display_name"],
                "entity_type": result["entity_type"],
                "metadata": result["metadata"],
                "is_known": True,
            }

    # Recherche partielle (pour gérer les variations mineures)
    for alias, data in ENTITY_CACHE.items():
        # Si le nom contient l'alias ou vice-versa
        if alias in normalized or normalized in alias:
            if preferred_type and data["entity_type"] != preferred_type:
                continue
            return {
                "canonical_id": data["canonical_id"],
                "display_name": data["display_name"],
                "entity_type": data["entity_type"],
                "metadata": data["metadata"],
                "is_known": True,
            }

    # Entité inconnue - générer un ID canonique
    # Nettoyer le nom pour créer un ID valide
    clean_id = normalized.replace(" ", "_").replace(".", "").replace(",", "").replace("'", "")
    clean_id = "".join(c for c in clean_id if c.isalnum() or c == "_")

    return {
        "canonical_id": clean_id,
        "display_name": entity_name.strip(),
        "entity_type": preferred_type or "UNKNOWN",
        "metadata": {},
        "is_known": False,
    }


# --- Endpoints ---
@app.get("/")
def root() -> dict[str, Union[str, int, list]]:
    """Point d'entrée de l'API."""
    return {
        "service": "Entity Resolver API",
        "version": "1.0.0",
        "cache_size": len(ENTITY_CACHE),
        "endpoints": [
            "/docs - Documentation interactive",
            "/health - Health check",
            "/resolve - Résoudre des entités",
            "/stats - Statistiques du service",
            "/admin/reload - Recharger le cache",
        ],
    }


@app.get("/health")
def health_check() -> dict[str, Union[str, bool, int]]:
    """Health check endpoint for container orchestration."""
    try:
        # Check if cache is loaded
        if not ENTITY_CACHE:
            return {"status": "unhealthy", "cache_loaded": False, "error": "Cache not loaded"}

        # Check database connectivity
        if Path(DB_FILE).exists():
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM canonical_entities")
            entity_count = cursor.fetchone()[0]
            conn.close()
        else:
            return {"status": "unhealthy", "database_exists": False, "error": "Database not found"}

        auth_status = get_auth_status()

        return {
            "status": "healthy",
            "cache_loaded": True,
            "cache_size": len(ENTITY_CACHE),
            "entity_count": entity_count,
            "service": "entity-resolver-api",
            "auth_enabled": auth_status["auth_enabled"],
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def add_to_enrichment_queue(conn: sqlite3.Connection, canonical_id: str, entity_type: str) -> None:
    """
    Ajoute une nouvelle entité à la file d'enrichissement.

    Args:
        conn: Connection SQLite
        canonical_id: ID canonique de l'entité
        entity_type: Type d'entité (COMPANY, SCHOOL, etc.)
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO enrichment_queue (canonical_id, entity_type) VALUES (?, ?)",
            (canonical_id, entity_type),
        )
        if cursor.rowcount > 0:
            print(f"  → Nouvelle entité '{canonical_id}' ajoutée à la file d'enrichissement")
    except sqlite3.Error as e:
        print(f"  ⚠️  Erreur lors de l'ajout à la file: {e}")


@app.post("/resolve", response_model=ResolveResponse)
def resolve_entities(request: ResolveRequest) -> ResolveResponse:
    """
    Résout une liste de noms d'entités en leurs formes canoniques.

    - **entities**: Liste des noms à résoudre
    - **entity_type**: Type préféré (COMPANY ou SCHOOL)
    """
    results = []
    known_count = 0
    unknown_count = 0
    new_entities = []

    for entity_name in request.entities:
        if not entity_name or not entity_name.strip():
            continue

        resolved = resolve_entity(entity_name, request.entity_type)

        results.append(
            ResolvedEntity(
                original_name=entity_name,
                canonical_id=str(resolved["canonical_id"]),
                display_name=str(resolved["display_name"]),
                is_known=bool(resolved["is_known"]),
                entity_type=(
                    str(resolved.get("entity_type")) if resolved.get("entity_type") else None
                ),
                metadata=(
                    dict(resolved["metadata"])
                    if isinstance(resolved.get("metadata"), dict)
                    else None
                ),
            )
        )

        if resolved["is_known"]:
            known_count += 1
        else:
            unknown_count += 1
            # Collecter les nouvelles entités pour les ajouter à la file
            new_entities.append((str(resolved["canonical_id"]), str(resolved["entity_type"])))

    # Ajouter les nouvelles entités à la file d'enrichissement
    if new_entities:
        conn = sqlite3.connect(DB_FILE)
        try:
            for canonical_id, entity_type in new_entities:
                add_to_enrichment_queue(conn, canonical_id, entity_type)
            conn.commit()
        finally:
            conn.close()

    return ResolveResponse(
        results=results,
        stats={
            "total": len(results),
            "known": known_count,
            "unknown": unknown_count,
            "cache_size": len(ENTITY_CACHE),
            "queued_for_enrichment": len(new_entities),
        },
    )


@app.get("/stats")
def get_stats() -> dict[str, Union[str, int, dict]]:
    """Retourne les statistiques du service."""
    if not Path(DB_FILE).exists():
        return {"error": "Database not found"}

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Compter les entités par type
    cursor.execute(
        """
        SELECT entity_type, COUNT(*)
        FROM canonical_entities
        GROUP BY entity_type
    """
    )
    entity_counts = dict(cursor.fetchall())

    # Total des alias
    cursor.execute("SELECT COUNT(*) FROM entity_aliases")
    total_aliases = cursor.fetchone()[0]

    # Statistiques de la file d'enrichissement
    cursor.execute(
        """
        SELECT status, COUNT(*)
        FROM enrichment_queue
        GROUP BY status
    """
    )
    enrichment_stats = dict(cursor.fetchall())

    conn.close()

    return {
        "cache_size": len(ENTITY_CACHE),
        "entities": entity_counts,
        "total_aliases": total_aliases,
        "enrichment_queue": enrichment_stats,
        "database": DB_FILE,
    }


@app.get("/metrics")
def get_metrics() -> str:
    """Prometheus metrics endpoint."""
    # Update cache metrics before returning
    track_cache_metrics("entities", len(ENTITY_CACHE))
    return str(metrics_endpoint())


@app.get("/enrichment/queue")
def get_enrichment_queue() -> dict[str, Union[str, int, list]]:
    """Retourne le contenu de la file d'enrichissement."""
    if not Path(DB_FILE).exists():
        return {"error": "Database not found"}

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT canonical_id, entity_type, status, created_at, processed_at, error_message
        FROM enrichment_queue
        ORDER BY created_at DESC
        LIMIT 50
    """
    )

    queue = []
    for row in cursor.fetchall():
        queue.append(
            {
                "canonical_id": row[0],
                "entity_type": row[1],
                "status": row[2],
                "created_at": row[3],
                "processed_at": row[4],
                "error_message": row[5],
            }
        )

    conn.close()

    return {"queue": queue, "count": len(queue)}


@app.post("/admin/reload", dependencies=[Depends(require_auth)])
def reload_cache() -> dict[str, Union[str, int]]:
    """
    Recharge le cache depuis la base de données.
    Utile après ajout de nouvelles entités.
    """
    load_cache()
    return {"status": "Cache reloaded", "cache_size": len(ENTITY_CACHE)}


@app.post("/admin/add_entity", dependencies=[Depends(require_auth)])
def add_entity(request: AddEntityRequest) -> dict[str, Union[str, int, bool]]:
    """
    Ajoute une nouvelle entité à la base (endpoint admin).
    """
    if not Path(DB_FILE).exists():
        raise HTTPException(status_code=500, detail="Database not found")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # Insérer l'entité canonique
        cursor.execute(
            "INSERT INTO canonical_entities (canonical_id, display_name, entity_type, metadata) VALUES (?, ?, ?, ?)",
            (
                request.canonical_id,
                request.display_name,
                request.entity_type,
                json.dumps(request.metadata or {}),
            ),
        )

        # Récupérer l'ID auto-généré
        entity_db_id = cursor.lastrowid

        # Insérer les alias
        inserted_aliases = []
        for alias in request.aliases:
            try:
                cursor.execute(
                    "INSERT INTO entity_aliases (alias_name, canonical_id) VALUES (?, ?)",
                    (alias.lower().strip(), entity_db_id),
                )
                inserted_aliases.append(alias)
            except sqlite3.IntegrityError:
                # L'alias existe déjà
                pass

        conn.commit()

        # Recharger le cache
        load_cache()

        return {
            "status": "success",
            "canonical_id": request.canonical_id,
            "aliases_added": len(inserted_aliases),
            "cache_reloaded": True,
        }

    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Entity already exists: {str(e)}")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
