#!/bin/bash
# bias-lookup.sh - Quick reference for cognitive bias stats
# Created 2026-02-05

KNOWLEDGE_FILE="$HOME/.openclaw/workspace/knowledge/cognitive-psychology.md"

if [ -z "$1" ]; then
    echo "Usage: bias-lookup.sh <bias-name>"
    echo "Examples: anchoring, hindsight, survivorship, dunbar, decision-fatigue"
    echo ""
    echo "Available biases in knowledge base:"
    grep -E "^## " "$KNOWLEDGE_FILE" | sed 's/## /  - /' | head -20
    exit 0
fi

BIAS="$1"

# Case-insensitive search for section
echo "=== $BIAS ==="
echo ""

# Extract section between ## headers
awk -v bias="$BIAS" '
    BEGIN { IGNORECASE=1; printing=0 }
    /^## / { 
        if (printing) exit
        if (tolower($0) ~ tolower(bias)) printing=1 
    }
    printing { print }
' "$KNOWLEDGE_FILE"

if [ $? -ne 0 ] || [ -z "$(awk -v bias="$BIAS" 'BEGIN{IGNORECASE=1} /^## / && tolower($0) ~ tolower(bias) {print; exit}' "$KNOWLEDGE_FILE")" ]; then
    echo "Bias '$BIAS' not found in knowledge base."
    echo "Try: anchoring, hindsight, survivorship, dunbar, peak-end, mere-exposure, decision-fatigue"
fi
