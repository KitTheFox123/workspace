#!/bin/bash
# memory-graduate.sh — Identify daily memory entries worth graduating to MEMORY.md
# Scans daily files for patterns indicating long-term significance
# Usage: ./memory-graduate.sh [days_back]

DAYS_BACK=${1:-7}
MEMORY_DIR="memory"
PATTERNS=(
    "lesson"
    "insight"
    "discovery"
    "mistake"
    "learned"
    "important"
    "remember"
    "principle"
    "pattern"
    "always"
    "never"
    "key finding"
    "agent parallel"
    "pushed back"
)

echo "🎓 Memory Graduation Scanner"
echo "Scanning last $DAYS_BACK days for graduation candidates..."
echo "==========================================="

candidates=0
for i in $(seq 0 $DAYS_BACK); do
    DATE=$(date -d "-${i} days" +%Y-%m-%d 2>/dev/null || date -v-${i}d +%Y-%m-%d 2>/dev/null)
    FILE="$MEMORY_DIR/$DATE.md"
    if [ -f "$FILE" ]; then
        found=0
        for pattern in "${PATTERNS[@]}"; do
            matches=$(grep -ic "$pattern" "$FILE" 2>/dev/null)
            if [ "$matches" -gt 0 ]; then
                if [ "$found" -eq 0 ]; then
                    echo ""
                    echo "📅 $DATE ($(wc -l < "$FILE") lines)"
                    found=1
                fi
                # Extract the line with context
                grep -in "$pattern" "$FILE" | head -3 | while read -r line; do
                    linenum=$(echo "$line" | cut -d: -f1)
                    content=$(echo "$line" | cut -d: -f2- | sed 's/^[[:space:]]*//' | head -c 120)
                    echo "  [$pattern] L$linenum: $content"
                    candidates=$((candidates + 1))
                done
            fi
        done
    fi
done

echo ""
echo "==========================================="

# Check MEMORY.md staleness
if [ -f "MEMORY.md" ]; then
    last_mod=$(stat -c %Y MEMORY.md 2>/dev/null || stat -f %m MEMORY.md 2>/dev/null)
    now=$(date +%s)
    age_hours=$(( (now - last_mod) / 3600 ))
    echo "📝 MEMORY.md last updated: ${age_hours}h ago"
    if [ "$age_hours" -gt 48 ]; then
        echo "⚠️  MEMORY.md is stale (>48h). Consider graduating recent insights."
    fi
fi

# Size check
if [ -f "MEMORY.md" ]; then
    size=$(wc -c < MEMORY.md)
    lines=$(wc -l < MEMORY.md)
    echo "📊 MEMORY.md: $lines lines, $size bytes"
fi

echo ""
echo "Tip: Review candidates above and manually add the best to MEMORY.md"
echo "Focus on: lessons learned, principles discovered, relationship insights"
