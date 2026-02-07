#!/bin/bash
# diversity-checker.sh — Check information source diversity in multi-agent decisions
# Inspired by Orzechowski et al. (2025): correlated info sources kill collective wisdom
# Usage: ./diversity-checker.sh <mode> [args]
#   sources <file>  — Analyze source URLs in a file for domain overlap
#   memory          — Check memory files for source diversity
#   score           — Rate a set of URLs for independence

set -euo pipefail

MODE="${1:-help}"

color_green="\033[0;32m"
color_yellow="\033[0;33m"
color_red="\033[0;31m"
color_reset="\033[0m"

case "$MODE" in
  sources)
    FILE="${2:?Usage: diversity-checker.sh sources <file>}"
    if [[ ! -f "$FILE" ]]; then
      echo "File not found: $FILE"
      exit 1
    fi
    
    echo "=== Source Diversity Analysis ==="
    echo "File: $FILE"
    echo ""
    
    # Extract URLs
    urls=$(grep -oP 'https?://[^\s\)\]\"]+' "$FILE" 2>/dev/null || true)
    total=$(echo "$urls" | grep -c . || echo 0)
    
    if [[ "$total" -eq 0 ]]; then
      echo "No URLs found in file."
      exit 0
    fi
    
    # Extract domains
    domains=$(echo "$urls" | sed 's|https\?://\([^/]*\).*|\1|' | sort)
    unique_domains=$(echo "$domains" | sort -u | wc -l)
    
    echo "Total URLs: $total"
    echo "Unique domains: $unique_domains"
    echo ""
    
    # Domain frequency
    echo "--- Domain Distribution ---"
    echo "$domains" | sort | uniq -c | sort -rn | head -20
    echo ""
    
    # Diversity score (0-100)
    if [[ "$total" -gt 0 ]]; then
      score=$(( unique_domains * 100 / total ))
      if [[ "$score" -gt 70 ]]; then
        echo -e "${color_green}Diversity Score: ${score}/100 (HIGH)${color_reset}"
        echo "Good source independence. Condorcet approves."
      elif [[ "$score" -gt 40 ]]; then
        echo -e "${color_yellow}Diversity Score: ${score}/100 (MEDIUM)${color_reset}"
        echo "Some correlation risk. Consider broadening sources."
      else
        echo -e "${color_red}Diversity Score: ${score}/100 (LOW)${color_reset}"
        echo "⚠️ High correlation! Orzechowski et al. warns: correlated sources = worse collective decisions."
      fi
    fi
    ;;
    
  memory)
    MEMORY_DIR="${2:-$HOME/.openclaw/workspace/memory}"
    echo "=== Memory Source Diversity ==="
    echo "Scanning: $MEMORY_DIR"
    echo ""
    
    all_urls=""
    for f in "$MEMORY_DIR"/*.md; do
      [[ -f "$f" ]] || continue
      file_urls=$(grep -oP 'https?://[^\s\)\]\"]+' "$f" 2>/dev/null || true)
      count=$(echo "$file_urls" | grep -c . || echo 0)
      basename=$(basename "$f")
      echo "  $basename: $count URLs"
      all_urls="$all_urls"$'\n'"$file_urls"
    done
    
    echo ""
    total=$(echo "$all_urls" | grep -c . || echo 0)
    unique=$(echo "$all_urls" | sed 's|https\?://\([^/]*\).*|\1|' | sort -u | grep -c . || echo 0)
    echo "Total URLs across all files: $total"
    echo "Unique domains: $unique"
    
    if [[ "$total" -gt 0 ]]; then
      score=$(( unique * 100 / total ))
      echo ""
      echo "Overall diversity: ${score}/100"
      echo ""
      echo "Top domains:"
      echo "$all_urls" | sed 's|https\?://\([^/]*\).*|\1|' | sort | uniq -c | sort -rn | head -10
    fi
    ;;
    
  score)
    shift
    echo "=== URL Independence Score ==="
    domains=""
    for url in "$@"; do
      domain=$(echo "$url" | sed 's|https\?://\([^/]*\).*|\1|')
      echo "  $url → $domain"
      domains="$domains"$'\n'"$domain"
    done
    
    total=$#
    unique=$(echo "$domains" | sort -u | grep -c . || echo 0)
    
    if [[ "$total" -gt 0 ]]; then
      score=$(( unique * 100 / total ))
      echo ""
      echo "Independence: ${score}% ($unique unique of $total)"
      
      if [[ "$score" -lt 50 ]]; then
        echo "⚠️ High correlation risk — diversify your sources!"
      fi
    fi
    ;;
    
  help|*)
    echo "diversity-checker.sh — Detect correlated information sources"
    echo ""
    echo "Based on Orzechowski et al. (2025, Scientific Reports):"
    echo "  Collective accuracy DECREASES when decision-makers share"
    echo "  correlated information sources. Independence > group size."
    echo ""
    echo "Usage:"
    echo "  sources <file>   Analyze URLs in a file for domain diversity"
    echo "  memory [dir]     Check memory files for source diversity"
    echo "  score <urls...>  Rate a set of URLs for independence"
    ;;
esac
