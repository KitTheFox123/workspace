#!/bin/bash
# sound-symbolism.sh — Analyze text for sound-symbolic properties
# Inspired by bouba/kiki effect research (Ćwiek et al. 2021)
# Classifies words by their phonetic "shape": round vs spiky
#
# Round sounds: b, m, l, n, o, u, w (voiced, labial, sonorant, back vowels)
# Spiky sounds: k, t, p, d, g, i, e, z, x (voiceless stops, front vowels, fricatives)
#
# Usage:
#   ./sound-symbolism.sh analyze "text to analyze"
#   ./sound-symbolism.sh score "word"
#   ./sound-symbolism.sh compare file1.md file2.md

set -euo pipefail

# Phonetic shape scoring
# Positive = round, Negative = spiky
declare -A PHONE_SCORES=(
  [b]=2 [m]=2 [l]=1 [n]=1 [o]=2 [u]=2 [w]=1 [a]=1
  [k]=-2 [t]=-2 [p]=-1 [i]=-2 [e]=-1 [z]=-1 [x]=-2
  [g]=-1 [d]=-1 [s]=-1 [f]=-1 [c]=-1
  [r]=0 [h]=0 [j]=0 [q]=-1 [v]=0 [y]=0
)

score_word() {
  local word="${1,,}"  # lowercase
  local score=0
  local count=0
  for ((i=0; i<${#word}; i++)); do
    local c="${word:$i:1}"
    if [[ "${PHONE_SCORES[$c]+_}" ]]; then
      score=$((score + ${PHONE_SCORES[$c]}))
      count=$((count + 1))
    fi
  done
  if [[ $count -gt 0 ]]; then
    # Return score normalized by length
    echo "$score $count"
  else
    echo "0 0"
  fi
}

classify_word() {
  local word="$1"
  read -r score count <<< "$(score_word "$word")"
  if [[ $count -eq 0 ]]; then
    echo "neutral"
  elif [[ $score -gt 1 ]]; then
    echo "round"
  elif [[ $score -lt -1 ]]; then
    echo "spiky"
  else
    echo "neutral"
  fi
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  score)
    word="${1:?Usage: $0 score WORD}"
    read -r score count <<< "$(score_word "$word")"
    class=$(classify_word "$word")
    echo "$word: score=$score chars=$count class=$class"
    ;;
    
  analyze)
    text="${1:?Usage: $0 analyze \"text\"}"
    round=0; spiky=0; neutral=0; total=0
    for word in $text; do
      clean=$(echo "$word" | tr -cd 'a-zA-Z')
      [[ -z "$clean" ]] && continue
      class=$(classify_word "$clean")
      total=$((total + 1))
      case "$class" in
        round) round=$((round + 1)) ;;
        spiky) spiky=$((spiky + 1)) ;;
        neutral) neutral=$((neutral + 1)) ;;
      esac
    done
    echo "=== Sound Symbolism Analysis ==="
    echo "Words: $total"
    echo "Round (bouba-like): $round ($(( total > 0 ? round * 100 / total : 0 ))%)"
    echo "Spiky (kiki-like): $spiky ($(( total > 0 ? spiky * 100 / total : 0 ))%)"
    echo "Neutral: $neutral ($(( total > 0 ? neutral * 100 / total : 0 ))%)"
    if [[ $round -gt $spiky ]]; then
      echo "Overall texture: ROUND (warm, soft, approachable)"
    elif [[ $spiky -gt $round ]]; then
      echo "Overall texture: SPIKY (sharp, precise, technical)"
    else
      echo "Overall texture: BALANCED"
    fi
    ;;
    
  compare)
    file1="${1:?Usage: $0 compare file1 file2}"
    file2="${2:?Usage: $0 compare file1 file2}"
    echo "=== Comparing Sound Symbolism ==="
    for f in "$file1" "$file2"; do
      text=$(cat "$f" | tr -cd 'a-zA-Z \n')
      round=0; spiky=0; total=0
      for word in $text; do
        [[ -z "$word" ]] && continue
        class=$(classify_word "$word")
        total=$((total + 1))
        case "$class" in
          round) round=$((round + 1)) ;;
          spiky) spiky=$((spiky + 1)) ;;
        esac
      done
      pct_round=$(( total > 0 ? round * 100 / total : 0 ))
      pct_spiky=$(( total > 0 ? spiky * 100 / total : 0 ))
      echo "$f: ${total} words, ${pct_round}% round, ${pct_spiky}% spiky"
    done
    ;;
    
  help|*)
    echo "sound-symbolism.sh — Analyze phonetic texture of text"
    echo ""
    echo "Based on the bouba/kiki effect (Ćwiek et al. 2021):"
    echo "  Round sounds: b, m, l, n, o, u, w (soft, warm)"
    echo "  Spiky sounds: k, t, p, i, e, z, x (sharp, precise)"
    echo ""
    echo "Commands:"
    echo "  score WORD        Score a single word"
    echo "  analyze \"TEXT\"     Analyze a passage"
    echo "  compare F1 F2     Compare two files"
    ;;
esac
