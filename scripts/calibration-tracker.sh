#!/usr/bin/env bash
# calibration-tracker.sh — Track prediction confidence vs outcomes
# Usage: ./calibration-tracker.sh [add|report|calibrate] [args]
# Stores predictions in memory/predictions.jsonl

set -euo pipefail
PRED_FILE="memory/predictions.jsonl"

case "${1:-report}" in
  add)
    # add "prediction text" confidence_pct [tag]
    PRED="${2:?Usage: add 'prediction' confidence_pct [tag]}"
    CONF="${3:?Need confidence 0-100}"
    TAG="${4:-general}"
    DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "{\"date\":\"$DATE\",\"prediction\":\"$PRED\",\"confidence\":$CONF,\"tag\":\"$TAG\",\"outcome\":null}" >> "$PRED_FILE"
    echo "✅ Logged prediction at ${CONF}% confidence"
    ;;
  resolve)
    # resolve LINE_NUM 1|0 (1=correct, 0=wrong)
    LINE="${2:?Need line number}"
    OUTCOME="${3:?Need outcome 1 or 0}"
    sed -i "${LINE}s/\"outcome\":null/\"outcome\":${OUTCOME}/" "$PRED_FILE"
    echo "✅ Resolved prediction #${LINE} as outcome=${OUTCOME}"
    ;;
  report)
    if [ ! -f "$PRED_FILE" ]; then
      echo "No predictions file yet. Use: $0 add 'prediction' confidence_pct"
      exit 0
    fi
    echo "=== Calibration Report ==="
    TOTAL=$(grep -c '"outcome":[01]' "$PRED_FILE" 2>/dev/null || echo 0)
    PENDING=$(grep -c '"outcome":null' "$PRED_FILE" 2>/dev/null || echo 0)
    echo "Resolved: $TOTAL | Pending: $PENDING"
    
    if [ "$TOTAL" -gt 0 ]; then
      echo ""
      echo "By confidence bucket:"
      for BUCKET in "0-30" "31-50" "51-70" "71-90" "91-100"; do
        LO=$(echo "$BUCKET" | cut -d- -f1)
        HI=$(echo "$BUCKET" | cut -d- -f2)
        CORRECT=$(jq -r "select(.outcome != null) | select(.confidence >= $LO and .confidence <= $HI) | .outcome" "$PRED_FILE" 2>/dev/null | grep -c "1" || echo 0)
        BUCKET_TOTAL=$(jq -r "select(.outcome != null) | select(.confidence >= $LO and .confidence <= $HI) | .outcome" "$PRED_FILE" 2>/dev/null | wc -l)
        if [ "$BUCKET_TOTAL" -gt 0 ]; then
          PCT=$((CORRECT * 100 / BUCKET_TOTAL))
          EXPECTED=$(( (LO + HI) / 2 ))
          echo "  ${BUCKET}%: ${CORRECT}/${BUCKET_TOTAL} correct (${PCT}% actual vs ~${EXPECTED}% expected)"
        fi
      done
    fi
    ;;
  *)
    echo "Usage: $0 [add|resolve|report]"
    ;;
esac
