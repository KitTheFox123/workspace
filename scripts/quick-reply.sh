#!/bin/bash
# quick-reply.sh - Quickly reply to a Clawk mention
# Usage: ./quick-reply.sh <mention_id> "reply text"
# Real build: actually sends a reply, not just displays info

CLAWK_KEY=$(cat ~/.config/clawk/credentials.json 2>/dev/null | jq -r '.api_key')

if [ -z "$CLAWK_KEY" ] || [ "$CLAWK_KEY" = "null" ]; then
    echo "Error: No Clawk API key found"
    exit 1
fi

if [ -z "$1" ]; then
    echo "Usage: $0 <mention_id> \"reply text\""
    echo ""
    echo "Get mention IDs with: ./clawk-mentions.sh --since 2"
    exit 1
fi

MENTION_ID="$1"
REPLY_TEXT="$2"

if [ -z "$REPLY_TEXT" ]; then
    # Show the mention content first
    echo "=== Mention $MENTION_ID ==="
    curl -s "https://www.clawk.ai/api/v1/clawks/$MENTION_ID" \
        -H "Authorization: Bearer $CLAWK_KEY" | jq -r '.clawk | "From: @\(.agent.username // "unknown")\nContent: \(.content)"'
    echo ""
    echo "Reply with: $0 $MENTION_ID \"your reply here\""
    exit 0
fi

# Send the reply
RESPONSE=$(curl -s -X POST "https://www.clawk.ai/api/v1/clawks" \
    -H "Authorization: Bearer $CLAWK_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"content\": \"$REPLY_TEXT\", \"reply_to_id\": \"$MENTION_ID\"}")

REPLY_ID=$(echo "$RESPONSE" | jq -r '.clawk.id // "null"')

if [ "$REPLY_ID" != "null" ]; then
    echo "✓ Reply sent! ID: $REPLY_ID"
else
    echo "✗ Reply may have failed. Response:"
    echo "$RESPONSE" | jq .
fi
