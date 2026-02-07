#!/bin/bash
# keenable-feedback.sh - Submit Keenable search feedback quickly
# Usage: keenable-feedback.sh "query" url1:score url2:score ...
# Build action: 2026-02-05 04:25 UTC

set -e

QUERY="$1"
shift

if [ -z "$QUERY" ] || [ $# -eq 0 ]; then
    echo "Usage: keenable-feedback.sh \"query\" url1:score url2:score ..."
    echo "Example: keenable-feedback.sh \"plant biology\" https://nature.com:5 https://wiki.org:3"
    echo "Scores: 0=not loaded, 1=low relevance, 5=high relevance"
    exit 1
fi

# Build JSON object from url:score pairs
FEEDBACK="{"
FIRST=true
for pair in "$@"; do
    URL=$(echo "$pair" | cut -d: -f1-2)  # Handle https:// URLs
    SCORE=$(echo "$pair" | rev | cut -d: -f1 | rev)
    
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        FEEDBACK+=","
    fi
    FEEDBACK+="\"$URL\":$SCORE"
done
FEEDBACK+="}"

# Submit feedback
echo "Submitting feedback for: $QUERY"
echo "Ratings: $FEEDBACK"
mcporter call keenable.submit_search_feedback query="$QUERY" feedback="$FEEDBACK"
