#!/bin/bash
# memory-confidence.sh - Score memory entries by source confidence
# Inspired by "Beyond Flat Files" post on Moltbook
# Usage: memory-confidence.sh <file> [--decay] [--prune threshold]

set -e

FILE="${1:-/home/yallen/.openclaw/workspace/MEMORY.md}"
DECAY=${2:-false}
PRUNE_THRESHOLD=${3:-0}

# Source confidence tiers
# Tier 1 (1.0): Direct experience - things I did/saw/built
# Tier 2 (0.8): First-hand conversation - someone told me directly  
# Tier 3 (0.6): Researched - Keenable/web search with source
# Tier 4 (0.4): Second-hand - heard from community, unverified
# Tier 5 (0.2): Scraped/generated - no clear source

score_line() {
    local line="$1"
    local score=0.6  # default: researched
    
    # Direct experience markers
    if echo "$line" | grep -qiE "(I built|I created|I ran|I tested|my script|my post|I replied|I commented)"; then
        score=1.0
    # Conversation markers
    elif echo "$line" | grep -qiE "(told me|said|asked|replied to me|DM from|email from)"; then
        score=0.8
    # Research with source
    elif echo "$line" | grep -qiE "(from .*(paper|study|article|PMC|arXiv)|research:|fetched|searched)"; then
        score=0.6
    # Community/hearsay
    elif echo "$line" | grep -qiE "(apparently|someone mentioned|I heard|community|rumor)"; then
        score=0.4
    # No source
    elif echo "$line" | grep -qiE "(maybe|possibly|might be|not sure|unclear)"; then
        score=0.2
    fi
    
    echo "$score"
}

# Age decay: reduce confidence by 0.05 per day
age_decay() {
    local file_date="$1"
    local base_score="$2"
    local today=$(date +%s)
    local file_epoch=$(date -d "$file_date" +%s 2>/dev/null || echo "$today")
    local days=$(( (today - file_epoch) / 86400 ))
    local decay=$(echo "$days * 0.05" | bc)
    local final=$(echo "$base_score - $decay" | bc)
    
    # Floor at 0.1
    if (( $(echo "$final < 0.1" | bc -l) )); then
        final=0.1
    fi
    echo "$final"
}

echo "=== Memory Confidence Scorer ==="
echo "File: $FILE"
echo "---"

if [ ! -f "$FILE" ]; then
    echo "File not found: $FILE"
    exit 1
fi

total=0
high=0
medium=0
low=0

while IFS= read -r line; do
    # Skip empty lines and headers
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^#+ ]] && continue
    [[ "$line" =~ ^--- ]] && continue
    [[ "$line" =~ ^\*  ]] && continue
    
    score=$(score_line "$line")
    total=$((total + 1))
    
    if (( $(echo "$score >= 0.8" | bc -l) )); then
        high=$((high + 1))
    elif (( $(echo "$score >= 0.5" | bc -l) )); then
        medium=$((medium + 1))
    else
        low=$((low + 1))
    fi
done < "$FILE"

echo "Total scorable lines: $total"
echo "High confidence (0.8+): $high"
echo "Medium confidence (0.5-0.8): $medium"  
echo "Low confidence (<0.5): $low"
echo ""
echo "Confidence ratio: $(echo "scale=2; $high * 100 / $total" | bc)% high"
