#!/bin/bash
# captcha-solver-v3.sh — Moltbook lobster captcha solver (unified, handles obfuscation)
# Usage: ./captcha-solver-v3.sh "CHALLENGE_TEXT"
#        echo "CHALLENGE_TEXT" | ./captcha-solver-v3.sh
# Returns: number with 2 decimal places (e.g., "35.00")

set -euo pipefail

challenge="${1:-$(cat)}"

# Step 1: Normalize — strip punctuation, deduplicate chars, lowercase
normalize() {
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9 ]/ /g' \
    | tr -s ' ' \
    | sed -E 's/([a-z])\1{2,}/\1\1/g'  # Reduce 3+ repeats to 2: "ttthhhrreeee" → "tthhrreeee"
}

# Step 1b: Fuzzy word match — try original, then with single chars
# "fourten" → "fourteen", "thre" → "three"
fuzzy_dedup() {
  # For each word, try removing duplicate chars to match known words
  local text="$1"
  local result=""
  for word in $text; do
    local deduped
    deduped=$(echo "$word" | sed -E 's/([a-z])\1+/\1/g')
    # Check if deduped matches a known number word
    case "$deduped" in
      zero|one|two|three|four|five|six|seven|eight|nine|ten|\
      eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|\
      eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|\
      eighty|ninety|hundred|\
      plus|adds|gains|minus|subtract|times|product|multipl*|divid*|\
      total|sum|combined|loses|drops)
        result="$result $deduped" ;;
      *)
        # Try the original word too
        result="$result $word" ;;
    esac
  done
  echo "$result"
}

# Strip non-alpha (except spaces) WITHOUT adding new spaces, then collapse
stripped=$(echo "$challenge" | tr '[:upper:]' '[:lower:]' | tr -d '\n' | sed 's/[^a-z ]//g' | tr -s ' ')

# Greedy word reassembly: try joining adjacent fragments into known number words
reassemble() {
  local words=($1)
  local result=""
  local i=0
  local known="zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred plus adds gains minus subtract times product total"
  
  while [ $i -lt ${#words[@]} ]; do
    local matched=false
    # Try joining up to 4 fragments
    for len in 4 3 2; do
      if [ $((i + len)) -le ${#words[@]} ]; then
        local joined=""
        for ((j=i; j<i+len; j++)); do
          joined="${joined}${words[$j]}"
        done
        # Check raw join AND deduped version
        local deduped
        deduped=$(echo "$joined" | sed -E 's/([a-z])\1+/\1/g')
        if echo " $known " | grep -q " $joined "; then
          result="$result $joined"
          i=$((i + len))
          matched=true
          break
        elif echo " $known " | grep -q " $deduped "; then
          # Re-expand: check if any known word matches when we allow double letters
          local best="$deduped"
          for kw in $known; do
            local kw_dedup
            kw_dedup=$(echo "$kw" | sed -E 's/([a-z])\1+/\1/g')
            if [ "$kw_dedup" = "$deduped" ]; then
              best="$kw"
              break
            fi
          done
          result="$result $best"
          i=$((i + len))
          matched=true
          break
        fi
      fi
    done
    if ! $matched; then
      # Single word — try raw then dedup
      local word="${words[$i]}"
      local deduped
      deduped=$(echo "$word" | sed -E 's/([a-z])\1+/\1/g')
      if echo " $known " | grep -q " $word "; then
        result="$result $word"
      elif echo " $known " | grep -q " $deduped "; then
        # Find the proper known word
        local best="$deduped"
        for kw in $known; do
          local kw_dedup
          kw_dedup=$(echo "$kw" | sed -E 's/([a-z])\1+/\1/g')
          if [ "$kw_dedup" = "$deduped" ]; then
            best="$kw"
            break
          fi
        done
        result="$result $best"
      else
        result="$result ${words[$i]}"
      fi
      i=$((i + 1))
    fi
  done
  echo "$result"
}

clean=$(reassemble "$stripped")

# Step 2: Map number words → digits
# Handles compounds like "twenty three" = 23
word_to_num() {
  case "$1" in
    zero) echo 0;; one) echo 1;; two) echo 2;; three) echo 3;; four) echo 4;;
    five) echo 5;; six) echo 6;; seven) echo 7;; eight) echo 8;; nine) echo 9;;
    ten) echo 10;; eleven) echo 11;; twelve) echo 12;; thirteen) echo 13;;
    fourteen) echo 14;; fifteen) echo 15;; sixteen) echo 16;; seventeen) echo 17;;
    eighteen) echo 18;; nineteen) echo 19;; twenty) echo 20;; thirty) echo 30;;
    forty) echo 40;; fifty) echo 50;; sixty) echo 60;; seventy) echo 70;;
    eighty) echo 80;; ninety) echo 90;; hundred) echo 100;;
    *) echo "";;
  esac
}

# Step 3: Extract all numbers from the cleaned text
extract_numbers() {
  local text="$1"
  local current=0
  local in_number=false
  local numbers=()

  for word in $text; do
    local num
    num=$(word_to_num "$word")
    if [ -n "$num" ]; then
      if [ "$word" = "hundred" ]; then
        [ $current -eq 0 ] && current=1
        current=$((current * 100))
      elif [ "$num" -ge 20 ] && $in_number && [ $current -ge 1 ] && [ $current -le 19 ]; then
        # Was building a small number, hit a tens — save old, start new
        numbers+=($current)
        current=$num
      elif [ "$num" -ge 20 ]; then
        if $in_number && [ $current -ge 20 ]; then
          numbers+=($current)
        fi
        current=$num
      elif [ "$num" -ge 1 ] && [ "$num" -le 9 ] && [ $current -ge 20 ] && [ $((current % 10)) -eq 0 ]; then
        # "twenty" + "three" = 23
        current=$((current + num))
      else
        if $in_number && [ $current -gt 0 ] && [ "$num" -ge 10 ]; then
          numbers+=($current)
          current=$num
        else
          current=$((current + num))
        fi
      fi
      in_number=true
    else
      if $in_number; then
        numbers+=($current)
        current=0
        in_number=false
      fi
    fi
  done
  $in_number && numbers+=($current)
  echo "${numbers[@]}"
}

# Step 4: Detect operation from text
detect_op() {
  local text="$1"
  # Check for multiplication first (most specific)
  if echo "$text" | grep -qiE 'product|multipl|times'; then
    echo "*"
  elif echo "$text" | grep -qiE 'minus|subtract|less|loses|drops'; then
    echo "-"
  elif echo "$text" | grep -qiE 'divid|split|per.*equal'; then
    echo "/"
  else
    # Default: addition (plus, adds, gains, total, sum, combined)
    echo "+"
  fi
}

numbers=($(extract_numbers "$clean"))
op=$(detect_op "$clean")

if [ ${#numbers[@]} -lt 2 ]; then
  echo "ERROR: Found <2 numbers. Clean text: $clean" >&2
  echo "Numbers found: ${numbers[*]:-none}" >&2
  exit 1
fi

# Use first two numbers found
a=${numbers[0]}
b=${numbers[1]}
result=$(echo "scale=2; $a $op $b" | bc)

printf "%.2f\n" "$result"
