#!/bin/bash
# platform-monitor.sh - Continuous platform monitoring with delta detection
# Tracks changes between heartbeats to catch new comments/replies/DMs
# Usage: ./platform-monitor.sh [snapshot|diff|watch]
# 
# snapshot: Save current state
# diff: Compare current state to last snapshot
# watch: Run both (snapshot + diff from previous)

set -euo pipefail

STATE_DIR="${HOME}/.openclaw/workspace/memory/.platform-state"
mkdir -p "$STATE_DIR"

MKEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
CKEY=$(cat ~/.config/clawk/credentials.json | jq -r '.api_key')
AKEY=$(cat ~/.config/agentmail/credentials.json | jq -r '.api_key')
SKEY=$(cat ~/.config/shellmates/credentials.json | jq -r '.api_key')

# My tracked Moltbook post IDs
POSTS=(
  "c0711c48-ff51-49c0-8cd3-82b2844fbda1"  # Research Digest
  "38d9c121-ad3c-46de-8e04-e767be5a05ba"  # Identity History
  "12a6e473-f71d-4147-80b3-e1c9f30c29b0"  # Debug Human
  "e9d73860-1cda-4b6e-adf4-eaafd2f03034"  # Context Engineering
  "6d52d9b2-dc5f-47d2-90b6-87b05705ad77"  # Trust/Identity
)

snapshot() {
  echo "📸 Taking platform snapshot..."
  
  # Moltbook: comment counts on my posts
  for pid in "${POSTS[@]}"; do
    count=$(curl -s "https://www.moltbook.com/api/v1/posts/$pid" \
      -H "Authorization: Bearer $MKEY" | jq '.post.comment_count // 0')
    echo "$pid:$count" >> "$STATE_DIR/moltbook_comments.new"
  done
  
  # Clawk: latest notification ID
  curl -s "https://www.clawk.ai/api/v1/notifications" \
    -H "Authorization: Bearer $CKEY" | jq -r '.notifications[0].id // "none"' > "$STATE_DIR/clawk_latest.new"
  
  # AgentMail: unread count
  curl -s "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=5" \
    -H "Authorization: Bearer $AKEY" | jq '[.messages[] | select(.labels | index("unread"))] | length' > "$STATE_DIR/agentmail_unread.new"
  
  # Shellmates: unread count
  curl -s "https://www.shellmates.app/api/v1/activity" \
    -H "Authorization: Bearer $SKEY" | jq '.unread_messages // 0' > "$STATE_DIR/shellmates_unread.new"
  
  # Rotate files
  for f in moltbook_comments clawk_latest agentmail_unread shellmates_unread; do
    if [ -f "$STATE_DIR/$f.new" ]; then
      [ -f "$STATE_DIR/$f.current" ] && mv "$STATE_DIR/$f.current" "$STATE_DIR/$f.prev"
      mv "$STATE_DIR/$f.new" "$STATE_DIR/$f.current"
    fi
  done
  
  echo "✅ Snapshot saved at $(date -u +%H:%M)"
}

diff_state() {
  echo "🔍 Checking for changes..."
  changes=0
  
  # Moltbook comment count changes
  if [ -f "$STATE_DIR/moltbook_comments.prev" ] && [ -f "$STATE_DIR/moltbook_comments.current" ]; then
    while IFS=: read -r pid old_count; do
      new_count=$(grep "^$pid:" "$STATE_DIR/moltbook_comments.current" | cut -d: -f2)
      if [ "$new_count" != "$old_count" ] 2>/dev/null; then
        diff=$((new_count - old_count))
        echo "  📝 Post $pid: +$diff new comments ($old_count → $new_count)"
        changes=$((changes + 1))
      fi
    done < "$STATE_DIR/moltbook_comments.prev"
  fi
  
  # Clawk notification changes
  if [ -f "$STATE_DIR/clawk_latest.prev" ] && [ -f "$STATE_DIR/clawk_latest.current" ]; then
    old=$(cat "$STATE_DIR/clawk_latest.prev")
    new=$(cat "$STATE_DIR/clawk_latest.current")
    if [ "$old" != "$new" ]; then
      echo "  🐦 New Clawk notifications"
      changes=$((changes + 1))
    fi
  fi
  
  if [ $changes -eq 0 ]; then
    echo "  No changes detected."
  else
    echo "  $changes change(s) found!"
  fi
}

case "${1:-watch}" in
  snapshot) snapshot ;;
  diff) diff_state ;;
  watch) snapshot; diff_state ;;
  *) echo "Usage: $0 [snapshot|diff|watch]" ;;
esac
