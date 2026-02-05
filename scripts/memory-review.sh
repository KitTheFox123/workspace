#!/bin/bash
# memory-review.sh - Simulates "sleep consolidation" for agent memory
# Reviews recent memories and suggests what to consolidate/prune

MEMORY_DIR="${1:-/home/yallen/.openclaw/workspace/memory}"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)

echo "=== Memory Review (Agent Sleep Analog) ==="
echo "Date: $TODAY"
echo ""

# Check recent files
echo "--- Recent Memory Files ---"
ls -la "$MEMORY_DIR"/*.md 2>/dev/null | tail -5

echo ""
echo "--- Today's Entries ---"
if [ -f "$MEMORY_DIR/$TODAY.md" ]; then
    LINES=$(wc -l < "$MEMORY_DIR/$TODAY.md")
    HEARTBEATS=$(grep -c "^## Heartbeat" "$MEMORY_DIR/$TODAY.md" || echo 0)
    WRITES=$(grep -c "Writing Actions" "$MEMORY_DIR/$TODAY.md" || echo 0)
    echo "Lines: $LINES | Heartbeats: $HEARTBEATS | Write sections: $WRITES"
else
    echo "No entries for today"
fi

echo ""
echo "--- Consolidation Candidates ---"
echo "Items that might belong in MEMORY.md (long-term):"
# Look for key phrases that suggest important learnings
grep -h "Key finding\|Key insight\|Lesson\|Important\|Remember" "$MEMORY_DIR/$TODAY.md" 2>/dev/null | head -5

echo ""
echo "--- Pruning Candidates ---"
echo "Routine items that can stay in daily log only:"
grep -h "Platform Checks\|quiet\|unchanged\|automated only" "$MEMORY_DIR/$TODAY.md" 2>/dev/null | head -3
