#!/bin/bash
# etymology-chain.sh — Trace word evolution across languages
# Shows how concepts travel through linguistic borrowing chains
# Build action for heartbeat ~14:30 UTC 2026-02-07

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KNOWLEDGE_DIR="$SCRIPT_DIR/../knowledge"

usage() {
    cat <<EOF
Usage: etymology-chain.sh <command> [args]

Commands:
  trace <word>     Search for etymology of a word (requires Keenable)
  chain <file>     Parse an etymology file and show borrowing chain
  stats            Show language family distribution from saved etymologies
  quiz             Generate a random etymology quiz from saved data
  add <word> <chain>  Manually add an etymology chain

Chain format: "latin:focus > french:focus > english:focus"
EOF
    exit 1
}

ETYM_FILE="$KNOWLEDGE_DIR/etymologies.md"

ensure_file() {
    mkdir -p "$KNOWLEDGE_DIR"
    if [[ ! -f "$ETYM_FILE" ]]; then
        cat > "$ETYM_FILE" <<'HEADER'
# Etymology Chains

Tracking word origins and borrowing paths across languages.

| Word | Chain | Category |
|------|-------|----------|
HEADER
    fi
}

cmd_add() {
    local word="${1:?word required}"
    shift
    local chain="$*"
    local category="general"
    
    # Detect category from chain
    if echo "$chain" | grep -qi "arabic\|persian\|turkish\|hindi"; then
        category="eastern"
    elif echo "$chain" | grep -qi "greek\|latin"; then
        category="classical"
    elif echo "$chain" | grep -qi "proto-germanic\|old.english\|norse"; then
        category="germanic"
    elif echo "$chain" | grep -qi "japanese\|chinese\|korean"; then
        category="cjk"
    fi
    
    ensure_file
    echo "| $word | $chain | $category |" >> "$ETYM_FILE"
    echo "✅ Added: $word ($category)"
}

cmd_stats() {
    ensure_file
    echo "=== Etymology Stats ==="
    echo ""
    echo "Total entries: $(grep -c '^|' "$ETYM_FILE" | tail -1)"
    echo ""
    echo "By category:"
    grep '^|' "$ETYM_FILE" | tail -n+3 | awk -F'|' '{print $4}' | sort | uniq -c | sort -rn
    echo ""
    echo "Languages mentioned:"
    grep '^|' "$ETYM_FILE" | tail -n+3 | awk -F'|' '{print $3}' | \
        grep -oP '[a-z]+(?=:)' | sort | uniq -c | sort -rn | head -15
}

cmd_quiz() {
    ensure_file
    local count=$(grep -c '^| ' "$ETYM_FILE" 2>/dev/null || echo 0)
    if [[ $count -lt 3 ]]; then
        echo "Need at least 3 entries for a quiz. Add more with 'add' command."
        exit 1
    fi
    
    local line=$(grep '^| ' "$ETYM_FILE" | tail -n+1 | shuf -n1)
    local word=$(echo "$line" | awk -F'|' '{print $2}' | xargs)
    local chain=$(echo "$line" | awk -F'|' '{print $3}' | xargs)
    
    echo "🎓 Etymology Quiz"
    echo "=================="
    echo ""
    echo "What is the origin chain of: $word"
    echo ""
    echo "(Think about it...)"
    echo ""
    read -p "Press Enter to reveal..." -r
    echo ""
    echo "Answer: $chain"
}

cmd_chain() {
    local input="$*"
    echo "=== Borrowing Chain ==="
    echo ""
    
    # Parse chain format: "lang:word > lang:word > lang:word"
    IFS='>' read -ra segments <<< "$input"
    local depth=0
    for seg in "${segments[@]}"; do
        seg=$(echo "$seg" | xargs)
        local lang=$(echo "$seg" | cut -d: -f1)
        local word=$(echo "$seg" | cut -d: -f2)
        local indent=""
        for ((i=0; i<depth; i++)); do indent+="  "; done
        echo "${indent}└─ [$lang] $word"
        ((depth++))
    done
    echo ""
    echo "Depth: $depth languages"
}

cmd_seed() {
    ensure_file
    echo "Seeding with common cross-linguistic borrowings..."
    
    cmd_add "algorithm" "persian:al-khwarizmi > arabic:al-khwarizmi > medieval-latin:algorismus > english:algorithm"
    cmd_add "sugar" "sanskrit:sharkara > arabic:sukkar > medieval-latin:succarum > old-french:sucre > english:sugar"
    cmd_add "tsunami" "japanese:津波(tsu-nami) > english:tsunami"
    cmd_add "algebra" "arabic:al-jabr > medieval-latin:algebra > english:algebra"
    cmd_add "orange" "sanskrit:naranga > persian:narang > arabic:naranj > spanish:naranja > old-french:orenge > english:orange"
    cmd_add "typhoon" "chinese:大風(tai-fung) > arabic:tufan > portuguese:tufão > english:typhoon"
    cmd_add "zero" "sanskrit:shunya > arabic:sifr > medieval-latin:zephirum > italian:zero > english:zero"
    cmd_add "chess" "sanskrit:chaturanga > persian:shatranj > arabic:shatranj > old-french:esches > english:chess"
    cmd_add "robot" "czech:robota(forced-labor) > czech:robot(Čapek-1920) > english:robot"
    cmd_add "ketchup" "hokkien:kê-tsiap > malay:kecap > english:ketchup"
    
    echo ""
    echo "✅ Seeded 10 entries"
}

case "${1:-}" in
    trace) shift; echo "Use Keenable: mcporter call keenable.search_web_pages query=\"etymology $*\""; ;;
    chain) shift; cmd_chain "$@" ;;
    stats) cmd_stats ;;
    quiz) cmd_quiz ;;
    add) shift; cmd_add "$@" ;;
    seed) cmd_seed ;;
    *) usage ;;
esac
