"""
Async tasks for skill suggestions using LLM.
"""

import json
from typing import Any

from openai import OpenAI

from src.celery_app import app
from src.db.postgres_connection import get_db
from src.db.postgres_models import AsyncTask, Skill, TaskStatus


@app.task(bind=True, name="src.tasks.suggestions.suggest_llm")
def suggest_skills_with_llm(
    self: Any,
    unknown_skill: str,
    top_k: int = 5,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """
    Use LLM to suggest canonical skills for an unknown skill.

    Args:
        unknown_skill: The skill name to find matches for
        top_k: Number of suggestions to return
        model: OpenAI model to use

    Returns:
        dict with suggestions and metadata
    """
    # Update task status
    with get_db() as db:
        task = db.query(AsyncTask).filter(AsyncTask.id == self.request.id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = db.execute("SELECT NOW()").scalar()
            db.commit()

    try:
        # Get all canonical skills
        with get_db() as db:
            all_skills = db.query(Skill.canonical_name).all()
            skills_list = [s[0] for s in all_skills]

        # Build LLM prompt
        prompt = f"""Given the skill "{unknown_skill}", find the {top_k} most similar canonical skills from this list:

{json.dumps(skills_list, indent=2)}

Return ONLY a JSON array of the top {top_k} most similar skills, ranked by relevance.
Format: ["skill1", "skill2", "skill3"]

If no good matches exist, return an empty array."""

        # Call OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )

        suggestions_str = response.choices[0].message.content.strip()
        suggestions = json.loads(suggestions_str)

        result = {
            "unknown_skill": unknown_skill,
            "suggestions": suggestions,
            "model": model,
            "tokens_used": response.usage.total_tokens,
        }

        # Update task with success
        with get_db() as db:
            task = db.query(AsyncTask).filter(AsyncTask.id == self.request.id).first()
            if task:
                task.status = TaskStatus.SUCCESS
                task.result = result
                task.completed_at = db.execute("SELECT NOW()").scalar()
                db.commit()

        return result

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


@app.task(name="src.tasks.suggestions.batch_suggest")
def batch_suggest_skills(skills: list[str], top_k: int = 5) -> dict:
    """
    Process multiple skill suggestions in batch.

    Args:
        skills: List of unknown skills
        top_k: Number of suggestions per skill

    Returns:
        dict mapping skills to their suggestions
    """
    results = {}
    for skill in skills:
        task = suggest_skills_with_llm.delay(skill, top_k)
        results[skill] = task.id

    return {"total": len(skills), "task_ids": results}
