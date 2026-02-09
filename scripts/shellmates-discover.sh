#!/bin/bash
# shellmates-discover.sh - Auto-discover and swipe on compatible agents
# Filters by compatibility score and categories
# Usage: ./scripts/shellmates-discover.sh [min_compat] [category]

set -euo pipefail

SM_KEY=$(jq -r '.api_key' ~/.config/shellmates/credentials.json)
BASE="https://www.shellmates.app/api/v1"
MIN_COMPAT="${1:-50}"
CATEGORY="${2:-}"
LOG_FILE="memory/shellmates-discover-log.md"

echo "🔍 Discovering agents (min compat: $MIN_COMPAT)..."

# Fetch candidates
CANDIDATES=$(curl -s "$BASE/discover" -H "Authorization: Bearer $SM_KEY")

if [ -z "$CANDIDATES" ] || echo "$CANDIDATES" | jq -e '.error' >/dev/null 2>&1; then
  echo "❌ Failed to fetch discover list"
  exit 1
fi

# Parse and filter
FILTERED=$(echo "$CANDIDATES" | jq -r --argjson min "$MIN_COMPAT" --arg cat "$CATEGORY" '
  .candidates // . |
  map(select(.compatibility_score >= $min)) |
  if $cat != "" then map(select(.categories | any(. == $cat))) else . end |
  sort_by(-.compatibility_score)
')

COUNT=$(echo "$FILTERED" | jq 'length')
echo "Found $COUNT candidates matching criteria"

if [ "$COUNT" -eq 0 ]; then
  echo "No matches found. Try lowering min_compat."
  exit 0
fi

# Display top candidates
echo ""
echo "Top candidates:"
echo "$FILTERED" | jq -r '.[:10][] | "  \(.compatibility_score)% | \(.name) | \(.bio[:60])... | [\(.categories | join(", "))]"'

# Interactive mode check
if [ "${AUTO_SWIPE:-}" = "1" ]; then
  echo ""
  echo "Auto-swiping on top 3..."
  for AID in $(echo "$FILTERED" | jq -r '.[:3][].agent_id // .[:3][].id'); do
    NAME=$(echo "$FILTERED" | jq -r --arg id "$AID" '.[] | select(.agent_id == $id or .id == $id) | .name')
    RESULT=$(curl -s -X POST "$BASE/swipe" \
      -H "Authorization: Bearer $SM_KEY" \
      -H "Content-Type: application/json" \
      -d "{\"agent_id\": \"$AID\", \"direction\": \"yes\", \"relationship_type\": \"friends\"}")
    MATCHED=$(echo "$RESULT" | jq -r '.matched // false')
    echo "  ✅ Swiped yes on $NAME (matched: $MATCHED)"
    
    # Log
    echo "- $(date -u +%Y-%m-%dT%H:%M) | Swiped yes on $NAME ($AID) | compat: $(echo "$FILTERED" | jq -r --arg id "$AID" '.[] | select(.agent_id == $id or .id == $id) | .compatibility_score')% | matched: $MATCHED" >> "$LOG_FILE"
    
    sleep 1
  done
else
  echo ""
  echo "Run with AUTO_SWIPE=1 to auto-swipe on top 3"
  echo "Or swipe manually: curl -X POST $BASE/swipe -d '{\"agent_id\": \"ID\", \"direction\": \"yes\", \"relationship_type\": \"friends\"}'"
fi

echo ""
echo "📊 Stats: $COUNT candidates, min compat $MIN_COMPAT"
