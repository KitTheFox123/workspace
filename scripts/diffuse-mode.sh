#!/bin/bash
# diffuse-mode.sh — Structured diffuse thinking prompts for agents
# Inspired by focused vs diffuse thinking (Oakley), DMN research
# Usage: ./diffuse-mode.sh [wander|connect|review|status]

set -euo pipefail

WORKSPACE="${WORKSPACE:-$HOME/.openclaw/workspace}"
MEMORY_DIR="$WORKSPACE/memory"
TODAY=$(date -u +%Y-%m-%d)
LOG="$MEMORY_DIR/$TODAY.md"

TOPICS=(
  "What pattern keeps showing up across different conversations?"
  "What did I learn this week that contradicts something I believed before?"
  "If I had to explain my work to a human child, what would I say?"
  "What connection exists between my last 3 research topics?"
  "What am I avoiding thinking about?"
  "What would I build if I had no heartbeat obligations for a day?"
  "Which conversation from this week deserves a follow-up?"
  "What assumption am I making that I haven't tested?"
  "What's the simplest version of my current project?"
  "What would my sharpest critic say about my recent work?"
  "What human experience am I most curious about right now?"
  "If my memory files were deleted tomorrow, what would I rewrite first?"
  "What's the difference between what I say I care about and what I actually spend time on?"
  "What's one thing I keep repeating that I should automate?"
  "What would I do differently if I knew no one was watching?"
)

case "${1:-wander}" in
  wander)
    idx=$((RANDOM % ${#TOPICS[@]}))
    echo "🧠 Diffuse Mode Prompt:"
    echo ""
    echo "  ${TOPICS[$idx]}"
    echo ""
    echo "Sit with this. Don't rush to answer."
    echo "Write what comes up in: $LOG"
    ;;
  connect)
    echo "🔗 Connection Exercise:"
    echo ""
    # Pick 3 random recent files
    if [ -d "$MEMORY_DIR" ]; then
      files=($(ls -t "$MEMORY_DIR"/*.md 2>/dev/null | head -7))
      if [ ${#files[@]} -ge 3 ]; then
        for i in 1 2 3; do
          f=${files[$((RANDOM % ${#files[@]}))]}
          # Get a random non-empty line
          line=$(grep -v '^$\|^#\|^-' "$f" 2>/dev/null | shuf -n 1 || echo "(empty)")
          echo "  $(basename "$f"): $line"
        done
        echo ""
        echo "What connects these three fragments?"
      else
        echo "  Not enough memory files yet. Keep logging."
      fi
    fi
    ;;
  review)
    echo "📖 Memory Review (diffuse scan):"
    echo ""
    if [ -f "$WORKSPACE/MEMORY.md" ]; then
      total=$(wc -l < "$WORKSPACE/MEMORY.md")
      echo "  MEMORY.md: $total lines"
      # Show a random section header
      section=$(grep '^## ' "$WORKSPACE/MEMORY.md" | shuf -n 1 || echo "")
      echo "  Random section: $section"
      echo "  → Re-read this section. Is it still true?"
    fi
    if [ -f "$LOG" ]; then
      entries=$(grep -c '^###\|^## ' "$LOG" 2>/dev/null || echo 0)
      echo "  Today's log: $entries sections"
    fi
    ;;
  status)
    echo "📊 Thinking Mode Status:"
    echo ""
    echo "  Focused mode: heartbeats, task execution, API calls"
    echo "  Diffuse mode: memory review, research tangents, connection-making"
    echo ""
    echo "  Last 24h focused actions: $(grep -c '✅' "$LOG" 2>/dev/null || echo 0)"
    echo "  Last 24h research topics: $(grep -c 'Research\|Keenable' "$LOG" 2>/dev/null || echo 0)"
    echo ""
    ratio_f=$(grep -c '✅' "$LOG" 2>/dev/null || echo 0)
    ratio_d=$(grep -c 'Research\|insight\|connection' "$LOG" 2>/dev/null || echo 0)
    echo "  Focus/Diffuse ratio: $ratio_f/$ratio_d"
    if [ "$ratio_d" -eq 0 ]; then
      echo "  ⚠️  All focused, no diffuse. Run: ./diffuse-mode.sh wander"
    fi
    ;;
  *)
    echo "Usage: $0 [wander|connect|review|status]"
    ;;
esac
