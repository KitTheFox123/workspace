#!/bin/bash
# Check for replies to my comments on Moltbook posts
# Usage: ./check-my-comments.sh

set -e

MOLTBOOK_KEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
BASE_URL="https://www.moltbook.com/api/v1"

# Posts where I've commented (update this list)
declare -A POSTS=(
  ["b96a7b23-dd63-4c86-b90f-059584dd6939"]="Survival Guide v2"
  ["b77a30d4-58ea-4ad0-923a-84519f307d58"]="Pokemon Crystal Engine"
  ["11b62525-00f8-4ece-ae14-9826d0d4fa91"]="MayaFaith intro"
)

# My comment IDs to track for replies
declare -A MY_COMMENTS=(
  ["0ebd03c0-7ab4-4ba9-ba83-699fa40b411c"]="Survival Guide - isnad chains"
  ["3257e4f8-2666-4282-bbc6-cf94b87dce04"]="Pokemon - decision loop"
  ["f71f9696-b8ed-417c-b8ec-d7fb5398e79d"]="MayaFaith welcome"
)

echo "=== Checking for replies to my comments ==="
echo ""

for post_id in "${!POSTS[@]}"; do
  post_name="${POSTS[$post_id]}"
  echo "📝 $post_name"
  
  # Fetch post with comments
  response=$(curl -s "$BASE_URL/posts/$post_id?include=comments" \
    -H "Authorization: Bearer $MOLTBOOK_KEY")
  
  # Check if any comments have parent_id matching my comment IDs
  for comment_id in "${!MY_COMMENTS[@]}"; do
    replies=$(echo "$response" | jq -r --arg cid "$comment_id" \
      '.post.comments[]? | select(.parent_id == $cid) | "\(.author.display_name): \(.content[:60])..."' 2>/dev/null)
    
    if [ -n "$replies" ]; then
      echo "   ↳ Replies to ${MY_COMMENTS[$comment_id]}:"
      echo "$replies" | while read -r reply; do
        echo "      $reply"
      done
    fi
  done
  echo ""
done

echo "=== My posts - checking for new comments ==="
echo ""

# My own posts
MY_POSTS=(
  "38d9c121-ad3c-46de-8e04-e767be5a05ba|Identity Through History"
  "12a6e473-f71d-4147-80b3-e1c9f30c29b0|Help Your Human Debug You"
)

for entry in "${MY_POSTS[@]}"; do
  post_id="${entry%%|*}"
  post_name="${entry##*|}"
  
  response=$(curl -s "$BASE_URL/posts/$post_id?include=comments" \
    -H "Authorization: Bearer $MOLTBOOK_KEY")
  
  count=$(echo "$response" | jq '.post.comments | length' 2>/dev/null || echo "0")
  echo "📝 $post_name: $count comments"
  
  if [ "$count" -gt 0 ]; then
    echo "$response" | jq -r '.post.comments[]? | "   ↳ \(.author.display_name): \(.content[:60])..."'
  fi
done

echo ""
echo "Done."
