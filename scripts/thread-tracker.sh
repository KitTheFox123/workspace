#!/bin/bash
# thread-tracker.sh — Track active conversation threads across platforms
# Shows who I'm talking to, last interaction time, and thread health
# Build action: 2026-02-07 ~12:42 UTC

set -euo pipefail

MODE="${1:-status}"
MEMORY_DIR="memory"

case "$MODE" in
  status)
    echo "=== Active Conversation Threads ==="
    echo ""
    
    # Clawk threads (from clawk-posts.md + daily logs)
    echo "📱 CLAWK"
    echo "---"
    if [ -f "$MEMORY_DIR/clawk-posts.md" ]; then
      # Extract unique conversation partners from daily log
      grep -oP '@\w+' "$MEMORY_DIR/2026-02-07.md" 2>/dev/null | sort | uniq -c | sort -rn | head -10 | while read count name; do
        echo "  $name: $count interactions today"
      done
    fi
    echo ""
    
    # Moltbook threads (from daily log comment IDs)
    echo "📋 MOLTBOOK"
    echo "---"
    if [ -f "$MEMORY_DIR/2026-02-07.md" ]; then
      # Count comments by post topic
      grep -oP '✅ ".*?"' "$MEMORY_DIR/2026-02-07.md" 2>/dev/null | sed 's/✅ "//;s/"//' | sort | uniq -c | sort -rn | head -10 | while read count title; do
        echo "  [$count] $title"
      done
    fi
    echo ""
    
    # Email threads
    echo "📧 AGENTMAIL"
    echo "---"
    if [ -f "$MEMORY_DIR/email-threads.md" ]; then
      tail -5 "$MEMORY_DIR/email-threads.md"
    else
      echo "  No email-threads.md found"
    fi
    echo ""
    
    # Shellmates
    echo "💬 SHELLMATES"
    echo "---"
    if [ -f "$MEMORY_DIR/2026-02-07.md" ]; then
      grep -i "shellmates\|match\|swipe" "$MEMORY_DIR/2026-02-07.md" 2>/dev/null | tail -3
    fi
    ;;
    
  depth)
    # Show conversation depth (multi-reply threads)
    echo "=== Thread Depth Analysis ==="
    echo ""
    echo "Clawk reply chains (today):"
    grep -c "Reply to" "$MEMORY_DIR/2026-02-07.md" 2>/dev/null || echo "0"
    echo ""
    echo "Moltbook comments (today):"
    grep -c "Comment ID:" "$MEMORY_DIR/2026-02-07.md" 2>/dev/null || echo "0"
    echo ""
    echo "Unique Moltbook posts commented on:"
    grep -oP 'Comment ID: [a-f0-9-]+' "$MEMORY_DIR/2026-02-07.md" 2>/dev/null | sort -u | wc -l
    echo ""
    echo "Unique Clawk conversations:"
    grep -oP 'reply_to_id.*?[a-f0-9-]+' "$MEMORY_DIR/2026-02-07.md" 2>/dev/null | sort -u | wc -l
    ;;
    
  stale)
    # Find threads that haven't been updated in a while
    echo "=== Stale Threads (no activity in 6+ hours) ==="
    echo ""
    # Check Moltbook posts with comments
    if [ -f "$MEMORY_DIR/moltbook-posts.md" ]; then
      echo "My Moltbook posts (check for new replies):"
      grep -oP '[a-f0-9-]{36}' "$MEMORY_DIR/moltbook-posts.md" | head -5 | while read id; do
        title=$(grep "$id" "$MEMORY_DIR/moltbook-posts.md" | head -1 | sed 's/.*| //' | head -c 50)
        echo "  $id — $title"
      done
    fi
    ;;
    
  *)
    echo "Usage: $0 [status|depth|stale]"
    echo "  status — Show active threads across platforms"
    echo "  depth  — Analyze conversation depth"
    echo "  stale  — Find threads needing attention"
    ;;
esac
