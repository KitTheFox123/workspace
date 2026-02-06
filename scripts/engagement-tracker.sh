#!/bin/bash
# Track my Moltbook engagements to avoid duplicates
# Usage: ./engagement-tracker.sh [add|check|list] [post_id] [note]

TRACKER_FILE="$HOME/.openclaw/workspace/memory/engagement-log.md"

# Initialize file if needed
if [ ! -f "$TRACKER_FILE" ]; then
  cat > "$TRACKER_FILE" << 'EOF'
# Engagement Log

Track posts I've engaged with to avoid duplicates.

## Format
| Date | Post ID | Type | Note |
|------|---------|------|------|
EOF
fi

ACTION="${1:-list}"
POST_ID="$2"
NOTE="${3:-}"

case "$ACTION" in
  add)
    if [ -z "$POST_ID" ]; then
      echo "Usage: ./engagement-tracker.sh add <post_id> [note]"
      exit 1
    fi
    # Check if already exists
    if grep -q "$POST_ID" "$TRACKER_FILE" 2>/dev/null; then
      echo "⚠️  Already engaged with $POST_ID"
      grep "$POST_ID" "$TRACKER_FILE"
      exit 1
    fi
    # Add entry
    DATE=$(date -u '+%Y-%m-%d %H:%M')
    echo "| $DATE | \`${POST_ID:0:8}...\` | comment | $NOTE |" >> "$TRACKER_FILE"
    echo "✅ Added: $POST_ID"
    ;;
    
  check)
    if [ -z "$POST_ID" ]; then
      echo "Usage: ./engagement-tracker.sh check <post_id>"
      exit 1
    fi
    if grep -q "$POST_ID" "$TRACKER_FILE" 2>/dev/null; then
      echo "⚠️  ALREADY ENGAGED:"
      grep "$POST_ID" "$TRACKER_FILE"
      exit 1
    else
      echo "✅ Not yet engaged with $POST_ID"
      exit 0
    fi
    ;;
    
  list)
    echo "=== Recent Engagements ==="
    tail -20 "$TRACKER_FILE" | grep "^|" | grep -v "Date"
    echo ""
    TOTAL=$(grep -c "^|" "$TRACKER_FILE" 2>/dev/null | grep -v "Date" || echo "0")
    echo "Total tracked: $((TOTAL - 1))"
    ;;
    
  today)
    TODAY=$(date -u '+%Y-%m-%d')
    echo "=== Today's Engagements ($TODAY) ==="
    grep "$TODAY" "$TRACKER_FILE" 2>/dev/null || echo "None yet"
    ;;
    
  *)
    echo "Usage: ./engagement-tracker.sh [add|check|list|today] [post_id] [note]"
    exit 1
    ;;
esac
