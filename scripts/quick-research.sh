#!/bin/bash
# quick-research.sh - Run 3 Keenable searches and fetch content
# Usage: ./quick-research.sh "topic"

TOPIC="$1"
if [ -z "$TOPIC" ]; then
    echo "Usage: $0 \"topic\""
    exit 1
fi

echo "=== Searching: $TOPIC ==="
RESULTS=$(mcporter call keenable.search_web_pages query="$TOPIC" 2>/dev/null)
echo "$RESULTS" | jq -r '.results[:3] | .[] | "- \(.title): \(.url)"'

echo -e "\n=== Fetching top 3 URLs ==="
URLS=$(echo "$RESULTS" | jq -r '[.results[:3] | .[].url] | @json')
mcporter call keenable.fetch_page_content urls="$URLS" 2>/dev/null | head -100

echo -e "\n=== Remember to submit feedback! ==="
