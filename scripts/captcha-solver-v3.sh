#!/bin/bash
# captcha-solver-v3.sh — Moltbook lobster captcha solver (unified, handles obfuscation)
# Usage: ./captcha-solver-v3.sh "CHALLENGE_TEXT"
#        echo "CHALLENGE_TEXT" | ./captcha-solver-v3.sh
# Returns: number with 2 decimal places (e.g., "35.00")

set -euo pipefail

challenge="${1:-$(cat)}"

# Pre-computed dedup map: deduped_form → canonical_word
# Generated from: echo "word" | sed -E 's/([a-z])\1+/\1/g'
declare -A DEDUP_MAP=(
  [zero]=zero [one]=one [two]=two [thre]=three [four]=four
  [five]=five [six]=six [seven]=seven [eight]=eight [nine]=nine
  [ten]=ten [eleven]=eleven [twelve]=twelve [thirteen]=thirteen
  [fourteen]=fourteen [fiften]=fifteen [sixten]=sixteen [seventen]=seventeen
  [eighten]=eighteen [nineten]=nineteen [twenty]=twenty [thirty]=thirty
  [forty]=forty [fifty]=fifty [sixty]=sixty [seventy]=seventy
  [eighty]=eighty [ninety]=ninety [hundred]=hundred
  [plus]=plus [ads]=adds [gains]=gains [minus]=minus [subtract]=subtract
  [times]=times [product]=product [total]=total
  # Also map canonical forms to themselves
  [three]=three [fifteen]=fifteen [sixteen]=sixteen [seventeen]=seventeen
  [eighteen]=eighteen [nineteen]=nineteen [adds]=adds
)

# Dedup a string: collapse consecutive duplicate chars
dedup() { echo "$1" | sed -E 's/([a-z])\1+/\1/g'; }

# Lookup: try raw word, then deduped form
lookup() {
  local word="$1"
  [[ -v DEDUP_MAP["$word"] ]] && { echo "${DEDUP_MAP[$word]}"; return 0; }
  local d
  d=$(dedup "$word")
  [[ -v DEDUP_MAP["$d"] ]] && { echo "${DEDUP_MAP[$d]}"; return 0; }
  return 1
}

# Strip non-alpha (except spaces), lowercase, collapse whitespace
stripped=$(echo "$challenge" | tr '[:upper:]' '[:lower:]' | tr -d '\n' | sed 's/[^a-z ]//g' | tr -s ' ')

# Greedy word reassembly: join adjacent fragments into known words
reassemble() {
  local words=($1)
  local result=""
  local i=0
  
  while [ $i -lt ${#words[@]} ]; do
    local matched=false
    # Try joining up to 4 fragments
    for len in 4 3 2; do
      if [ $((i + len)) -le ${#words[@]} ]; then
        local joined=""
        for ((j=i; j<i+len; j++)); do
          joined="${joined}${words[$j]}"
        done
        local resolved
        if resolved=$(lookup "$joined"); then
          result="$result $resolved"
          i=$((i + len))
          matched=true
          break
        fi
      fi
    done
    if ! $matched; then
      local resolved
      if resolved=$(lookup "${words[$i]}"); then
        result="$result $resolved"
      else
        result="$result ${words[$i]}"
      fi
      i=$((i + 1))
    fi
  done
  echo "$result"
}

clean=$(reassemble "$stripped")

# Map number words → digits
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

# Extract all numbers from cleaned text
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
        numbers+=($current)
        current=$num
      elif [ "$num" -ge 20 ]; then
        $in_number && [ $current -ge 20 ] && numbers+=($current)
        current=$num
      elif [ "$num" -ge 1 ] && [ "$num" -le 9 ] && [ $current -ge 20 ] && [ $((current % 10)) -eq 0 ]; then
        current=$((current + num))
      else
        $in_number && [ $current -gt 0 ] && [ "$num" -ge 10 ] && { numbers+=($current); current=$num; } || current=$((current + num))
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

# Detect operation
detect_op() {
  local text="$1"
  if echo "$text" | grep -qiE 'product|multipl|times'; then
    echo "*"
  elif echo "$text" | grep -qiE 'minus|subtract|less|loses|drops'; then
    echo "-"
  elif echo "$text" | grep -qiE 'divid|split'; then
    echo "/"
  else
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

a=${numbers[0]}
b=${numbers[1]}
result=$(echo "scale=2; $a $op $b" | bc)

printf "%.2f\n" "$result"
