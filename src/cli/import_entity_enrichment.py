#!/usr/bin/env python3
"""
Import des enrichissements d'entités validés manuellement.
Lit le CSV de revue et met à jour la base de données avec les informations validées.
"""

import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Configuration
RESOLVER_DB = Path("data/databases/entity_resolver.db")
OUTPUT_DIR = Path("data/output")


def import_reviewed_entities(csv_file: Optional[str] = None) -> None:
    """
    Import les entités validées depuis le CSV de revue.

    Args:
        csv_file: Chemin vers le fichier CSV (par défaut: entity_review_latest.csv)
    """

    # Utiliser le fichier spécifié ou le dernier
    if csv_file:
        input_file = Path(csv_file)
    else:
        input_file = OUTPUT_DIR / "entity_review_latest.csv"

    if not input_file.exists():
        print(f"❌ Fichier non trouvé: {input_file}")
        return

    # Connexion à la base
    conn = sqlite3.connect(RESOLVER_DB)
    cursor = conn.cursor()

    # Lire le CSV
    imported = 0
    skipped = 0

    with open(input_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            canonical_id = row["canonical_id"]
            approve = row.get("approve", "").upper()

            # Ignorer si pas approuvé
            if approve not in ["OUI", "YES", "Y", "1", "TRUE"]:
                skipped += 1
                continue

            # Préparer les métadonnées enrichies
            metadata = {}

            if row.get("wikipedia_url"):
                metadata["wikipedia_url"] = row["wikipedia_url"]

            if row.get("description"):
                metadata["description"] = row["description"]

            if row.get("notes"):
                metadata["manual_notes"] = row["notes"]

            metadata["manually_reviewed"] = True
            metadata["review_date"] = datetime.now().isoformat()

            # Mettre à jour l'entité canonique si elle existe
            cursor.execute(
                """
                UPDATE canonical_entities
                SET metadata = ?
                WHERE canonical_id = ?
            """,
                (json.dumps(metadata), canonical_id),
            )

            # Marquer comme complété dans la queue d'enrichissement
            cursor.execute(
                """
                UPDATE enrichment_queue
                SET status = 'COMPLETED',
                    processed_at = ?,
                    error_message = 'Manually reviewed and approved'
                WHERE canonical_id = ?
                AND status = 'NEEDS_REVIEW'
            """,
                (datetime.now().isoformat(), canonical_id),
            )

            if cursor.rowcount > 0:
                imported += 1
                print(f"✅ Importé: {canonical_id}")

    conn.commit()
    conn.close()

    # Résumé
    print("\n" + "=" * 50)
    print("📊 RÉSUMÉ DE L'IMPORT")
    print(f"   ✅ Entités importées: {imported}")
    print(f"   ⏭️  Entités ignorées: {skipped}")
    print(f"   📊 Total traité: {imported + skipped}")

    if imported > 0:
        print("\n💡 Les métadonnées ont été mises à jour dans la base.")
        print("   Lancez le script d'enrichissement Neo4j pour propager les changements.")


if __name__ == "__main__":
    # Vérifier si un fichier est passé en argument
    if len(sys.argv) > 1:
        import_reviewed_entities(sys.argv[1])
    else:
        import_reviewed_entities()
