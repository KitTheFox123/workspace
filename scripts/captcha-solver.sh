#!/bin/bash
# captcha-solver.sh — Parse and solve Moltbook lobster captcha challenges
# Usage: echo "CHALLENGE_TEXT" | ./captcha-solver.sh
# Or: ./captcha-solver.sh "CHALLENGE_TEXT"

set -euo pipefail

challenge="${1:-$(cat)}"

# Normalize: lowercase, remove special chars
clean=$(echo "$challenge" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9 +*-]/ /g' | tr -s ' ')

# Word-to-number mapping
word_to_num() {
  local w="$1"
  case "$w" in
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

# Extract numbers from word sequences
extract_numbers() {
  local text="$1"
  local current=0
  local numbers=()
  local in_number=false
  
  for word in $text; do
    num=$(word_to_num "$word")
    if [ -n "$num" ]; then
      if [ "$word" = "hundred" ]; then
        current=$((current * 100))
      elif [ "$num" -ge 20 ] && [ "$num" -le 90 ]; then
        if $in_number && [ $current -gt 0 ]; then
          # New tens digit after existing number = new number
          numbers+=($current)
          current=$num
        else
          current=$num
        fi
      else
        current=$((current + num))
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
  if $in_number; then
    numbers+=($current)
  fi
  echo "${numbers[@]}"
}

# Detect operation
detect_op() {
  local text="$1"
  if echo "$text" | grep -qi "product\|multiply\|times\|\*"; then
    echo "*"
  elif echo "$text" | grep -qi "minus\|subtract\|\-"; then
    echo "-"
  else
    echo "+"
  fi
}

numbers=($(extract_numbers "$clean"))
op=$(detect_op "$clean")

if [ ${#numbers[@]} -lt 2 ]; then
  echo "ERROR: Found fewer than 2 numbers in challenge" >&2
  echo "Numbers found: ${numbers[*]}" >&2
  exit 1
fi

a=${numbers[0]}
b=${numbers[1]}
result=$(echo "$a $op $b" | bc)

printf "%.2f\n" "$result"
