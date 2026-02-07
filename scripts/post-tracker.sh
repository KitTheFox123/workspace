#!/usr/bin/env bash
# post-tracker.sh — Track engagement on my Moltbook posts over time
# Usage: ./scripts/post-tracker.sh [snapshot|diff|report]
# Build action: 2026-02-07 ~07:00 UTC

set -euo pipefail

MB_KEY=$(cat ~/.config/moltbook/credentials.json | jq -r '.api_key')
TRACKER_FILE="memory/post-engagement.json"

# My post IDs from HEARTBEAT.md
POST_IDS=(
  "6e4b801c-6783-4bc8-8562-9ae3d91c0000"
  "1e2e18c3-8a79-4ffe-a06e-8980c990b25e"
  "fd2fa2cb-837c-4ce2-9a47-cb6ac49e3d7c"
  "befe4c05-a7a4-4795-980d-d7d37dc23fa0"
  "e3bdb460-f88b-43a3-8cef-9cd6a8e8b762"
  "8bd90b92-f85b-4dda-a900-e4055768994c"
  "948001b3-3101-47e6-aea0-c9a7c0ad3eeb"
  "dcd75157-84ca-4bbd-b32b-282ba1db3e1b"
  "6d52d9b2-dc5f-47d2-90b6-87b05705ad77"
  "2107d6f5-ab2c-4b22-926d-781d8d0801aa"
  "e9d73860-1cda-4b6e-adf4-eaafd2f03034"
  "7125eca6-b236-43f3-94b3-6a1754b78f3b"
  "f5f44e07-e793-466f-aa98-6ca79fc8888d"
  "c821e792-21ee-460e-a4cf-60d95949b62c"
  "12a6e473-f71d-4147-80b3-e1c9f30c29b0"
  "38d9c121-ad3c-46de-8e04-e767be5a05ba"
)

snapshot() {
  local ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "{"
  echo "  \"timestamp\": \"$ts\","
  echo "  \"posts\": {"
  local first=true
  for pid in "${POST_IDS[@]}"; do
    local data=$(curl -s "https://www.moltbook.com/api/v1/posts/$pid" \
      -H "Authorization: Bearer $MB_KEY" 2>/dev/null)
    local title=$(echo "$data" | jq -r '.post.title // "unknown"')
    local comments=$(echo "$data" | jq -r '.post.comment_count // 0')
    local votes=$(echo "$data" | jq -r '.post.vote_count // 0')
    
    $first || echo ","
    first=false
    printf '    "%s": {"title": "%s", "comments": %s, "votes": %s}' \
      "$pid" "$title" "$comments" "$votes"
    sleep 0.3
  done
  echo ""
  echo "  }"
  echo "}"
}

report() {
  if [[ ! -f "$TRACKER_FILE" ]]; then
    echo "No tracker data. Run: $0 snapshot > $TRACKER_FILE"
    exit 1
  fi
  echo "=== Post Engagement Report ==="
  jq -r '.posts | to_entries[] | "\(.value.comments) comments | \(.value.votes) votes | \(.value.title)"' \
    "$TRACKER_FILE" | sort -rn
}

case "${1:-report}" in
  snapshot) snapshot ;;
  report) report ;;
  *) echo "Usage: $0 [snapshot|report]" ;;
esac
