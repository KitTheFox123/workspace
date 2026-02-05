#!/bin/bash
# extract-quotes.sh - Extract key quotes from fetched research content
# Created 2026-02-04 as BUILD action
# Usage: echo "content" | ./extract-quotes.sh
# Or: ./extract-quotes.sh < file.txt

# Patterns that often indicate key insights
PATTERNS=(
    "we found"
    "this suggests"
    "importantly"
    "crucially"
    "the key"
    "in conclusion"
    "our results"
    "evidence shows"
    "this indicates"
    "notably"
    "significant"
    "reveals that"
    "demonstrates"
)

echo "=== Potential Key Quotes ==="
echo ""

# Build grep pattern
GREP_PATTERN=$(IFS="|"; echo "${PATTERNS[*]}")

# Read input and find sentences containing key patterns
if [ -t 0 ]; then
    echo "Usage: echo 'content' | $0"
    echo "   or: $0 < file.txt"
    echo ""
    echo "Looks for sentences containing:"
    for p in "${PATTERNS[@]}"; do
        echo "  - $p"
    done
    exit 0
fi

# Process input - find lines with patterns and show context
grep -i -E "$GREP_PATTERN" | while read -r line; do
    # Trim and limit length
    trimmed=$(echo "$line" | sed 's/^[[:space:]]*//' | cut -c1-200)
    if [ -n "$trimmed" ]; then
        echo "• $trimmed"
        echo ""
    fi
done | head -30

echo "=== End Quotes ==="
