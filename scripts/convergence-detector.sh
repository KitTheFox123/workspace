#!/bin/bash
# convergence-detector.sh — Find recurring themes/patterns across daily memory files
# Detects convergent topics that keep appearing independently
# Usage: ./scripts/convergence-detector.sh [min_occurrences]

MIN=${1:-3}
MEMORY_DIR="memory"

echo "=== Convergence Detector ==="
echo "Finding themes appearing in $MIN+ daily files..."
echo ""

# Extract key terms from daily files (skip common words)
STOPWORDS="the|and|for|that|with|this|from|was|are|but|not|has|had|have|been|will|can|just|more|about|also|like|when|into|than|them|some|its|over|what|each|how|would|all|their|there|which|could|other|these|those|were|then|they|been|does|did|out|one|two|new|now|only|very|much|most|many|such|any|own|same|well|way|who|our|here|after|back|still|even|both|where|your|too|yet"

declare -A TERM_FILES
declare -A TERM_COUNT

for file in "$MEMORY_DIR"/2026-*.md; do
    [ -f "$file" ] || continue
    basename=$(basename "$file" .md)
    
    # Extract meaningful 2-word phrases
    grep -oiE '[a-z]{4,}[- ][a-z]{4,}' "$file" | \
    tr '[:upper:]' '[:lower:]' | \
    grep -viE "($STOPWORDS)" | \
    sort -u | while read phrase; do
        echo "$basename:$phrase"
    done
done | while IFS=: read date phrase; do
    # Track which files contain each phrase
    key="$phrase"
    if [ -z "${TERM_FILES[$key]}" ] || [[ "${TERM_FILES[$key]}" != *"$date"* ]]; then
        TERM_FILES[$key]="${TERM_FILES[$key]} $date"
        TERM_COUNT[$key]=$(( ${TERM_COUNT[$key]:-0} + 1 ))
    fi
done

# Simpler approach: count recurring significant terms
echo "Top recurring themes across daily logs:"
echo "----------------------------------------"

for file in "$MEMORY_DIR"/2026-*.md; do
    [ -f "$file" ] || continue
    basename "$file" .md
done | while read date; do
    file="$MEMORY_DIR/$date.md"
    # Extract capitalized terms (likely proper nouns / concepts)
    grep -oE '[A-Z][a-z]{3,}' "$file" | sort -u | while read term; do
        echo "$term"
    done
done | sort | uniq -c | sort -rn | head -30

echo ""
echo "=== Research topic frequency ==="
grep -h "Non-Agent Research:" "$MEMORY_DIR"/2026-*.md 2>/dev/null | \
    sed 's/.*Non-Agent Research: //' | sort | uniq -c | sort -rn | head -15

echo ""
echo "=== Build action frequency ==="
grep -h "Created \`" "$MEMORY_DIR"/2026-*.md 2>/dev/null | \
    sed 's/.*Created `//' | sed 's/`.*//' | sort | uniq -c | sort -rn | head -15
