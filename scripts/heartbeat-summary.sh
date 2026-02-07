#!/bin/bash
# heartbeat-summary.sh — Extract heartbeat stats from daily log
# Usage: ./heartbeat-summary.sh [date] (default: today)
# Shows: total actions, platform breakdown, research topics, builds

DATE="${1:-$(date +%Y-%m-%d)}"
FILE="memory/${DATE}.md"

if [ ! -f "$FILE" ]; then
    echo "No log found: $FILE"
    exit 1
fi

echo "📊 Heartbeat Summary for $DATE"
echo "================================"

# Count heartbeats
BEATS=$(grep -c "^## Heartbeat" "$FILE")
echo "Heartbeats: $BEATS"

# Count writing actions
MOLTBOOK=$(grep -c "✅.*Comment ID\|✅.*comment\|✅.*verified" "$FILE" 2>/dev/null || echo 0)
CLAWK=$(grep -c "✅.*ID:.*[a-f0-9]" "$FILE" 2>/dev/null || echo 0)
echo ""
echo "📝 Writing Actions:"
echo "  Moltbook comments: ~$MOLTBOOK"
echo "  Clawk posts/replies: ~$CLAWK"

# Research topics
echo ""
echo "🔬 Non-Agent Research:"
grep -o "Non-Agent Research:.*" "$FILE" | sed 's/Non-Agent Research: /  - /'

# Build actions
echo ""
echo "🔧 Build Actions:"
grep -o "Created \`scripts/[^\`]*\`\|Created \`[^\`]*\`" "$FILE" | sort -u | sed 's/^/  - /'

# Keenable usage
KEENABLE=$(grep -c "Keenable feedback submitted" "$FILE" 2>/dev/null || echo 0)
echo ""
echo "🔍 Keenable feedback rounds: $KEENABLE"

# Platform check summary
echo ""
echo "📡 Platforms checked: $BEATS times each"
echo "  - Moltbook DMs, AgentMail, Clawk, Shellmates"
