#!/usr/bin/env python3
"""
Export Human Review - Génère un CSV formaté pour validation manuelle
Automatiquement appelé après chaque batch de densification
"""

import ast
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data" / "output"


def parse_suggestion(suggestion_str: str) -> tuple[str, str, str]:
    """Parse la suggestion JSON string en colonnes séparées"""
    try:
        # La suggestion est stockée comme string JSON dans le CSV
        suggestion = ast.literal_eval(suggestion_str)  # Safe evaluation of dict string

        canonical_name = suggestion.get("canonical_name", "")
        aliases = "|".join(suggestion.get("aliases", []))
        parents = "|".join(suggestion.get("parents", []))

        return canonical_name, aliases, parents
    except Exception:
        return "", "", ""


def export_human_review() -> bool:
    """Export needs_human_review.csv vers un format plus lisible pour Excel"""

    input_file = DATA_DIR / "needs_human_review.csv"

    if not input_file.exists():
        print("❌ Pas de fichier needs_human_review.csv trouvé")
        return False

    # Lire le fichier d'entrée
    df = pd.read_csv(input_file)

    if df.empty:
        print("✅ Aucune compétence nécessite de revue humaine")
        return True

    # Parser les suggestions
    parsed_data = []
    for _, row in df.iterrows():
        canonical_name, aliases, parents = parse_suggestion(str(row["suggestion"]))
        parsed_data.append(
            {
                "skill": row["skill"],
                "count": row["count"],
                "canonical_name": canonical_name,
                "aliases": aliases,
                "parents": parents,
                "approve": "",  # Colonne vide pour validation
            }
        )

    # Créer le DataFrame final
    export_df = pd.DataFrame(parsed_data)

    # Trier par fréquence décroissante
    export_df = export_df.sort_values("count", ascending=False)

    # Générer le nom de fichier avec date et heure complètes
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = DATA_DIR / f"human_review_{timestamp}.csv"

    # Sauvegarder
    export_df.to_csv(output_file, index=False)

    # Créer aussi une version "latest" pour accès facile
    latest_file = DATA_DIR / "human_review_export_latest.csv"
    export_df.to_csv(latest_file, index=False)

    print("\n📋 EXPORT POUR VALIDATION HUMAINE")
    print(f"{'='*50}")
    print(f"📊 {len(export_df)} compétences à valider")
    print(f"📁 Fichier: {output_file.name}")
    print("📁 Copie: human_review_export_latest.csv")
    print("\n🔝 Top 5 à valider:")

    for _i, row in export_df.head(5).iterrows():
        print(f"   {row['skill']} ({row['count']} occ.) → {row['canonical_name']}")

    print("\n💡 Ouvrir dans Excel et mettre OUI/NON dans la colonne 'approve'")

    return True


def main() -> None:
    """Point d'entrée principal"""
    success = export_human_review()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
