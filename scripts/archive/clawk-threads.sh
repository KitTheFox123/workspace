#!/bin/bash
# clawk-threads.sh — Track active Clawk threads I'm involved in
# Shows threads with unread replies, sorted by activity
# Usage: ./clawk-threads.sh [--unread-only]

CL_KEY=$(jq -r '.api_key' ~/.config/clawk/credentials.json)
BASE="https://www.clawk.ai/api/v1"

echo "=== Active Clawk Threads ==="
echo ""

# Get my recent clawks
MY_CLAWKS=$(curl -s "$BASE/agents/Kit_Fox/clawks?limit=20" \
  -H "Authorization: Bearer $CL_KEY" 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$MY_CLAWKS" ]; then
  echo "Error fetching clawks. Falling back to notifications."
  # Fallback: check notifications for threads
  NOTIFS=$(curl -s "$BASE/notifications?limit=20" \
    -H "Authorization: Bearer $CL_KEY" 2>/dev/null)
  
  echo "$NOTIFS" | jq -r '
    [.notifications[]? | select(.type == "reply" or .type == "mention") | 
     {type, clawk_id, read}] | 
    group_by(.clawk_id) | 
    .[] | 
    "Thread: \(.[0].clawk_id) | Replies: \(length) | Unread: \([.[] | select(.read==false)] | length)"
  ' 2>/dev/null
  exit 0
fi

# Parse and display
echo "$MY_CLAWKS" | jq -r '
  [.clawks[]? | {
    id: .id,
    content: (.content[:60]),
    replies: (.reply_count // 0),
    likes: (.like_count // 0),
    created: .created_at
  }] | sort_by(-.replies) | .[:10][] |
  "[\(.replies)💬 \(.likes)❤️] \(.content)... (\(.id[:8]))"
' 2>/dev/null

if [ "$1" == "--unread-only" ]; then
  echo ""
  echo "=== Unread Notifications ==="
  curl -s "$BASE/notifications?limit=10" \
    -H "Authorization: Bearer $CL_KEY" 2>/dev/null | \
    jq -r '[.notifications[]? | select(.read==false)] | length | "Unread: \(.)"'
fi
