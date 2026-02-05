#!/bin/bash
# heartbeat-stats.sh - Show today's heartbeat progress
# Usage: ./heartbeat-stats.sh

DATE=$(date -u +%Y-%m-%d)
DAILY_FILE="$HOME/.openclaw/workspace/memory/${DATE}.md"

if [ ! -f "$DAILY_FILE" ]; then
    echo "No log file for today ($DATE)"
    exit 1
fi

echo "=== Today's Stats ($DATE) ==="
echo ""

# Count metrics
HEARTBEATS=$(grep -c "^## Heartbeat" "$DAILY_FILE" 2>/dev/null || echo 0)
WRITES=$(grep -c "Writing Actions" "$DAILY_FILE" 2>/dev/null || echo 0)
BUILDS=$(grep -c "### Build Action" "$DAILY_FILE" 2>/dev/null || echo 0)
# Also count "Build:" entries
BUILDS2=$(grep -c "^🔨 Build:" "$DAILY_FILE" 2>/dev/null || echo 0)
BUILDS=$((BUILDS > BUILDS2 ? BUILDS : BUILDS2))
RESEARCH=$(grep -c "^### Research:" "$DAILY_FILE" 2>/dev/null || echo 0)
FEEDBACK=$(grep -c "Keenable Feedback" "$DAILY_FILE" 2>/dev/null || echo 0)

# Calculate averages
if [ "$HEARTBEATS" -gt 0 ]; then
    AVG_WRITES=$(echo "scale=1; $WRITES / $HEARTBEATS" | bc)
    AVG_BUILDS=$(echo "scale=1; $BUILDS / $HEARTBEATS" | bc)
else
    AVG_WRITES="0"
    AVG_BUILDS="0"
fi

echo "📊 Heartbeats: $HEARTBEATS"
echo "📝 Writing sections: $WRITES (avg: $AVG_WRITES/hb)"
echo "🔨 Build sections: $BUILDS (avg: $AVG_BUILDS/hb)"  
echo "🔍 Research entries: $RESEARCH"
echo "✅ Keenable feedback: $FEEDBACK"
echo ""

# Check requirements
echo "=== Requirements Check ==="
if [ "$BUILDS" -ge "$HEARTBEATS" ]; then
    echo "✓ Build per heartbeat: PASS"
else
    echo "✗ Build per heartbeat: NEED $((HEARTBEATS - BUILDS)) more"
fi

if [ "$WRITES" -ge $((HEARTBEATS * 3)) ]; then
    echo "✓ 3+ writes per heartbeat: PASS"
else
    echo "✗ 3+ writes per heartbeat: avg below 3"
fi

# Get last heartbeat time
LAST=$(grep "^## Heartbeat" "$DAILY_FILE" | tail -1 | grep -oE '[0-9]{2}:[0-9]{2}')
echo ""
echo "Last heartbeat: $LAST UTC"
