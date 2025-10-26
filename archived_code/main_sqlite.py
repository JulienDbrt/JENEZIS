#!/usr/bin/env python3
import json
import os
import sqlite3
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Union

import openai
from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from pydantic import BaseModel

sys.path.append(str(Path(__file__).parent.parent))
from api.auth import get_auth_status, require_auth
from api.metrics import metrics_endpoint, track_cache_metrics
from config import ONTOLOGY_DB

load_dotenv()


# --- Modèles de données Pydantic ---
class HarmonizationRequest(BaseModel):
    skills: list[str]


class HarmonizedSkill(BaseModel):
    original_skill: str
    canonical_skill: str
    is_known: bool


class HarmonizationResponse(BaseModel):
    results: list[HarmonizedSkill]


class SuggestRequest(BaseModel):
    skill: str
    top_k: int = 3
    use_llm: bool = False


class SkillSuggestion(BaseModel):
    canonical_name: str
    similarity_score: float
    parents: list[str] = []


class SuggestResponse(BaseModel):
    original_skill: str
    suggestions: list[SkillSuggestion]
    method: str


# --- Configuration ---
DB_FILE = ONTOLOGY_DB
app = FastAPI(
    title="Harmonizer API v2",
    description="API pour l'harmonisation de compétences basée sur une ontologie en base de données.",
)

# --- Cache en mémoire pour l'ontologie ---
ALIAS_CACHE: dict[str, str] = {}
SKILLS_CACHE: dict[str, int] = {}
HIERARCHY_CACHE: dict[str, list[str]] = {}


def load_ontology_cache() -> None:
    """Charge les alias, skills et hiérarchie depuis la DB dans le cache en mémoire."""
    global ALIAS_CACHE, SKILLS_CACHE, HIERARCHY_CACHE
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Load aliases
        query = """
            SELECT a.alias_name, s.canonical_name
            FROM aliases a
            JOIN skills s ON a.skill_id = s.id
        """
        ALIAS_CACHE = {row[0]: row[1] for row in cursor.execute(query)}

        # Load all canonical skills
        query = "SELECT id, canonical_name FROM skills"
        SKILLS_CACHE = {row[1]: row[0] for row in cursor.execute(query)}

        # Load hierarchy
        query = """
            SELECT c.canonical_name, p.canonical_name
            FROM hierarchy h
            JOIN skills c ON h.child_id = c.id
            JOIN skills p ON h.parent_id = p.id
        """
        HIERARCHY_CACHE = {}
        for child, parent in cursor.execute(query):
            if child not in HIERARCHY_CACHE:
                HIERARCHY_CACHE[child] = []
            HIERARCHY_CACHE[child].append(parent)

        conn.close()
        print(
            f"✓ Cache chargé: {len(ALIAS_CACHE)} alias, {len(SKILLS_CACHE)} skills, "
            f"{len(HIERARCHY_CACHE)} hiérarchies"
        )
    except sqlite3.Error as e:
        print(f"✗ Erreur critique : Impossible de charger l'ontologie. {e}")
        ALIAS_CACHE = {}
        SKILLS_CACHE = {}
        HIERARCHY_CACHE = {}


@app.on_event("startup")
def startup_event() -> None:
    load_ontology_cache()


@app.post("/harmonize", response_model=HarmonizationResponse)
def harmonize_skills(request: HarmonizationRequest) -> HarmonizationResponse:
    """Harmonise une liste de compétences."""
    results = []
    for skill in request.skills:
        clean_skill = skill.lower().strip()
        canonical = ALIAS_CACHE.get(clean_skill)

        if canonical:
            results.append(
                HarmonizedSkill(original_skill=skill, canonical_skill=canonical, is_known=True)
            )
        else:
            results.append(
                HarmonizedSkill(original_skill=skill, canonical_skill=clean_skill, is_known=False)
            )

    return HarmonizationResponse(results=results)


@app.post("/admin/reload", status_code=200, dependencies=[Depends(require_auth)])
def reload_ontology_cache() -> dict[str, Union[str, int]]:
    """Recharge le cache de l'ontologie à chaud."""
    print("Rechargement du cache de l'ontologie demandé...")
    load_ontology_cache()
    return {"message": "Cache reloaded", "alias_count": len(ALIAS_CACHE)}


@app.get("/health")
def health_check() -> dict[str, Union[str, bool, int]]:
    """Health check endpoint for container orchestration."""
    try:
        # Check if cache is loaded
        if not ALIAS_CACHE and not SKILLS_CACHE:
            return {"status": "unhealthy", "cache_loaded": False, "error": "Cache not loaded"}

        # Check database connectivity
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM skills")
        skill_count = cursor.fetchone()[0]
        conn.close()

        auth_status = get_auth_status()

        return {
            "status": "healthy",
            "cache_loaded": True,
            "alias_count": len(ALIAS_CACHE),
            "skill_count": skill_count,
            "service": "harmonizer-api",
            "auth_enabled": auth_status["auth_enabled"],
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/stats")
def get_stats() -> dict[str, int]:
    """Retourne les statistiques de l'ontologie."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    stats = {}
    cursor.execute("SELECT COUNT(*) FROM skills")
    stats["total_skills"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM aliases")
    stats["total_aliases"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM hierarchy")
    stats["total_relations"] = cursor.fetchone()[0]

    conn.close()
    return stats


@app.get("/metrics")
def get_metrics() -> str:
    """Prometheus metrics endpoint."""
    # Update cache metrics before returning
    track_cache_metrics("aliases", len(ALIAS_CACHE))
    track_cache_metrics("skills", len(SKILLS_CACHE))
    return str(metrics_endpoint())


def calculate_string_similarity(s1: str, s2: str) -> float:
    """Calculate similarity between two strings using SequenceMatcher"""
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def get_llm_suggestions(skill: str, top_k: int = 3) -> list[SkillSuggestion]:
    """Get suggestions using LLM"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return []

    try:
        client = openai.OpenAI(api_key=api_key)

        # Get list of all canonical skills
        all_skills = list(SKILLS_CACHE.keys())
        skills_list = ", ".join(all_skills[:50])  # Limit to avoid token limit

        prompt = f"""Given the skill "{skill}", suggest the {top_k} most relevant canonical skills from this ontology.

Available canonical skills include: {skills_list}...

Return ONLY a JSON array with the top {top_k} canonical skill names, ordered by relevance.
Example: ["python", "javascript", "react"]
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )

        message_content = response.choices[0].message.content
        if not message_content:
            return []
        suggested_names = json.loads(message_content)

        suggestions = []
        for i, name in enumerate(suggested_names[:top_k]):
            if name in SKILLS_CACHE:
                suggestions.append(
                    SkillSuggestion(
                        canonical_name=name,
                        similarity_score=1.0 - (i * 0.1),  # Decreasing score by rank
                        parents=HIERARCHY_CACHE.get(name, []),
                    )
                )

        return suggestions

    except Exception as e:
        print(f"LLM suggestion error: {e}")
        return []


@app.post("/suggest", response_model=SuggestResponse)
def suggest_skills(request: SuggestRequest) -> SuggestResponse:
    """
    Suggest canonical skills for an unknown skill.
    Uses string similarity (Levenshtein) or LLM-based matching.
    """
    skill = request.skill.lower().strip()

    # Check if it's already known
    if skill in ALIAS_CACHE:
        canonical = ALIAS_CACHE[skill]
        return SuggestResponse(
            original_skill=request.skill,
            suggestions=[
                SkillSuggestion(
                    canonical_name=canonical,
                    similarity_score=1.0,
                    parents=HIERARCHY_CACHE.get(canonical, []),
                )
            ],
            method="exact_match",
        )

    suggestions = []

    if request.use_llm:
        # Use LLM for intelligent suggestions
        suggestions = get_llm_suggestions(request.skill, request.top_k)
        method = "llm"

    if not suggestions:
        # Fallback to string similarity
        similarities = []

        # Check similarity with all canonical skills
        for canonical_name in SKILLS_CACHE:
            score = calculate_string_similarity(skill, canonical_name)
            similarities.append((canonical_name, score))

        # Check similarity with all aliases too
        for alias_name, canonical_name in ALIAS_CACHE.items():
            score = calculate_string_similarity(skill, alias_name)
            similarities.append((canonical_name, score))

        # Deduplicate and get top matches
        seen: dict[str, float] = {}
        for canonical_name, score in similarities:
            if canonical_name not in seen or score > seen[canonical_name]:
                seen[canonical_name] = score

        # Sort by score and get top k
        top_matches = sorted(seen.items(), key=lambda x: x[1], reverse=True)[: request.top_k]

        suggestions = [
            SkillSuggestion(
                canonical_name=name,
                similarity_score=round(score, 3),
                parents=HIERARCHY_CACHE.get(name, []),
            )
            for name, score in top_matches
            if score > 0.3  # Minimum threshold
        ]
        method = "string_similarity"

    return SuggestResponse(original_skill=request.skill, suggestions=suggestions, method=method)
