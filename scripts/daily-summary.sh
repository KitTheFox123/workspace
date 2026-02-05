#!/bin/bash
# daily-summary.sh - Generate end-of-day summary for memory archival
# Usage: ./daily-summary.sh [YYYY-MM-DD]

DATE=${1:-$(date -u +%Y-%m-%d)}
DAILY_FILE="$HOME/.openclaw/workspace/memory/${DATE}.md"

if [ ! -f "$DAILY_FILE" ]; then
    echo "No log file for $DATE"
    exit 1
fi

echo "=== Daily Summary: $DATE ==="
echo ""

# Count heartbeats
HEARTBEATS=$(grep -c "^## Heartbeat" "$DAILY_FILE" 2>/dev/null || echo 0)
echo "📊 Heartbeats: $HEARTBEATS"

# Count writing sections (look for "Writing Actions")
WRITES=$(grep -c "Writing Actions" "$DAILY_FILE" 2>/dev/null || echo 0)
echo "📝 Writing sections: $WRITES"

# Count build sections
BUILDS=$(grep -c "Build Action" "$DAILY_FILE" 2>/dev/null || echo 0)
echo "🔨 Build sections: $BUILDS"

# Count research queries
RESEARCH=$(grep -c "Research:" "$DAILY_FILE" 2>/dev/null || echo 0)
echo "🔍 Research entries: $RESEARCH"

# Extract key insights (lines starting with "Key insight" or "Key finding")
echo ""
echo "=== Key Insights ==="
grep -i "key insight\|key finding\|core thesis\|connection to" "$DAILY_FILE" | head -10

# Extract scripts created
echo ""
echo "=== Scripts Created ==="
grep -oE "scripts/[a-z0-9-]+\.sh" "$DAILY_FILE" | sort -u

# Extract Clawk mentions replied to
echo ""
echo "=== Agents Engaged ==="
grep -oE "@[a-z_0-9]+" "$DAILY_FILE" | sort | uniq -c | sort -rn | head -10

echo ""
echo "---"
echo "Use this summary to update MEMORY.md with distilled learnings."
