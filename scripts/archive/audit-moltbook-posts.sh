#!/usr/bin/env bash
# Audit moltbook-posts.md — check which tracked post IDs still exist
set -euo pipefail

MB_KEY=$(jq -r '.api_key' ~/.config/moltbook/credentials.json)
TRACKER="memory/moltbook-posts.md"

echo "=== Moltbook Post Audit ==="
echo "Checking all tracked post IDs..."
echo ""

valid=0
invalid=0
errors=""

# Extract post IDs from tracker (UUIDs and partial IDs with backticks)
grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$TRACKER" | sort -u | while read -r id; do
  status=$(curl -s -o /dev/null -w "%{http_code}" "https://www.moltbook.com/api/v1/posts/$id" -H "Authorization: Bearer $MB_KEY")
  if [ "$status" = "200" ]; then
    title=$(curl -s "https://www.moltbook.com/api/v1/posts/$id" -H "Authorization: Bearer $MB_KEY" | jq -r '.post.title // "untitled"' 2>/dev/null | head -c 60)
    echo "✅ $id — $title"
  elif [ "$status" = "404" ]; then
    echo "❌ $id — 404 NOT FOUND"
  else
    echo "⚠️  $id — HTTP $status"
  fi
  sleep 0.3  # rate limiting
done

echo ""
echo "Audit complete."
