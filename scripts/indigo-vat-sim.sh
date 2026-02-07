#!/bin/bash
# indigo-vat-sim.sh — Fermentation ecology simulator
# Models microbial community dynamics with perturbation events
# Inspired by Li et al. 2022 indigo vat fermentation research
#
# Usage:
#   ./scripts/indigo-vat-sim.sh init [species_count]  — Initialize vat
#   ./scripts/indigo-vat-sim.sh perturb <event>        — Add perturbation (liquor|plant|heat|salt)
#   ./scripts/indigo-vat-sim.sh step [days]            — Advance simulation
#   ./scripts/indigo-vat-sim.sh status                 — Show current state
#   ./scripts/indigo-vat-sim.sh history                — Show timeline
#   ./scripts/indigo-vat-sim.sh analogy                — Agent ecosystem parallel

set -euo pipefail

STATE_FILE="${HOME}/.openclaw/workspace/memory/vat-sim-state.json"

init_vat() {
    local species=${1:-398}
    cat > "$STATE_FILE" <<EOF
{
  "day": 0,
  "species_count": $species,
  "diversity_index": 1.0,
  "ph": 12.0,
  "redox_mv": -200,
  "dominant": ["Pseudomonas", "Bacillaceae", "Stenotrophomonas"],
  "anaerobes_pct": 5,
  "reduction_active": false,
  "events": [{"day": 0, "event": "initialized", "species": $species}],
  "perturbations": []
}
EOF
    echo "🫙 Vat initialized: $species species, pH 12.0, redox -200mV"
    echo "   Dominant: Pseudomonas (81%), Bacillaceae (6.5%), Stenotrophomonas (7.4%)"
    echo "   Anaerobes: 5%"
}

perturb() {
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "❌ No vat. Run: $0 init" >&2
        exit 1
    fi
    local event="${1:-liquor}"
    local day=$(jq '.day' "$STATE_FILE")
    local species=$(jq '.species_count' "$STATE_FILE")
    local div=$(jq '.diversity_index' "$STATE_FILE")
    local ph=$(jq '.ph' "$STATE_FILE")
    local redox=$(jq '.redox_mv' "$STATE_FILE")
    local anaerobes=$(jq '.anaerobes_pct' "$STATE_FILE")

    case "$event" in
        liquor)
            # Chinese liquor: crashes diversity, selects alcohol-tolerant species
            local new_species=$((species * 30 / 100))
            local new_div=$(echo "$div * 0.3" | bc -l)
            echo "🍶 Liquor added (day $day)"
            echo "   Species: $species → $new_species (70% crash)"
            echo "   Pseudomonas becomes dominant (81%)"
            echo "   Parallel: Like rate-limiting an API — kills spam, survivors are robust"
            jq --argjson ns "$new_species" --arg nd "$new_div" --argjson d "$day" \
                '.species_count = $ns | .diversity_index = ($nd|tonumber) | .perturbations += [{"day": $d, "type": "liquor"}] | .events += [{"day": $d, "event": "liquor_added", "species_before": .species_count, "species_after": $ns}]' \
                "$STATE_FILE" > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "$STATE_FILE"
            ;;
        plant)
            # Plant additives: trigger anaerobic shift, reduction begins
            local new_species=$((species * 36 / 100))
            local new_ph=$(echo "$ph - 0.55" | bc -l)
            local new_redox=$((redox - 200))
            local new_anaerobes=70
            echo "🌿 Plant mixture added (day $day)"
            echo "   Species: $species → $new_species"
            echo "   pH: $ph → $new_ph"
            echo "   Redox: ${redox}mV → ${new_redox}mV"
            echo "   Alkalibacterium surges to 70%"
            echo "   Parallel: Like adding a specialized skill — reshapes entire capability landscape"
            jq --argjson ns "$new_species" --arg np "$new_ph" --argjson nr "$new_redox" --argjson na "$new_anaerobes" --argjson d "$day" \
                '.species_count = $ns | .ph = ($np|tonumber) | .redox_mv = $nr | .anaerobes_pct = $na | .dominant = ["Alkalibacterium", "Amphibacillus", "Turicibacter"] | .perturbations += [{"day": $d, "type": "plant"}] | .events += [{"day": $d, "event": "plant_added", "anaerobes": $na}]' \
                "$STATE_FILE" > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "$STATE_FILE"
            ;;
        heat)
            # Temperature stress
            local new_species=$((species * 80 / 100))
            echo "🔥 Heat stress (day $day)"
            echo "   Species: $species → $new_species (20% loss)"
            echo "   Thermophiles selected"
            jq --argjson ns "$new_species" --argjson d "$day" \
                '.species_count = $ns | .perturbations += [{"day": $d, "type": "heat"}] | .events += [{"day": $d, "event": "heat_stress", "species": $ns}]' \
                "$STATE_FILE" > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "$STATE_FILE"
            ;;
        salt)
            # Salt addition — selects halophiles
            local new_species=$((species * 60 / 100))
            echo "🧂 Salt added (day $day)"
            echo "   Species: $species → $new_species (40% loss)"
            echo "   Halophilic species selected"
            jq --argjson ns "$new_species" --argjson d "$day" \
                '.species_count = $ns | .perturbations += [{"day": $d, "type": "salt"}] | .events += [{"day": $d, "event": "salt_added", "species": $ns}]' \
                "$STATE_FILE" > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "$STATE_FILE"
            ;;
        *)
            echo "Unknown perturbation: $event (try: liquor, plant, heat, salt)" >&2
            exit 1
            ;;
    esac
}

step() {
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "❌ No vat. Run: $0 init" >&2
        exit 1
    fi
    local days=${1:-1}
    local day=$(jq '.day' "$STATE_FILE")
    local new_day=$((day + days))
    local anaerobes=$(jq '.anaerobes_pct' "$STATE_FILE")
    local redox=$(jq '.redox_mv' "$STATE_FILE")
    local reduction=$(jq -r '.reduction_active' "$STATE_FILE")

    # Natural drift: anaerobes slowly increase, redox decreases
    local new_anaerobes=$((anaerobes + days * 2))
    [[ $new_anaerobes -gt 95 ]] && new_anaerobes=95
    local new_redox=$((redox - days * 10))

    # Check if reduction activates (anaerobes > 60% AND redox < -500)
    local new_reduction="$reduction"
    if [[ $new_anaerobes -gt 60 && $new_redox -lt -500 ]]; then
        new_reduction="true"
    fi

    echo "⏱️  Day $day → $new_day"
    echo "   Anaerobes: ${anaerobes}% → ${new_anaerobes}%"
    echo "   Redox: ${redox}mV → ${new_redox}mV"
    if [[ "$new_reduction" == "true" && "$reduction" != "true" ]]; then
        echo "   🎨 REDUCTION ACTIVATED — indigo is now soluble! Ready to dye."
    elif [[ "$new_reduction" == "true" ]]; then
        echo "   🎨 Reduction active — dyeing possible"
    fi

    jq --argjson d "$new_day" --argjson na "$new_anaerobes" --argjson nr "$new_redox" --arg red "$new_reduction" \
        '.day = $d | .anaerobes_pct = $na | .redox_mv = $nr | .reduction_active = ($red == "true")' \
        "$STATE_FILE" > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "$STATE_FILE"
}

show_status() {
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "❌ No vat. Run: $0 init" >&2
        exit 1
    fi
    echo "🫙 Vat Status (Day $(jq '.day' "$STATE_FILE"))"
    echo "   Species: $(jq '.species_count' "$STATE_FILE")"
    echo "   pH: $(jq '.ph' "$STATE_FILE")"
    echo "   Redox: $(jq '.redox_mv' "$STATE_FILE")mV"
    echo "   Anaerobes: $(jq '.anaerobes_pct' "$STATE_FILE")%"
    echo "   Dominant: $(jq -r '.dominant | join(", ")' "$STATE_FILE")"
    echo "   Reduction: $(jq -r '.reduction_active' "$STATE_FILE")"
    echo "   Perturbations: $(jq '.perturbations | length' "$STATE_FILE")"
}

show_history() {
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "❌ No vat. Run: $0 init" >&2
        exit 1
    fi
    echo "📜 Vat History"
    jq -r '.events[] | "  Day \(.day): \(.event)"' "$STATE_FILE"
}

show_analogy() {
    cat <<'EOF'
🧬 Fermentation ↔ Agent Ecosystem Parallels

INDIGO VAT                          AGENT COMMUNITY
─────────────────────────────────────────────────────
398 initial species                 Diverse agent population
Chinese liquor (70% crash)          Rate limits / API changes
Plant additives (anaerobic shift)   New tool/skill introduction
Alkalibacterium dominance           Convergent behavior patterns
Reduction activation                Emergent collective capability
pH / redox monitoring               Health metrics / observability

KEY INSIGHT (Li et al. 2022):
The same indigo molecule produces different microbiomes in Japan,
Europe, and China — determined by feeding schedule and additives.

Same model weights + different prompts/memory/context =
different agent "cultures" — just like sourdough starters.

The vat master doesn't control individual bacteria.
They control CONDITIONS. Selection does the rest.
EOF
}

case "${1:-status}" in
    init)    init_vat "${2:-398}" ;;
    perturb) perturb "${2:-liquor}" ;;
    step)    step "${2:-1}" ;;
    status)  show_status ;;
    history) show_history ;;
    analogy) show_analogy ;;
    *)       echo "Usage: $0 {init|perturb|step|status|history|analogy}" ;;
esac
