#!/usr/bin/env python3
"""
Analyse des compétences non mappées dans l'ontologie.

Ce module fournit des fonctions pour analyser les compétences qui ne sont pas
encore présentes dans l'ontologie et identifier des patterns utiles.
"""

import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from config import CANDIDATS_COMPETENCES_CSV, ONTOLOGY_DB, OUTPUT_DIR


def load_mapped_skills(db_path: str) -> set[str]:
    """
    Charge la liste des compétences déjà mappées depuis la base de données.

    Args:
        db_path: Chemin vers la base de données d'ontologie

    Returns:
        Set des noms canoniques des compétences mappées
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT canonical_name FROM skills")
    mapped_skills = {row[0] for row in cursor.fetchall()}
    conn.close()
    return mapped_skills


def load_skills_data(csv_path: str) -> pd.DataFrame:
    """
    Charge les données des compétences depuis le fichier CSV.

    Args:
        csv_path: Chemin vers le fichier CSV des candidats

    Returns:
        DataFrame avec les données des compétences
    """
    return pd.read_csv(csv_path)


def identify_unmapped_skills(df: pd.DataFrame, mapped_skills: set[str]) -> set[str]:
    """
    Identifie les compétences non mappées.

    Args:
        df: DataFrame avec les données des compétences
        mapped_skills: Set des compétences déjà mappées

    Returns:
        Set des compétences non mappées
    """
    all_skills = set(df["competence"].unique())
    return all_skills - mapped_skills


def count_skill_frequencies(df: pd.DataFrame, unmapped_skills: set[str]) -> dict[str, Any]:
    """
    Compte les occurrences des compétences non mappées.

    Args:
        df: DataFrame avec les données des compétences
        unmapped_skills: Set des compétences non mappées

    Returns:
        Dictionnaire {compétence: nombre_occurrences}
    """
    skill_counts = df["competence"].value_counts()
    return {skill: skill_counts[skill] for skill in unmapped_skills if skill in skill_counts.index}


def sort_skills_by_frequency(unmapped_counts: dict[str, Any]) -> list[tuple[str, Any]]:
    """
    Trie les compétences par fréquence décroissante.

    Args:
        unmapped_counts: Dictionnaire {compétence: count}

    Returns:
        Liste de tuples (compétence, count) triée par fréquence
    """
    return sorted(unmapped_counts.items(), key=lambda x: x[1], reverse=True)


def detect_frameworks(unmapped_skills: set[str]) -> list[str]:
    """
    Détecte les frameworks/librairies dans les compétences non mappées.

    Args:
        unmapped_skills: Set des compétences non mappées

    Returns:
        Liste des frameworks détectés
    """
    framework_keywords = [".js", "framework", "lib"]
    return [
        skill
        for skill in unmapped_skills
        if any(word in skill.lower() for word in framework_keywords)
    ]


def detect_tools(unmapped_skills: set[str]) -> list[str]:
    """
    Détecte les outils/produits dans les compétences non mappées.

    Args:
        unmapped_skills: Set des compétences non mappées

    Returns:
        Liste des outils détectés
    """
    tool_keywords = ["tool", "suite", "server", "manager"]
    return [
        skill for skill in unmapped_skills if any(word in skill.lower() for word in tool_keywords)
    ]


def detect_certifications(unmapped_skills: set[str]) -> list[str]:
    """
    Détecte les certifications dans les compétences non mappées.

    Args:
        unmapped_skills: Set des compétences non mappées

    Returns:
        Liste des certifications détectées
    """
    cert_keywords = ["certified", "certification", "crt"]
    return [
        skill for skill in unmapped_skills if any(word in skill.lower() for word in cert_keywords)
    ]


def calculate_statistics(
    df: pd.DataFrame, unmapped_skills: set[str], unmapped_counts: dict[str, Any]
) -> dict[str, float]:
    """
    Calcule les statistiques de l'analyse.

    Args:
        df: DataFrame avec toutes les données
        unmapped_skills: Set des compétences non mappées
        unmapped_counts: Dictionnaire des comptages

    Returns:
        Dictionnaire avec les statistiques
    """
    total_skills = len(df["competence"].unique())
    total_relations = len(df)
    total_unmapped_occurrences = sum(unmapped_counts.values())

    return {
        "total_unmapped_skills": len(unmapped_skills),
        "total_skills": total_skills,
        "total_unmapped_occurrences": total_unmapped_occurrences,
        "total_relations": total_relations,
        "unmapped_percentage": 100 * total_unmapped_occurrences / total_relations,
    }


def save_analysis_results(sorted_unmapped: list[tuple[str, Any]], output_path: Path) -> None:
    """
    Sauvegarde les résultats de l'analyse dans un fichier CSV.

    Args:
        sorted_unmapped: Liste triée des compétences non mappées
        output_path: Chemin de sortie pour le fichier CSV
    """
    df_output = pd.DataFrame(sorted_unmapped, columns=["skill", "count"])
    df_output.to_csv(output_path, index=False)


def print_analysis_results(
    stats: dict[str, float],
    sorted_unmapped: list[tuple[str, Any]],
    frameworks: list[str],
    tools: list[str],
    certifications: list[str],
) -> None:
    """
    Affiche les résultats de l'analyse.

    Args:
        stats: Statistiques calculées
        sorted_unmapped: Compétences triées par fréquence
        frameworks: Frameworks détectés
        tools: Outils détectés
        certifications: Certifications détectées
    """
    print("=== ANALYSE DES COMPÉTENCES NON MAPPÉES ===\n")
    print(
        f"Total: {stats['total_unmapped_skills']} compétences non mappées sur {stats['total_skills']}"
    )
    print(f"Ces compétences représentent {stats['total_unmapped_occurrences']} occurrences")
    print(
        f"sur {stats['total_relations']} relations totales ({stats['unmapped_percentage']:.1f}%)\n"
    )

    print("Top 50 des compétences non mappées (à considérer pour l'ontologie):\n")
    for i, (skill, count) in enumerate(sorted_unmapped[:50], 1):
        print(f"{i:3}. {skill[:40]:40} ({count:5} occurrences)")

    print("\n=== PATTERNS DÉTECTÉS ===\n")

    if frameworks[:10]:
        print("Frameworks/Libraries possibles:")
        for f in frameworks[:10]:
            print(f"  - {f}")

    if tools[:10]:
        print("\nOutils/Produits possibles:")
        for t in tools[:10]:
            print(f"  - {t}")

    if certifications[:10]:
        print("\nCertifications possibles:")
        for c in certifications[:10]:
            print(f"  - {c}")


def analyze_unmapped_skills(
    csv_path: Optional[str] = None, db_path: Optional[str] = None, output_dir: Optional[Path] = None
) -> dict:
    """
    Fonction principale d'analyse des compétences non mappées.

    Args:
        csv_path: Chemin vers le fichier CSV (optionnel, utilise config par défaut)
        db_path: Chemin vers la DB (optionnel, utilise config par défaut)
        output_dir: Répertoire de sortie (optionnel, utilise config par défaut)

    Returns:
        Dictionnaire avec tous les résultats de l'analyse
    """
    # Utiliser les valeurs par défaut si non spécifiées
    csv_path = csv_path or CANDIDATS_COMPETENCES_CSV
    db_path = db_path or ONTOLOGY_DB
    output_dir = output_dir or OUTPUT_DIR

    # Étapes de l'analyse
    df = load_skills_data(csv_path)
    mapped_skills = load_mapped_skills(db_path)
    unmapped_skills = identify_unmapped_skills(df, mapped_skills)
    unmapped_counts = count_skill_frequencies(df, unmapped_skills)
    sorted_unmapped = sort_skills_by_frequency(unmapped_counts)

    # Détection de patterns
    frameworks = detect_frameworks(unmapped_skills)
    tools = detect_tools(unmapped_skills)
    certifications = detect_certifications(unmapped_skills)

    # Statistiques
    stats = calculate_statistics(df, unmapped_skills, unmapped_counts)

    # Sauvegarde
    output_file = output_dir / "unmapped_skills_analysis.csv"
    save_analysis_results(sorted_unmapped, output_file)

    # Assemblage des résultats
    results = {
        "stats": stats,
        "sorted_unmapped": sorted_unmapped,
        "patterns": {"frameworks": frameworks, "tools": tools, "certifications": certifications},
        "output_file": str(output_file),
    }

    return results


def main() -> None:
    """Point d'entrée principal du script."""
    results = analyze_unmapped_skills()

    # Affichage des résultats
    print_analysis_results(
        results["stats"],
        results["sorted_unmapped"],
        results["patterns"]["frameworks"],
        results["patterns"]["tools"],
        results["patterns"]["certifications"],
    )

    print(f"\n✓ Analyse complète sauvegardée dans: {results['output_file']}")


if __name__ == "__main__":
    main()
