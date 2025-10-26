"""
Async tasks for ontology enrichment using LLM.
"""

import json
from typing import Any

from openai import OpenAI

from src.celery_app import app
from src.db.postgres_connection import get_db
from src.db.postgres_models import AsyncTask, Skill, TaskStatus


@app.task(bind=True, name="src.tasks.enrichment.enrich_skill")
def enrich_skill_with_llm(
    self: Any,
    skill_name: str,
    frequency: int,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """
    Use LLM to determine canonical name, aliases, and parents for a skill.

    Args:
        skill_name: Raw skill name from production data
        frequency: Occurrence count in dataset
        model: OpenAI model to use

    Returns:
        dict with canonical_name, aliases, parents
    """
    # Update task status
    with get_db() as db:
        task = db.query(AsyncTask).filter(AsyncTask.id == self.request.id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = db.execute("SELECT NOW()").scalar()
            db.commit()

    try:
        # Get existing skills for context
        with get_db() as db:
            existing_skills = db.query(Skill.canonical_name).all()
            skills_list = [s[0] for s in existing_skills]

        # Build prompt
        prompt = f"""You are an expert at normalizing skill names for a job marketplace.

Given skill: "{skill_name}" (appears {frequency} times in our dataset)
Existing skills in ontology: {json.dumps(skills_list[:50])}

Determine:
1. canonical_name: The normalized, standardized name (snake_case, lowercase)
2. aliases: List of alternative names (including the original if different)
3. parents: List of broader parent skills from the existing ontology (0-3 parents)

Rules:
- Use snake_case for canonical_name (e.g., "machine_learning")
- Include original name in aliases if it differs from canonical
- Only reference parents that exist in the ontology
- If no suitable parents exist, use empty array

Return ONLY valid JSON:
{{"canonical_name": "", "aliases": [], "parents": []}}"""

        # Call OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        enriched_result: dict[str, Any] = {
            **result,
            "original_skill": skill_name,
            "frequency": frequency,
            "tokens_used": response.usage.total_tokens,
            "auto_approved": frequency > 1000,
        }

        # Update task with success
        with get_db() as db:
            task = db.query(AsyncTask).filter(AsyncTask.id == self.request.id).first()
            if task:
                task.status = TaskStatus.SUCCESS
                task.result = enriched_result
                task.completed_at = db.execute("SELECT NOW()").scalar()
                db.commit()

        return enriched_result

    except Exception as e:
        # Update task with failure
        with get_db() as db:
            task = db.query(AsyncTask).filter(AsyncTask.id == self.request.id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = db.execute("SELECT NOW()").scalar()
                db.commit()

        raise


@app.task(name="src.tasks.enrichment.batch_enrich")
def batch_enrich_skills(skills_with_frequency: list[tuple[str, int]]) -> dict[str, Any]:
    """
    Process multiple skills in batch for enrichment.

    Args:
        skills_with_frequency: List of (skill_name, frequency) tuples

    Returns:
        dict with task IDs for each skill
    """
    results = {}
    for skill_name, frequency in skills_with_frequency:
        task = enrich_skill_with_llm.delay(skill_name, frequency)
        results[skill_name] = {"task_id": task.id, "frequency": frequency}

    return {"total": len(skills_with_frequency), "tasks": results}
