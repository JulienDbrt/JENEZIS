#!/usr/bin/env python3
"""
Export des entités nécessitant une revue humaine.
Génère un CSV pour validation manuelle des entités non trouvées sur Wikipedia.
"""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

# Configuration
RESOLVER_DB = Path("data/databases/entity_resolver.db")
OUTPUT_DIR = Path("data/output")


def export_entities_for_review() -> None:
    """Export les entités marquées NEEDS_REVIEW vers un CSV."""

    # Créer le dossier de sortie si nécessaire
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Connexion à la base
    conn = sqlite3.connect(RESOLVER_DB)
    cursor = conn.cursor()

    # Récupérer les entités à valider
    cursor.execute(
        """
        SELECT
            eq.canonical_id,
            eq.entity_type,
            ce.display_name,
            eq.error_message,
            eq.created_at,
            eq.processed_at
        FROM enrichment_queue eq
        LEFT JOIN canonical_entities ce ON eq.canonical_id = ce.canonical_id
        WHERE eq.status = 'NEEDS_REVIEW'
        ORDER BY eq.entity_type, eq.canonical_id
    """
    )

    entities = cursor.fetchall()

    if not entities:
        print("✅ Aucune entité en attente de revue !")
        conn.close()
        return

    # Générer le nom du fichier avec timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = OUTPUT_DIR / f"entity_review_{timestamp}.csv"

    # Créer le CSV
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # En-têtes
        writer.writerow(
            [
                "canonical_id",
                "display_name",
                "entity_type",
                "wikipedia_url",
                "description",
                "approve",
                "notes",
            ]
        )

        # Données
        for entity in entities:
            canonical_id, entity_type, display_name, error_msg, created_at, processed_at = entity
            writer.writerow(
                [
                    canonical_id,
                    display_name or canonical_id.replace("_", " ").title(),
                    entity_type,
                    "",  # URL Wikipedia à remplir manuellement
                    "",  # Description à remplir manuellement
                    "",  # Colonne approve (OUI/NON)
                    error_msg,  # Notes
                ]
            )

    # Créer aussi une copie "latest" pour faciliter l'accès
    latest_file = OUTPUT_DIR / "entity_review_latest.csv"
    with open(output_file, "rb") as src, open(latest_file, "wb") as dst:
        dst.write(src.read())

    # Afficher le résumé
    print("\n📋 EXPORT POUR VALIDATION D'ENTITÉS")
    print("=" * 50)
    print(f"📊 {len(entities)} entité(s) à valider")
    print(f"📁 Fichier: {output_file.name}")
    print(f"📁 Copie: {latest_file.name}")

    # Afficher un aperçu
    print("\n🔝 Aperçu des entités à valider:")
    for entity in entities[:5]:
        canonical_id, entity_type, display_name, *_ = entity
        name = display_name or canonical_id.replace("_", " ").title()
        print(f"   {name} ({entity_type})")

    if len(entities) > 5:
        print(f"   ... et {len(entities) - 5} autres")

    print("\n💡 Instructions:")
    print("1. Ouvrir le CSV dans Excel")
    print("2. Rechercher manuellement les entités sur Wikipedia")
    print("3. Remplir les colonnes wikipedia_url et description")
    print("4. Mettre OUI dans 'approve' pour valider")
    print("5. Utiliser import_entity_enrichment.py pour réimporter")

    conn.close()


if __name__ == "__main__":
    export_entities_for_review()
