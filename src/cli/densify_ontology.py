#!/usr/bin/env python3
"""
Densification de l'ontologie des compétences via LLM.

Ce module utilise des modèles de langage pour enrichir automatiquement
l'ontologie en analysant les compétences non mappées et en proposant
des catégorisations.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# Add paths before importing local modules
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

# Now import local modules
from prompts import LLM_PROMPT, SYSTEM_PROMPT  # noqa: E402

from config import HARMONIZER_API_URL, ONTOLOGY_DB, OUTPUT_DIR  # noqa: E402


class DensificationConfig:
    """Configuration pour la densification d'ontologie."""

    def __init__(self) -> None:
        """Initialise la configuration depuis les variables d'environnement."""
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini-2024-07-18")
        self.use_openai = bool(self.openai_api_key and self.openai_api_key != "sk-...")
        self.db_file = ONTOLOGY_DB
        self.data_dir = OUTPUT_DIR
        self.api_url = HARMONIZER_API_URL

        if self.use_openai:
            from openai import OpenAI

            self.client = OpenAI(api_key=self.openai_api_key)
            print("✓ API OpenAI configurée")
        else:
            self.client = None
            print("⚠️  Mode simulation (pas de clé API OpenAI)")


class SkillDatabaseManager:
    """Gestionnaire pour les opérations de base de données des compétences."""

    def __init__(self, db_path: str):
        """Initialise le gestionnaire avec le chemin de la DB."""
        self.db_path = db_path

    def get_existing_canonical_skills(self) -> set[str]:
        """Récupère tous les nœuds canoniques existants depuis la DB."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT canonical_name FROM skills")
        skills = {row[0] for row in cursor.fetchall()}
        conn.close()
        return skills

    def add_skill_to_database(self, suggestion: dict[str, Any]) -> bool:
        """Ajoute une nouvelle compétence dans la base de données."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 1. Insérer la compétence canonique
            cursor.execute(
                "INSERT OR IGNORE INTO skills (canonical_name) VALUES (?)",
                (suggestion["canonical_name"],),
            )
            cursor.execute(
                "SELECT id FROM skills WHERE canonical_name = ?", (suggestion["canonical_name"],)
            )
            skill_id = cursor.fetchone()[0]

            # 2. Insérer les alias
            for alias in suggestion["aliases"]:
                cursor.execute(
                    "INSERT OR IGNORE INTO aliases (alias_name, skill_id) VALUES (?, ?)",
                    (alias.lower().strip(), skill_id),
                )

            # 3. Gérer les parents
            for parent in suggestion["parents"]:
                cursor.execute(
                    "INSERT OR IGNORE INTO skills (canonical_name) VALUES (?)", (parent,)
                )
                cursor.execute("SELECT id FROM skills WHERE canonical_name = ?", (parent,))
                parent_id = cursor.fetchone()[0]

                cursor.execute(
                    "INSERT OR IGNORE INTO hierarchy (child_id, parent_id) VALUES (?, ?)",
                    (skill_id, parent_id),
                )

            conn.commit()
            conn.close()
            print(f"  ✓ Ajouté: {suggestion['canonical_name']}")
            return True
        except Exception as e:
            print(f"  ✗ Erreur lors de l'ajout en DB: {e}")
            return False


class LLMSkillProcessor:
    """Processeur pour analyser les compétences via LLM."""

    def __init__(self, config: DensificationConfig):
        """Initialise le processeur avec la configuration."""
        self.config = config

    def call_openai_api(self, prompt: str) -> Optional[str]:
        """Appel réel à l'API OpenAI."""
        if not self.config.use_openai:
            return None

        try:
            response = self.config.client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=1,
                max_completion_tokens=500,
            )
            content = response.choices[0].message.content
            return content if content else None
        except Exception as e:
            print(f"  ✗ Erreur API OpenAI: {e}")
            return None

    def simulate_llm_response(self, skill_name: str) -> str:
        """Simulation pour les tests sans API."""
        simulations = {
            "git": '{"canonical_name": "git", "aliases": ["git"], "parents": ["version_control"]}',
            "jira": '{"canonical_name": "jira", "aliases": ["jira", "atlassian jira"], "parents": ["agile", "tools"]}',
            "typescript": '{"canonical_name": "typescript", "aliases": ["typescript", "ts"], "parents": ["javascript", "programming"]}',
            "wordpress": '{"canonical_name": "wordpress", "aliases": ["wordpress", "wp"], "parents": ["cms", "web_dev"]}',
            "uml": '{"canonical_name": "uml", "aliases": ["uml", "unified modeling language"], "parents": ["architecture", "methodologie"]}',
        }
        skill_lower = skill_name.lower()
        if skill_lower in simulations:
            return simulations[skill_lower]
        return f'{{"canonical_name": "{skill_lower.replace(" ", "_")}", "aliases": ["{skill_lower}"], "parents": ["other"]}}'

    def get_llm_suggestion(
        self, skill_name: str, skill_count: int, existing_skills: set[str]
    ) -> Optional[dict[str, Any]]:
        """Interroge le LLM et retourne sa suggestion en JSON."""
        existing_skills_str = ", ".join(sorted(existing_skills)[:50])
        prompt = LLM_PROMPT.format(skill_name=skill_name, existing_skills=existing_skills_str)

        print(f"→ Traitement de '{skill_name}' ({skill_count} occurrences)...")

        try:
            if self.config.use_openai:
                response = self.call_openai_api(prompt)
            else:
                response = self.simulate_llm_response(skill_name)

            if response:
                parsed_response: dict[str, Any] = json.loads(response)
                return parsed_response
            else:
                return None
        except json.JSONDecodeError as e:
            print(f"  ✗ Réponse LLM invalide : {e}")
            return None
        except Exception as e:
            print(f"  ✗ Erreur : {e}")
            return None


class ApiCacheManager:
    """Gestionnaire pour le cache de l'API."""

    def __init__(self, api_url: str):
        """Initialise le gestionnaire avec l'URL de l'API."""
        self.api_url = api_url

    def reload_api_cache(self) -> bool:
        """Demande à l'API de recharger son cache."""
        try:
            response = requests.post(f"{self.api_url}/admin/reload", timeout=10)
            if response.status_code == 200:
                print("✓ Cache de l'API rechargé")
                return True
            else:
                print(f"⚠️  Erreur lors du rechargement du cache: {response.status_code}")
                return False
        except Exception as e:
            print(f"⚠️  L'API n'est pas accessible pour le rechargement du cache: {e}")
            return False


class HumanReviewManager:
    """Gestionnaire pour la validation humaine."""

    def __init__(self, data_dir: Path):
        """Initialise le gestionnaire avec le répertoire de données."""
        self.data_dir = data_dir

    def save_needs_review(self, needs_review: list[dict[str, Any]]) -> None:
        """Sauvegarde les cas nécessitant une revue humaine."""
        if needs_review:
            review_df = pd.DataFrame(needs_review)
            review_df.to_csv(self.data_dir / "needs_human_review.csv", index=False)
            print(f"\n⚠️  {len(needs_review)} compétences nécessitent une revue humaine")
            print("    Voir: needs_human_review.csv")

    def export_human_review(self) -> bool:
        """Génère automatiquement l'export CSV pour validation humaine."""
        try:
            subprocess.run(
                ["poetry", "run", "python", "src/cli/export_human_review.py"], check=True
            )
            return True
        except Exception as e:
            print(f"⚠️  Impossible de générer l'export CSV pour validation humaine: {e}")
            return False


class OntologyDensifier:
    """Classe principale pour la densification d'ontologie."""

    def __init__(self, config: Optional[DensificationConfig] = None):
        """Initialise le densificateur avec la configuration."""
        self.config = config or DensificationConfig()
        self.db_manager = SkillDatabaseManager(self.config.db_file)
        self.llm_processor = LLMSkillProcessor(self.config)
        self.cache_manager = ApiCacheManager(self.config.api_url)
        self.review_manager = HumanReviewManager(self.config.data_dir)

    def load_unmapped_skills(self) -> pd.DataFrame:
        """Charge les compétences non mappées depuis le fichier d'analyse."""
        return pd.read_csv(self.config.data_dir / "unmapped_skills_analysis.csv")

    def should_auto_approve(
        self, skill_count: int, suggestion: dict[str, Any], existing_skills: set[str]
    ) -> bool:
        """Détermine si une compétence doit être auto-approuvée."""
        return skill_count > 1000 or suggestion["canonical_name"] in existing_skills

    def process_skill_batch(
        self, batch_df: pd.DataFrame, existing_skills: set[str]
    ) -> tuple[int, list[dict[str, Any]]]:
        """Traite un batch de compétences et retourne le nombre ajouté + cas à réviser."""
        added_count = 0
        needs_review = []

        for _, row in batch_df.iterrows():
            skill_name = str(row["skill"])
            skill_count = int(row["count"])

            suggestion = self.llm_processor.get_llm_suggestion(
                skill_name, skill_count, existing_skills
            )

            if suggestion:
                if self.should_auto_approve(skill_count, suggestion, existing_skills):
                    # Auto-approuver les compétences très fréquentes
                    if self.db_manager.add_skill_to_database(suggestion):
                        added_count += 1
                        existing_skills.add(suggestion["canonical_name"])
                else:
                    # Nécessite revue humaine
                    needs_review.append(
                        {"skill": skill_name, "count": skill_count, "suggestion": suggestion}
                    )

            time.sleep(0.5)  # Rate limiting

        return added_count, needs_review

    def print_final_stats(self, added_count: int, needs_review_count: int) -> None:
        """Affiche les statistiques finales."""
        print("\n✓ Densification terminée")
        print(f"  - {added_count} compétences ajoutées")
        print(f"  - {needs_review_count} en attente de revue")

    def densify_ontology(self, batch_size: int = 10) -> dict[str, Any]:
        """
        Fonction principale de densification d'ontologie.

        Args:
            batch_size: Nombre de compétences à traiter dans ce batch

        Returns:
            Dictionnaire avec les résultats de la densification
        """
        # Charger les données
        unmapped_df = self.load_unmapped_skills()
        existing_skills = self.db_manager.get_existing_canonical_skills()

        print("\n=== DENSIFICATION DE L'ONTOLOGIE ===")
        print(f"Compétences existantes: {len(existing_skills)}")
        print(f"Compétences à traiter: {len(unmapped_df)}")
        print(f"Batch size: {batch_size}")

        # Limiter au top N pour ce run
        top_unmapped = unmapped_df.head(batch_size)

        # Traiter le batch
        added_count, needs_review = self.process_skill_batch(top_unmapped, existing_skills)

        # Sauvegarder les cas à réviser
        self.review_manager.save_needs_review(needs_review)

        # Afficher les statistiques
        self.print_final_stats(added_count, len(needs_review))

        # Générer automatiquement l'export CSV pour validation humaine
        if len(needs_review) > 0:
            self.review_manager.export_human_review()

        # Recharger le cache de l'API
        cache_reloaded = self.cache_manager.reload_api_cache()

        return {
            "added_count": added_count,
            "needs_review_count": len(needs_review),
            "needs_review": needs_review,
            "cache_reloaded": cache_reloaded,
            "existing_skills_count": len(existing_skills),
        }


def parse_batch_size_from_args() -> int:
    """Parse la taille du batch depuis les arguments de ligne de commande."""
    batch_size = 10
    if len(sys.argv) > 1:
        try:
            batch_size = int(sys.argv[1])
        except ValueError:
            print("⚠️  Argument invalide, utilisation de la taille par défaut: 10")
    return batch_size


def main() -> None:
    """Fonction principale du script."""
    batch_size = parse_batch_size_from_args()

    densifier = OntologyDensifier()
    densifier.densify_ontology(batch_size)

    # Les statistiques sont déjà affichées dans densify_ontology()
    # Function doesn't need to return anything


if __name__ == "__main__":
    main()
