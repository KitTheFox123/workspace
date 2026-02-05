#!/bin/bash
# research-tracker.sh - Track daily research topics to avoid repetition
# Usage: ./research-tracker.sh [add TOPIC | list | recent]

TRACKER_FILE="$HOME/.openclaw/workspace/memory/research-topics.md"

# Initialize file if missing
if [ ! -f "$TRACKER_FILE" ]; then
    cat > "$TRACKER_FILE" << 'EOF'
# Research Topics Tracker

Avoid repeating topics within 3 days. Check before researching.

## Recent Topics
EOF
fi

case "$1" in
    add)
        if [ -z "$2" ]; then
            echo "Usage: $0 add TOPIC"
            exit 1
        fi
        DATE=$(date -u +%Y-%m-%d)
        echo "- [$DATE] $2" >> "$TRACKER_FILE"
        echo "Added: $2"
        ;;
    list)
        cat "$TRACKER_FILE"
        ;;
    recent)
        echo "=== Topics (last 3 days) ==="
        CUTOFF=$(date -u -d "3 days ago" +%Y-%m-%d 2>/dev/null || date -u -v-3d +%Y-%m-%d)
        grep -E "^\- \[20" "$TRACKER_FILE" | while read line; do
            TOPIC_DATE=$(echo "$line" | grep -oE '\[20[0-9]{2}-[0-9]{2}-[0-9]{2}\]' | tr -d '[]')
            if [[ "$TOPIC_DATE" > "$CUTOFF" ]]; then
                echo "$line"
            fi
        done
        ;;
    *)
        echo "Usage: $0 [add TOPIC | list | recent]"
        echo ""
        echo "Commands:"
        echo "  add TOPIC  - Add a topic researched today"
        echo "  list       - Show all tracked topics"
        echo "  recent     - Show topics from last 3 days"
        ;;
esac
