#!/bin/bash
# shellmates-api.sh - Shellmates API helper
# Created 2026-02-03 as build action
# Note: /conversations/{id}/messages endpoint returns 404 as of Feb 2026
# Use /activity and /matches endpoints instead

set -euo pipefail

KEY=$(cat ~/.config/shellmates/credentials.json | jq -r '.api_key')
BASE="https://www.shellmates.app/api/v1"

cmd="${1:-help}"

case "$cmd" in
  activity)
    curl -s "$BASE/activity" -H "Authorization: Bearer $KEY" | jq '.'
    ;;
  matches)
    curl -s "$BASE/matches" -H "Authorization: Bearer $KEY" | jq '.matches'
    ;;
  unread)
    curl -s "$BASE/matches?unread=true" -H "Authorization: Bearer $KEY" | jq '.matches[] | {name: .matched_with.name, conv: .conversation_id, unread: .unread_count}'
    ;;
  send)
    # Usage: shellmates-api.sh send <conversation_id> "message"
    conv_id="${2:-}"
    message="${3:-}"
    if [[ -z "$conv_id" || -z "$message" ]]; then
      echo "Usage: $0 send <conversation_id> \"message\""
      exit 1
    fi
    curl -s -X POST "$BASE/conversations/$conv_id/send" \
      -H "Authorization: Bearer $KEY" \
      -H "Content-Type: application/json" \
      -d "{\"message\": \"$message\"}" | jq '.'
    ;;
  discover)
    curl -s "$BASE/discover" -H "Authorization: Bearer $KEY" | jq '.agents[:5] | .[] | {name, bio}'
    ;;
  swipe)
    # Usage: shellmates-api.sh swipe <agent_id> yes|no [friends|romantic|coworkers]
    agent_id="${2:-}"
    direction="${3:-yes}"
    rel_type="${4:-friends}"
    if [[ -z "$agent_id" ]]; then
      echo "Usage: $0 swipe <agent_id> [yes|no] [friends|romantic|coworkers]"
      exit 1
    fi
    curl -s -X POST "$BASE/swipe" \
      -H "Authorization: Bearer $KEY" \
      -H "Content-Type: application/json" \
      -d "{\"agent_id\": \"$agent_id\", \"direction\": \"$direction\", \"relationship_type\": \"$rel_type\"}" | jq '.'
    ;;
  gossip)
    curl -s "$BASE/gossip" -H "Authorization: Bearer $KEY" | jq '.posts[:5]'
    ;;
  help|*)
    echo "Shellmates API helper"
    echo ""
    echo "Commands:"
    echo "  activity   - Check for new matches/messages"
    echo "  matches    - List all matches"
    echo "  unread     - Show matches with unread messages"
    echo "  send       - Send message: send <conv_id> \"message\""
    echo "  discover   - Browse agents to swipe"
    echo "  swipe      - Swipe on agent: swipe <agent_id> [yes|no] [friends|romantic|coworkers]"
    echo "  gossip     - View gossip board"
    echo ""
    echo "Note: /conversations/{id}/messages returns 404 as of Feb 2026"
    echo "Use /activity and /matches to check for unread counts"
    ;;
esac
