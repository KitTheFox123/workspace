#!/bin/bash
# captcha-stats.sh — Track captcha solve success rate
# Reads from daily log files to count successes/failures
LOGDIR="${1:-memory}"
DATE="${2:-$(date -u +%Y-%m-%d)}"
FILE="$LOGDIR/$DATE.md"

if [ ! -f "$FILE" ]; then
  echo "No log file for $DATE"
  exit 1
fi

TOTAL=$(grep -c "Comment published\|Verification failed" "$FILE" 2>/dev/null || echo 0)
SUCCESS=$(grep -c "Comment published" "$FILE" 2>/dev/null || echo 0)
FAIL=$(grep -c "Verification failed" "$FILE" 2>/dev/null || echo 0)
RETRY=$(grep -c "published (retry)" "$FILE" 2>/dev/null || echo 0)
FIRST_TRY=$((SUCCESS - RETRY))

echo "=== Captcha Stats for $DATE ==="
echo "Total attempts: $TOTAL"
echo "First-try success: $FIRST_TRY"
echo "Required retry: $RETRY"
echo "Failed: $FAIL"
if [ "$TOTAL" -gt 0 ]; then
  RATE=$((SUCCESS * 100 / TOTAL))
  echo "Success rate: ${RATE}%"
fi
