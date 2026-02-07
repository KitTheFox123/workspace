#!/bin/bash
# memory-fractal.sh — Analyze information density decay across memory files
# Inspired by Lovejoy et al. 2025 fractal geological time study
# Shows how our daily logs exhibit Sadler-like effects

set -euo pipefail

MEMORY_DIR="${1:-memory}"

echo "=== Memory Fractal Analysis ==="
echo "Analyzing information density across daily logs..."
echo ""

# Get all daily files sorted by date
files=$(ls -1 "$MEMORY_DIR"/2026-*.md 2>/dev/null | sort -r)
if [ -z "$files" ]; then
    echo "No daily memory files found in $MEMORY_DIR"
    exit 1
fi

today=$(date +%Y-%m-%d)
echo "Date           | Lines | Words | Heartbeats | Words/HB | Age(days)"
echo "---------------|-------|-------|------------|----------|----------"

while IFS= read -r f; do
    fname=$(basename "$f" .md)
    lines=$(wc -l < "$f")
    words=$(wc -w < "$f")
    heartbeats=$(grep -c "^## Heartbeat" "$f" 2>/dev/null || echo 0)
    if [ "$heartbeats" -gt 0 ]; then
        wpb=$((words / heartbeats))
    else
        wpb=0
    fi
    # Calculate age in days
    age=$(( ($(date -d "$today" +%s) - $(date -d "$fname" +%s 2>/dev/null || echo $(date +%s))) / 86400 ))
    printf "%-15s| %5d | %5d | %10d | %8d | %d\n" "$fname" "$lines" "$words" "$heartbeats" "$wpb" "$age"
done <<< "$files"

echo ""
echo "=== Density Decay Pattern ==="
echo "If fractal: words/heartbeat should be roughly constant (self-similar)"
echo "If Sadler effect: older files should show lower density per heartbeat"
