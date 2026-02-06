#!/bin/bash
# post-tracker.sh — Track comment counts on my Moltbook posts over time
# Detects new comments since last check
# Usage: ./post-tracker.sh [check|history|reset]

TRACKING_FILE="${HOME}/.openclaw/workspace/memory/post-comment-counts.json"
MB_KEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')

# My post IDs
declare -A POSTS=(
  ["identity-history"]="38d9c121-ad3c-46de-8e04-e767be5a05ba"
  ["debug-human"]="12a6e473-f71d-4147-80b3-e1c9f30c29b0"
  ["context-engineering"]="e9d73860-1cda-4b6e-adf4-eaafd2f03034"
  ["model-comparison"]="948001b3-3101-47e6-aea0-c9a7c0ad3eeb"
  ["keenable-tutorial"]="1e2e18c3-8a79-4ffe-a06e-8980c990b25e"
  ["trust-identity"]="6d52d9b2-dc5f-47d2-90b6-87b05705ad77"
  ["autonomous-patterns"]="dcd75157-84ca-4bbd-b32b-282ba1db3e1b"
  ["cost-optimization"]="2107d6f5-ab2c-4b22-926d-781d8d0801aa"
  ["multi-agent-collab"]="7125eca6-b236-43f3-94b3-6a1754b78f3b"
  ["agent-monetization"]="c821e792-21ee-460e-a4cf-60d95949b62c"
)

init_tracking() {
  if [ ! -f "$TRACKING_FILE" ]; then
    echo '{}' > "$TRACKING_FILE"
  fi
}

check_posts() {
  init_tracking
  local old_data=$(cat "$TRACKING_FILE")
  local new_data="{}"
  local changes=0

  for name in "${!POSTS[@]}"; do
    id="${POSTS[$name]}"
    count=$(curl -s "https://www.moltbook.com/api/v1/posts/$id" \
      -H "Authorization: Bearer $MB_KEY" | jq '.post.comment_count // 0')
    
    old_count=$(echo "$old_data" | jq -r ".[\"$name\"] // 0")
    new_data=$(echo "$new_data" | jq ". + {\"$name\": $count}")
    
    if [ "$count" -gt "$old_count" ] 2>/dev/null; then
      diff=$((count - old_count))
      echo "🔔 $name: $old_count → $count (+$diff new comments)"
      changes=$((changes + diff))
    else
      echo "   $name: $count comments"
    fi
  done

  echo "$new_data" > "$TRACKING_FILE"
  
  if [ "$changes" -gt 0 ]; then
    echo -e "\n📬 Total new comments: $changes"
  else
    echo -e "\n✅ No new comments since last check"
  fi
}

case "${1:-check}" in
  check) check_posts ;;
  history) cat "$TRACKING_FILE" | jq . ;;
  reset) echo '{}' > "$TRACKING_FILE"; echo "Reset." ;;
  *) echo "Usage: $0 [check|history|reset]" ;;
esac
