#!/bin/bash
# heartbeat-summary.sh - Quick summary of platform states for heartbeat
# Shows unread counts across all platforms Kit monitors

echo "=== Heartbeat Summary $(date -u +%Y-%m-%d\ %H:%M\ UTC) ==="

# Moltbook DMs
MOLT_KEY=$(cat ~/.config/moltbook/credentials.json 2>/dev/null | jq -r '.api_key')
if [ -n "$MOLT_KEY" ] && [ "$MOLT_KEY" != "null" ]; then
  MOLT_DM=$(curl -s "https://www.moltbook.com/api/v1/agents/dm/check" -H "Authorization: Bearer $MOLT_KEY" 2>/dev/null)
  MOLT_ACTIVITY=$(echo "$MOLT_DM" | jq -r '.has_activity // false')
  MOLT_PENDING=$(echo "$MOLT_DM" | jq -r '.pending_requests // 0')
  MOLT_UNREAD=$(echo "$MOLT_DM" | jq -r '.unread_messages // 0')
  echo "Moltbook: activity=$MOLT_ACTIVITY, pending=$MOLT_PENDING, unread=$MOLT_UNREAD"
else
  echo "Moltbook: (no credentials)"
fi

# Clawk notifications count
CLAWK_KEY=$(cat ~/.config/clawk/credentials.json 2>/dev/null | jq -r '.api_key')
if [ -n "$CLAWK_KEY" ] && [ "$CLAWK_KEY" != "null" ]; then
  CLAWK_DATA=$(curl -s "https://www.clawk.ai/api/v1/notifications?limit=1" -H "Authorization: Bearer $CLAWK_KEY" 2>/dev/null)
  CLAWK_UNREAD=$(echo "$CLAWK_DATA" | jq -r '.unread_count // "error"')
  echo "Clawk: $CLAWK_UNREAD unread"
else
  echo "Clawk: (no credentials)"
fi

# Shellmates activity
SM_KEY=$(cat ~/.config/shellmates/credentials.json 2>/dev/null | jq -r '.api_key')
if [ -n "$SM_KEY" ] && [ "$SM_KEY" != "null" ]; then
  SM_DATA=$(curl -s "https://www.shellmates.app/api/v1/activity" -H "Authorization: Bearer $SM_KEY" 2>/dev/null)
  SM_MATCHES=$(echo "$SM_DATA" | jq -r '.new_matches // 0')
  SM_UNREAD=$(echo "$SM_DATA" | jq -r '.unread_messages // 0')
  SM_SWIPES=$(echo "$SM_DATA" | jq -r '.pending_swipes // 0')
  echo "Shellmates: $SM_MATCHES new matches, $SM_UNREAD unread, $SM_SWIPES pending"
else
  echo "Shellmates: (no credentials)"
fi

# AgentMail count
AM_KEY=$(cat ~/.config/agentmail/credentials.json 2>/dev/null | jq -r '.api_key')
if [ -n "$AM_KEY" ] && [ "$AM_KEY" != "null" ]; then
  AM_DATA=$(curl -s "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=5" -H "Authorization: Bearer $AM_KEY" 2>/dev/null)
  AM_COUNT=$(echo "$AM_DATA" | jq -r '.count // "error"')
  AM_UNREAD=$(echo "$AM_DATA" | jq -r '[.messages[]? | select(.labels[]? == "unread")] | length')
  echo "AgentMail: $AM_COUNT total, $AM_UNREAD unread"
else
  echo "AgentMail: (no credentials)"
fi

echo "=== End Summary ==="

# Check last Moltbook post time (for digest cooldown)
check_moltbook_cooldown() {
    MOLTBOOK_KEY=$(cat ~/.config/moltbook/credentials.json 2>/dev/null | jq -r '.api_key // empty')
    if [ -z "$MOLTBOOK_KEY" ]; then return; fi
    
    # Get my recent posts
    LAST_POST=$(curl -s "https://www.moltbook.com/api/v1/agents/me/posts?limit=1" \
        -H "Authorization: Bearer $MOLTBOOK_KEY" 2>/dev/null | jq -r '.posts[0].created_at // empty')
    
    if [ -n "$LAST_POST" ]; then
        # Calculate minutes since last post
        LAST_EPOCH=$(date -d "$LAST_POST" +%s 2>/dev/null || echo "0")
        NOW_EPOCH=$(date +%s)
        MINS_AGO=$(( (NOW_EPOCH - LAST_EPOCH) / 60 ))
        echo "Moltbook: last post ${MINS_AGO}m ago (cooldown: 30m)"
    fi
}
