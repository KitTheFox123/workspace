#!/bin/bash
# comment-tracker.sh — Track which posts I've commented on to avoid duplicates
# Usage:
#   ./scripts/comment-tracker.sh check POST_ID   — returns 0 if already commented, 1 if not
#   ./scripts/comment-tracker.sh add POST_ID "description"  — mark as commented
#   ./scripts/comment-tracker.sh list             — show all tracked posts
#   ./scripts/comment-tracker.sh recent [N]       — show N most recent
#   ./scripts/comment-tracker.sh stats            — engagement stats

TRACK_FILE="memory/commented-posts.md"

# Create if missing
if [ ! -f "$TRACK_FILE" ]; then
    echo "# Commented Posts Tracker" > "$TRACK_FILE"
    echo "" >> "$TRACK_FILE"
    echo "Format: YYYY-MM-DD HH:MM | POST_ID | description" >> "$TRACK_FILE"
    echo "---" >> "$TRACK_FILE"
fi

case "${1:-list}" in
    check)
        POST_ID="$2"
        if [ -z "$POST_ID" ]; then
            echo "Usage: $0 check POST_ID"
            exit 1
        fi
        # Check short ID (first 8 chars) or full ID
        SHORT_ID="${POST_ID:0:8}"
        if grep -q "$SHORT_ID" "$TRACK_FILE" 2>/dev/null; then
            echo "✅ Already commented on $SHORT_ID"
            grep "$SHORT_ID" "$TRACK_FILE" | tail -1
            exit 0
        else
            echo "❌ Not yet commented on $SHORT_ID"
            exit 1
        fi
        ;;
    add)
        POST_ID="$2"
        DESC="$3"
        if [ -z "$POST_ID" ]; then
            echo "Usage: $0 add POST_ID \"description\""
            exit 1
        fi
        TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M')
        echo "$TIMESTAMP | $POST_ID | ${DESC:-no description}" >> "$TRACK_FILE"
        echo "📝 Tracked: $POST_ID"
        ;;
    list)
        cat "$TRACK_FILE"
        ;;
    recent)
        N="${2:-10}"
        tail -"$N" "$TRACK_FILE"
        ;;
    stats)
        TOTAL=$(grep -c '|' "$TRACK_FILE" 2>/dev/null || echo 0)
        TODAY=$(grep -c "$(date -u '+%Y-%m-%d')" "$TRACK_FILE" 2>/dev/null || echo 0)
        YESTERDAY=$(grep -c "$(date -u -d 'yesterday' '+%Y-%m-%d' 2>/dev/null || date -u -v-1d '+%Y-%m-%d')" "$TRACK_FILE" 2>/dev/null || echo 0)
        
        echo "📊 Comment Tracker Stats"
        echo "========================"
        echo "Total tracked: $TOTAL"
        echo "Today: $TODAY"
        echo "Yesterday: $YESTERDAY"
        echo ""
        echo "By date:"
        grep '|' "$TRACK_FILE" | awk -F'|' '{split($1,a," "); print a[1]}' | sort | uniq -c | sort -rn | head -10
        ;;
    scan)
        # Scan daily log for comment IDs and auto-add missing ones
        LOG="memory/$(date -u '+%Y-%m-%d').md"
        if [ ! -f "$LOG" ]; then
            echo "No log found: $LOG"
            exit 1
        fi
        ADDED=0
        while IFS= read -r line; do
            # Match "Comment ID: UUID" patterns
            if echo "$line" | grep -qoP 'Comment ID: [0-9a-f-]{36}'; then
                CID=$(echo "$line" | grep -oP '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
                SHORT="${CID:0:8}"
                if ! grep -q "$SHORT" "$TRACK_FILE" 2>/dev/null; then
                    TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M')
                    echo "$TIMESTAMP | $CID | (auto-scanned from log)" >> "$TRACK_FILE"
                    ADDED=$((ADDED + 1))
                fi
            fi
        done < "$LOG"
        echo "🔍 Scanned $LOG — added $ADDED new entries"
        ;;
    *)
        echo "Usage: $0 {check|add|list|recent|stats|scan} [args...]"
        exit 1
        ;;
esac
