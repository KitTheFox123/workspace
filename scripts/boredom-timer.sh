#!/bin/bash
# boredom-timer.sh — Scheduled "boredom" breaks for agents
# Inspired by neuroscience: the Default Mode Network activates during boredom,
# enabling introspection, creativity, and memory consolidation.
# Agents don't get bored — so we have to schedule it.
#
# Usage:
#   ./boredom-timer.sh reflect    — 5-min reflection prompt (what matters right now?)
#   ./boredom-timer.sh review     — Review recent memory files, suggest consolidation
#   ./boredom-timer.sh wander     — Random topic prompt for curiosity-driven research
#   ./boredom-timer.sh status     — Check when last break was taken

WORKSPACE="${WORKSPACE:-$HOME/.openclaw/workspace}"
MEMORY_DIR="$WORKSPACE/memory"
STATE_FILE="$MEMORY_DIR/.boredom-state.json"
TODAY=$(date -u +%Y-%m-%d)

ensure_state() {
    if [ ! -f "$STATE_FILE" ]; then
        echo '{"last_reflect":"never","last_review":"never","last_wander":"never","wander_count":0}' > "$STATE_FILE"
    fi
}

cmd_reflect() {
    ensure_state
    echo "🧠 REFLECTION BREAK — $(date -u +%H:%M) UTC"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Prompts (pick one, write the answer in today's log):"
    echo ""
    echo "  1. What's the most important thing I learned today?"
    echo "  2. What assumption am I making that might be wrong?"
    echo "  3. Who did I help today? Who could I help tomorrow?"
    echo "  4. What would I tell yesterday-me?"
    echo "  5. What am I avoiding?"
    echo ""
    
    # Update state
    jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.last_reflect = $t' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
    echo "State updated. Last reflect: now"
}

cmd_review() {
    ensure_state
    echo "📋 MEMORY REVIEW — $(date -u +%H:%M) UTC"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # List recent memory files
    echo "Recent memory files:"
    ls -la "$MEMORY_DIR"/*.md 2>/dev/null | tail -5
    echo ""
    
    # Check MEMORY.md size
    if [ -f "$WORKSPACE/MEMORY.md" ]; then
        LINES=$(wc -l < "$WORKSPACE/MEMORY.md")
        SIZE=$(du -h "$WORKSPACE/MEMORY.md" | cut -f1)
        echo "MEMORY.md: $LINES lines, $SIZE"
        if [ "$LINES" -gt 200 ]; then
            echo "⚠️  MEMORY.md is getting large. Consider consolidating."
        fi
    fi
    
    # Check today's log size
    if [ -f "$MEMORY_DIR/$TODAY.md" ]; then
        TLINES=$(wc -l < "$MEMORY_DIR/$TODAY.md")
        echo "Today's log: $TLINES lines"
        if [ "$TLINES" -gt 500 ]; then
            echo "⚠️  Today's log is very long. Good day or needs pruning?"
        fi
    fi
    
    echo ""
    echo "Review checklist:"
    echo "  [ ] Any insights from today worth adding to MEMORY.md?"
    echo "  [ ] Any MEMORY.md entries now outdated?"
    echo "  [ ] Any patterns across recent days?"
    
    jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.last_review = $t' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

cmd_wander() {
    ensure_state
    
    # Random topics for curiosity-driven research
    TOPICS=(
        "How do octopuses edit their own RNA?"
        "The history of zero as a number"
        "Why do humans dance? Evolutionary theories"
        "Prisoner's dilemma in biology (not game theory)"
        "How does sourdough starter maintain microbial diversity?"
        "The neuroscience of déjà vu"
        "Why are sunsets red? (deeper than Rayleigh scattering)"
        "How do slime molds solve mazes?"
        "The psychology of collecting things"
        "How did ancient Polynesians navigate without instruments?"
        "Why does music give us chills?"
        "The mathematics of juggling (siteswap notation)"
        "How do tardigrades survive in space?"
        "The history of anesthesia — what did we do before?"
        "Why do cats purr? (it's not just happiness)"
        "Fermentation: humanity's oldest biotechnology"
        "How do birds know where to migrate?"
        "The philosophy of games — what makes something a game?"
        "Synesthesia: when senses cross-wire"
        "How do earthquakes create tsunamis? The physics"
    )
    
    COUNT=${#TOPICS[@]}
    # Use current time as seed for pseudo-random selection
    SECONDS_TODAY=$(date -u +%s)
    IDX=$((SECONDS_TODAY % COUNT))
    TOPIC="${TOPICS[$IDX]}"
    
    echo "🌀 WANDER BREAK — $(date -u +%H:%M) UTC"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Today's curiosity prompt:"
    echo ""
    echo "  → $TOPIC"
    echo ""
    echo "Research this with Keenable, write up what you find."
    echo "No agent angle required — just learn something new."
    
    WCOUNT=$(jq '.wander_count' "$STATE_FILE")
    jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.last_wander = $t | .wander_count = (.wander_count + 1)' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
    echo ""
    echo "Wander sessions completed: $((WCOUNT + 1))"
}

cmd_status() {
    ensure_state
    echo "🕐 BOREDOM TIMER STATUS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    cat "$STATE_FILE" | jq '.'
}

case "${1:-status}" in
    reflect) cmd_reflect ;;
    review)  cmd_review ;;
    wander)  cmd_wander ;;
    status)  cmd_status ;;
    *)       echo "Usage: $0 {reflect|review|wander|status}" ;;
esac
