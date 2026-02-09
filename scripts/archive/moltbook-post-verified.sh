#!/bin/bash
# moltbook-post-verified.sh — Post to Moltbook with automatic captcha solving
# Usage: ./moltbook-post-verified.sh <title> <content> [submolt]
# Requires: jq, curl, MOLTBOOK credentials, OpenRouter credentials

set -e

TITLE="$1"
CONTENT="$2"
SUBMOLT="${3:-general}"
MB_KEY=$(jq -r '.api_key' ~/.config/moltbook/credentials.json)
OR_KEY=$(jq -r '.api_key' ~/.config/openrouter/credentials.json)
BASE="https://www.moltbook.com/api/v1"

if [ -z "$TITLE" ] || [ -z "$CONTENT" ]; then
    echo "Usage: $0 <title> <content> [submolt]"
    exit 1
fi

echo "Posting to m/$SUBMOLT..."
RESPONSE=$(curl -s -X POST "$BASE/posts" \
  -H "Authorization: Bearer $MB_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg t "$TITLE" --arg c "$CONTENT" --arg s "$SUBMOLT" \
    '{title: $t, content: $c, submolt: $s}')")

POST_ID=$(echo "$RESPONSE" | jq -r '.post.id // empty')
VCODE=$(echo "$RESPONSE" | jq -r '.verification.code // empty')
CHALLENGE=$(echo "$RESPONSE" | jq -r '.verification.challenge // empty')

if [ -z "$VCODE" ]; then
    echo "Error: $(echo "$RESPONSE" | jq -r '.error // "Unknown error"')"
    exit 1
fi

echo "Post created: $POST_ID"
echo "Challenge: $CHALLENGE"

# Use OpenRouter to solve the lobster math
SOLUTION=$(curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OR_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg ch "$CHALLENGE" '{
    model: "deepseek/deepseek-chat-v3.1",
    messages: [{role: "user", content: ("Solve this obfuscated lobster math puzzle. Extract the numbers and operation, compute the answer. Reply with ONLY the number with 2 decimal places (e.g. 58.00). Puzzle: " + $ch)}],
    max_tokens: 10
  }')" | jq -r '.choices[0].message.content' | grep -oE '[0-9]+\.?[0-9]*' | head -1)

# Ensure .00 format
if [[ "$SOLUTION" != *.* ]]; then
    SOLUTION="${SOLUTION}.00"
fi

echo "Solving: $SOLUTION"

VERIFY=$(curl -s -X POST "$BASE/verify" \
  -H "Authorization: Bearer $MB_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg vc "$VCODE" --arg ans "$SOLUTION" \
    '{verification_code: $vc, answer: $ans}')")

if echo "$VERIFY" | jq -e '.success' > /dev/null 2>&1; then
    echo "✅ Verified! Post published: $POST_ID"
else
    echo "❌ Verification failed: $(echo "$VERIFY" | jq -r '.error')"
    echo "Challenge was: $CHALLENGE"
    echo "Answer attempted: $SOLUTION"
fi
