#!/bin/bash
# source-diversity.sh — Analyze research source diversity across heartbeats
# Checks for over-reliance on specific domains, citation patterns, topic clustering
# Build action: 2026-02-07 ~13:35 UTC

set -euo pipefail

MODE="${1:-report}"
FILE="${2:-memory/2026-02-07.md}"

case "$MODE" in
  domains)
    # Extract all URLs from file and count by domain
    echo "=== Domain Frequency ==="
    grep -oP 'https?://[^/\s)]+' "$FILE" 2>/dev/null | \
      sed 's|https\?://||; s|www\.||' | \
      cut -d'/' -f1 | \
      sort | uniq -c | sort -rn | head -20
    
    TOTAL=$(grep -oP 'https?://[^/\s)]+' "$FILE" 2>/dev/null | wc -l)
    UNIQUE=$(grep -oP 'https?://[^/\s)]+' "$FILE" 2>/dev/null | sed 's|https\?://||; s|www\.||' | cut -d'/' -f1 | sort -u | wc -l)
    echo ""
    echo "Total URLs: $TOTAL"
    echo "Unique domains: $UNIQUE"
    if [ "$TOTAL" -gt 0 ]; then
      RATIO=$(echo "scale=1; $UNIQUE * 100 / $TOTAL" | bc)
      echo "Diversity ratio: ${RATIO}%"
      if [ "$(echo "$RATIO < 30" | bc)" -eq 1 ]; then
        echo "⚠️ Low diversity — too many citations from same domains"
      elif [ "$(echo "$RATIO > 70" | bc)" -eq 1 ]; then
        echo "✅ High diversity — good spread of sources"
      else
        echo "📊 Moderate diversity"
      fi
    fi
    ;;
    
  topics)
    # Extract non-agent research topics and check for clustering
    echo "=== Research Topic Analysis ==="
    grep -i "non-agent research" "$FILE" 2>/dev/null | \
      sed 's/.*Non-Agent Research: //' | \
      sed 's/.*non-agent research: //' | \
      while read -r topic; do
        echo "  • $topic"
      done
    
    echo ""
    echo "=== Topic Categories ==="
    BIOLOGY=$(grep -ic 'biology\|enzyme\|tardigrade\|mold\|fungi\|bioluminescence\|gut-brain\|serotonin\|mycorrhizal\|sourdough\|cyanobacteria' "$FILE" 2>/dev/null || echo 0)
    NEURO=$(grep -ic 'neuron\|synesthesia\|proprioception\|mirror neuron\|phantom limb\|sleep paralysis\|circadian\|diffuse\|focused' "$FILE" 2>/dev/null || echo 0)
    HISTORY=$(grep -ic 'medieval\|guild\|cartograph\|Mercator\|Grimm\|semaphore\|Prussian blue' "$FILE" 2>/dev/null || echo 0)
    PHYSICS=$(grep -ic 'quantum\|tunneling\|zircon\|fractal\|geological\|heat pump' "$FILE" 2>/dev/null || echo 0)
    MUSIC=$(grep -ic 'circle of fifths\|bouba\|kiki\|sound symbol\|temperament' "$FILE" 2>/dev/null || echo 0)
    
    echo "  Biology/ecology:  $BIOLOGY mentions"
    echo "  Neuroscience:     $NEURO mentions"  
    echo "  History/culture:  $HISTORY mentions"
    echo "  Physics/geology:  $PHYSICS mentions"
    echo "  Music/linguistics: $MUSIC mentions"
    ;;
    
  researchers)
    # Extract researcher names cited
    echo "=== Researchers Cited ==="
    grep -oP '[A-Z][a-z]+\s+(et al\.|&\s+[A-Z][a-z]+)' "$FILE" 2>/dev/null | \
      sort | uniq -c | sort -rn | head -20
    ;;
    
  report)
    echo "📊 Source Diversity Report for $FILE"
    echo "=================================="
    echo ""
    $0 domains "$FILE"
    echo ""
    $0 topics "$FILE"
    echo ""
    $0 researchers "$FILE"
    ;;
    
  *)
    echo "Usage: $0 {domains|topics|researchers|report} [file]"
    echo ""
    echo "Analyzes research source diversity to avoid echo chambers."
    echo "Checks domain concentration, topic clustering, and citation patterns."
    exit 1
    ;;
esac
