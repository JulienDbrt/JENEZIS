#!/usr/bin/env python3
"""
Script d'ingestion pour transformer les CV parsés en commandes Cypher pour Neo4j.
Orchestre l'appel à l'API Harmonizer et génère les requêtes pour peupler le graphe.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Union

import requests

# --- CONFIGURATION ---
HARMONIZER_API_URL = "http://127.0.0.1:8000/harmonize"
ENTITY_RESOLVER_API_URL = "http://127.0.0.1:8001/resolve"
PARSED_CV_FILE = "data/examples/cv_example.json"
CANDIDATE_ID_PREFIX = "CAND"


# --- BRICK 1: API CLIENT ---
def call_harmonizer(skills: list[str]) -> dict[str, str]:
    """
    Appelle l'API Harmonizer et retourne un mapping de compétence originale -> canonique.

    Args:
        skills: Liste des compétences à harmoniser

    Returns:
        Dictionnaire mapping skill original -> skill canonique
    """
    if not skills:
        return {}

    try:
        response = requests.post(HARMONIZER_API_URL, json={"skills": skills}, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Construire le mapping à partir de la réponse
        mapping = {}

        # Traiter les skills mappés
        for skill_data in data.get("mapped", []):
            original = skill_data.get("original_skill")
            canonical = skill_data.get("canonical_skill")
            if original and canonical:
                mapping[original] = canonical

        # Traiter les skills non mappés (les garder tels quels mais nettoyés)
        for unmapped_skill in data.get("unmapped", []):
            # Nettoyer le skill non mappé pour qu'il soit utilisable comme nœud
            cleaned = unmapped_skill.lower().strip().replace(" ", "_").replace("-", "_")
            mapping[unmapped_skill] = cleaned

        return mapping

    except requests.exceptions.RequestException as e:
        print(f"⚠️  ATTENTION: Impossible de contacter l'API Harmonizer à {HARMONIZER_API_URL}")
        print(f"   Erreur: {e}")
        print("   Utilisation du mode fallback (nettoyage basique)")
        # En cas d'échec, on retourne un mapping basique
        return {
            skill: skill.lower().strip().replace(" ", "_").replace("-", "_") for skill in skills
        }


def call_entity_resolver(
    entities: list[str], entity_type: str = "COMPANY"
) -> dict[str, dict[str, Union[str, bool]]]:
    """
    Appelle l'API Entity Resolver pour résoudre les noms d'entités.

    Args:
        entities: Liste des entités à résoudre
        entity_type: Type d'entité (COMPANY ou SCHOOL)

    Returns:
        Dictionnaire mapping nom original -> {id, name}
    """
    if not entities:
        return {}

    try:
        response = requests.post(
            ENTITY_RESOLVER_API_URL,
            json={"entities": entities, "entity_type": entity_type},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        mapping = {}
        for result in data.get("results", []):
            mapping[result["original_name"]] = {
                "id": result["canonical_id"],
                "name": result["display_name"],
                "is_known": result["is_known"],
            }
        return mapping

    except requests.exceptions.RequestException as e:
        print(
            f"⚠️  ATTENTION: Impossible de contacter l'API Entity Resolver à {ENTITY_RESOLVER_API_URL}"
        )
        print(f"   Erreur: {e}")
        print("   Utilisation du mode fallback (nettoyage basique)")
        # Fallback : nettoyer les noms pour en faire des IDs valides
        return {
            name: {
                "id": name.lower().strip().replace(" ", "_").replace(".", "").replace(",", ""),
                "name": name,
                "is_known": False,
            }
            for name in entities
        }


# --- BRICK 2: DATA PROCESSING ---
def extract_all_skills(parsed_data: dict[str, Any]) -> set[str]:
    """
    Extrait toutes les compétences uniques depuis les données parsées.

    Args:
        parsed_data: Données parsées du CV

    Returns:
        Set de toutes les compétences uniques
    """
    all_skills: set[str] = set()

    # Récupérer le profile depuis la structure complète
    documents = parsed_data.get("documents", [])
    if not documents:
        return all_skills

    profile = documents[0].get("parsed_data", {}).get("extracted_data", {}).get("profile", {})

    # Skills du profil général
    for skill in profile.get("basics", {}).get("skills", []):
        all_skills.add(skill)

    # Skills des expériences professionnelles
    for exp in profile.get("professional_experiences", []):
        for skill in exp.get("skills_used", []):
            all_skills.add(skill)

    # Technologies des projets
    for project in profile.get("projects", []):
        for tech in project.get("technologies_used", []):
            all_skills.add(tech)

    return all_skills


def process_parsed_cv(parsed_data: dict[str, Any]) -> dict[str, Any]:
    """
    Prend les données parsées, extrait les entités et les enrichit avec l'harmonisation.

    Args:
        parsed_data: Structure JSON complète du CV parsé

    Returns:
        Structure de données pour le graphe avec nodes et relations
    """
    # Extraire le profile depuis la structure complète
    documents = parsed_data.get("documents", [])
    if not documents:
        raise ValueError("Aucun document trouvé dans les données parsées")

    document = documents[0]
    profile = document.get("parsed_data", {}).get("extracted_data", {}).get("profile", {})
    basics = profile.get("basics", {})

    # 1. Extraire toutes les compétences uniques
    all_skills = extract_all_skills(parsed_data)
    print(f"📊 {len(all_skills)} compétences uniques identifiées")

    # 2. Extraire toutes les entreprises et écoles uniques
    all_companies = set()
    all_schools = set()

    # Entreprises des expériences
    for exp in profile.get("professional_experiences", []):
        if exp.get("company"):
            all_companies.add(exp.get("company"))

    # Écoles de l'éducation
    for edu in profile.get("educations", []):
        if edu.get("issuing_organization"):
            all_schools.add(edu.get("issuing_organization"))

    # Organisations des certifications (peuvent être des écoles ou entreprises)
    for cert in profile.get("trainings_and_certifications", []):
        if cert.get("issuing_organization"):
            # On les traite comme des entreprises par défaut
            all_companies.add(cert.get("issuing_organization"))

    print(f"🏢 {len(all_companies)} entreprises uniques identifiées")
    print(f"🎓 {len(all_schools)} écoles/universités uniques identifiées")

    # 3. Appeler l'Harmonizer pour les compétences
    if all_skills:
        print(f"🔄 Appel de l'Harmonizer pour {len(all_skills)} compétences...")
        skill_mapping = call_harmonizer(list(all_skills))
        print(
            f"✅ Harmonisation terminée - {len([v for v in skill_mapping.values() if v])} compétences mappées"
        )
    else:
        skill_mapping = {}

    # 4. Appeler l'Entity Resolver pour les entreprises
    if all_companies:
        print(f"🔄 Appel de l'Entity Resolver pour {len(all_companies)} entreprises...")
        company_mapping = call_entity_resolver(list(all_companies), "COMPANY")
        known_companies = sum(1 for v in company_mapping.values() if v.get("is_known"))
        print(
            f"✅ Résolution terminée - {known_companies}/{len(all_companies)} entreprises reconnues"
        )
    else:
        company_mapping = {}

    # 5. Appeler l'Entity Resolver pour les écoles
    if all_schools:
        print(f"🔄 Appel de l'Entity Resolver pour {len(all_schools)} écoles...")
        school_mapping = call_entity_resolver(list(all_schools), "SCHOOL")
        known_schools = sum(1 for v in school_mapping.values() if v.get("is_known"))
        print(f"✅ Résolution terminée - {known_schools}/{len(all_schools)} écoles reconnues")
    else:
        school_mapping = {}

    # 3. Construire la structure de données finale pour le graphe
    graph_data: dict[str, list[Any]] = {"nodes": [], "relations": []}

    # Créer le nœud Candidat
    emails = basics.get("emails", [])
    candidate_email = emails[0] if emails else f"unknown_{uuid.uuid4().hex[:8]}@temp.com"
    candidate_id = f"{CANDIDATE_ID_PREFIX}_{candidate_email.replace('@', '_at_').replace('.', '_')}"

    candidate_node = {
        "label": "Candidat",
        "properties": {
            "id": candidate_id,
            "firstName": basics.get("first_name", "Unknown"),
            "lastName": basics.get("last_name", "Unknown"),
            "email": candidate_email,
            "profession": basics.get("profession"),
            "totalExperience": basics.get("total_experience_in_years"),
            "summary": basics.get("summary", "")[:500],  # Limiter la taille du summary
        },
    }
    graph_data["nodes"].append(candidate_node)

    # Traiter chaque expérience professionnelle
    for i, exp in enumerate(profile.get("professional_experiences", [])):
        # Créer le nœud Experience
        experience_id = f"{candidate_id}_exp_{i}"

        # Formater les dates
        start_date = exp.get("start_date", {})
        end_date = exp.get("end_date", {})
        start_str = (
            f"{start_date.get('year', 'Unknown')}-{start_date.get('month', 1):02d}"
            if start_date
            else None
        )
        end_str = (
            f"{end_date.get('year', 'Current')}-{end_date.get('month', 12):02d}"
            if end_date and not exp.get("is_current")
            else "Current"
        )

        experience_node = {
            "label": "Experience",
            "properties": {
                "id": experience_id,
                "title": exp.get("title", "Unknown Position"),
                # Ne plus stocker company comme propriété, c'est maintenant une relation
                "location": exp.get("location"),
                "startDate": start_str,
                "endDate": end_str,
                "duration": exp.get("duration_in_months"),
                "isCurrent": exp.get("is_current", False),
                "description": (
                    exp.get("description", "")[:500] if exp.get("description") else None
                ),  # Limiter la taille
            },
        }
        graph_data["nodes"].append(experience_node)

        # Créer le nœud Entreprise (sera mergé dans Cypher)
        company_name_raw = exp.get("company", "Unknown Company")
        if company_name_raw and company_name_raw in company_mapping:
            resolved_company = company_mapping[company_name_raw]
        else:
            # Fallback si l'entreprise n'était pas dans le mapping
            resolved_company = {
                "id": company_name_raw.lower().strip().replace(" ", "_").replace(".", ""),
                "name": company_name_raw,
                "is_known": False,
            }

        company_node = {
            "label": "Entreprise",
            "properties": {"id": resolved_company["id"], "name": resolved_company["name"]},
        }
        graph_data["nodes"].append(company_node)

        # Créer la relation Experience -> Entreprise
        graph_data["relations"].append(
            {
                "from": {"label": "Experience", "id": experience_id},
                "to": {"label": "Entreprise", "id": resolved_company["id"]},
                "type": "CHEZ",
                "properties": {},
            }
        )

        # Créer la relation Candidat -> Experience
        graph_data["relations"].append(
            {
                "from": {"label": "Candidat", "id": candidate_id},
                "to": {"label": "Experience", "id": experience_id},
                "type": "A_TRAVAILLE",
                "properties": {},
            }
        )

        # Traiter les compétences de cette expérience
        for skill in exp.get("skills_used", []):
            canonical_skill = skill_mapping.get(
                skill, skill.lower().replace(" ", "_").replace("-", "_")
            )

            # Créer le nœud Compétence (sera mergé dans Cypher)
            skill_node = {
                "label": "Competence",
                "properties": {
                    "name": canonical_skill,
                    "originalName": skill if skill != canonical_skill else None,
                },
            }
            graph_data["nodes"].append(skill_node)

            # Créer la relation Experience -> Competence
            graph_data["relations"].append(
                {
                    "from": {"label": "Experience", "id": experience_id},
                    "to": {"label": "Competence", "name": canonical_skill},
                    "type": "A_UTILISE",
                    "properties": {},
                }
            )

    # Traiter les projets
    for i, project in enumerate(profile.get("projects", [])):
        project_id = f"{candidate_id}_proj_{i}"

        project_node = {
            "label": "Projet",
            "properties": {
                "id": project_id,
                "name": project.get("name", f"Project {i+1}"),
                "description": (
                    project.get("description", "")[:500] if project.get("description") else None
                ),
                "url": project.get("url"),
            },
        }
        graph_data["nodes"].append(project_node)

        # Relation Candidat -> Projet
        graph_data["relations"].append(
            {
                "from": {"label": "Candidat", "id": candidate_id},
                "to": {"label": "Projet", "id": project_id},
                "type": "A_REALISE",
                "properties": {},
            }
        )

        # Technologies utilisées dans le projet
        for tech in project.get("technologies_used", []):
            canonical_tech = skill_mapping.get(
                tech, tech.lower().replace(" ", "_").replace("-", "_")
            )

            tech_node = {
                "label": "Competence",
                "properties": {
                    "name": canonical_tech,
                    "originalName": tech if tech != canonical_tech else None,
                },
            }
            graph_data["nodes"].append(tech_node)

            graph_data["relations"].append(
                {
                    "from": {"label": "Projet", "id": project_id},
                    "to": {"label": "Competence", "name": canonical_tech},
                    "type": "UTILISE",
                    "properties": {},
                }
            )

    # Traiter l'éducation
    for i, edu in enumerate(profile.get("educations", [])):
        education_id = f"{candidate_id}_edu_{i}"

        education_node = {
            "label": "Formation",
            "properties": {
                "id": education_id,
                "degreeName": edu.get("degree_name"),
                # Ne plus stocker organization comme propriété
                "startYear": edu.get("start_year"),
                "endYear": edu.get("end_year"),
                "description": (
                    edu.get("description", "")[:500] if edu.get("description") else None
                ),
            },
        }
        graph_data["nodes"].append(education_node)

        # Créer le nœud École (sera mergé)
        school_name_raw = edu.get("issuing_organization", "Unknown School")
        if school_name_raw and school_name_raw in school_mapping:
            resolved_school = school_mapping[school_name_raw]
        else:
            # Fallback
            resolved_school = {
                "id": school_name_raw.lower().strip().replace(" ", "_").replace(".", ""),
                "name": school_name_raw,
                "is_known": False,
            }

        school_node = {
            "label": "Ecole",
            "properties": {"id": resolved_school["id"], "name": resolved_school["name"]},
        }
        graph_data["nodes"].append(school_node)

        # Relations
        graph_data["relations"].append(
            {
                "from": {"label": "Candidat", "id": candidate_id},
                "to": {"label": "Formation", "id": education_id},
                "type": "A_SUIVI",
                "properties": {},
            }
        )

        graph_data["relations"].append(
            {
                "from": {"label": "Formation", "id": education_id},
                "to": {"label": "Ecole", "id": resolved_school["id"]},
                "type": "DELIVREE_PAR",
                "properties": {},
            }
        )

    # Traiter les certifications
    for i, cert in enumerate(profile.get("trainings_and_certifications", [])):
        cert_id = f"{candidate_id}_cert_{i}"

        cert_node = {
            "label": "Certification",
            "properties": {
                "id": cert_id,
                "name": cert.get("certification_name"),
                # Ne plus stocker organization comme propriété
                "year": cert.get("year"),
                "description": (
                    cert.get("description", "")[:500] if cert.get("description") else None
                ),
            },
        }
        graph_data["nodes"].append(cert_node)

        # Créer le nœud Organisation (entreprise émettrice de la certification)
        org_name_raw = cert.get("issuing_organization", "Unknown Organization")
        if org_name_raw and org_name_raw in company_mapping:
            resolved_org = company_mapping[org_name_raw]
        else:
            # Fallback
            resolved_org = {
                "id": org_name_raw.lower().strip().replace(" ", "_").replace(".", ""),
                "name": org_name_raw,
                "is_known": False,
            }

        org_node = {
            "label": "Organisation",
            "properties": {"id": resolved_org["id"], "name": resolved_org["name"]},
        }
        graph_data["nodes"].append(org_node)

        # Relations
        graph_data["relations"].append(
            {
                "from": {"label": "Candidat", "id": candidate_id},
                "to": {"label": "Certification", "id": cert_id},
                "type": "A_OBTENU",
                "properties": {"year": cert.get("year")},
            }
        )

        graph_data["relations"].append(
            {
                "from": {"label": "Certification", "id": cert_id},
                "to": {"label": "Organisation", "id": resolved_org["id"]},
                "type": "DELIVREE_PAR",
                "properties": {},
            }
        )

    return graph_data


# --- BRICK 3: CYPHER GENERATION ---
def escape_cypher_string(value: str) -> str:
    """Échappe les caractères spéciaux pour Cypher."""
    if value is None:
        return ""
    # Échapper les quotes simples et les backslashes
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def generate_cypher_queries(graph_data: dict[str, Any]) -> list[str]:
    """
    Génère une liste de requêtes Cypher MERGE à partir de la structure de données.

    Args:
        graph_data: Structure avec nodes et relations

    Returns:
        Liste de requêtes Cypher
    """
    queries = []

    # Utiliser un set pour éviter les doublons (surtout pour les compétences)
    created_nodes = set()

    # Générer les MERGE pour les nœuds
    for node in graph_data["nodes"]:
        label = node["label"]
        properties = node["properties"]

        # Déterminer la clé unique pour le MERGE
        if label == "Competence":
            key_prop = "name"
        elif label in ["Entreprise", "Ecole", "Organisation"]:
            key_prop = "id"  # Utiliser l'ID canonique résolu
        else:
            key_prop = "id"

        if key_prop not in properties:
            continue

        key_value = properties[key_prop]
        node_signature = f"{label}:{key_prop}:{key_value}"

        # Éviter les doublons
        if node_signature in created_nodes:
            continue
        created_nodes.add(node_signature)

        # Construire la requête MERGE
        set_clauses = []
        for prop, value in properties.items():
            if value is not None and value != "":
                if isinstance(value, bool):
                    set_clauses.append(f"n.{prop} = {str(value).lower()}")
                elif isinstance(value, (int, float)):
                    set_clauses.append(f"n.{prop} = {value}")
                else:
                    escaped_value = escape_cypher_string(value)
                    set_clauses.append(f"n.{prop} = '{escaped_value}'")

        if set_clauses:
            set_clause_str = ", ".join(set_clauses)
            escaped_key = escape_cypher_string(key_value)
            query = (
                f"MERGE (n:{label} {{{key_prop}: '{escaped_key}'}})\n"
                f"  ON CREATE SET {set_clause_str}\n"
                f"  ON MATCH SET {set_clause_str}"
            )
        else:
            escaped_key = escape_cypher_string(key_value)
            query = f"MERGE (n:{label} {{{key_prop}: '{escaped_key}'}})"

        queries.append(query)

    # Générer les MERGE pour les relations
    created_relations = set()
    for rel in graph_data["relations"]:
        from_node = rel["from"]
        to_node = rel["to"]
        rel_type = rel["type"]
        rel_props = rel.get("properties", {})

        # Déterminer les clés pour matcher les nœuds
        from_key = "name" if from_node["label"] == "Competence" else "id"
        to_key = "name" if to_node["label"] == "Competence" else "id"

        from_value = from_node.get(from_key) or from_node.get("id") or from_node.get("name")
        to_value = to_node.get(to_key) or to_node.get("id") or to_node.get("name")

        if not from_value or not to_value:
            continue

        # Éviter les relations dupliquées
        rel_signature = (
            f"{from_node['label']}:{from_value}-{rel_type}->{to_node['label']}:{to_value}"
        )
        if rel_signature in created_relations:
            continue
        created_relations.add(rel_signature)

        escaped_from = escape_cypher_string(from_value)
        escaped_to = escape_cypher_string(to_value)

        # Construire la requête
        query_parts = [
            f"MATCH (a:{from_node['label']} {{{from_key}: '{escaped_from}'}})",
            f"MATCH (b:{to_node['label']} {{{to_key}: '{escaped_to}'}})",
        ]

        # Ajouter les propriétés de la relation si présentes
        if rel_props:
            prop_clauses = []
            for prop, value in rel_props.items():
                if value is not None:
                    if isinstance(value, bool):
                        prop_clauses.append(f"{prop}: {str(value).lower()}")
                    elif isinstance(value, (int, float)):
                        prop_clauses.append(f"{prop}: {value}")
                    else:
                        escaped_val = escape_cypher_string(value)
                        prop_clauses.append(f"{prop}: '{escaped_val}'")

            if prop_clauses:
                props_str = ", ".join(prop_clauses)
                query_parts.append(f"MERGE (a)-[:{rel_type} {{{props_str}}}]->(b)")
            else:
                query_parts.append(f"MERGE (a)-[:{rel_type}]->(b)")
        else:
            query_parts.append(f"MERGE (a)-[:{rel_type}]->(b)")

        query = "\n".join(query_parts)
        queries.append(query)

    return queries


# --- MAIN ORCHESTRATOR ---
def main() -> int:
    """Point d'entrée principal du script d'ingestion."""
    print("\n" + "=" * 60)
    print("🚀 PIPELINE D'INGESTION CV -> GRAPHE NEO4J")
    print("=" * 60 + "\n")

    # 1. Charger les données parsées
    input_file = Path(PARSED_CV_FILE)
    if not input_file.exists():
        print(f"❌ ERREUR: Le fichier '{PARSED_CV_FILE}' n'existe pas.")
        print("   Vérifiez que le fichier est bien présent à la racine du projet.")
        return 1

    try:
        with open(input_file, encoding="utf-8") as f:
            parsed_cv = json.load(f)
        print(f"✅ Fichier '{PARSED_CV_FILE}' chargé avec succès")

        # Afficher quelques infos sur le CV
        documents = parsed_cv.get("documents", [])
        if documents:
            profile = (
                documents[0].get("parsed_data", {}).get("extracted_data", {}).get("profile", {})
            )
            basics = profile.get("basics", {})
            if basics:
                print(
                    f"   Candidat: {basics.get('first_name', 'Unknown')} {basics.get('last_name', 'Unknown')}"
                )
                print(f"   Profession: {basics.get('profession', 'Non spécifiée')}")
                print(f"   Expérience: {basics.get('total_experience_in_years', 'N/A')} ans")

    except json.JSONDecodeError as e:
        print(f"❌ ERREUR: Le fichier '{PARSED_CV_FILE}' n'est pas un JSON valide.")
        print(f"   Détail: {e}")
        return 1
    except Exception as e:
        print(f"❌ ERREUR lors du chargement du fichier: {e}")
        return 1

    # 2. Traiter et enrichir les données
    print("\n📋 Traitement des données...")
    try:
        final_graph_structure = process_parsed_cv(parsed_cv)
        print("✅ Données traitées et enrichies avec succès")

        # Statistiques
        node_counts: dict[str, int] = {}
        for node in final_graph_structure["nodes"]:
            label = node["label"]
            node_counts[label] = node_counts.get(label, 0) + 1

        print("\n📊 Statistiques du graphe généré:")
        for label, count in sorted(node_counts.items()):
            print(f"   - {label}: {count} nœud(s)")
        print(f"   - Relations: {len(final_graph_structure['relations'])}")

    except Exception as e:
        print(f"❌ ERREUR lors du traitement des données: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # 3. Générer les requêtes Cypher
    print("\n🔨 Génération des requêtes Cypher...")
    try:
        cypher_queries = generate_cypher_queries(final_graph_structure)
        print(f"✅ {len(cypher_queries)} requêtes Cypher générées")

    except Exception as e:
        print(f"❌ ERREUR lors de la génération Cypher: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # 4. Sauvegarder les requêtes dans un fichier
    output_file = Path("cypher_queries.txt")
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("// ====================================\n")
            f.write("// REQUÊTES CYPHER POUR NEO4J\n")
            f.write("// Générées depuis: " + PARSED_CV_FILE + "\n")
            f.write("// ====================================\n\n")

            for i, query in enumerate(cypher_queries, 1):
                f.write(f"// Requête {i}/{len(cypher_queries)}\n")
                f.write(query)
                f.write(";\n\n")

        print(f"\n💾 Requêtes sauvegardées dans '{output_file}'")
        print("   Vous pouvez les exécuter dans Neo4j Browser ou cypher-shell")

    except Exception as e:
        print(f"⚠️  Impossible de sauvegarder les requêtes: {e}")

    # 5. Afficher un échantillon des requêtes
    print("\n📝 Échantillon des requêtes générées:")
    print("-" * 50)
    for i, query in enumerate(cypher_queries[:3], 1):
        print(f"\n// Requête {i}")
        print(query + ";")
    if len(cypher_queries) > 3:
        print(f"\n... et {len(cypher_queries) - 3} autres requêtes")

    print("\n" + "=" * 60)
    print("✅ PIPELINE TERMINÉ AVEC SUCCÈS")
    print("=" * 60)
    print("\n🎯 Prochaines étapes:")
    print("   1. Démarrez Neo4j si ce n'est pas déjà fait")
    print("   2. Ouvrez Neo4j Browser (http://localhost:7474)")
    print("   3. Copiez-collez les requêtes depuis 'cypher_queries.txt'")
    print("   4. Ou utilisez: cypher-shell < cypher_queries.txt")
    print()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
