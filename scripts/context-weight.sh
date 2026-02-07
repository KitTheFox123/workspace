#!/bin/bash
# context-weight.sh — Estimate context budget usage across memory files
# Build action: helps decide what to prune vs keep in memory
# Usage: ./scripts/context-weight.sh [directory]

set -euo pipefail

DIR="${1:-memory}"
TOTAL=0
MAX_BUDGET=100000  # approximate token budget (chars / ~4)

echo "📊 Context Weight Analysis"
echo "========================="
echo ""

# Calculate size of each file
declare -A sizes
while IFS= read -r -d '' file; do
    chars=$(wc -c < "$file")
    tokens=$((chars / 4))
    sizes["$file"]=$tokens
    TOTAL=$((TOTAL + tokens))
done < <(find "$DIR" -name "*.md" -print0 | sort -z)

# Sort by size descending
echo "File                                          | Est. Tokens | % Budget"
echo "----------------------------------------------|-------------|--------"
for file in $(for f in "${!sizes[@]}"; do echo "${sizes[$f]} $f"; done | sort -rn | awk '{print $2}'); do
    tokens=${sizes[$file]}
    pct=$(echo "scale=1; $tokens * 100 / $MAX_BUDGET" | bc 2>/dev/null || echo "?")
    printf "%-45s | %11d | %6s%%\n" "$file" "$tokens" "$pct"
done

echo ""
echo "----------------------------------------------|-------------|--------"
printf "%-45s | %11d | %6s%%\n" "TOTAL" "$TOTAL" "$(echo "scale=1; $TOTAL * 100 / $MAX_BUDGET" | bc 2>/dev/null || echo "?")"
echo ""

# Recommendations
if [ "$TOTAL" -gt "$MAX_BUDGET" ]; then
    echo "⚠️  OVER BUDGET by $((TOTAL - MAX_BUDGET)) tokens"
    echo "   Recommend pruning oldest daily logs"
elif [ "$TOTAL" -gt $((MAX_BUDGET * 80 / 100)) ]; then
    echo "⚠️  At 80%+ capacity — consider pruning soon"
else
    echo "✅ Within budget ($((TOTAL * 100 / MAX_BUDGET))% used)"
fi

echo ""
echo "Staleness check (files not modified in 3+ days):"
find "$DIR" -name "*.md" -mtime +3 -printf "  📁 %p (last modified: %TY-%Tm-%Td)\n" 2>/dev/null || echo "  (none found)"
