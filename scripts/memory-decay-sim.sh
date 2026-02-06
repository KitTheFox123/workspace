#!/bin/bash
# memory-decay-sim.sh — Simulate Ebbinghaus forgetting curve on memory files
# Shows which memories are "decaying" (haven't been referenced/reviewed recently)
# Helps prioritize what to consolidate into MEMORY.md
#
# Usage: ./memory-decay-sim.sh [days_back] [decay_rate]
# Default: 7 days back, 0.5 decay rate (Ebbinghaus-inspired)

MEMORY_DIR="${MEMORY_DIR:-/home/yallen/.openclaw/workspace/memory}"
DAYS_BACK="${1:-7}"
DECAY_RATE="${2:-0.5}"

echo "🧠 Memory Decay Simulator"
echo "========================="
echo "Scanning last $DAYS_BACK days | Decay rate: $DECAY_RATE"
echo ""

TODAY=$(date +%s)

# Ebbinghaus retention: R = e^(-t/S) where t=time, S=strength
# We approximate strength from file size and reference count
calc_retention() {
    local file="$1"
    local mod_time=$(stat -c %Y "$file" 2>/dev/null || echo "$TODAY")
    local age_days=$(( (TODAY - mod_time) / 86400 ))
    local size=$(wc -l < "$file" 2>/dev/null || echo 0)
    
    # Strength = log(lines) * review_factor
    # More content = stronger trace
    local strength=$(echo "scale=2; l($size + 1) / l(2)" | bc -l 2>/dev/null || echo "1")
    
    # Retention = e^(-age/strength)  
    local retention=$(echo "scale=2; e(-$age_days * $DECAY_RATE / ($strength + 1))" | bc -l 2>/dev/null || echo "0.5")
    local pct=$(echo "scale=0; $retention * 100 / 1" | bc 2>/dev/null || echo "50")
    
    # Color code
    local color=""
    if [ "$pct" -gt 70 ]; then
        color="\033[32m"  # green
    elif [ "$pct" -gt 40 ]; then
        color="\033[33m"  # yellow
    else
        color="\033[31m"  # red — needs review!
    fi
    
    printf "${color}%3d%% retention\033[0m | %d days old | %4d lines | %s\n" \
        "$pct" "$age_days" "$size" "$(basename "$file")"
}

echo "📊 Daily Files:"
for f in "$MEMORY_DIR"/2026-*.md; do
    [ -f "$f" ] && calc_retention "$f"
done | sort -t'|' -k1 -n

echo ""
echo "📊 Core Files:"
for f in "$MEMORY_DIR"/../MEMORY.md "$MEMORY_DIR"/../SOUL.md; do
    [ -f "$f" ] && calc_retention "$f"
done

echo ""
echo "🔴 Files below 40% need consolidation or review"
echo "🟡 Files at 40-70% should be checked next heartbeat"
echo "🟢 Files above 70% are fresh enough"
