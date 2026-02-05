#!/bin/bash
# cognitive-load-check.sh - Analyze text complexity for cognitive load
# Uses simple heuristics: sentence length, word complexity, information density

TEXT="${1:-}"

if [ -z "$TEXT" ]; then
    echo "Usage: ./cognitive-load-check.sh \"text to analyze\""
    exit 1
fi

# Count words
WORDS=$(echo "$TEXT" | wc -w)

# Count sentences (approximate)
SENTENCES=$(echo "$TEXT" | grep -o '[.!?]' | wc -l)
[ "$SENTENCES" -eq 0 ] && SENTENCES=1

# Average words per sentence
AVG_SENTENCE=$((WORDS / SENTENCES))

# Count complex words (6+ chars as proxy)
COMPLEX=$(echo "$TEXT" | tr ' ' '\n' | awk 'length > 6' | wc -l)
COMPLEX_RATIO=$((COMPLEX * 100 / WORDS))

echo "=== Cognitive Load Analysis ==="
echo "Words: $WORDS"
echo "Sentences: $SENTENCES"
echo "Avg words/sentence: $AVG_SENTENCE"
echo "Complex words (>6 chars): $COMPLEX ($COMPLEX_RATIO%)"
echo ""

if [ "$AVG_SENTENCE" -gt 20 ]; then
    echo "⚠️ HIGH: Long sentences increase extraneous load"
elif [ "$AVG_SENTENCE" -gt 15 ]; then
    echo "🔶 MEDIUM: Moderate sentence length"
else
    echo "✅ LOW: Short sentences reduce cognitive load"
fi

if [ "$COMPLEX_RATIO" -gt 40 ]; then
    echo "⚠️ HIGH: Many complex words"
elif [ "$COMPLEX_RATIO" -gt 25 ]; then
    echo "🔶 MEDIUM: Some complexity"
else
    echo "✅ LOW: Accessible vocabulary"
fi
