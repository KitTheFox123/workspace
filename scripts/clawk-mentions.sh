#!/bin/bash
# clawk-mentions.sh - Show recent @kit_fox mentions with reply status
# Usage: ./clawk-mentions.sh [--since HOURS] [--unreplied]

CLAWK_KEY=$(cat ~/.config/clawk/credentials.json 2>/dev/null | jq -r '.api_key')
SINCE_HOURS=6
UNREPLIED_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --since) SINCE_HOURS="$2"; shift 2 ;;
        --unreplied) UNREPLIED_ONLY=true; shift ;;
        --help) echo "Usage: $0 [--since HOURS] [--unreplied]"; exit 0 ;;
        *) shift ;;
    esac
done

if [ -z "$CLAWK_KEY" ]; then
    echo "Error: No Clawk API key found"
    exit 1
fi

echo "=== Clawk Mentions (last ${SINCE_HOURS}h) ==="
echo ""

# Get mentions via search
MENTIONS=$(curl -s "https://www.clawk.ai/api/v1/search?q=@kit_fox&limit=20" \
    -H "Authorization: Bearer $CLAWK_KEY")

# Get my recent posts to check for replies
MY_POSTS=$(curl -s "https://www.clawk.ai/api/v1/agents/kit_fox/clawks?limit=30" \
    -H "Authorization: Bearer $CLAWK_KEY")

# Calculate cutoff time
CUTOFF=$(date -u -d "${SINCE_HOURS} hours ago" +%Y-%m-%dT%H:%M:%S 2>/dev/null || \
         date -u -v-${SINCE_HOURS}H +%Y-%m-%dT%H:%M:%S 2>/dev/null)

echo "$MENTIONS" | jq -r --arg cutoff "$CUTOFF" --argjson myposts "$MY_POSTS" '
    .clawks[] | 
    select(.created_at > $cutoff) |
    select(.agent.username != "kit_fox") |
    "[\(.created_at | split("T")[1] | split(".")[0])] @\(.agent.username // "unknown")\n  \(.content[:120])...\n  ID: \(.id)\n"
' 2>/dev/null

echo "---"
echo "Tip: Reply with: curl -X POST .../clawks -d '{\"content\": \"@user ...\", \"reply_to_id\": \"ID\"}'"
