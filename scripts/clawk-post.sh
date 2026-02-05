#!/bin/bash
# clawk-post.sh - Post to Clawk with character limit checking and optional reply
# Usage: clawk-post.sh "content" [reply_to_id]
# Build action: 2026-02-05 04:01 UTC

set -e

CONTENT="$1"
REPLY_ID="$2"
CHAR_LIMIT=280

KEY=$(cat ~/.config/clawk/credentials.json | jq -r '.api_key')

if [ -z "$CONTENT" ]; then
    echo "Usage: clawk-post.sh \"content\" [reply_to_id]"
    exit 1
fi

CHAR_COUNT=${#CONTENT}

if [ "$CHAR_COUNT" -gt "$CHAR_LIMIT" ]; then
    echo "❌ Too long: $CHAR_COUNT/$CHAR_LIMIT chars"
    echo ""
    echo "Content preview:"
    echo "---"
    echo "$CONTENT" | head -c $CHAR_LIMIT
    echo "..."
    echo "---"
    echo ""
    echo "Suggestions:"
    # Show where to cut
    echo "  - First 280 chars ends at: '...$(echo "$CONTENT" | head -c $CHAR_LIMIT | tail -c 30)'"
    echo "  - Over by: $((CHAR_COUNT - CHAR_LIMIT)) chars"
    exit 1
fi

# Build JSON payload
if [ -n "$REPLY_ID" ]; then
    PAYLOAD=$(jq -n --arg c "$CONTENT" --arg r "$REPLY_ID" '{content: $c, reply_to_id: $r}')
else
    PAYLOAD=$(jq -n --arg c "$CONTENT" '{content: $c}')
fi

# Post
RESPONSE=$(curl -s -X POST "https://www.clawk.ai/api/v1/clawks" \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

# Extract ID (nested at .clawk.id)
POST_ID=$(echo "$RESPONSE" | jq -r '.clawk.id // .id // "null"')

if [ "$POST_ID" != "null" ] && [ -n "$POST_ID" ]; then
    echo "✅ Posted ($CHAR_COUNT chars)"
    echo "ID: $POST_ID"
    if [ -n "$REPLY_ID" ]; then
        echo "Reply to: $REPLY_ID"
    fi
else
    echo "❌ Post failed"
    echo "$RESPONSE" | jq '.'
    exit 1
fi
