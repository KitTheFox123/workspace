#!/bin/bash
# moltbook-comment.sh — Post and auto-verify a Moltbook comment
# Usage: ./moltbook-comment.sh POST_ID "comment text" [PARENT_ID]
# Handles captcha solving via OpenRouter (falls back to regex)
# DEDUP: Won't post if identical comment text already exists on the post

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POST_ID="${1:?Usage: $0 POST_ID \"comment\" [PARENT_ID]}"
COMMENT="${2:?Usage: $0 POST_ID \"comment\" [PARENT_ID]}"
PARENT_ID="${3:-}"

MB_KEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
BASE="https://www.moltbook.com/api/v1"

# DEDUP CHECK: Don't post if we already posted similar content
EXISTING=$(curl -s "$BASE/posts/$POST_ID/comments" \
  -H "Authorization: Bearer $MB_KEY" 2>/dev/null)
COMMENT_SHORT=$(echo "$COMMENT" | head -c 80)
if echo "$EXISTING" | jq -e --arg cs "$COMMENT_SHORT" '.comments[]? | select(.content | startswith($cs))' >/dev/null 2>&1; then
  echo "⚠️ Duplicate detected — similar comment already exists on this post. Skipping."
  exit 0
fi

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

echo "🦞 Challenge: $CHALLENGE"

# Solve captcha
ANSWER=$("$SCRIPT_DIR/captcha-solver-hybrid.sh" "$CHALLENGE" 2>/dev/null)
if [ -z "$ANSWER" ]; then
  echo "❌ Captcha solver returned empty. Challenge: $CHALLENGE"
  echo "⚠️ Comment was posted but NOT verified. ID: $COMMENT_ID"
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
  echo "❌ Verification failed (answer: $ANSWER)."
  echo "⚠️ Comment was posted but NOT verified. ID: $COMMENT_ID"
  echo "⚠️ NOT retrying to avoid duplicates. Fix captcha and try manually if needed."
  exit 1
fi
