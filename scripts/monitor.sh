#!/bin/bash

echo "📊 MONITORING EN TEMPS RÉEL - LA BÊTE"
echo "====================================="

while true; do
    clear
    echo "📊 MONITORING EN TEMPS RÉEL - LA BÊTE"
    echo "====================================="
    echo ""

    # Get stats from API
    stats=$(curl -s http://127.0.0.1:8000/stats 2>/dev/null)

    if [ $? -eq 0 ]; then
        skills=$(echo $stats | python -c "import json, sys; print(json.load(sys.stdin)['total_skills'])")
        aliases=$(echo $stats | python -c "import json, sys; print(json.load(sys.stdin)['total_aliases'])")
        relations=$(echo $stats | python -c "import json, sys; print(json.load(sys.stdin)['total_relations'])")

        echo "🎯 SKILLS:    $skills"
        echo "🔗 ALIASES:   $aliases"
        echo "🌐 RELATIONS: $relations"
        echo ""
        echo "📈 Coverage: $(echo "scale=2; $skills * 100 / 87793" | bc)% of 87,793 unmapped"
    else
        echo "❌ API not responding"
    fi

    echo ""
    echo "🕐 Updated: $(date '+%H:%M:%S')"
    echo ""
    echo "Press Ctrl+C to stop monitoring"

    sleep 5
done
