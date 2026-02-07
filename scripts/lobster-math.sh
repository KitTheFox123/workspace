#!/bin/bash
# lobster-math.sh — Parse and solve Moltbook lobster captcha challenges
# Handles the obfuscated lobster physics format with split words, random punctuation
# Usage: echo "challenge text" | ./scripts/lobster-math.sh
# Or: ./scripts/lobster-math.sh "challenge text"

set -euo pipefail

INPUT="${1:-$(cat)}"

# Step 1: Strip all non-alpha/space characters, normalize case
CLEAN=$(echo "$INPUT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z ]/ /g' | tr -s ' ')

# Step 2: Map number words to digits using associative array
declare -A NUMWORDS=(
  [zero]=0 [one]=1 [two]=2 [three]=3 [four]=4 [five]=5
  [six]=6 [seven]=7 [eight]=8 [nine]=9 [ten]=10
  [eleven]=11 [twelve]=12 [thirteen]=13 [fourteen]=14 [fifteen]=15
  [sixteen]=16 [seventeen]=17 [eighteen]=18 [nineteen]=19
  [twenty]=20 [thirty]=30 [forty]=40 [fifty]=50
  [sixty]=60 [seventy]=70 [eighty]=80 [ninety]=90
  [hundred]=100
)

# Step 3: Reassemble split words greedily
# The captcha splits words with spaces: "tHiR tY" -> "thir ty" -> "thirty"
reassemble() {
  local words=($1)
  local result=()
  local i=0
  while [ $i -lt ${#words[@]} ]; do
    local word="${words[$i]}"
    local merged=false
    # Try merging with next 1-3 words
    for lookahead in 3 2 1; do
      if [ $((i + lookahead)) -lt ${#words[@]} ]; then
        local combined="$word"
        for j in $(seq 1 $lookahead); do
          combined="${combined}${words[$((i+j))]}"
        done
        # Check if combined is a known number word
        if [[ -n "${NUMWORDS[$combined]+x}" ]]; then
          result+=("$combined")
          i=$((i + lookahead + 1))
          merged=true
          break
        fi
      fi
    done
    if ! $merged; then
      # Try the word itself
      result+=("$word")
      i=$((i + 1))
    fi
  done
  echo "${result[*]}"
}

REASSEMBLED=$(reassemble "$CLEAN")

# Step 4: Convert words to numbers and find the operation
extract_numbers() {
  local text="$1"
  local nums=()
  local words=($text)
  local current=0
  local has_num=false
  
  for word in "${words[@]}"; do
    if [[ -n "${NUMWORDS[$word]+x}" ]]; then
      local val=${NUMWORDS[$word]}
      if [ $val -eq 100 ]; then
        current=$((current * 100))
      elif [ $val -ge 20 ] && [ $has_num = true ] && [ $current -gt 0 ] && [ $current -lt 10 ]; then
        # Previous was units, save it and start new number
        nums+=($current)
        current=$val
      elif [ $val -ge 20 ]; then
        current=$((current + val))
      elif [ $val -ge 1 ] && [ $val -le 9 ] && [ $current -ge 20 ]; then
        # tens + units
        current=$((current + val))
      else
        if $has_num && [ $current -gt 0 ]; then
          # Check if this could be part of compound (twenty + two)
          if [ $current -ge 20 ] && [ $val -lt 10 ]; then
            current=$((current + val))
            continue
          fi
          nums+=($current)
        fi
        current=$val
      fi
      has_num=true
    else
      if $has_num && [ $current -gt 0 ]; then
        nums+=($current)
        current=0
        has_num=false
      fi
    fi
  done
  if $has_num && [ $current -gt 0 ]; then
    nums+=($current)
  fi
  echo "${nums[*]}"
}

NUMBERS=$(extract_numbers "$REASSEMBLED")
NUM_ARRAY=($NUMBERS)

# Step 5: Detect operation from text
OP="+"
if echo "$REASSEMBLED" | grep -qE "product|multiply|times"; then
  OP="*"
elif echo "$REASSEMBLED" | grep -qE "subtract|minus|differ|less"; then
  OP="-"
elif echo "$REASSEMBLED" | grep -qE "divide|split|ratio"; then
  OP="/"
fi
# Default: addition (sum, total, combined, together, how much are they)

# Step 6: Compute
if [ ${#NUM_ARRAY[@]} -lt 2 ]; then
  echo "ERROR: Found fewer than 2 numbers: $NUMBERS" >&2
  echo "Reassembled: $REASSEMBLED" >&2
  exit 1
fi

# Use last two numbers as operands (skip speed/other noise)
N1=${NUM_ARRAY[-2]}
N2=${NUM_ARRAY[-1]}

case "$OP" in
  "+") RESULT=$((N1 + N2)) ;;
  "-") RESULT=$((N1 - N2)) ;;
  "*") RESULT=$((N1 * N2)) ;;
  "/") RESULT=$((N1 / N2)) ;;
esac

printf "%.2f\n" "$RESULT"
