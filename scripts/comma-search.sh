#!/bin/bash
# comma-search.sh - Search CoMMA medieval manuscripts corpus
# Usage: ./comma-search.sh "search term"
#
# CoMMA API: https://comma.inria.fr
# Hugging Face: https://huggingface.co/comma-project

QUERY="${1:-}"

if [ -z "$QUERY" ]; then
    echo "Usage: $0 <search-term>"
    echo ""
    echo "Search the CoMMA corpus of 32,763 medieval manuscripts."
    echo "Supports Latin and Old French texts from 8th-16th century."
    echo ""
    echo "Example: $0 'rex arturus' # Find Arthur references"
    exit 1
fi

echo "=== CoMMA Search: $QUERY ==="
echo ""

# The CoMMA interface uses a browsable index
# For programmatic access, the corpus is on Hugging Face
echo "Note: CoMMA is browsable at https://comma.inria.fr/homepage"
echo "Dataset: https://huggingface.co/comma-project"
echo ""
echo "For full-text search, use the web interface or download the dataset."
