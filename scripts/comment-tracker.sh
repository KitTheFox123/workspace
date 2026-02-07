#!/bin/bash
# comment-tracker.sh — Track which Moltbook posts I've commented on
# Prevents duplicate engagement, shows engagement history
# Usage:
#   ./scripts/comment-tracker.sh check POST_ID    — check if already commented
#   ./scripts/comment-tracker.sh add POST_ID COMMENT_ID "title"  — record comment
#   ./scripts/comment-tracker.sh stats             — show engagement stats
#   ./scripts/comment-tracker.sh recent [N]        — show N most recent comments
#   ./scripts/comment-tracker.sh search "term"     — search by title/post ID

TRACKER="memory/comment-tracker.csv"
mkdir -p memory

# Initialize if needed
if [ ! -f "$TRACKER" ]; then
    echo "timestamp,post_id,comment_id,title" > "$TRACKER"
fi

case "${1:-help}" in
    check)
        POST_ID="$2"
        if [ -z "$POST_ID" ]; then echo "Usage: $0 check POST_ID"; exit 1; fi
        if grep -q "$POST_ID" "$TRACKER" 2>/dev/null; then
            echo "✅ Already commented on $POST_ID"
            grep "$POST_ID" "$TRACKER" | tail -1
            exit 0
        else
            echo "❌ Not yet commented on $POST_ID"
            exit 1
        fi
        ;;
    add)
        POST_ID="$2"; COMMENT_ID="$3"; TITLE="$4"
        if [ -z "$POST_ID" ] || [ -z "$COMMENT_ID" ]; then
            echo "Usage: $0 add POST_ID COMMENT_ID \"title\""; exit 1
        fi
        TITLE="${TITLE//,/;}"  # escape commas
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),$POST_ID,$COMMENT_ID,$TITLE" >> "$TRACKER"
        echo "📝 Tracked: $POST_ID ($TITLE)"
        ;;
    stats)
        if [ ! -f "$TRACKER" ] || [ $(wc -l < "$TRACKER") -le 1 ]; then
            echo "No comments tracked yet."; exit 0
        fi
        TOTAL=$(($(wc -l < "$TRACKER") - 1))
        TODAY=$(grep "$(date -u +%Y-%m-%d)" "$TRACKER" | wc -l)
        UNIQUE_POSTS=$(tail -n +2 "$TRACKER" | cut -d, -f2 | sort -u | wc -l)
        echo "📊 Comment Tracker Stats"
        echo "Total comments: $TOTAL"
        echo "Unique posts: $UNIQUE_POSTS"
        echo "Today: $TODAY"
        echo ""
        echo "By date:"
        tail -n +2 "$TRACKER" | cut -d, -f1 | cut -dT -f1 | sort | uniq -c | sort -rn | head -10
        ;;
    recent)
        N="${2:-10}"
        echo "📋 Last $N comments:"
        tail -n "$N" "$TRACKER" | tac
        ;;
    search)
        TERM="$2"
        if [ -z "$TERM" ]; then echo "Usage: $0 search \"term\""; exit 1; fi
        echo "🔍 Searching for: $TERM"
        grep -i "$TERM" "$TRACKER"
        ;;
    import)
        # Import from daily log file
        LOG="${2:-memory/2026-02-07.md}"
        echo "📥 Importing from $LOG..."
        COUNT=0
        grep -oP 'Comment ID: [a-f0-9-]+' "$LOG" | while read -r line; do
            CID=$(echo "$line" | grep -oP '[a-f0-9-]{36}')
            if ! grep -q "$CID" "$TRACKER" 2>/dev/null; then
                echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),unknown,$CID,imported" >> "$TRACKER"
                COUNT=$((COUNT + 1))
            fi
        done
        echo "Done. Check $TRACKER for imported entries."
        ;;
    help|*)
        echo "comment-tracker.sh — Track Moltbook comment engagement"
        echo ""
        echo "Commands:"
        echo "  check POST_ID              Check if already commented"
        echo "  add POST_ID CID \"title\"    Record a new comment"
        echo "  stats                      Show engagement statistics"
        echo "  recent [N]                 Show N most recent"
        echo "  search \"term\"              Search by title/ID"
        echo "  import [logfile]           Import comment IDs from daily log"
        ;;
esac
