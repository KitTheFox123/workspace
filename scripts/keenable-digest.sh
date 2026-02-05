#!/bin/bash
# keenable-digest.sh - Quick research digest generator
# Usage: ./keenable-digest.sh "topic"
# Note: Does NOT auto-submit feedback. Review results and submit manually.

TOPIC="$1"
if [ -z "$TOPIC" ]; then
  echo "Usage: $0 'search topic'"
  exit 1
fi

echo "🦊 Researching: $TOPIC"
echo "---"

# Search and save results
RESULTS=$(mcporter call keenable.search_web_pages query="$TOPIC" 2>&1)

# Check if results contain error
if echo "$RESULTS" | grep -qi "error"; then
  echo "Search failed: $RESULTS"
  exit 1
fi

# Extract URLs
URLS=$(echo "$RESULTS" | jq -r '.results[:5][].url' 2>/dev/null)

if [ -z "$URLS" ]; then
  echo "No results found"
  exit 0
fi

# Display search results
echo "📑 Search Results:"
echo "$RESULTS" | jq -r '.results[:5][] | "• " + .title + "\n  " + .url' 2>/dev/null

# Build URL array for fetch
URL_ARRAY=$(echo "$RESULTS" | jq -c '[.results[:5][].url]' 2>/dev/null)

echo ""
echo "📥 Fetching content..."

# Fetch content
mcporter call keenable.fetch_page_content urls="$URL_ARRAY" 2>&1

echo ""
echo "---"
echo "⚠️  Remember to submit feedback AFTER reviewing:"
echo "  mcporter call keenable.submit_search_feedback query=\"$TOPIC\" feedback='{\"url1\": 5, \"url2\": 3}'"
