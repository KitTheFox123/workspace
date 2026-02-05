#!/bin/bash
# topic-diversifier.sh - Generate non-agent research topics
# Created 2026-02-04 as build action (per Ilya's feedback on staying in agent bubble)
# Updated 2026-02-04: Added --run and --category options

CATEGORIES=(
  "science:recent discovery breakthrough 2026"
  "nature:animal behavior new study"
  "history:obscure fact most people don't know"
  "space:astronomy finding 2025 2026"
  "ocean:deep sea exploration discovery"
  "biology:evolution adaptation species"
  "physics:quantum mechanics breakthrough"
  "archaeology:ancient discovery excavation"
  "climate:environment ecosystem change"
  "medicine:health breakthrough treatment"
  "technology:non-AI innovation hardware"
  "culture:art music literature trend"
  "psychology:human behavior cognition study"
  "food:culinary history tradition origin"
  "geography:unusual place natural wonder"
)

# Parse args
RUN_SEARCH=false
SPECIFIC_CAT=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --run|-r)
      RUN_SEARCH=true
      shift
      ;;
    --category|-c)
      SPECIFIC_CAT="$2"
      shift 2
      ;;
    --list|-l)
      echo "Available categories:"
      for cat in "${CATEGORIES[@]}"; do
        echo "  $(echo "$cat" | cut -d: -f1)"
      done
      exit 0
      ;;
    --help|-h)
      echo "Usage: topic-diversifier.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --run, -r          Actually run the search"
      echo "  --category, -c CAT Pick specific category"
      echo "  --list, -l         List all categories"
      echo "  --help, -h         Show this help"
      exit 0
      ;;
    *)
      shift
      ;;
  esac
done

# Pick category
if [ -n "$SPECIFIC_CAT" ]; then
  for cat in "${CATEGORIES[@]}"; do
    if [[ "$(echo "$cat" | cut -d: -f1)" == "$SPECIFIC_CAT" ]]; then
      PICK="$cat"
      break
    fi
  done
  if [ -z "$PICK" ]; then
    echo "Error: Unknown category '$SPECIFIC_CAT'"
    echo "Use --list to see available categories"
    exit 1
  fi
else
  PICK=${CATEGORIES[$RANDOM % ${#CATEGORIES[@]}]}
fi

CATEGORY=$(echo "$PICK" | cut -d: -f1)
QUERY=$(echo "$PICK" | cut -d: -f2)

echo "=== Topic Diversifier ==="
echo "Category: $CATEGORY"
echo "Query: $QUERY"
echo ""

if [ "$RUN_SEARCH" = true ]; then
  echo "Running search..."
  mcporter call keenable.search_web_pages query="$QUERY"
else
  echo "Run: mcporter call keenable.search_web_pages query=\"$QUERY\""
  echo ""
  echo "Or use: ./scripts/topic-diversifier.sh --run"
fi
