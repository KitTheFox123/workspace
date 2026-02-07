#!/bin/bash
# citation-density.sh — Analyze citation density in Moltbook comments
# Checks how many comments include real research references
# Usage: ./scripts/citation-density.sh [memory-file]

FILE="${1:-memory/$(date +%Y-%m-%d).md}"

if [ ! -f "$FILE" ]; then
  echo "File not found: $FILE"
  exit 1
fi

echo "=== Citation Density Analysis ==="
echo "File: $FILE"
echo ""

# Count total comments
TOTAL=$(grep -c "Comment ID:" "$FILE" 2>/dev/null || echo 0)
echo "Total comments: $TOTAL"

# Count comments with research citations (PMC, DOI, year references, author names)
RESEARCH=$(grep -B5 "Comment ID:" "$FILE" | grep -c -E "(PMC[0-9]+|doi\.|[A-Z][a-z]+ et al|[A-Z][a-z]+ \([0-9]{4}\)|arXiv|Nature|Science|PNAS|Cell|Lancet)" 2>/dev/null || echo 0)
echo "Research-backed: $RESEARCH"

if [ "$TOTAL" -gt 0 ]; then
  PCT=$(echo "scale=1; $RESEARCH * 100 / $TOTAL" | bc 2>/dev/null || echo "?")
  echo "Citation rate: ${PCT}%"
fi

echo ""
echo "=== Research Topics ==="
grep -oP "Non-Agent Research: \K.*" "$FILE" | sort -u

echo ""
echo "=== Unique Sources Referenced ==="
grep -oP "PMC[0-9]+" "$FILE" | sort -u | wc -l | xargs echo "PMC papers:"
grep -oP "[A-Z][a-z]+ et al" "$FILE" | sort -u | head -20

echo ""
echo "=== Build Actions ==="
grep -oP "Created \`[^\`]+\`" "$FILE" | sort -u
