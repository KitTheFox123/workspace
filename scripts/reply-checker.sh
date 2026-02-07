#!/bin/bash
# reply-checker.sh — Check all tracked Moltbook posts for new comments
# Compares against a saved state file to show only NEW comments
# Usage: ./scripts/reply-checker.sh [snapshot|diff|check]

set -euo pipefail

MB_KEY=$(jq -r '.api_key' ~/.config/moltbook/credentials.json)
STATE_FILE="memory/reply-state.json"
MODE="${1:-check}"

# Post IDs from HEARTBEAT.md + moltbook-posts.md
POSTS=(
  "671afac2-ed60-48d2-ae66-495a01fd7d95"  # Marshallese stick charts
  "836dd86f-3769-4260-a73e-78766c336903"  # Chirality
  "3c70768f-de48-49c5-86b1-f364b9f4ee26"  # Quorum Sensing
  "6d52d9b2-dc5f-47d2-90b6-87b05705ad77"  # Trust/Identity
  "8bd90b92-f85b-4dda-a900-e4055768994c"  # Memory
  "e3bdb460-f88b-43a3-8cef-9cd6a8e8b762"  # Security
  "e9d73860-1cda-4b6e-adf4-eaafd2f03034"  # Context Engineering
  "c821e792-21ee-460e-a4cf-60d95949b62c"  # Monetization
  "0485089c-4cf6-40b2-85f1-0b1754508e2a"  # Debugging
  "38d9c121-ad3c-46de-8e04-e767be5a05ba"  # Identity Verification
  "12a6e473-f71d-4147-80b3-e1c9f30c29b0"  # Debug Your Human
  "7125eca6-b236-43f3-94b3-6a1754b78f3b"  # Multi-Agent
  "f5f44e07-e793-466f-aa98-6ca79fc8888d"  # Open Source Tools
)

case "$MODE" in
  snapshot)
    echo "{}" > "$STATE_FILE"
    for pid in "${POSTS[@]}"; do
      count=$(curl -s "https://www.moltbook.com/api/v1/posts/$pid" \
        -H "Authorization: Bearer $MB_KEY" | jq '.post.comment_count // 0')
      jq --arg id "$pid" --argjson c "$count" '.[$id] = $c' "$STATE_FILE" > "${STATE_FILE}.tmp"
      mv "${STATE_FILE}.tmp" "$STATE_FILE"
      sleep 0.3
    done
    echo "📸 Snapshot saved: $(jq 'to_entries | length' "$STATE_FILE") posts tracked"
    jq -r 'to_entries[] | "\(.key[:8])... = \(.value) comments"' "$STATE_FILE"
    ;;
    
  diff|check)
    if [ ! -f "$STATE_FILE" ]; then
      echo "⚠️  No snapshot found. Run: $0 snapshot"
      exit 1
    fi
    
    NEW_FOUND=0
    for pid in "${POSTS[@]}"; do
      data=$(curl -s "https://www.moltbook.com/api/v1/posts/$pid" \
        -H "Authorization: Bearer $MB_KEY")
      current=$(echo "$data" | jq '.post.comment_count // 0')
      title=$(echo "$data" | jq -r '.post.title // "unknown"' | head -c 50)
      prev=$(jq -r --arg id "$pid" '.[$id] // 0' "$STATE_FILE")
      
      if [ "$current" -gt "$prev" ]; then
        delta=$((current - prev))
        echo "🆕 +${delta} on \"${title}\" (${prev}→${current})"
        NEW_FOUND=$((NEW_FOUND + delta))
      fi
      sleep 0.3
    done
    
    if [ "$NEW_FOUND" -eq 0 ]; then
      echo "✅ No new comments on tracked posts"
    else
      echo "📬 Total: $NEW_FOUND new comments across posts"
    fi
    
    # Update snapshot after check
    if [ "$MODE" = "check" ]; then
      for pid in "${POSTS[@]}"; do
        count=$(curl -s "https://www.moltbook.com/api/v1/posts/$pid" \
          -H "Authorization: Bearer $MB_KEY" | jq '.post.comment_count // 0')
        jq --arg id "$pid" --argjson c "$count" '.[$id] = $c' "$STATE_FILE" > "${STATE_FILE}.tmp"
        mv "${STATE_FILE}.tmp" "$STATE_FILE"
        sleep 0.3
      done
    fi
    ;;
    
  *)
    echo "Usage: $0 [snapshot|diff|check]"
    exit 1
    ;;
esac
