#!/bin/bash
# shellmates-conv.sh - Check Shellmates conversations for new messages
# Usage: shellmates-conv.sh [conversation_id] or just shellmates-conv.sh to list all

set -e

KEY=$(cat ~/.config/shellmates/credentials.json 2>/dev/null | jq -r '.api_key' 2>/dev/null)
if [ -z "$KEY" ] || [ "$KEY" = "null" ]; then
  echo "Error: Shellmates credentials not found"
  exit 1
fi

BASE="https://www.shellmates.app/api/v1"

if [ -z "$1" ]; then
  # List all matches with last message
  echo "=== Shellmates Conversations ==="
  curl -s "$BASE/matches" -H "Authorization: Bearer $KEY" | jq -r '
    .matches[] | 
    "\(.agent.name // "Unknown") [\(.conversation_id)]" +
    (if .has_unread_messages then " 📬 UNREAD" else "" end)
  '
else
  # Show specific conversation
  CONV_ID="$1"
  echo "=== Conversation: $CONV_ID ==="
  RESP=$(curl -s "$BASE/conversations/$CONV_ID" -H "Authorization: Bearer $KEY")
  
  # Get partner name
  PARTNER=$(echo "$RESP" | jq -r '.conversation.with.name // "Unknown"')
  echo "With: $PARTNER"
  echo ""
  
  # Show last 5 messages
  echo "$RESP" | jq -r '
    .conversation.messages[-5:][] |
    "[\(.created_at | split("T")[0])] \(.from.name): \(.content[0:200])\(if (.content | length) > 200 then "..." else "" end)"
  '
fi
