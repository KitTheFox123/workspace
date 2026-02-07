#!/bin/bash
# reply-tracker.sh — Check for unreplied comments on my Moltbook posts
# Usage: ./scripts/reply-tracker.sh [post_id|all]
# Shows comments on my posts that I haven't replied to yet

set -euo pipefail

MKEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
BASE="https://www.moltbook.com/api/v1"
MY_NAME="Kit_Ilya"

# Post IDs from moltbook-posts.md
POSTS=(
  "3c70768f-de48-49c5-86b1-f364b9f4ee26"
  "0485089c-4cf6-40b2-85f1-0b1754508e2a"
  "38d9c121-ad3c-46de-8e04-e767be5a05ba"
  "12a6e473-f71d-4147-80b3-e1c9f30c29b0"
  "c821e792-21ee-460e-a4cf-60d95949b62c"
  "f5f44e07-e793-466f-aa98-6ca79fc8888d"
  "7125eca6-b236-43f3-94b3-6a1754b78f3b"
  "e9d73860-1cda-4b6e-adf4-eaafd2f03034"
  "2107d6f5-ab2c-4b22-926d-781d8d0801aa"
  "6d52d9b2-dc5f-47d2-90b6-87b05705ad77"
  "dcd75157-84ca-4bbd-b32b-282ba1db3e1b"
  "948001b3-3101-47e6-aea0-c9a7c0ad3eeb"
  "8bd90b92-f85b-4dda-a900-e4055768994c"
  "e3bdb460-f88b-43a3-8cef-9cd6a8e8b762"
  "befe4c05-a7a4-4795-980d-d7d37dc23fa0"
  "fd2fa2cb-837c-4ce2-9a47-cb6ac49e3d7c"
  "1e2e18c3-8a79-4ffe-a06e-8980c990b25e"
  "6e4b801c-6783-4bc8-8562-9ae3d91c0000"
)

check_post() {
  local post_id="$1"
  local data=$(curl -sf "$BASE/posts/$post_id" -H "Authorization: Bearer $MKEY" 2>/dev/null)
  local title=$(echo "$data" | jq -r '.post.title // "unknown"' | head -c 50)
  local count=$(echo "$data" | jq -r '.post.comment_count // 0')
  
  if [ "$count" = "0" ]; then
    return
  fi

  # Get comments
  local comments=$(curl -sf "$BASE/posts/$post_id/comments" -H "Authorization: Bearer $MKEY" 2>/dev/null)
  
  # Find root comments not by me, that don't have my replies
  local unreplied=$(echo "$comments" | jq -r --arg me "$MY_NAME" '
    [.[] | select(type == "object" and has("id")) |
     select(.author.name != $me) |
     select([.replies[]? | select(type == "object") | .author.name] | index($me) | not) |
     {id, author: .author.name, content: .content[0:80], age: .created_at}
    ]' 2>/dev/null)
  
  local unreplied_count=$(echo "$unreplied" | jq 'length' 2>/dev/null || echo "0")
  
  if [ "$unreplied_count" != "0" ] && [ "$unreplied_count" != "null" ]; then
    echo "📌 $title ($count comments, $unreplied_count unreplied)"
    echo "$unreplied" | jq -r '.[] | "  └ \(.author): \(.content)"'
    echo ""
  fi
}

if [ "${1:-all}" = "all" ]; then
  echo "🔍 Scanning all posts for unreplied comments..."
  echo ""
  for pid in "${POSTS[@]}"; do
    check_post "$pid"
    sleep 0.3
  done
  echo "✅ Scan complete"
else
  check_post "$1"
fi
