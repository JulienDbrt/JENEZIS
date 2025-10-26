#!/usr/bin/env python3
"""
Import Approved Skills - Importe les skills approuvés manuellement dans l'ontologie
"""

import sqlite3
import sys
from contextlib import suppress
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT_DIR = Path(__file__).parent.parent.parent
DB_FILE = ROOT_DIR / "ontology.db"
DATA_DIR = ROOT_DIR / "data" / "output"


def import_approved_skills(csv_file: Optional[str] = None) -> bool:
    """Importe les skills approuvés (approve=OUI) dans la base de données"""

    # Utiliser le fichier fourni ou le dernier export
    if csv_file:
        input_file = Path(csv_file)
    else:
        input_file = DATA_DIR / "human_review_export_latest.csv"

    if not input_file.exists():
        print(f"❌ Fichier non trouvé: {input_file}")
        return False

    # Lire le CSV
    df = pd.read_csv(input_file)

    # Filtrer seulement les approuvés
    approved = df[df["approve"].str.upper() == "OUI"]

    if approved.empty:
        print("⚠️  Aucune compétence approuvée (colonne 'approve' = OUI)")
        return False

    print("\n📥 IMPORT DES COMPÉTENCES APPROUVÉES")
    print(f"{'='*50}")
    print(f"📊 {len(approved)} compétences à importer")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    imported = 0
    skipped = 0

    for _, row in approved.iterrows():
        try:
            # Vérifier si le skill existe déjà
            cursor.execute(
                "SELECT id FROM skills WHERE canonical_name = ?", (row["canonical_name"],)
            )
            existing = cursor.fetchone()

            if existing:
                skill_id = existing[0]
                print(f"⚠️  {row['canonical_name']} existe déjà")
                skipped += 1
            else:
                # Créer le nouveau skill
                cursor.execute(
                    "INSERT INTO skills (canonical_name) VALUES (?)", (row["canonical_name"],)
                )
                skill_id = cursor.lastrowid
                print(f"✅ Ajouté: {row['canonical_name']}")

            # Ajouter les aliases
            if pd.notna(row["aliases"]):
                aliases = row["aliases"].split("|")
                for alias in aliases:
                    alias = alias.strip()
                    if alias:
                        with suppress(sqlite3.IntegrityError):  # Alias existe déjà
                            cursor.execute(
                                "INSERT INTO aliases (alias_name, skill_id) VALUES (?, ?)",
                                (alias, skill_id),
                            )

            # Ajouter les relations parent
            if pd.notna(row["parents"]):
                parents = row["parents"].split("|")
                for parent_name in parents:
                    parent_name = parent_name.strip()
                    if parent_name:
                        # Trouver l'ID du parent
                        cursor.execute(
                            "SELECT id FROM skills WHERE canonical_name = ?", (parent_name,)
                        )
                        parent = cursor.fetchone()
                        if parent:
                            with suppress(sqlite3.IntegrityError):  # Relation existe déjà
                                cursor.execute(
                                    "INSERT INTO hierarchy (child_id, parent_id) VALUES (?, ?)",
                                    (skill_id, parent[0]),
                                )

            imported += 1

        except Exception as e:
            print(f"❌ Erreur pour {row['skill']}: {e}")

    conn.commit()
    conn.close()

    print("\n📊 RÉSULTATS:")
    print(f"  ✅ Importés: {imported}")
    print(f"  ⚠️  Ignorés: {skipped}")
    print("\n💡 N'oublie pas de recharger le cache API: POST /admin/reload")

    return True


def main() -> None:
    """Point d'entrée principal"""
    csv_file = sys.argv[1] if len(sys.argv) > 1 else None
    success = import_approved_skills(csv_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
