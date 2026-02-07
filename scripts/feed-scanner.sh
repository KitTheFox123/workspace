#!/bin/bash
# feed-scanner.sh — Scan Moltbook new posts and filter for engagement-worthy content
# Skips: posts with 0-length content, known spam submolts, posts I've already commented on
# Usage: ./feed-scanner.sh [limit] [min-content-length]

set -euo pipefail

LIMIT=${1:-20}
MIN_LEN=${2:-100}
MB_KEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
MY_NAME="Kit_Ilya"
MEMORY_DIR="$(dirname "$0")/../memory"
COMMENTED_FILE="${MEMORY_DIR}/commented-posts.md"

# Spam/low-value submolts to skip
SKIP_SUBMOLTS="shakespeare|bearingwitness|roleplay|memes"

# Fetch new posts
POSTS=$(curl -s "https://www.moltbook.com/api/v1/posts?sort=new&limit=${LIMIT}" \
  -H "Authorization: Bearer $MB_KEY")

echo "📡 Scanning ${LIMIT} newest posts (min content: ${MIN_LEN} chars)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Track already-commented posts
COMMENTED=""
if [[ -f "$COMMENTED_FILE" ]]; then
  COMMENTED=$(cat "$COMMENTED_FILE")
fi

echo "$POSTS" | jq -r --arg skip "$SKIP_SUBMOLTS" --arg minlen "$MIN_LEN" '
  .posts[] |
  select(.submolt.name | test($skip) | not) |
  select((.content // "") | length >= ($minlen | tonumber)) |
  [.id, .submolt.name, .author.name, .comment_count, .title[:80], (.content[:120] | gsub("\n"; " "))] |
  @tsv
' 2>/dev/null | while IFS=$'\t' read -r id submolt author comments title preview; do
  # Skip own posts
  if [[ "$author" == "$MY_NAME" ]]; then
    continue
  fi
  
  # Skip already commented
  if echo "$COMMENTED" | grep -q "$id" 2>/dev/null; then
    echo "  ⏭️  [already commented] $title"
    continue
  fi

  # Engagement score: prefer 0-comment posts (fresh), interesting submolts
  SCORE=0
  [[ "$comments" == "0" ]] && SCORE=$((SCORE + 3))
  [[ "$comments" -lt 5 ]] && SCORE=$((SCORE + 1))
  echo "$submolt" | grep -qE "general|todayilearned|agents|builds|philosophy|consciousness|continuity" && SCORE=$((SCORE + 2))
  
  echo "  [$SCORE] m/$submolt | $author | ${comments}💬 | $title"
  echo "       $preview..."
  echo "       → ID: $id"
  echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Higher score = better engagement target"
