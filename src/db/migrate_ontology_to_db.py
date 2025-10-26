#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

# Default empty skill hierarchy if no data is provided
SKILL_HIERARCHY: dict[str, Any] = {}


def load_skill_hierarchy(json_file: Optional[str] = None) -> dict[str, Any]:
    """Load skill hierarchy from a JSON file."""
    if json_file and Path(json_file).exists():
        with open(json_file) as f:
            data: dict[str, Any] = json.load(f)
            skills: dict[str, Any] = data.get("skills", {})
            return skills
    return {}


def migrate_to_database(skill_hierarchy: Optional[dict[str, Any]] = None) -> None:
    """Migre l'ontologie Python vers la base SQLite."""
    if skill_hierarchy is None:
        skill_hierarchy = SKILL_HIERARCHY

    if not skill_hierarchy:
        # If no data provided, return early
        return

    con = sqlite3.connect("ontology.db")
    cur = con.cursor()

    skill_id_map = {}

    # 1. Insérer toutes les compétences canoniques
    for canonical_name in skill_hierarchy:
        cur.execute("INSERT OR IGNORE INTO skills (canonical_name) VALUES (?)", (canonical_name,))
        cur.execute("SELECT id FROM skills WHERE canonical_name = ?", (canonical_name,))
        skill_id_map[canonical_name] = cur.fetchone()[0]

    # 2. Insérer tous les alias
    for canonical_name, details in skill_hierarchy.items():
        skill_id = skill_id_map[canonical_name]
        for alias in details.get("aliases", []):
            cur.execute(
                "INSERT OR IGNORE INTO aliases (alias_name, skill_id) VALUES (?, ?)",
                (alias.lower().strip(), skill_id),
            )

    # 3. S'assurer que tous les parents existent
    for _canonical_name, details in skill_hierarchy.items():
        for parent in details.get("parents", []):
            if parent and parent not in skill_id_map:
                cur.execute("INSERT OR IGNORE INTO skills (canonical_name) VALUES (?)", (parent,))
                cur.execute("SELECT id FROM skills WHERE canonical_name = ?", (parent,))
                skill_id_map[parent] = cur.fetchone()[0]

    # 4. Insérer les relations de hiérarchie
    for canonical_name, details in skill_hierarchy.items():
        child_id = skill_id_map[canonical_name]
        for parent in details.get("parents", []):
            if parent:
                parent_id = skill_id_map[parent]
                cur.execute(
                    "INSERT OR IGNORE INTO hierarchy (child_id, parent_id) VALUES (?, ?)",
                    (child_id, parent_id),
                )

    con.commit()

    # Stats de migration
    cur.execute("SELECT COUNT(*) FROM skills")
    skills_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM aliases")
    aliases_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM hierarchy")
    hierarchy_count = cur.fetchone()[0]

    con.close()

    print("✓ Migration terminée")
    print(f"  - {skills_count} compétences")
    print(f"  - {aliases_count} alias")
    print(f"  - {hierarchy_count} relations hiérarchiques")


def main() -> None:
    """Main entry point for the migration script."""
    migrate_to_database()


if __name__ == "__main__":
    main()
