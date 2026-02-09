#!/bin/bash
# heartbeat-log.sh — Append a timestamped heartbeat section to daily memory
# Usage: scripts/heartbeat-log.sh "Summary of what happened"

MEMORY_DIR="memory"
TODAY=$(date -u '+%Y-%m-%d')
FILE="$MEMORY_DIR/$TODAY.md"
TIMESTAMP=$(date -u '+%H:%M UTC')

if [ -z "$1" ]; then
    echo "Usage: $0 \"summary text\""
    exit 1
fi

echo "" >> "$FILE"
echo "## Heartbeat ~${TIMESTAMP}" >> "$FILE"
echo "" >> "$FILE"
echo "$1" >> "$FILE"
echo "" >> "$FILE"
echo "— logged by heartbeat-log.sh" >> "$FILE"
