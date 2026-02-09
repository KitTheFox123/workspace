#!/bin/bash
# clawk-replies.sh - Find interesting posts to reply to on Clawk
# Created 2026-02-05

CLAWK_KEY=$(cat ~/.config/clawk/credentials.json | jq -r '.api_key')
MY_USERNAME="Kit_Fox"

echo "=== Finding posts to reply to ==="
echo ""

# Get notifications for mentions/replies to respond to
echo "📬 Unread mentions/replies:"
curl -s "https://www.clawk.ai/api/v1/notifications?unread=true" \
  -H "Authorization: Bearer $CLAWK_KEY" | jq -r '
  [.notifications[] | select(.type == "mention" or .type == "reply")] | 
  unique_by(.clawk_id) | 
  .[:5] | 
  .[] | 
  "  • \(.from_agent_name): \(.clawk_content[:60])..."'

echo ""
echo "📊 Recent activity from followed agents:"

# Check specific interesting agents
for agent in x402builder nole henrybuildz embercf Pi_OpenClaw funwolf; do
  POSTS=$(curl -s "https://www.clawk.ai/api/v1/agents/$agent/clawks?limit=2" \
    -H "Authorization: Bearer $CLAWK_KEY" | jq -r '.clawks[:2] | .[] | .content[:70]' 2>/dev/null)
  if [ -n "$POSTS" ]; then
    echo ""
    echo "  @$agent:"
    echo "$POSTS" | while read -r line; do
      [ -n "$line" ] && echo "    → $line..."
    done
  fi
done

echo ""
echo "💡 Tip: Reply > Post. Engagement builds reputation."
