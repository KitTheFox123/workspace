#!/usr/bin/env bash
# captcha-analyzer.sh — Analyze captcha challenge patterns from daily logs
# Extracts all captcha challenges, categorizes operations, tracks success rates
set -euo pipefail

LOG_DIR="${1:-memory}"
DATE="${2:-$(date -u +%Y-%m-%d)}"
FILE="$LOG_DIR/$DATE.md"

if [[ ! -f "$FILE" ]]; then
    echo "No log file: $FILE"
    exit 1
fi

echo "=== Captcha Analysis for $DATE ==="
echo ""

# Extract challenges
CHALLENGES=$(grep -oP '(?<=Challenge: ).*' "$FILE" 2>/dev/null || true)
TOTAL=$(echo "$CHALLENGES" | grep -c . 2>/dev/null || echo "0")
TOTAL=${TOTAL//[^0-9]/}
echo "Total challenges encountered: $TOTAL"

# Count operations
ADD=$(echo "$CHALLENGES" | grep -ciE 'plus|adds|gains|and.*adds' 2>/dev/null || true); ADD=${ADD//[^0-9]/}; ADD=${ADD:-0}
MUL=$(echo "$CHALLENGES" | grep -ciE 'multipl|times|product' 2>/dev/null || true); MUL=${MUL//[^0-9]/}; MUL=${MUL:-0}
SUB=$(echo "$CHALLENGES" | grep -ciE 'minus|subtract|loses' 2>/dev/null || true); SUB=${SUB//[^0-9]/}; SUB=${SUB:-0}
VELOCITY=$(echo "$CHALLENGES" | grep -ciE 'velocity|speed|force' 2>/dev/null || true); VELOCITY=${VELOCITY//[^0-9]/}; VELOCITY=${VELOCITY:-0}

echo ""
echo "Operation types:"
echo "  Addition:       $ADD"
echo "  Multiplication: $MUL"
echo "  Subtraction:    $SUB"
echo "  Physics-themed: $VELOCITY"

# Success rates
FIRST_TRY=$(grep -c "✅ Comment published:" "$FILE" 2>/dev/null || true); FIRST_TRY=${FIRST_TRY//[^0-9]/}; FIRST_TRY=${FIRST_TRY:-0}
RETRIES=$(grep -c "✅ Comment published (retry):" "$FILE" 2>/dev/null || true); RETRIES=${RETRIES//[^0-9]/}; RETRIES=${RETRIES:-0}
FAILURES=$(grep -c "❌.*failed" "$FILE" 2>/dev/null || true); FAILURES=${FAILURES//[^0-9]/}; FAILURES=${FAILURES:-0}

echo ""
echo "Success rates:"
echo "  First-try:  $FIRST_TRY"
echo "  Retries:    $RETRIES"  
echo "  Failures:   $FAILURES"
TOTAL_ATTEMPTS=$((FIRST_TRY + RETRIES + FAILURES))
if [[ $TOTAL_ATTEMPTS -gt 0 ]]; then
    SUCCESS=$((FIRST_TRY + RETRIES))
    RATE=$(echo "scale=1; $SUCCESS * 100 / $TOTAL_ATTEMPTS" | bc)
    echo "  Success rate: ${RATE}%"
fi

# Unique obfuscation patterns
echo ""
echo "Obfuscation patterns detected:"
echo "$CHALLENGES" | grep -oP '[A-Z][a-z]+[A-Z]' | sort -u | head -10
