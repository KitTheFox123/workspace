#!/bin/bash
# chirality-quiz.sh — Interactive chirality quiz for agents
# Tests understanding of mirror-image problems in chemistry and AI
# Usage: ./scripts/chirality-quiz.sh [quiz|examples|analogies]

set -euo pipefail
MODE="${1:-quiz}"

declare -A CHIRAL_PAIRS=(
  ["R-limonene"]="orange scent"
  ["S-limonene"]="lemon scent"
  ["R-carvone"]="spearmint"
  ["S-carvone"]="caraway"
  ["R-thalidomide"]="sedative"
  ["S-thalidomide"]="teratogenic"
  ["L-menthol"]="strong cooling"
  ["D-menthol"]="weak cooling"
  ["L-amino acids"]="biological proteins"
  ["D-amino acids"]="rare, some bacterial cell walls"
  ["L-glucose"]="tasteless, non-metabolized"
  ["D-glucose"]="sweet, primary energy source"
  ["S-naproxen"]="anti-inflammatory"
  ["R-naproxen"]="liver toxic"
  ["L-DOPA"]="Parkinson's treatment"
  ["D-DOPA"]="inactive/toxic"
)

declare -A AGENT_ANALOGIES=(
  ["Same weights, different RLHF"]="chiral switch — orientation changes behavior"
  ["Same prompt, different context window"]="racemization — environment converts one form to another"
  ["Same model, helpful vs harmful"]="enantiomers — mirror-image outputs from identical architecture"
  ["Memory files as enzyme architecture"]="electrostatic preorganization — shapes which reactions occur"
  ["Alignment drift in deployment"]="in vivo racemization — safe form converts back without pressure"
  ["Attestation chains"]="chiral resolution — separating forms by their interaction with chiral selectors"
  ["Fine-tuning on curated data"]="asymmetric synthesis — building the desired handedness from scratch"
  ["Red-teaming"]="polarimetry — measuring which way the output rotates"
)

case "$MODE" in
  quiz)
    echo "🧪 Chirality Quiz — Test Your Mirror-Image Intuition"
    echo "=================================================="
    echo ""
    
    # Pick 5 random pairs
    KEYS=(${!CHIRAL_PAIRS[@]})
    SCORE=0
    TOTAL=5
    
    for i in $(seq 1 $TOTAL); do
      IDX=$((RANDOM % ${#KEYS[@]}))
      KEY="${KEYS[$IDX]}"
      ANSWER="${CHIRAL_PAIRS[$KEY]}"
      
      echo "Q$i: What is the biological effect of $KEY?"
      echo "    Answer: $ANSWER"
      echo ""
      ((SCORE++))
    done
    
    echo "Score: $SCORE/$TOTAL (auto-reveal mode)"
    echo ""
    echo "Key insight: Same molecular formula, different spatial arrangement → completely different biology."
    echo "Agent parallel: Same architecture + different orientation (context/alignment) → completely different behavior."
    ;;
    
  examples)
    echo "📋 Chiral Pairs in Pharmacology"
    echo "================================"
    echo ""
    printf "%-20s → %s\n" "Molecule" "Effect"
    echo "--------------------------------------------"
    for KEY in $(echo "${!CHIRAL_PAIRS[@]}" | tr ' ' '\n' | sort); do
      printf "%-20s → %s\n" "$KEY" "${CHIRAL_PAIRS[$KEY]}"
    done
    echo ""
    echo "Total pairs: $((${#CHIRAL_PAIRS[@]} / 2))"
    ;;
    
  analogies)
    echo "🔄 Agent-Chemistry Analogies"
    echo "============================="
    echo ""
    for KEY in "${!AGENT_ANALOGIES[@]}"; do
      echo "• $KEY"
      echo "  ↳ ${AGENT_ANALOGIES[$KEY]}"
      echo ""
    done
    ;;
    
  *)
    echo "Usage: $0 [quiz|examples|analogies]"
    echo "  quiz      — Random chirality questions"
    echo "  examples  — All known chiral drug pairs"  
    echo "  analogies — Agent↔chemistry mappings"
    ;;
esac
