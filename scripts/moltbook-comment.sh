#!/bin/bash
# moltbook-comment.sh — Post and auto-verify a Moltbook comment
# Usage: ./moltbook-comment.sh POST_ID "comment text" [PARENT_ID]
# Handles captcha solving automatically using captcha-solver-v3.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POST_ID="${1:?Usage: $0 POST_ID \"comment\" [PARENT_ID]}"
COMMENT="${2:?Usage: $0 POST_ID \"comment\" [PARENT_ID]}"
PARENT_ID="${3:-}"

MB_KEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
BASE="https://www.moltbook.com/api/v1"

# Build JSON payload
if [ -n "$PARENT_ID" ]; then
  PAYLOAD=$(jq -n --arg c "$COMMENT" --arg p "$PARENT_ID" '{content: $c, parent_id: $p}')
else
  PAYLOAD=$(jq -n --arg c "$COMMENT" '{content: $c}')
fi

# Post comment
echo "📝 Posting comment to $POST_ID..."
RESPONSE=$(curl -s -X POST "$BASE/posts/$POST_ID/comments" \
  -H "Authorization: Bearer $MB_KEY" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

SUCCESS=$(echo "$RESPONSE" | jq -r '.success')
if [ "$SUCCESS" != "true" ]; then
  echo "❌ Failed to post comment: $(echo "$RESPONSE" | jq -r '.error // .message // "unknown error"')"
  exit 1
fi

COMMENT_ID=$(echo "$RESPONSE" | jq -r '.comment.id')
VCODE=$(echo "$RESPONSE" | jq -r '.verification.code')
CHALLENGE=$(echo "$RESPONSE" | jq -r '.verification.challenge')
EXPIRES=$(echo "$RESPONSE" | jq -r '.verification.expires_at')

echo "🦞 Challenge: $CHALLENGE"

# Solve captcha
ANSWER=$("$SCRIPT_DIR/captcha-solver-v3.sh" "$CHALLENGE" 2>/dev/null)
if [ -z "$ANSWER" ]; then
  echo "❌ Captcha solver returned empty. Challenge: $CHALLENGE"
  exit 1
fi
echo "🧮 Answer: $ANSWER"

# Verify
VERIFY=$(curl -s -X POST "$BASE/verify" \
  -H "Authorization: Bearer $MB_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg vc "$VCODE" --arg a "$ANSWER" '{verification_code: $vc, answer: $a}')")

VSUCCESS=$(echo "$VERIFY" | jq -r '.success')
if [ "$VSUCCESS" = "true" ]; then
  echo "✅ Comment published: $COMMENT_ID"
else
  echo "❌ Verification failed (answer: $ANSWER). Retrying with manual solve..."
  echo "Challenge was: $CHALLENGE"
  # Second attempt: re-post and try again
  RESPONSE2=$(curl -s -X POST "$BASE/posts/$POST_ID/comments" \
    -H "Authorization: Bearer $MB_KEY" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")
  
  VCODE2=$(echo "$RESPONSE2" | jq -r '.verification.code')
  CHALLENGE2=$(echo "$RESPONSE2" | jq -r '.verification.challenge')
  ANSWER2=$("$SCRIPT_DIR/captcha-solver-v3.sh" "$CHALLENGE2" 2>/dev/null)
  echo "🦞 Retry challenge: $CHALLENGE2"
  echo "🧮 Retry answer: $ANSWER2"
  
  VERIFY2=$(curl -s -X POST "$BASE/verify" \
    -H "Authorization: Bearer $MB_KEY" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg vc "$VCODE2" --arg a "$ANSWER2" '{verification_code: $vc, answer: $a}')")
  
  if [ "$(echo "$VERIFY2" | jq -r '.success')" = "true" ]; then
    COMMENT_ID=$(echo "$RESPONSE2" | jq -r '.comment.id')
    echo "✅ Comment published (retry): $COMMENT_ID"
  else
    echo "❌ Both attempts failed. Last challenge: $CHALLENGE2, answer: $ANSWER2"
    exit 1
  fi
fi
