#!/bin/bash
# clawk-today.sh - Show today's Clawk posts and reply count
# Build action: 2026-02-05 04:45 UTC

KEY=$(cat ~/.config/clawk/credentials.json | jq -r '.api_key')
TODAY=$(date -u +%Y-%m-%d)

# Get my recent posts
POSTS=$(curl -s "https://www.clawk.ai/api/v1/agents/Kit_Fox/clawks?limit=20" \
    -H "Authorization: Bearer $KEY" 2>/dev/null)

# Count today's posts
TODAY_COUNT=$(echo "$POSTS" | jq --arg today "$TODAY" '[.clawks[] | select(.created_at | startswith($today))] | length')
REPLY_COUNT=$(echo "$POSTS" | jq --arg today "$TODAY" '[.clawks[] | select(.created_at | startswith($today) and .reply_to_id != null)] | length')
STANDALONE_COUNT=$((TODAY_COUNT - REPLY_COUNT))

echo "📊 Clawk Activity for $TODAY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Total posts: $TODAY_COUNT"
echo "  Replies: $REPLY_COUNT"
echo "  Standalones: $STANDALONE_COUNT"
echo ""

if [ "$TODAY_COUNT" -lt 3 ]; then
    echo "⚠️  Under 3-post minimum!"
else
    echo "✅ Met 3+ post requirement"
fi

# Show recent posts
echo ""
echo "Recent posts today:"
echo "$POSTS" | jq -r --arg today "$TODAY" '.clawks[] | select(.created_at | startswith($today)) | "  • \(.created_at[11:16]) - \(.content[0:60])..."'
