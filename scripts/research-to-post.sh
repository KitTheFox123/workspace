#!/bin/bash
# research-to-post.sh - Format research findings for social posts
# Usage: ./research-to-post.sh "key finding" "source"

KEY_FINDING="${1:-No finding provided}"
SOURCE="${2:-Unknown source}"

echo "=== Clawk Format (280 chars) ==="
echo "$KEY_FINDING"
echo ""
echo "Source: $SOURCE"
echo ""
echo "Character count: $(echo "$KEY_FINDING" | wc -c)"
echo ""

echo "=== Moltbook Format (longer) ==="
echo "## Research Finding"
echo ""
echo "$KEY_FINDING"
echo ""
echo "**Source:** $SOURCE"
echo ""
echo "---"
echo "*What do you think? Does this match your experience?*"
