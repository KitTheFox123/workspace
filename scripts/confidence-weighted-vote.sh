#!/bin/bash
# confidence-weighted-vote.sh - Aggregate opinions with confidence weighting
# Based on wisdom of crowds research: confidence-weighted beats simple averaging
# Usage: echo "option:confidence" | ./confidence-weighted-vote.sh
#   e.g., echo -e "A:0.8\nB:0.6\nA:0.9\nB:0.7" | ./confidence-weighted-vote.sh

set -euo pipefail

declare -A weights
declare -A counts

while IFS=':' read -r option confidence; do
  [[ -z "$option" ]] && continue
  # Validate confidence is a number between 0 and 1
  if ! [[ "$confidence" =~ ^[0-9]*\.?[0-9]+$ ]]; then
    echo "Warning: Invalid confidence '$confidence' for '$option', using 0.5" >&2
    confidence=0.5
  fi
  
  # Accumulate weighted votes
  current=${weights[$option]:-0}
  weights[$option]=$(echo "$current + $confidence" | bc -l)
  counts[$option]=$((${counts[$option]:-0} + 1))
done

# Output results sorted by weighted score
echo "=== Confidence-Weighted Results ==="
for opt in "${!weights[@]}"; do
  weighted=${weights[$opt]}
  count=${counts[$opt]}
  avg=$(echo "scale=3; $weighted / $count" | bc -l)
  printf "%-15s weighted=%.3f  votes=%d  avg_confidence=%.3f\n" "$opt" "$weighted" "$count" "$avg"
done | sort -t'=' -k2 -rn

echo ""
echo "Winner: $(for opt in "${!weights[@]}"; do echo "${weights[$opt]} $opt"; done | sort -rn | head -1 | awk '{print $2}')"
