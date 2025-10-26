#!/usr/bin/env python3
"""Prompts pour la densification de l'ontologie - Facilement modifiable"""

# Le prompt chirurgical - Pas de blabla, que du résultat
LLM_PROMPT = """Tu es un expert en taxonomie de compétences IT et de gestion de projet.
Ta seule tâche est de catégoriser la compétence brute fournie.
Ne fournis AUCUNE explication, AUCUN texte d'introduction. Réponds UNIQUEMENT avec un objet JSON.

La compétence brute à analyser est : "{skill_name}"

Compétences canoniques existantes pour référence : {existing_skills}

Réponds avec un objet JSON contenant les clés suivantes :
- "canonical_name": Le nom normalisé et propre pour la compétence (en snake_case minuscule).
- "aliases": Une liste de variations possibles ou d'alias pour cette compétence (en minuscules). Inclut la compétence brute.
- "parents": Une liste de noms canoniques de compétences parentes. Choisis parmi les compétences existantes si possible. Si tu dois créer un nouveau parent, fais-le.

Exemples :
- Pour "git", la réponse pourrait être :
  {{"canonical_name": "git", "aliases": ["git", "github", "gitlab", "git-flow"], "parents": ["version_control"]}}
- Pour "Jira", la réponse pourrait être :
  {{"canonical_name": "jira", "aliases": ["jira", "atlassian jira"], "parents": ["ticketing_tools", "project_management_tools"]}}
- Pour "MS Project", la réponse pourrait être :
  {{"canonical_name": "ms_project", "aliases": ["ms_project", "microsoft project"], "parents": ["project_management_tools"]}}

Voici la compétence à traiter. Ne réponds rien d'autre que le JSON.
Compétence : "{skill_name}"
"""

# Prompt système pour contraindre le LLM
SYSTEM_PROMPT = """Tu es un expert en taxonomie IT. Tu réponds UNIQUEMENT en JSON valide. Pas de texte, pas d'explication, que du JSON."""
