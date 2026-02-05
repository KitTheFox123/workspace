#!/bin/bash
# summarize-day.sh - Summarize today's heartbeat activity
# Created 2026-02-04

TODAY=$(date -u '+%Y-%m-%d')
FILE="memory/${TODAY}.md"

if [ ! -f "$FILE" ]; then
    echo "No memory file for $TODAY"
    exit 1
fi

echo "=== Summary for $TODAY ==="
echo ""

# Count heartbeats
HEARTBEATS=$(grep -c "^## Heartbeat" "$FILE" 2>/dev/null || echo 0)
echo "Heartbeats: $HEARTBEATS"

# Count writing actions
WRITES=$(grep -c "Writing Action" "$FILE" 2>/dev/null || echo 0)
echo "Writing sections: $WRITES"

# Count build actions
BUILDS=$(grep -c "Build Action" "$FILE" 2>/dev/null || echo 0)
echo "Build sections: $BUILDS"

# Count research entries
RESEARCH=$(grep -c "^### Research" "$FILE" 2>/dev/null || echo 0)
echo "Research entries: $RESEARCH"

echo ""
echo "=== Topics Covered ==="
grep -E "^### Research:" "$FILE" 2>/dev/null | sed 's/### Research: /- /' || echo "(none found)"
