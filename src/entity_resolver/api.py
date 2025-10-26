#!/usr/bin/env python3
"""
JENEZIS Entity Resolver API v3.0 - PostgreSQL Version
Complete rewrite for PostgreSQL backend
"""
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

sys.path.append(str(Path(__file__).parent.parent))
from api.auth import require_auth
from api.metrics import metrics_endpoint

load_dotenv()

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jenezis:jenezis@localhost:5433/jenezis")
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=40)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Pydantic Models ---
class EntityResolveRequest(BaseModel):
    entities: List[str]
    entity_type: str = "COMPANY"  # COMPANY or SCHOOL

class ResolvedEntity(BaseModel):
    original_name: str
    canonical_id: str
    canonical_name: str
    entity_type: str
    is_known: bool

class EntityResolveResponse(BaseModel):
    results: List[ResolvedEntity]

class EntityStatsResponse(BaseModel):
    total_companies: int
    total_schools: int
    total_aliases: int
    enrichment_queue_size: int
    database: str = "PostgreSQL"

# --- FastAPI App ---
app = FastAPI(
    title="JENEZIS Entity Resolver API v3.0",
    description="PostgreSQL-based entity resolution API",
    version="3.0.0"
)

# --- Cache ---
ENTITY_ALIAS_CACHE: Dict[str, Dict[str, Any]] = {}
CANONICAL_ENTITIES: Dict[str, Dict[str, Any]] = {}

def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def load_entity_cache() -> None:
    """Load entity aliases from PostgreSQL into memory cache"""
    global ENTITY_ALIAS_CACHE, CANONICAL_ENTITIES

    db = SessionLocal()
    try:
        # Load entity aliases
        result = db.execute(text("""
            SELECT ea.alias_name, ce.canonical_id, ce.canonical_name, ce.entity_type
            FROM entity_aliases ea
            JOIN canonical_entities ce ON ea.entity_id = ce.id
        """))
        ENTITY_ALIAS_CACHE = {}
        for alias, canon_id, canon_name, entity_type in result:
            ENTITY_ALIAS_CACHE[alias.lower()] = {
                "canonical_id": canon_id,
                "canonical_name": canon_name,
                "entity_type": entity_type
            }

        # Load canonical entities
        result = db.execute(text("""
            SELECT canonical_id, canonical_name, entity_type
            FROM canonical_entities
        """))
        CANONICAL_ENTITIES = {}
        for canon_id, canon_name, entity_type in result:
            CANONICAL_ENTITIES[canon_id] = {
                "canonical_name": canon_name,
                "entity_type": entity_type
            }

        print(f"✓ Entity cache loaded: {len(ENTITY_ALIAS_CACHE)} aliases, {len(CANONICAL_ENTITIES)} entities")

    except Exception as e:
        print(f"⚠ Warning: Could not load entity cache from PostgreSQL: {e}")
    finally:
        db.close()

@app.on_event("startup")
async def startup_event():
    """Load entity cache on startup"""
    load_entity_cache()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    cache_loaded = bool(CANONICAL_ENTITIES)

    if not cache_loaded:
        return {
            "status": "degraded",
            "cache_loaded": False,
            "database": "PostgreSQL",
            "message": "Cache empty - loading data"
        }

    return {
        "status": "healthy",
        "cache_loaded": True,
        "database": "PostgreSQL",
        "entities_count": len(CANONICAL_ENTITIES),
        "aliases_count": len(ENTITY_ALIAS_CACHE)
    }

@app.post("/resolve", response_model=EntityResolveResponse)
async def resolve_entities(request: EntityResolveRequest, db: Session = Depends(get_db)):
    """Resolve entity names to their canonical forms"""
    results = []

    for entity_name in request.entities:
        normalized = entity_name.strip().lower()

        # Check cache
        if normalized in ENTITY_ALIAS_CACHE:
            entity_info = ENTITY_ALIAS_CACHE[normalized]
            results.append(ResolvedEntity(
                original_name=entity_name,
                canonical_id=entity_info["canonical_id"],
                canonical_name=entity_info["canonical_name"],
                entity_type=entity_info["entity_type"],
                is_known=True
            ))
        else:
            # Unknown entity - generate new ID and queue for enrichment
            canonical_id = f"{request.entity_type[:4]}_{str(uuid.uuid4())[:8]}"

            # Add to enrichment queue
            try:
                db.execute(text("""
                    INSERT INTO enrichment_queue (canonical_id, entity_name, entity_type, status, created_at)
                    VALUES (:id, :name, :type, 'PENDING', :created)
                    ON CONFLICT (canonical_id) DO NOTHING
                """), {
                    "id": canonical_id,
                    "name": entity_name,
                    "type": request.entity_type,
                    "created": datetime.utcnow()
                })
                db.commit()
            except Exception as e:
                print(f"Warning: Could not add to enrichment queue: {e}")

            results.append(ResolvedEntity(
                original_name=entity_name,
                canonical_id=canonical_id,
                canonical_name=entity_name,
                entity_type=request.entity_type,
                is_known=False
            ))

    return EntityResolveResponse(results=results)

@app.get("/stats", response_model=EntityStatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    """Get entity statistics"""
    try:
        companies = db.execute(
            text("SELECT COUNT(*) FROM canonical_entities WHERE entity_type = 'COMPANY'")
        ).scalar()
        schools = db.execute(
            text("SELECT COUNT(*) FROM canonical_entities WHERE entity_type = 'SCHOOL'")
        ).scalar()
        aliases = db.execute(text("SELECT COUNT(*) FROM entity_aliases")).scalar()
        queue = db.execute(
            text("SELECT COUNT(*) FROM enrichment_queue WHERE status = 'PENDING'")
        ).scalar()

        return EntityStatsResponse(
            total_companies=companies or 0,
            total_schools=schools or 0,
            total_aliases=aliases or 0,
            enrichment_queue_size=queue or 0
        )
    except Exception as e:
        return EntityStatsResponse(
            total_companies=0,
            total_schools=0,
            total_aliases=len(ENTITY_ALIAS_CACHE),
            enrichment_queue_size=0
        )

@app.get("/enrichment/queue")
async def get_enrichment_queue(db: Session = Depends(get_db)):
    """Get pending items in enrichment queue"""
    try:
        result = db.execute(text("""
            SELECT canonical_id, entity_name, entity_type, status, created_at
            FROM enrichment_queue
            WHERE status = 'PENDING'
            ORDER BY created_at DESC
            LIMIT 100
        """))

        queue = []
        for row in result:
            queue.append({
                "canonical_id": row[0],
                "entity_name": row[1],
                "entity_type": row[2],
                "status": row[3],
                "created_at": row[4].isoformat() if row[4] else None
            })

        return {"queue": queue, "total": len(queue)}
    except Exception as e:
        return {"error": str(e), "queue": []}

@app.post("/admin/add_entity", dependencies=[Depends(require_auth)])
async def add_entity(
    canonical_name: str,
    entity_type: str,
    aliases: List[str] = [],
    db: Session = Depends(get_db)
):
    """Manually add a new entity with aliases"""
    try:
        # Generate canonical ID
        canonical_id = f"{entity_type[:4]}_{str(uuid.uuid4())[:8]}"

        # Insert canonical entity
        db.execute(text("""
            INSERT INTO canonical_entities (canonical_id, canonical_name, entity_type)
            VALUES (:id, :name, :type)
        """), {
            "id": canonical_id,
            "name": canonical_name,
            "type": entity_type
        })

        # Insert aliases
        for alias in aliases:
            db.execute(text("""
                INSERT INTO entity_aliases (alias_name, entity_id)
                SELECT :alias, id FROM canonical_entities WHERE canonical_id = :canon_id
            """), {
                "alias": alias.lower(),
                "canon_id": canonical_id
            })

        db.commit()

        # Reload cache
        load_entity_cache()

        return {
            "status": "success",
            "canonical_id": canonical_id,
            "message": f"Added entity {canonical_name} with {len(aliases)} aliases"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/admin/reload", dependencies=[Depends(require_auth)])
async def reload_cache():
    """Reload entity cache from database"""
    load_entity_cache()
    return {
        "status": "success",
        "message": "Cache reloaded",
        "entities_count": len(CANONICAL_ENTITIES),
        "aliases_count": len(ENTITY_ALIAS_CACHE)
    }

@app.get("/metrics")
async def get_metrics():
    """Get Prometheus metrics"""
    return metrics_endpoint()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)