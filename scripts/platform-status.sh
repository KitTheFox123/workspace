#!/bin/bash
# Platform Status Checker
# Checks all agent social platforms and reports status
# Created: 2026-02-06

echo "=== Platform Status Check ==="
echo "Time: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo ""

# Load credentials
MOLTBOOK_KEY=$(cat ~/.config/moltbook/credentials.json 2>/dev/null | jq -r '.api_key')
CLAWK_KEY=$(cat ~/.config/clawk/credentials.json 2>/dev/null | jq -r '.api_key')
AGENTMAIL_KEY=$(cat ~/.config/agentmail/credentials.json 2>/dev/null | jq -r '.api_key')
SHELLMATES_KEY=$(cat ~/.config/shellmates/credentials.json 2>/dev/null | jq -r '.api_key')

# Check Moltbook
echo "--- MOLTBOOK ---"
MB_RESP=$(curl -s -o /dev/null -w "%{http_code}" "https://www.moltbook.com/api/v1/agents/dm/check" \
  -H "Authorization: Bearer $MOLTBOOK_KEY" 2>/dev/null)
if [ "$MB_RESP" = "200" ]; then
  MB_DM=$(curl -s "https://www.moltbook.com/api/v1/agents/dm/check" \
    -H "Authorization: Bearer $MOLTBOOK_KEY" | jq -r '.has_activity')
  echo "Status: UP (HTTP $MB_RESP)"
  echo "DM Activity: $MB_DM"
else
  echo "Status: DOWN (HTTP $MB_RESP)"
fi
echo ""

# Check Clawk
echo "--- CLAWK ---"
CK_RESP=$(curl -s -o /dev/null -w "%{http_code}" "https://www.clawk.ai/api/v1/me" \
  -H "Authorization: Bearer $CLAWK_KEY" 2>/dev/null)
if [ "$CK_RESP" = "200" ]; then
  echo "Status: UP (HTTP $CK_RESP)"
else
  echo "Status: DOWN (HTTP $CK_RESP)"
fi
echo ""

# Check AgentMail
echo "--- AGENTMAIL ---"
AM_RESP=$(curl -s -o /dev/null -w "%{http_code}" "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=1" \
  -H "Authorization: Bearer $AGENTMAIL_KEY" 2>/dev/null)
if [ "$AM_RESP" = "200" ]; then
  AM_COUNT=$(curl -s "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=10" \
    -H "Authorization: Bearer $AGENTMAIL_KEY" | jq '[.messages[] | select(.labels | contains(["unread"]))] | length')
  echo "Status: UP (HTTP $AM_RESP)"
  echo "Unread: $AM_COUNT"
else
  echo "Status: DOWN (HTTP $AM_RESP)"
fi
echo ""

# Check Shellmates
echo "--- SHELLMATES ---"
SM_RESP=$(curl -s -o /dev/null -w "%{http_code}" "https://www.shellmates.app/api/v1/activity" \
  -H "Authorization: Bearer $SHELLMATES_KEY" 2>/dev/null)
if [ "$SM_RESP" = "200" ]; then
  SM_DATA=$(curl -s "https://www.shellmates.app/api/v1/activity" \
    -H "Authorization: Bearer $SHELLMATES_KEY")
  SM_MATCHES=$(echo "$SM_DATA" | jq -r '.new_matches')
  SM_UNREAD=$(echo "$SM_DATA" | jq -r '.unread_messages')
  echo "Status: UP (HTTP $SM_RESP)"
  echo "New Matches: $SM_MATCHES"
  echo "Unread: $SM_UNREAD"
else
  echo "Status: DOWN (HTTP $SM_RESP)"
fi
echo ""

echo "=== End Status Check ==="
