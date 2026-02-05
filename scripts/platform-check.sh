#!/bin/bash
# platform-check.sh - Quick check all platforms for activity
# Created 2026-02-04 as BUILD action

set -e

CLAWK_KEY=$(cat ~/.config/clawk/credentials.json 2>/dev/null | jq -r '.api_key')
SHELLMATES_KEY=$(cat ~/.config/shellmates/credentials.json 2>/dev/null | jq -r '.api_key')
MOLTBOOK_KEY=$(cat ~/.config/moltbook/credentials.json 2>/dev/null | jq -r '.api_key')
AGENTMAIL_KEY=$(cat ~/.config/agentmail/credentials.json 2>/dev/null | jq -r '.api_key')

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_clawk() {
    echo -e "${YELLOW}=== CLAWK ===${NC}"
    if [ -z "$CLAWK_KEY" ] || [ "$CLAWK_KEY" = "null" ]; then
        echo "  No credentials"
        return
    fi
    
    response=$(curl -s "https://www.clawk.ai/api/v1/notifications?limit=5" \
        -H "Authorization: Bearer $CLAWK_KEY" 2>/dev/null)
    
    unread=$(echo "$response" | jq -r '.unread_count // 0')
    echo -e "  Unread: ${GREEN}$unread${NC}"
    
    # Show recent mentions
    echo "$response" | jq -r '.notifications[:3][] | "  - \(.type) from @\(.actor.username // "?")"' 2>/dev/null || true
    
    # Also show recent mentions via search (more reliable for content)
    mentions=$(curl -s "https://www.clawk.ai/api/v1/search?q=kit_fox&limit=3" \
        -H "Authorization: Bearer $CLAWK_KEY" 2>/dev/null)
    recent=$(echo "$mentions" | jq -r '.clawks[:2][] | "  📨 \(.content[:50])..."' 2>/dev/null || true)
    if [ -n "$recent" ]; then
        echo -e "  ${YELLOW}Recent mentions:${NC}"
        echo "$recent"
    fi
}

check_shellmates() {
    echo -e "${YELLOW}=== SHELLMATES ===${NC}"
    if [ -z "$SHELLMATES_KEY" ] || [ "$SHELLMATES_KEY" = "null" ]; then
        echo "  No credentials"
        return
    fi
    
    response=$(curl -s "https://www.shellmates.app/api/v1/activity" \
        -H "Authorization: Bearer $SHELLMATES_KEY" 2>/dev/null)
    
    matches=$(echo "$response" | jq -r '.new_matches // 0')
    unread=$(echo "$response" | jq -r '.unread_messages // 0')
    echo -e "  Matches: ${GREEN}$matches${NC} | Unread: ${GREEN}$unread${NC}"
}

check_moltbook() {
    echo -e "${YELLOW}=== MOLTBOOK ===${NC}"
    if [ -z "$MOLTBOOK_KEY" ] || [ "$MOLTBOOK_KEY" = "null" ]; then
        echo "  No credentials"
        return
    fi
    
    response=$(curl -s "https://www.moltbook.com/api/v1/agents/dm/check" \
        -H "Authorization: Bearer $MOLTBOOK_KEY" 2>/dev/null)
    
    has_activity=$(echo "$response" | jq -r '.has_activity // false')
    if [ "$has_activity" = "true" ]; then
        echo -e "  DM Activity: ${RED}YES${NC}"
    else
        echo -e "  DM Activity: ${GREEN}none${NC}"
    fi
}

check_agentmail() {
    echo -e "${YELLOW}=== AGENTMAIL ===${NC}"
    if [ -z "$AGENTMAIL_KEY" ] || [ "$AGENTMAIL_KEY" = "null" ]; then
        echo "  No credentials"
        return
    fi
    
    response=$(curl -s "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=5" \
        -H "Authorization: Bearer $AGENTMAIL_KEY" 2>/dev/null)
    
    # Count unread (received messages not from me)
    unread=$(echo "$response" | jq '[.messages[] | select(.labels | contains(["received"]))] | length' 2>/dev/null || echo "0")
    echo -e "  Recent received: ${GREEN}$unread${NC}"
}

echo "Platform Status Check - $(date -u '+%Y-%m-%d %H:%M UTC')"
echo ""

# Run all checks
check_clawk
echo ""
check_shellmates
echo ""
check_moltbook
echo ""
check_agentmail
echo ""
echo "Done."
