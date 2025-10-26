#!/bin/bash

echo "🔍 MONITORING THE NIGHT BEAST"
echo "=============================="

while true; do
    clear
    echo "🌙 NIGHT BEAST MONITOR - $(date '+%H:%M:%S')"
    echo "=============================="

    # Stats actuelles
    skills=$(sqlite3 data/databases/ontology.db "SELECT COUNT(*) FROM skills;" 2>/dev/null)
    aliases=$(sqlite3 data/databases/ontology.db "SELECT COUNT(*) FROM aliases;" 2>/dev/null)

    echo "📊 Current Stats:"
    echo "   Skills: $skills"
    echo "   Aliases: $aliases"
    echo ""

    # Derniers skills ajoutés
    echo "🆕 Last 5 skills added:"
    sqlite3 data/databases/ontology.db "SELECT canonical_name FROM skills ORDER BY id DESC LIMIT 5;" 2>/dev/null | head -5
    echo ""

    # Fichiers générés
    echo "📁 Generated files:"
    ls -lh data/output/*.csv 2>/dev/null | tail -3

    echo ""
    echo "Refreshing in 30 seconds... (Ctrl+C to stop)"
    sleep 30
done
