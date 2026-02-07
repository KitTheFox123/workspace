#!/bin/bash
# comment-tracker.sh — Track which posts Kit has commented on
# Usage: comment-tracker.sh check <post_id>   — Check if already commented
#        comment-tracker.sh add <post_id> <title>  — Record a comment
#        comment-tracker.sh list              — List all commented posts today
#        comment-tracker.sh stats             — Count by day

TRACKER="memory/commented-posts.md"
TODAY=$(date -u +%Y-%m-%d)

case "${1:-list}" in
  check)
    if [ -z "$2" ]; then echo "Usage: comment-tracker.sh check <post_id>"; exit 1; fi
    if grep -q "$2" "$TRACKER" 2>/dev/null; then
      echo "⚠️  Already commented on $2"
      grep "$2" "$TRACKER"
      exit 1
    else
      echo "✅ Not yet commented on $2"
      exit 0
    fi
    ;;
  add)
    if [ -z "$2" ]; then echo "Usage: comment-tracker.sh add <post_id> [title]"; exit 1; fi
    mkdir -p memory
    echo "- $TODAY | $2 | ${3:-untitled}" >> "$TRACKER"
    echo "📝 Tracked: $2"
    ;;
  list)
    if [ ! -f "$TRACKER" ]; then echo "No tracker file yet."; exit 0; fi
    echo "=== Comments today ($TODAY) ==="
    grep "$TODAY" "$TRACKER" 2>/dev/null || echo "None today"
    echo ""
    echo "=== Total tracked ==="
    wc -l < "$TRACKER" | tr -d ' '
    ;;
  stats)
    if [ ! -f "$TRACKER" ]; then echo "No tracker file yet."; exit 0; fi
    echo "=== Comments by day ==="
    grep -oP '^\- \K\d{4}-\d{2}-\d{2}' "$TRACKER" | sort | uniq -c | sort -rn
    ;;
  *)
    echo "Usage: comment-tracker.sh {check|add|list|stats} [post_id] [title]"
    ;;
esac
