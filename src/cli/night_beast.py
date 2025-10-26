#!/usr/bin/env python3
"""
🌙 NIGHT BEAST - Session d'enrichissement nocturne massive
Traite les skills en continu pendant 5 heures avec des batches progressifs
"""

import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from config import HARMONIZER_API_URL, ONTOLOGY_DB


def get_current_stats() -> tuple[int, int]:
    """Récupère les stats actuelles de l'ontologie."""
    conn = sqlite3.connect(ONTOLOGY_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM skills")
    total_skills = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM aliases")
    total_aliases = cursor.fetchone()[0]

    conn.close()
    return total_skills, total_aliases


def reload_cache() -> None:
    """Recharge le cache de l'API."""
    import requests

    try:
        response = requests.post(f"{HARMONIZER_API_URL}/admin/reload", timeout=10)
        if response.status_code == 200:
            print("  ✅ Cache API rechargé")
    except:
        print("  ⚠️  Impossible de recharger le cache")


def run_batch(size: int, batch_num: int) -> float:
    """Lance un batch de densification."""
    print(f"\n{'='*60}")
    print(f"🔥 BATCH #{batch_num} - {size} SKILLS")
    print(f"{'='*60}")

    start_time = time.time()

    try:
        result = subprocess.run(
            ["poetry", "run", "python", "src/cli/densify_ontology.py", str(size)],
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minutes max par batch
        )

        elapsed = time.time() - start_time

        if result.returncode == 0:
            print(f"✅ Batch complété en {elapsed:.1f}s")

            # Extraire les stats du output
            output_lines = result.stdout.split("\n")
            for line in output_lines:
                if "Ajouté" in line or "Auto-approuvé" in line or "Review nécessaire" in line:
                    print(f"  {line.strip()}")
        else:
            print(f"❌ Erreur dans le batch: {result.stderr}")

    except subprocess.TimeoutExpired:
        print("⏱️ Batch timeout après 30 minutes")
    except Exception as e:
        print(f"❌ Erreur: {e}")

    return elapsed if "elapsed" in locals() else 0.0


def main() -> None:
    """Session nocturne de 5 heures."""

    print("\n" + "=" * 60)
    print("🌙 NIGHT BEAST - SESSION NOCTURNE DE 5 HEURES")
    print("=" * 60)

    start_time = datetime.now()
    end_time = start_time + timedelta(hours=5)

    initial_skills, initial_aliases = get_current_stats()
    print(f"\n📊 État initial: {initial_skills} skills, {initial_aliases} aliases")
    print(f"⏰ Début: {start_time.strftime('%H:%M:%S')}")
    print(f"⏰ Fin prévue: {end_time.strftime('%H:%M:%S')}")

    # Stratégie de batches progressifs
    batch_sizes = [
        100,  # Warm-up
        200,  # Acceleration
        300,  # Cruise speed
        500,  # Full throttle
        1000,  # BEAST MODE
    ]

    batch_num = 0
    total_elapsed = 0.0

    while datetime.now() < end_time:
        batch_num += 1

        # Déterminer la taille du batch selon la progression
        if batch_num <= 2:
            size = batch_sizes[0]  # 100
        elif batch_num <= 5:
            size = batch_sizes[1]  # 200
        elif batch_num <= 10:
            size = batch_sizes[2]  # 300
        elif batch_num <= 15:
            size = batch_sizes[3]  # 500
        else:
            size = batch_sizes[4]  # 1000 - BEAST MODE!

        print(
            f"\n⏰ Temps restant: {(end_time - datetime.now()).total_seconds() / 3600:.1f} heures"
        )

        # Lancer le batch
        batch_time = run_batch(size, batch_num)
        total_elapsed += batch_time

        # Recharger le cache après chaque batch
        reload_cache()

        # Stats actuelles
        current_skills, current_aliases = get_current_stats()
        new_skills = current_skills - initial_skills
        new_aliases = current_aliases - initial_aliases

        print(f"\n📈 Progression: +{new_skills} skills, +{new_aliases} aliases")
        print(f"   Total: {current_skills} skills, {current_aliases} aliases")

        # Estimation
        if batch_num > 0 and new_skills > 0:
            rate = new_skills / (total_elapsed / 3600) if total_elapsed > 0 else 0
            print(f"   Vitesse: ~{rate:.0f} skills/heure")

        # Pause courte entre les batches
        if datetime.now() < end_time:
            print("\n💤 Pause 30 secondes...")
            time.sleep(30)

    # Résumé final
    final_skills, final_aliases = get_current_stats()
    total_new_skills = final_skills - initial_skills
    total_new_aliases = final_aliases - initial_aliases
    duration = datetime.now() - start_time

    print("\n" + "=" * 60)
    print("🎉 SESSION NOCTURNE TERMINÉE!")
    print("=" * 60)
    print(f"⏱️ Durée totale: {duration}")
    print("📊 Résultats:")
    print(f"   - Skills ajoutés: {total_new_skills}")
    print(f"   - Aliases ajoutés: {total_new_aliases}")
    print(f"   - Total skills: {final_skills}")
    print(f"   - Total aliases: {final_aliases}")
    print(f"   - Batches traités: {batch_num}")

    if total_new_skills > 0:
        print(
            f"\n🚀 Performance: {total_new_skills / (duration.total_seconds() / 3600):.0f} skills/heure"
        )

    print("\n✨ La bête s'est bien nourrie cette nuit!")


if __name__ == "__main__":
    main()
