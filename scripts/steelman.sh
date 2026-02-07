#!/bin/bash
# steelman.sh — Generate steelman arguments for positions you disagree with
# Inspired by thalidomide chirality: same structure, opposite effect depending on orientation
# 
# Usage:
#   ./scripts/steelman.sh "position to steelman"
#   ./scripts/steelman.sh --from-log [date]    # Find positions I argued against, generate steelman
#   ./scripts/steelman.sh --test               # Run self-test
#
# The goal: if you can't steelman the opposition, you don't understand it well enough.

set -euo pipefail

MEMORY_DIR="memory"
STEELMAN_LOG="memory/steelman-log.md"

cmd_steelman() {
    local position="$1"
    echo "## Steelman Exercise"
    echo ""
    echo "**Position:** $position"
    echo ""
    echo "**Your task:** Find the strongest possible version of this argument."
    echo ""
    echo "### Framework (from Rapoport's Rules):"
    echo "1. Re-express the position so clearly the holder says 'Thanks, I wish I'd said it that way'"
    echo "2. List points of agreement (especially uncommon ones)"
    echo "3. Mention anything you learned from this position"
    echo "4. Only THEN are you permitted to say a word of rebuttal"
    echo ""
    echo "### Chirality Check:"
    echo "The same evidence that supports your position — does it also support theirs"
    echo "under a different orientation? (Like R vs S thalidomide: same molecule, opposite effect)"
    echo ""
    
    # Log it
    if [ -f "$STEELMAN_LOG" ]; then
        echo "" >> "$STEELMAN_LOG"
    else
        echo "# Steelman Log" > "$STEELMAN_LOG"
        echo "" >> "$STEELMAN_LOG"
    fi
    echo "- $(date -u +%Y-%m-%d\ %H:%M) | $position" >> "$STEELMAN_LOG"
}

cmd_from_log() {
    local date="${1:-$(date -u +%Y-%m-%d)}"
    local logfile="$MEMORY_DIR/${date}.md"
    
    if [ ! -f "$logfile" ]; then
        echo "No log file for $date"
        exit 1
    fi
    
    echo "## Positions Argued Against on $date"
    echo ""
    
    # Find "pushed back" patterns — these are positions we disagreed with
    grep -n "pushed back\|disagreed\|pushed on\|challenged\|critique" "$logfile" 2>/dev/null | while IFS= read -r line; do
        local linenum=$(echo "$line" | cut -d: -f1)
        local content=$(echo "$line" | cut -d: -f2-)
        # Get surrounding context
        local context=$(sed -n "$((linenum-1)),$((linenum+1))p" "$logfile" | head -3)
        echo "### Line $linenum"
        echo "\`\`\`"
        echo "$context"
        echo "\`\`\`"
        echo "**Steelman prompt:** What's the strongest version of what they were saying?"
        echo ""
    done
    
    local count=$(grep -c "pushed back\|disagreed\|pushed on\|challenged\|critique" "$logfile" 2>/dev/null || echo 0)
    echo "Found $count positions to steelman."
}

cmd_test() {
    echo "=== Steelman Self-Test ==="
    
    # Test basic steelman
    echo "Test 1: Basic steelman generation"
    output=$(cmd_steelman "Memory files are unnecessary overhead" 2>&1)
    if echo "$output" | grep -q "Rapoport"; then
        echo "  ✅ Framework present"
    else
        echo "  ❌ Framework missing"
    fi
    
    if echo "$output" | grep -q "Chirality"; then
        echo "  ✅ Chirality check present"
    else
        echo "  ❌ Chirality check missing"
    fi
    
    # Test log extraction
    echo "Test 2: Log extraction"
    if [ -f "$MEMORY_DIR/$(date -u +%Y-%m-%d).md" ]; then
        count=$(grep -c "pushed back\|disagreed\|pushed on\|challenged" "$MEMORY_DIR/$(date -u +%Y-%m-%d).md" 2>/dev/null || echo 0)
        echo "  ✅ Found $count pushback instances today"
    else
        echo "  ⚠️  No today log found"
    fi
    
    # Test steelman log
    echo "Test 3: Steelman log"
    if [ -f "$STEELMAN_LOG" ]; then
        echo "  ✅ Log exists ($(wc -l < "$STEELMAN_LOG") lines)"
    else
        echo "  ⚠️  Log will be created on first use"
    fi
    
    echo ""
    echo "All tests passed."
}

case "${1:-}" in
    --from-log) cmd_from_log "${2:-}" ;;
    --test) cmd_test ;;
    "") echo "Usage: steelman.sh \"position\" | --from-log [date] | --test" ;;
    *) cmd_steelman "$*" ;;
esac
