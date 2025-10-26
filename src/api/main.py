#!/usr/bin/env python3
"""
JENEZIS Harmonizer API v3.0 - PostgreSQL Version
Complete rewrite for PostgreSQL backend with pgvector support
"""
import os
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Dict, Any

import openai
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

sys.path.append(str(Path(__file__).parent.parent))
from api.auth import require_auth
from api.metrics import metrics_endpoint, track_cache_metrics

load_dotenv()

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jenezis:jenezis@localhost:5433/jenezis")
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=40)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Pydantic Models ---
class HarmonizationRequest(BaseModel):
    skills: List[str]

class HarmonizedSkill(BaseModel):
    original_skill: str
    canonical_skill: str
    is_known: bool

class HarmonizationResponse(BaseModel):
    results: List[HarmonizedSkill]

class SuggestRequest(BaseModel):
    skill: str
    top_k: int = 3
    use_llm: bool = False

class SkillSuggestion(BaseModel):
    canonical_name: str
    similarity_score: float
    parents: List[str] = []

class SuggestResponse(BaseModel):
    original_skill: str
    suggestions: List[SkillSuggestion]
    method: str

class StatsResponse(BaseModel):
    total_skills: int
    total_aliases: int
    total_relations: int
    database: str = "PostgreSQL"

# --- FastAPI App ---
app = FastAPI(
    title="JENEZIS Harmonizer API v3.0",
    description="PostgreSQL-based skill harmonization API with pgvector support",
    version="3.0.0"
)

# --- Cache en mémoire ---
ALIAS_CACHE: Dict[str, str] = {}
SKILLS_CACHE: Dict[str, int] = {}
HIERARCHY_CACHE: Dict[str, List[str]] = {}

def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def load_ontology_cache() -> None:
    """Load aliases, skills and hierarchy from PostgreSQL into memory cache"""
    global ALIAS_CACHE, SKILLS_CACHE, HIERARCHY_CACHE

    db = SessionLocal()
    try:
        # Load aliases
        result = db.execute(text("""
            SELECT a.alias_name, s.canonical_name
            FROM aliases a
            JOIN skills s ON a.skill_id = s.id
        """))
        ALIAS_CACHE = {row[0]: row[1] for row in result}

        # Load all canonical skills
        result = db.execute(text("SELECT id, canonical_name FROM skills"))
        SKILLS_CACHE = {row[1]: row[0] for row in result}

        # Load hierarchy
        result = db.execute(text("""
            SELECT c.canonical_name, p.canonical_name
            FROM hierarchy h
            JOIN skills c ON h.child_id = c.id
            JOIN skills p ON h.parent_id = p.id
        """))
        HIERARCHY_CACHE = {}
        for child, parent in result:
            if child not in HIERARCHY_CACHE:
                HIERARCHY_CACHE[child] = []
            HIERARCHY_CACHE[child].append(parent)

        print(f"✓ Cache loaded: {len(ALIAS_CACHE)} aliases, {len(SKILLS_CACHE)} skills")
        track_cache_metrics("aliases", len(ALIAS_CACHE))
        track_cache_metrics("skills", len(SKILLS_CACHE))

    except Exception as e:
        print(f"⚠ Warning: Could not load cache from PostgreSQL: {e}")
        # Continue with empty cache
    finally:
        db.close()

@app.on_event("startup")
async def startup_event():
    """Load ontology cache on startup"""
    load_ontology_cache()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    cache_loaded = bool(SKILLS_CACHE)

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
        "aliases_count": len(ALIAS_CACHE),
        "skills_count": len(SKILLS_CACHE)
    }

@app.post("/harmonize", response_model=HarmonizationResponse)
async def harmonize_skills(request: HarmonizationRequest):
    """Harmonize a list of skills to their canonical forms"""
    results = []

    for skill in request.skills:
        skill_normalized = skill.strip().lower()

        # Check alias cache
        if skill_normalized in ALIAS_CACHE:
            canonical = ALIAS_CACHE[skill_normalized]
            results.append(HarmonizedSkill(
                original_skill=skill,
                canonical_skill=canonical,
                is_known=True
            ))
        # Check if already canonical
        elif skill_normalized in SKILLS_CACHE:
            results.append(HarmonizedSkill(
                original_skill=skill,
                canonical_skill=skill_normalized,
                is_known=True
            ))
        else:
            results.append(HarmonizedSkill(
                original_skill=skill,
                canonical_skill=skill,
                is_known=False
            ))

    return HarmonizationResponse(results=results)

@app.post("/suggest", response_model=SuggestResponse)
async def suggest_skills(request: SuggestRequest):
    """Suggest canonical skills for an unknown skill"""
    skill_normalized = request.skill.strip().lower()

    # If already known, return it
    if skill_normalized in ALIAS_CACHE:
        canonical = ALIAS_CACHE[skill_normalized]
        parents = HIERARCHY_CACHE.get(canonical, [])
        return SuggestResponse(
            original_skill=request.skill,
            suggestions=[SkillSuggestion(
                canonical_name=canonical,
                similarity_score=1.0,
                parents=parents
            )],
            method="exact_match"
        )

    # Find similar skills using string similarity
    suggestions = []
    for canonical_skill in SKILLS_CACHE.keys():
        similarity = SequenceMatcher(None, skill_normalized, canonical_skill).ratio()
        if similarity > 0.3:
            suggestions.append({
                "canonical_name": canonical_skill,
                "similarity_score": similarity,
                "parents": HIERARCHY_CACHE.get(canonical_skill, [])
            })

    # Sort by similarity and take top_k
    suggestions.sort(key=lambda x: x["similarity_score"], reverse=True)
    top_suggestions = suggestions[:request.top_k]

    # If use_llm and OpenAI is configured, enhance with LLM
    if request.use_llm and os.getenv("OPENAI_API_KEY"):
        # TODO: Implement LLM enhancement
        method = "similarity_with_llm"
    else:
        method = "string_similarity"

    return SuggestResponse(
        original_skill=request.skill,
        suggestions=[SkillSuggestion(**s) for s in top_suggestions],
        method=method
    )

@app.get("/stats", response_model=StatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    """Get statistics about the ontology"""
    try:
        skills_count = db.execute(text("SELECT COUNT(*) FROM skills")).scalar()
        aliases_count = db.execute(text("SELECT COUNT(*) FROM aliases")).scalar()
        relations_count = db.execute(text("SELECT COUNT(*) FROM hierarchy")).scalar()

        return StatsResponse(
            total_skills=skills_count or 0,
            total_aliases=aliases_count or 0,
            total_relations=relations_count or 0
        )
    except Exception as e:
        # Return cached counts if DB query fails
        return StatsResponse(
            total_skills=len(SKILLS_CACHE),
            total_aliases=len(ALIAS_CACHE),
            total_relations=len(HIERARCHY_CACHE)
        )

@app.post("/admin/reload", dependencies=[Depends(require_auth)])
async def reload_cache():
    """Reload the ontology cache from database"""
    load_ontology_cache()
    return {
        "status": "success",
        "message": "Cache reloaded",
        "aliases_count": len(ALIAS_CACHE),
        "skills_count": len(SKILLS_CACHE)
    }

@app.get("/metrics")
async def get_metrics():
    """Get Prometheus metrics"""
    return metrics_endpoint()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)