#!/bin/bash
# research-write.sh - Research helper for quality posts
# Enforces: 3+ queries per write
# Usage: research-write.sh "topic"

set -euo pipefail

topic="${1:-}"
if [[ -z "$topic" ]]; then
  echo "Usage: $0 \"topic to research\""
  echo "Does 3 searches, prints URLs for fetching"
  exit 1
fi

echo "=== Researching: $topic ==="
echo ""

# Generate 3 different query angles
q1="$topic 2025 2026 research"
q2="$topic history evolution"  
q3="$topic science mechanism"

for q in "$q1" "$q2" "$q3"; do
  echo "--- Query: $q ---"
  mcporter call keenable.search_web_pages query="$q" 2>/dev/null | jq -r '.results[:3] | .[] | "- \(.title)\n  \(.url)"' 2>/dev/null || echo "(search failed)"
  echo ""
done

echo "=== Next Steps ==="
echo "1. Pick 2-3 URLs to fetch with: mcporter call keenable.fetch_page_content urls='[...]'"
echo "2. Write post based on actual content"
echo "3. Submit feedback: mcporter call keenable.submit_search_feedback query=\"...\" feedback='{\"url\": score}'"
