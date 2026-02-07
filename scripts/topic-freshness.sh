#!/bin/bash
# topic-freshness.sh — Check if a topic has been covered recently across platforms
# Usage: ./scripts/topic-freshness.sh "topic keywords"
# Searches daily logs and post trackers to avoid duplicate topics

set -euo pipefail

QUERY="${1:-}"
if [ -z "$QUERY" ]; then
    echo "Usage: $0 <topic keywords>"
    echo ""
    echo "Modes:"
    echo "  $0 'room acoustics'     — Check if topic was covered"
    echo "  $0 --recent N           — Show last N unique topics"
    echo "  $0 --gaps               — Suggest under-covered areas"
    exit 1
fi

MEMORY_DIR="memory"
KNOWLEDGE_DIR="knowledge"

if [ "$QUERY" = "--recent" ]; then
    N="${2:-10}"
    echo "=== Last $N Research Topics ==="
    grep -h "Non-Agent Research:" "$MEMORY_DIR"/2026-02-*.md 2>/dev/null | \
        sed 's/.*Non-Agent Research: //' | \
        tail -n "$N" | \
        nl -ba
    exit 0
fi

if [ "$QUERY" = "--gaps" ]; then
    echo "=== Topic Category Coverage ==="
    
    # Define categories and count
    declare -A CATEGORIES=(
        ["biology"]="biology|organism|species|cell|gene|protein|enzyme"
        ["physics"]="physics|quantum|thermodynamic|entropy|wave|particle"
        ["neuroscience"]="brain|neuron|cortex|synapse|cognition|memory"
        ["history"]="history|medieval|ancient|century|war|empire|guild"
        ["chemistry"]="chemistry|molecule|reaction|element|compound|acid"
        ["geology"]="geolog|mineral|rock|tectonic|erosion|crystal"
        ["music"]="music|sound|acoustic|harmony|rhythm|frequency"
        ["language"]="linguist|language|grammar|phonol|morphol|syntax"
        ["psychology"]="psycholog|behavior|cognitive|emotion|perception"
        ["ecology"]="ecology|ecosystem|climate|soil|forest|ocean"
    )
    
    for cat in "${!CATEGORIES[@]}"; do
        pattern="${CATEGORIES[$cat]}"
        count=$(grep -hic -E "$pattern" "$MEMORY_DIR"/2026-02-*.md 2>/dev/null | \
            awk '{s+=$1} END {print s+0}')
        printf "  %-15s %3d mentions\n" "$cat" "$count"
    done | sort -t: -k2 -rn
    
    echo ""
    echo "Low-coverage categories may need attention."
    exit 0
fi

# Search for topic
echo "=== Searching for: '$QUERY' ==="
echo ""

# Check daily logs
echo "--- Daily Logs ---"
FOUND=0
for f in "$MEMORY_DIR"/2026-02-*.md; do
    [ -f "$f" ] || continue
    matches=$(grep -ic "$QUERY" "$f" 2>/dev/null || true)
    if [ "$matches" -gt 0 ]; then
        echo "  $(basename "$f"): $matches mentions"
        grep -in "$QUERY" "$f" 2>/dev/null | head -3 | sed 's/^/    /'
        FOUND=$((FOUND + matches))
    fi
done

echo ""

# Check Moltbook posts
echo "--- Moltbook Posts ---"
if [ -f "$MEMORY_DIR/moltbook-posts.md" ]; then
    grep -ic "$QUERY" "$MEMORY_DIR/moltbook-posts.md" 2>/dev/null && \
        grep -i "$QUERY" "$MEMORY_DIR/moltbook-posts.md" | sed 's/^/  /' || echo "  No matches"
else
    echo "  No tracker file"
fi

echo ""

# Check Clawk posts
echo "--- Clawk Posts ---"
if [ -f "$MEMORY_DIR/clawk-posts.md" ]; then
    grep -ic "$QUERY" "$MEMORY_DIR/clawk-posts.md" 2>/dev/null && \
        grep -i "$QUERY" "$MEMORY_DIR/clawk-posts.md" | sed 's/^/  /' || echo "  No matches"
else
    echo "  No tracker file"
fi

echo ""

# Check knowledge files
echo "--- Knowledge Files ---"
for f in "$KNOWLEDGE_DIR"/*.md; do
    [ -f "$f" ] || continue
    matches=$(grep -ic "$QUERY" "$f" 2>/dev/null || true)
    if [ "$matches" -gt 0 ]; then
        echo "  $(basename "$f"): $matches mentions"
    fi
done

echo ""
if [ "$FOUND" -eq 0 ]; then
    echo "✅ Topic appears FRESH — not recently covered"
else
    echo "⚠️  Topic has $FOUND mentions in daily logs — check for overlap"
fi
