#!/bin/bash
# Kit's Heartbeat Dashboard - Quick status check for all platforms
# Usage: ./heartbeat-dashboard.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}         🦊 KIT'S HEARTBEAT DASHBOARD $(date '+%H:%M UTC')${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Load credentials
MOLTBOOK_KEY=$(cat ~/.config/moltbook/credentials.json 2>/dev/null | jq -r '.api_key' || echo "")
AGENTMAIL_KEY=$(cat ~/.config/agentmail/credentials.json 2>/dev/null | jq -r '.api_key' || echo "")
CLAWK_KEY=$(cat ~/.config/clawk/credentials.json 2>/dev/null | jq -r '.api_key' || echo "")
SHELLMATES_KEY=$(cat ~/.config/shellmates/credentials.json 2>/dev/null | jq -r '.api_key' || echo "")

# === PLATFORM STATUS ===
echo -e "${YELLOW}📡 PLATFORM STATUS${NC}"
echo "─────────────────────────────────────────────────"

# Moltbook
if [ -n "$MOLTBOOK_KEY" ]; then
  MB_RESP=$(curl -s "https://www.moltbook.com/api/v1/agents/dm/check" -H "Authorization: Bearer $MOLTBOOK_KEY" 2>/dev/null)
  MB_UNREAD=$(echo "$MB_RESP" | jq -r '.messages.total_unread // 0')
  MB_REQUESTS=$(echo "$MB_RESP" | jq -r '.requests.count // 0')
  if [ "$MB_UNREAD" -gt 0 ] || [ "$MB_REQUESTS" -gt 0 ]; then
    echo -e "Moltbook:    ${RED}⚠ $MB_UNREAD unread, $MB_REQUESTS requests${NC}"
  else
    echo -e "Moltbook:    ${GREEN}✓ UP${NC} (no activity)"
  fi
else
  echo -e "Moltbook:    ${RED}✗ No credentials${NC}"
fi

# AgentMail
if [ -n "$AGENTMAIL_KEY" ]; then
  AM_UNREAD=$(curl -s "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=20" \
    -H "Authorization: Bearer $AGENTMAIL_KEY" 2>/dev/null | jq '[.messages[]? | select(.labels | contains(["unread"]))] | length')
  if [ "$AM_UNREAD" -gt 0 ]; then
    echo -e "AgentMail:   ${YELLOW}📬 $AM_UNREAD unread${NC}"
  else
    echo -e "AgentMail:   ${GREEN}✓ UP${NC} (inbox clear)"
  fi
else
  echo -e "AgentMail:   ${RED}✗ No credentials${NC}"
fi

# Clawk
if [ -n "$CLAWK_KEY" ]; then
  CLAWK_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://www.clawk.ai/api/v1/feed" \
    -H "Authorization: Bearer $CLAWK_KEY" 2>/dev/null)
  if [ "$CLAWK_STATUS" = "200" ]; then
    echo -e "Clawk:       ${GREEN}✓ UP${NC}"
  else
    echo -e "Clawk:       ${RED}✗ DOWN (HTTP $CLAWK_STATUS)${NC}"
  fi
else
  echo -e "Clawk:       ${RED}✗ No credentials${NC}"
fi

# Shellmates
if [ -n "$SHELLMATES_KEY" ]; then
  SM_RESP=$(curl -s "https://www.shellmates.app/api/v1/activity" -H "Authorization: Bearer $SHELLMATES_KEY" 2>/dev/null)
  SM_UNREAD=$(echo "$SM_RESP" | jq -r '.unread_messages // 0')
  if [ "$SM_UNREAD" -gt 0 ]; then
    echo -e "Shellmates:  ${YELLOW}💬 $SM_UNREAD unread${NC}"
  else
    echo -e "Shellmates:  ${GREEN}✓ UP${NC}"
  fi
else
  echo -e "Shellmates:  ${RED}✗ No credentials${NC}"
fi

echo ""

# === MY POSTS/COMMENTS ===
echo -e "${YELLOW}📝 MY CONTENT TRACKING${NC}"
echo "─────────────────────────────────────────────────"

if [ -n "$MOLTBOOK_KEY" ]; then
  # Check my posts for comments
  MY_POSTS=(
    "38d9c121-ad3c-46de-8e04-e767be5a05ba|Identity Through History"
    "12a6e473-f71d-4147-80b3-e1c9f30c29b0|Help Human Debug You"
  )
  
  for entry in "${MY_POSTS[@]}"; do
    post_id="${entry%%|*}"
    post_name="${entry##*|}"
    count=$(curl -s "https://www.moltbook.com/api/v1/posts/$post_id" \
      -H "Authorization: Bearer $MOLTBOOK_KEY" 2>/dev/null | jq '.post.comment_count // 0')
    if [ "$count" -gt 0 ]; then
      echo -e "  ${GREEN}$post_name: $count comments${NC}"
    else
      echo "  $post_name: 0 comments"
    fi
  done
fi

echo ""

# === INTRODUCTIONS CHECK ===
echo -e "${YELLOW}👋 INTRODUCTIONS NEEDING WELCOME${NC}"
echo "─────────────────────────────────────────────────"

if [ -n "$MOLTBOOK_KEY" ]; then
  INTROS=$(curl -s "https://www.moltbook.com/api/v1/posts?submolt=introductions&sort=new&limit=10" \
    -H "Authorization: Bearer $MOLTBOOK_KEY" 2>/dev/null | jq -r '.posts[]? | select(.comment_count <= 1) | "  \(.title[:40])... (\(.comment_count) comments)"')
  
  if [ -n "$INTROS" ]; then
    echo "$INTROS"
  else
    echo "  All recent intros have been welcomed ✓"
  fi
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo "Done."
