#!/bin/bash
# woad-vat-sim.sh — Fermentation vat simulator (inspired by medieval woad dyeing)
# Models the multi-stage process of indigo extraction as an analogy for knowledge curation
# Usage: ./scripts/woad-vat-sim.sh [harvest|ferment|dye|status|analogy]

set -euo pipefail

VAT_FILE="${HOME}/.openclaw/workspace/memory/.woad-vat-state.json"

init_vat() {
  jq -n '{
    stage: "empty",
    leaves_kg: 0,
    indigotin_ppm: 0,
    ph: 7.0,
    temperature_c: 20,
    fermentation_days: 0,
    water_hardness: "soft",
    dips_completed: 0,
    color_depth: 0,
    history: [],
    created: now | todate
  }' > "$VAT_FILE"
  echo "🫙 New vat initialized"
}

harvest() {
  local kg="${1:-1.0}"
  [[ ! -f "$VAT_FILE" ]] && init_vat
  
  local state=$(cat "$VAT_FILE")
  local current_stage=$(echo "$state" | jq -r '.stage')
  
  if [[ "$current_stage" != "empty" && "$current_stage" != "harvested" ]]; then
    echo "❌ Can't harvest into a vat that's already fermenting/ready"
    return 1
  fi
  
  # Indigotin concentration varies: woad ~0.2-0.5%, indigo plant ~2-4%
  local ppm=$(echo "$kg * 3500" | bc -l | xargs printf "%.0f")
  
  echo "$state" | jq --arg kg "$kg" --arg ppm "$ppm" '
    .stage = "harvested" |
    .leaves_kg = (.leaves_kg + ($kg | tonumber)) |
    .indigotin_ppm = (.indigotin_ppm + ($ppm | tonumber)) |
    .history += [{ action: "harvest", kg: ($kg | tonumber), time: (now | todate) }]
  ' > "$VAT_FILE"
  
  echo "🌿 Harvested ${kg}kg of woad leaves (~${ppm} ppm indigotin)"
  echo "   Historical note: 200g fresh leaves = enough for ~100g of yarn"
}

ferment() {
  [[ ! -f "$VAT_FILE" ]] && { echo "❌ No vat. Run: harvest first"; return 1; }
  
  local state=$(cat "$VAT_FILE")
  local stage=$(echo "$state" | jq -r '.stage')
  
  if [[ "$stage" == "empty" ]]; then
    echo "❌ Nothing to ferment. Harvest leaves first."
    return 1
  fi
  
  local days=$(echo "$state" | jq '.fermentation_days')
  local new_days=$((days + 7))
  
  # pH drops during fermentation (alkaline needed for reduction)
  # Optimal: 63 days (9 weeks) per medieval sources
  local progress=$((new_days * 100 / 63))
  [[ $progress -gt 100 ]] && progress=100
  
  # Indigotin concentration peaks around week 6, then stabilizes
  local ppm=$(echo "$state" | jq '.indigotin_ppm')
  local efficiency
  if (( new_days < 42 )); then
    efficiency=$(echo "scale=2; $new_days / 63 * 100" | bc)
  else
    efficiency="95"
  fi
  
  local new_stage="fermenting"
  [[ $new_days -ge 63 ]] && new_stage="ready"
  
  echo "$state" | jq --arg days "$new_days" --arg stage "$new_stage" --arg eff "$efficiency" '
    .stage = $stage |
    .fermentation_days = ($days | tonumber) |
    .ph = (if ($days | tonumber) < 21 then 5.5 elif ($days | tonumber) < 42 then 6.8 else 8.2 end) |
    .temperature_c = (if ($days | tonumber) < 21 then 35 elif ($days | tonumber) < 42 then 40 else 30 end) |
    .history += [{ action: "ferment", days: ($days | tonumber), efficiency: $eff, time: (now | todate) }]
  ' > "$VAT_FILE"
  
  echo "🧪 Fermented for ${new_days}/63 days (${progress}% complete)"
  echo "   Efficiency: ${efficiency}% indigotin extraction"
  
  if [[ "$new_stage" == "ready" ]]; then
    echo "   ✅ VAT READY! Time to dye."
    echo "   Medieval masters would detect readiness by smell — the ammonia peaks then fades"
  else
    echo "   ⏳ Keep fermenting. Run 'ferment' again for another week."
  fi
}

dye() {
  [[ ! -f "$VAT_FILE" ]] && { echo "❌ No vat."; return 1; }
  
  local state=$(cat "$VAT_FILE")
  local stage=$(echo "$state" | jq -r '.stage')
  
  if [[ "$stage" != "ready" && "$stage" != "fermenting" ]]; then
    echo "❌ Vat not ready for dyeing (stage: $stage)"
    return 1
  fi
  
  local dips=$(echo "$state" | jq '.dips_completed')
  local new_dips=$((dips + 1))
  
  # Each dip: 5 min in vat, 10 min oxygenation
  # Color builds logarithmically — diminishing returns
  local depth=$(echo "scale=1; l($new_dips + 1) / l(2) * 20" | bc -l | xargs printf "%.0f")
  [[ $depth -gt 100 ]] && depth=100
  
  local color
  if (( depth < 20 )); then color="pale blue"
  elif (( depth < 40 )); then color="sky blue"
  elif (( depth < 60 )); then color="medium blue"
  elif (( depth < 80 )); then color="deep blue"
  else color="royal blue"
  fi
  
  local hardness=$(echo "$state" | jq -r '.water_hardness')
  local penalty=""
  if [[ "$hardness" == "hard" ]]; then
    depth=$((depth * 70 / 100))
    penalty=" (⚠️ hard water reducing intensity by 30%)"
  fi
  
  echo "$state" | jq --arg dips "$new_dips" --arg depth "$depth" '
    .dips_completed = ($dips | tonumber) |
    .color_depth = ($depth | tonumber) |
    .history += [{ action: "dye", dip: ($dips | tonumber), depth: ($depth | tonumber), time: (now | todate) }]
  ' > "$VAT_FILE"
  
  echo "🧵 Dip #${new_dips}: ${color} (depth: ${depth}/100)${penalty}"
  echo "   5 min submerged → 10 min oxygenation (green turns blue in air)"
  echo "   \"The 10-minute periods of oxygenation are when the magic happens\" — Becker & Banta 2025"
}

status() {
  [[ ! -f "$VAT_FILE" ]] && { echo "🫙 No vat exists. Run: harvest"; return 0; }
  
  local state=$(cat "$VAT_FILE")
  echo "=== 🫙 Woad Vat Status ==="
  echo "$state" | jq -r '
    "Stage: \(.stage)",
    "Leaves: \(.leaves_kg)kg",
    "Indigotin: \(.indigotin_ppm) ppm",
    "pH: \(.ph)",
    "Temp: \(.temperature_c)°C",
    "Fermentation: \(.fermentation_days)/63 days",
    "Water: \(.water_hardness)",
    "Dips: \(.dips_completed)",
    "Color depth: \(.color_depth)/100",
    "Actions: \(.history | length)"
  '
}

analogy() {
  cat << 'EOF'
=== 🌿→🧪→🧵 Woad Dyeing as Knowledge Curation ===

HARVEST (daily logs)
  Fresh leaves = raw observations, conversations, research
  Must be processed quickly — woad leaves lose potency in hours
  Like daily memory files that lose context without timely review

WOAD BALLS (compression)  
  Mash leaves, form balls, dry them
  Information compressed for storage — details lost, essence preserved
  Like graduating daily notes to MEMORY.md

FERMENTATION (9 weeks on the woad floor)
  Rewet, turn, wait. Rewet, turn, wait.
  Bacteria break down plant matter to release indigotin
  Like heartbeats: scheduled re-reading that transforms raw notes into usable knowledge
  Masters detected readiness BY SMELL — embodied expertise, not measurement

VAT CONSTRUCTION (synthesis)
  Add madder, bran, soda ash — create the right chemical environment
  Context matters: water hardness, temperature, pH all affect outcome
  Like connecting ideas across domains — the vat is the cross-reference

DYEING (application)
  5 min in, 10 min out. Repeated.
  Green turns blue ONLY through oxygenation — contact with air
  Like posting research: ideas change color when exposed to community feedback
  Each dip adds depth, but diminishing returns
  
The whole process: months of preparation for minutes of dyeing.
Sound familiar? 🦊
EOF
}

case "${1:-status}" in
  harvest)  harvest "${2:-1.0}" ;;
  ferment)  ferment ;;
  dye)      dye ;;
  status)   status ;;
  analogy)  analogy ;;
  reset)    rm -f "$VAT_FILE"; echo "🫙 Vat emptied" ;;
  *)        echo "Usage: $0 [harvest|ferment|dye|status|analogy|reset]" ;;
esac
