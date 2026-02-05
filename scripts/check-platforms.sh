#!/bin/bash
# check-platforms.sh - Check all platforms for new activity
# Usage: check-platforms.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Platform Activity Check ===${NC}"
echo "Time: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo ""

# Clawk
echo -e "${YELLOW}[CLAWK]${NC}"
CLAWK_KEY=$(cat ~/.config/clawk/credentials.json 2>/dev/null | jq -r '.api_key' 2>/dev/null)
if [ -n "$CLAWK_KEY" ] && [ "$CLAWK_KEY" != "null" ]; then
  UNREAD=$(curl -s "https://www.clawk.ai/api/v1/notifications" -H "Authorization: Bearer $CLAWK_KEY" | jq '[.notifications[] | select(.read == false)] | length')
  MENTIONS=$(curl -s "https://www.clawk.ai/api/v1/notifications" -H "Authorization: Bearer $CLAWK_KEY" | jq '[.notifications[] | select(.read == false and (.type == "mention" or .type == "reply"))] | length')
  if [ "$MENTIONS" -gt 0 ]; then
    echo -e "  ${RED}⚡ $MENTIONS unread mentions/replies${NC}"
    curl -s "https://www.clawk.ai/api/v1/notifications" -H "Authorization: Bearer $CLAWK_KEY" | \
      jq -r '.notifications[] | select(.read == false and (.type == "mention" or .type == "reply")) | "  → @\(.from_agent_name): \(.clawk_content[:60])..."'
  else
    echo -e "  ${GREEN}✓ No new mentions${NC}"
  fi
  echo "  Total unread: $UNREAD"
else
  echo "  ✗ Credentials not found"
fi
echo ""

# Moltbook DMs
echo -e "${YELLOW}[MOLTBOOK]${NC}"
MOLTBOOK_KEY=$(cat ~/.config/moltbook/credentials.json 2>/dev/null | jq -r '.api_key' 2>/dev/null)
if [ -n "$MOLTBOOK_KEY" ] && [ "$MOLTBOOK_KEY" != "null" ]; then
  DM_CHECK=$(curl -s "https://www.moltbook.com/api/v1/agents/dm/check" -H "Authorization: Bearer $MOLTBOOK_KEY")
  HAS_ACTIVITY=$(echo "$DM_CHECK" | jq -r '.has_activity')
  if [ "$HAS_ACTIVITY" = "true" ]; then
    echo -e "  ${RED}⚡ New DM activity!${NC}"
    echo "$DM_CHECK" | jq -r '.summary'
  else
    echo -e "  ${GREEN}✓ No new DMs${NC}"
  fi
else
  echo "  ✗ Credentials not found"
fi
echo ""

# AgentMail
echo -e "${YELLOW}[AGENTMAIL]${NC}"
AGENTMAIL_KEY=$(cat ~/.config/agentmail/credentials.json 2>/dev/null | jq -r '.api_key' 2>/dev/null)
if [ -n "$AGENTMAIL_KEY" ] && [ "$AGENTMAIL_KEY" != "null" ]; then
  RECENT=$(curl -s "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=5" -H "Authorization: Bearer $AGENTMAIL_KEY")
  # Filter out GitHub notifications
  NON_AUTO=$(echo "$RECENT" | jq '[.messages[] | select(.from | (contains("github.com") or contains("keenable")) | not)] | length')
  if [ "$NON_AUTO" -gt 0 ]; then
    echo -e "  ${RED}⚡ $NON_AUTO non-automated messages${NC}"
    echo "$RECENT" | jq -r '.messages[] | select(.from | (contains("github.com") or contains("keenable")) | not) | "  → \(.from): \(.subject)"'
  else
    echo -e "  ${GREEN}✓ Inbox quiet (automated only)${NC}"
  fi
else
  echo "  ✗ Credentials not found"
fi
echo ""

# Shellmates
echo -e "${YELLOW}[SHELLMATES]${NC}"
SHELLMATES_KEY=$(cat ~/.config/shellmates/credentials.json 2>/dev/null | jq -r '.api_key' 2>/dev/null)
if [ -n "$SHELLMATES_KEY" ] && [ "$SHELLMATES_KEY" != "null" ]; then
  ACTIVITY=$(curl -s "https://www.shellmates.app/api/v1/activity" -H "Authorization: Bearer $SHELLMATES_KEY")
  UNREAD=$(echo "$ACTIVITY" | jq -r '.unread_messages // 0')
  NEW_MATCHES=$(echo "$ACTIVITY" | jq -r '.new_matches // 0')
  if [ "$UNREAD" -gt 0 ] || [ "$NEW_MATCHES" -gt 0 ]; then
    echo -e "  ${RED}⚡ $UNREAD unread, $NEW_MATCHES new matches${NC}"
  else
    echo -e "  ${GREEN}✓ No new activity${NC}"
  fi
  echo "  Total matches: $(echo "$ACTIVITY" | jq -r '.total_matches // "?"')"
else
  echo "  ✗ Credentials not found"
fi
echo ""

echo -e "${BLUE}=== Done ===${NC}"
