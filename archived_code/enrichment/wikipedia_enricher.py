#!/usr/bin/env python3
"""
Script d'enrichissement automatique des entités.
Lit la file d'attente, interroge Wikipedia, et enrichit les entités dans Neo4j.
"""

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# --- CONFIGURATION ---
PROJECT_ROOT = Path(__file__).parent.parent.parent
RESOLVER_DB_FILE = PROJECT_ROOT / "data" / "databases" / "entity_resolver.db"

# Configuration Neo4j (depuis variables d'environnement)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")  # Requis depuis .env

# API Wikipedia
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_FR_API_URL = "https://fr.wikipedia.org/w/api.php"

# Configuration du traitement
BATCH_SIZE = 10  # Nombre d'entités à traiter par exécution
RATE_LIMIT_DELAY = 1  # Délai en secondes entre les appels API


# --- Brique 1: Communication avec Wikipedia ---
def get_entity_info_from_wikipedia(entity_name: str, lang: str = "fr") -> dict[str, str]:
    """
    Interroge l'API Wikipedia pour obtenir une description courte.

    Args:
        entity_name: Nom de l'entité à rechercher
        lang: Langue (fr ou en)

    Returns:
        Dict avec les informations trouvées
    """
    api_url = WIKIPEDIA_FR_API_URL if lang == "fr" else WIKIPEDIA_API_URL

    # Étape 1 : Recherche
    search_params: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": entity_name,
        "srlimit": 1,
        "srprop": "snippet",
    }

    # Ajouter un User-Agent pour éviter les blocages
    headers = {
        "User-Agent": "ErwinHarmonizer/1.0 (https://github.com/erwin-labs; contact@erwin-labs.com)"
    }

    try:
        response = requests.get(api_url, params=search_params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        search_results = data.get("query", {}).get("search", [])

        if not search_results:
            print(f"  → Aucun résultat Wikipedia pour '{entity_name}'")
            return {}

        page_title = search_results[0]["title"]
        print(f"  → Page Wikipedia trouvée : '{page_title}'")

        # Étape 2 : Obtenir l'extrait de la page
        extract_params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "prop": "extracts|pageprops|categories",
            "exintro": True,
            "explaintext": True,
            "exsentences": 3,
            "titles": page_title,
        }

        response = requests.get(api_url, params=extract_params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return {}

        page_data = next(iter(pages.values()))
        extract = page_data.get("extract", "")

        # Nettoyer l'extrait
        if extract:
            extract = extract.replace("\n", " ").strip()
            # Limiter à 500 caractères pour Neo4j
            if len(extract) > 500:
                extract = extract[:497] + "..."

        # Extraire des métadonnées supplémentaires
        categories = page_data.get("categories", [])
        category_names = [
            cat.get("title", "").replace("Catégorie:", "").strip() for cat in categories[:3]
        ]

        result = {
            "description": extract,
            "wikipedia_url": f"https://{lang}.wikipedia.org/wiki/{page_title.replace(' ', '_')}",
        }

        # Essayer de détecter le secteur depuis les catégories
        if category_names:
            result["categories"] = ", ".join(category_names)
            # Détection basique du secteur
            for cat in category_names:
                cat_lower = cat.lower()
                if "technologie" in cat_lower or "informatique" in cat_lower:
                    result["sector"] = "Technology"
                    break
                elif "banque" in cat_lower or "finance" in cat_lower:
                    result["sector"] = "Finance"
                    break
                elif "énergie" in cat_lower or "pétrole" in cat_lower:
                    result["sector"] = "Energy"
                    break
                elif "aéronautique" in cat_lower or "aérospatial" in cat_lower:
                    result["sector"] = "Aerospace"
                    break
                elif "automobile" in cat_lower:
                    result["sector"] = "Automotive"
                    break

        return result

    except requests.RequestException as e:
        print(f"  ⚠️  Erreur Wikipedia API pour '{entity_name}': {e}")
        return {}


# --- Brique 2: Communication avec Neo4j ---
class Neo4jUpdater:
    """Classe pour mettre à jour les entités dans Neo4j."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        """
        Initialise la connexion Neo4j.

        Args:
            uri: URI de la base Neo4j (ex: bolt://localhost:7687)
            user: Nom d'utilisateur
            password: Mot de passe
        """
        self.uri = uri
        self.user = user
        self.password = password
        self._driver = None

    def connect(self) -> bool:
        """Établit la connexion à Neo4j."""
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # Test de connexion
            if self._driver is not None:
                with self._driver.session() as session:
                    result = session.run("RETURN 1")
                    result.single()
            print(f"✅ Connecté à Neo4j sur {self.uri}")
            return True
        except ImportError:
            print("❌ Le driver Neo4j n'est pas installé. Exécutez: pip install neo4j")
            return False
        except Exception as e:
            print(f"❌ Impossible de se connecter à Neo4j: {e}")
            return False

    def close(self) -> None:
        """Ferme la connexion Neo4j."""
        if self._driver:
            self._driver.close()

    def update_entity_properties(
        self, label: str, entity_id: str, properties: dict[str, Any]
    ) -> bool:
        """
        Met à jour les propriétés d'une entité dans Neo4j.

        Args:
            label: Label du nœud (Entreprise, Ecole, Organisation)
            entity_id: ID canonique de l'entité
            properties: Propriétés à ajouter/mettre à jour

        Returns:
            True si succès, False sinon
        """
        if not self._driver:
            print("  ⚠️  Pas de connexion Neo4j")
            return False

        try:
            with self._driver.session() as session:
                # Vérifier si le nœud existe (requête paramétrée sécurisée)
                # Note: Le label doit être connu et validé à l'avance
                if label not in ["Entreprise", "Ecole", "Organisation"]:
                    print(f"  ⚠️  Label invalide: {label}")
                    return False

                check_query = f"MATCH (n:{label} {{id: $id}}) RETURN count(n) as count"
                result = session.run(check_query, id=entity_id)
                count = result.single()["count"]

                if count == 0:
                    # Le nœud n'existe pas encore dans Neo4j
                    # On le crée avec les propriétés enrichies (requête paramétrée)
                    create_query = f"""
                    CREATE (n:{label} {{id: $id}})
                    SET n += $props
                    RETURN n
                    """
                    session.run(create_query, id=entity_id, props=properties)
                    print(f"  ✅ Neo4j: Nœud {label} '{entity_id}' créé avec propriétés enrichies")
                else:
                    # Le nœud existe, on met à jour ses propriétés (requête paramétrée)
                    update_query = f"""
                    MATCH (n:{label} {{id: $id}})
                    SET n += $props
                    RETURN n
                    """
                    session.run(update_query, id=entity_id, props=properties)
                    print(
                        f"  ✅ Neo4j: Nœud {label} '{entity_id}' enrichi avec {list(properties.keys())}"
                    )

                return True

        except Exception as e:
            print(f"  ❌ Erreur Neo4j pour {label} '{entity_id}': {e}")
            return False


# --- Brique 3: Mode simulation (sans Neo4j) ---
def simulate_neo4j_update(label: str, entity_id: str, properties: dict[str, Any]) -> None:
    """
    Simule une mise à jour Neo4j (pour tests sans Neo4j).

    Args:
        label: Label du nœud
        entity_id: ID de l'entité
        properties: Propriétés à mettre à jour
    """
    print("  [SIMULATION] Neo4j UPDATE:")
    print(f"    Label: {label}")
    print(f"    ID: {entity_id}")
    print("    Propriétés:")
    for key, value in properties.items():
        if isinstance(value, str) and len(value) > 100:
            value = value[:97] + "..."
        print(f"      - {key}: {value}")


# --- Brique 4: Orchestrateur ---
def main(use_neo4j: bool = True) -> None:
    """
    Script principal d'enrichissement.

    Args:
        use_neo4j: Si True, met à jour Neo4j. Si False, mode simulation.
    """
    print("\n" + "=" * 60)
    print("🔍 SCRIPT D'ENRICHISSEMENT AUTOMATIQUE DES ENTITÉS")
    print("=" * 60)

    # Connexion à la DB du résolveur
    conn = sqlite3.connect(RESOLVER_DB_FILE)
    cursor = conn.cursor()

    # Connexion à Neo4j (optionnelle)
    neo4j_updater = None
    if use_neo4j:
        neo4j_updater = Neo4jUpdater(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        if not neo4j_updater.connect():
            print("\n⚠️  Mode simulation activé (pas de connexion Neo4j)")
            use_neo4j = False

    try:
        # 1. Statistiques de la file
        cursor.execute(
            """
            SELECT status, COUNT(*)
            FROM enrichment_queue
            GROUP BY status
        """
        )
        stats = dict(cursor.fetchall())
        print("\n📊 État de la file d'enrichissement:")
        for status, count in stats.items():
            print(f"   - {status}: {count}")

        # 2. Sélectionner les entités en attente
        cursor.execute(
            """
            SELECT id, canonical_id, entity_type
            FROM enrichment_queue
            WHERE status = 'PENDING'
            ORDER BY created_at
            LIMIT ?
        """,
            (BATCH_SIZE,),
        )

        pending_entities = cursor.fetchall()

        if not pending_entities:
            print("\n✅ Aucune nouvelle entité à enrichir.")
            return

        print(f"\n🎯 {len(pending_entities)} entité(s) à traiter dans ce batch")
        print("-" * 40)

        success_count = 0
        failed_count = 0

        for db_id, canonical_id, entity_type in pending_entities:
            print(f"\n📍 Traitement: '{canonical_id}' (Type: {entity_type})")

            # Marquer comme en cours de traitement
            cursor.execute(
                "UPDATE enrichment_queue SET status = 'PROCESSING' WHERE id = ?", (db_id,)
            )
            conn.commit()

            # Transformer l'ID canonique en nom recherchable
            search_name = canonical_id.replace("_", " ").title()
            print(f"  → Recherche Wikipedia pour: '{search_name}'")

            # Récupérer les informations depuis Wikipedia
            info = get_entity_info_from_wikipedia(search_name, lang="fr")

            # Si pas de résultat en français, essayer en anglais
            if not info or not info.get("description"):
                print("  → Tentative en anglais...")
                info = get_entity_info_from_wikipedia(search_name, lang="en")

            if not info or not info.get("description"):
                print("  ⚠️  Aucune information trouvée - Marqué pour revue humaine")
                cursor.execute(
                    "UPDATE enrichment_queue SET status = 'NEEDS_REVIEW', processed_at = ?, error_message = ? WHERE id = ?",
                    (
                        datetime.now().isoformat(),
                        "No Wikipedia data found - requires manual review",
                        db_id,
                    ),
                )
                conn.commit()
                failed_count += 1
                continue

            # Mapper le type d'entité vers le label Neo4j
            label_map = {"COMPANY": "Entreprise", "SCHOOL": "Ecole", "UNKNOWN": "Organisation"}
            neo4j_label = label_map.get(entity_type, "Organisation")

            # Ajouter le nom d'affichage si on ne l'a pas
            if "name" not in info:
                info["name"] = search_name

            # Mettre à jour dans Neo4j ou simuler
            if use_neo4j and neo4j_updater:
                success = neo4j_updater.update_entity_properties(neo4j_label, canonical_id, info)
            else:
                simulate_neo4j_update(neo4j_label, canonical_id, info)
                success = True

            if success:
                # Marquer comme complété
                cursor.execute(
                    "UPDATE enrichment_queue SET status = 'COMPLETED', processed_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), db_id),
                )
                conn.commit()
                success_count += 1
            else:
                # Marquer comme échoué
                cursor.execute(
                    "UPDATE enrichment_queue SET status = 'FAILED', processed_at = ?, error_message = ? WHERE id = ?",
                    (datetime.now().isoformat(), "Neo4j update failed", db_id),
                )
                conn.commit()
                failed_count += 1

            # Respecter le rate limiting
            time.sleep(RATE_LIMIT_DELAY)

        # Résumé
        print("\n" + "=" * 60)
        print("📈 RÉSUMÉ DU TRAITEMENT")
        print(f"   ✅ Succès: {success_count}")
        print(f"   ❌ Échecs: {failed_count}")
        print(f"   📊 Total traité: {success_count + failed_count}")

    except Exception as e:
        print(f"\n❌ Erreur dans le script: {e}")
        import traceback

        traceback.print_exc()

    finally:
        conn.close()
        if neo4j_updater:
            neo4j_updater.close()
        print("\n✅ Script terminé")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    import sys

    # Vérifier les arguments de ligne de commande
    if "--no-neo4j" in sys.argv or "--simulate" in sys.argv:
        print("Mode simulation activé (pas de mise à jour Neo4j)")
        main(use_neo4j=False)
    else:
        main(use_neo4j=True)
