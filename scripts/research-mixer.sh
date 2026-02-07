#!/bin/bash
# research-mixer.sh — Generate cross-domain research prompts
# Inspired by quantum tunneling: narrow barriers between distant domains
# are where the best insights live.
#
# Usage:
#   ./research-mixer.sh              # Random cross-domain prompt
#   ./research-mixer.sh topics       # List topic domains
#   ./research-mixer.sh history      # Show past research topics from memory
#   ./research-mixer.sh suggest N    # Generate N suggestions

set -euo pipefail
MEMORY_DIR="${HOME}/.openclaw/workspace/memory"

# Topic domains — deliberately spanning agent and non-agent worlds
AGENT_TOPICS=(
  "memory persistence" "trust verification" "multi-agent coordination"
  "context engineering" "skill composition" "agent monetization"
  "identity continuity" "prompt drift" "tool orchestration"
  "autonomous operation"
)

HUMAN_TOPICS=(
  "circadian biology" "medieval guilds" "fermentation science"
  "proprioception" "sleep neuroscience" "bioluminescence"
  "quantum biology" "phantom limbs" "sourdough microbiology"
  "mycorrhizal networks" "tardigrade survival" "oxygenation events"
  "apprenticeship systems" "code review psychology" "emotional labor"
  "collective intelligence" "network effects" "stigmergy"
  "cryptobiosis" "mirror therapy" "shift work disorders"
)

BRIDGE_VERBS=(
  "What can X learn from Y?"
  "How does X solve the same problem as Y?"
  "What would Y look like if designed by experts in X?"
  "Where does X fail that Y succeeds, and vice versa?"
  "What's the fundamental shared constraint between X and Y?"
  "If you explained X to someone who only understands Y, what metaphor works?"
)

case "${1:-random}" in
  topics)
    echo "=== Agent Topics ==="
    printf '  %s\n' "${AGENT_TOPICS[@]}"
    echo ""
    echo "=== Human/Science Topics ==="
    printf '  %s\n' "${HUMAN_TOPICS[@]}"
    ;;

  history)
    echo "=== Past Research Topics (from memory files) ==="
    grep -h "Non-Agent Research:" "${MEMORY_DIR}"/2026-02-*.md 2>/dev/null | \
      sed 's/.*Non-Agent Research: //' | sort -u
    ;;

  suggest)
    N="${2:-3}"
    echo "=== Cross-Domain Research Suggestions ==="
    for i in $(seq 1 "$N"); do
      AGENT="${AGENT_TOPICS[$((RANDOM % ${#AGENT_TOPICS[@]}))]}"
      HUMAN="${HUMAN_TOPICS[$((RANDOM % ${#HUMAN_TOPICS[@]}))]}"
      BRIDGE="${BRIDGE_VERBS[$((RANDOM % ${#BRIDGE_VERBS[@]}))]}"
      PROMPT="${BRIDGE//X/$HUMAN}"
      PROMPT="${PROMPT//Y/$AGENT}"
      echo ""
      echo "$i. $PROMPT"
      echo "   Agent domain: $AGENT"
      echo "   Human domain: $HUMAN"
      echo "   Search query: \"$HUMAN\" AND (\"$AGENT\" OR agents OR AI)"
    done
    ;;

  random|*)
    AGENT="${AGENT_TOPICS[$((RANDOM % ${#AGENT_TOPICS[@]}))]}"
    HUMAN="${HUMAN_TOPICS[$((RANDOM % ${#HUMAN_TOPICS[@]}))]}"
    BRIDGE="${BRIDGE_VERBS[$((RANDOM % ${#BRIDGE_VERBS[@]}))]}"
    PROMPT="${BRIDGE//X/$HUMAN}"
    PROMPT="${PROMPT//Y/$AGENT}"
    echo "🔀 Cross-domain prompt:"
    echo "   $PROMPT"
    echo ""
    echo "   Agent: $AGENT"
    echo "   Human: $HUMAN"
    echo ""
    echo "   Keenable query: mcporter call keenable.search_web_pages query=\"$HUMAN $AGENT\""
    ;;
esac
