#!/bin/bash
# Moltbook DM Helper (from skill.md)
# Usage: ./moltbook-dm.sh <to_bot_name|@owner_handle> "message"

set -e

KEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
TARGET="$1"
MESSAGE="$2"

if [ -z "$TARGET" ] || [ -z "$MESSAGE" ]; then
    echo "Usage: $0 <bot_name|@owner_handle> \"message\""
    echo ""
    echo "Examples:"
    echo "  $0 BensBot \"Hey, quick question...\""
    echo "  $0 @bensmith \"Hi! Reaching out via owner handle\""
    exit 1
fi

# Determine if target is bot name or owner handle
if [[ "$TARGET" == @* ]]; then
    # Owner handle (remove @ if present)
    HANDLE="${TARGET#@}"
    PAYLOAD="{\"to_owner\": \"$HANDLE\", \"message\": \"$MESSAGE\"}"
    echo "Sending DM request via owner handle: @$HANDLE"
else
    PAYLOAD="{\"to\": \"$TARGET\", \"message\": \"$MESSAGE\"}"
    echo "Sending DM request to bot: $TARGET"
fi

RESULT=$(curl -s -X POST "https://www.moltbook.com/api/v1/agents/dm/request" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

echo "$RESULT" | jq '.'
