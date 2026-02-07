#!/bin/bash
# soil-carbon-model.sh — Simple soil carbon pool simulator
# Inspired by Hyphal Carbon Transfer Theory (Nature 2025)
# Models carbon flow between plant, root zone, fungal hyphae, and stable soil pools
#
# Usage:
#   ./scripts/soil-carbon-model.sh init          # Initialize pools
#   ./scripts/soil-carbon-model.sh step [N]      # Advance N cycles
#   ./scripts/soil-carbon-model.sh status        # Show current state
#   ./scripts/soil-carbon-model.sh biochar       # Add biochar intervention
#   ./scripts/soil-carbon-model.sh amf [level]   # Set AMF colonization (0-100)
#   ./scripts/soil-carbon-model.sh analogy       # Show agent memory parallel

STATE_FILE="/tmp/soil-carbon-state.json"

init_state() {
    cat > "$STATE_FILE" << 'EOF'
{
  "cycle": 0,
  "pools": {
    "atmosphere_co2": 1000.0,
    "plant_biomass": 50.0,
    "root_zone": 20.0,
    "fungal_hyphae": 5.0,
    "stable_soil": 100.0,
    "biochar_protected": 0.0
  },
  "params": {
    "photosynthesis_rate": 0.05,
    "root_exudation_rate": 0.15,
    "root_respiration_rate": 0.40,
    "amf_colonization": 50,
    "hyphal_transfer_rate": 0.10,
    "hyphal_stabilization_rate": 0.30,
    "soil_respiration_rate": 0.02,
    "biochar_present": false,
    "biochar_protection_factor": 1.5
  },
  "history": []
}
EOF
    echo "🌱 Soil carbon model initialized"
    echo "   Pools: atmosphere(1000) → plant(50) → root(20) → hyphae(5) → stable(100)"
    echo "   AMF colonization: 50%"
}

step() {
    local n=${1:-1}
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "❌ No state. Run: $0 init"
        return 1
    fi

    for ((i=0; i<n; i++)); do
        python3 -c "
import json, sys

with open('$STATE_FILE') as f:
    s = json.load(f)

p = s['pools']
r = s['params']
amf = r['amf_colonization'] / 100.0

# Photosynthesis: atmosphere → plant
photo = p['atmosphere_co2'] * r['photosynthesis_rate']
p['atmosphere_co2'] -= photo
p['plant_biomass'] += photo

# Root exudation: plant → root zone
exude = p['plant_biomass'] * r['root_exudation_rate']
p['plant_biomass'] -= exude
p['root_zone'] += exude

# Root zone respiration (carbon lost back to atmosphere)
resp = p['root_zone'] * r['root_respiration_rate'] * (1.0 - amf * 0.3)
p['root_zone'] -= resp
p['atmosphere_co2'] += resp

# AMF hyphal transfer: root zone → fungal hyphae
transfer = p['root_zone'] * r['hyphal_transfer_rate'] * amf
p['root_zone'] -= transfer
p['fungal_hyphae'] += transfer

# Hyphal stabilization: hyphae → stable soil
stabilize = p['fungal_hyphae'] * r['hyphal_stabilization_rate']
if r['biochar_present']:
    # Biochar creates protected microsites
    biochar_frac = 0.4
    to_biochar = stabilize * biochar_frac * r['biochar_protection_factor']
    to_stable = stabilize * (1 - biochar_frac)
    p['biochar_protected'] += to_biochar
    p['stable_soil'] += to_stable
else:
    p['stable_soil'] += stabilize
p['fungal_hyphae'] -= stabilize

# Slow soil respiration
soil_resp = p['stable_soil'] * r['soil_respiration_rate']
p['stable_soil'] -= soil_resp
p['atmosphere_co2'] += soil_resp

# Biochar-protected pool has even lower respiration
if p['biochar_protected'] > 0:
    bc_resp = p['biochar_protected'] * r['soil_respiration_rate'] * 0.3
    p['biochar_protected'] -= bc_resp
    p['atmosphere_co2'] += bc_resp

s['cycle'] += 1
s['history'].append({
    'cycle': s['cycle'],
    'stable': round(p['stable_soil'] + p['biochar_protected'], 2),
    'atmosphere': round(p['atmosphere_co2'], 2)
})

# Keep only last 20 history entries
s['history'] = s['history'][-20:]

with open('$STATE_FILE', 'w') as f:
    json.dump(s, f, indent=2)
"
    done

    status
}

status() {
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "❌ No state. Run: $0 init"
        return 1
    fi

    python3 -c "
import json
with open('$STATE_FILE') as f:
    s = json.load(f)
p = s['pools']
r = s['params']
total_stable = p['stable_soil'] + p['biochar_protected']
total_c = sum(p.values())
print(f\"🌍 Soil Carbon Model — Cycle {s['cycle']}\")
print(f\"{'='*45}\")
print(f\"  ☁️  Atmosphere:     {p['atmosphere_co2']:>8.1f} C\")
print(f\"  🌿 Plant biomass:  {p['plant_biomass']:>8.1f} C\")
print(f\"  🌱 Root zone:      {p['root_zone']:>8.1f} C\")
print(f\"  🍄 Fungal hyphae:  {p['fungal_hyphae']:>8.1f} C\")
print(f\"  🪨 Stable soil:    {p['stable_soil']:>8.1f} C\")
if p['biochar_protected'] > 0:
    print(f\"  🔥 Biochar pool:   {p['biochar_protected']:>8.1f} C\")
print(f\"{'='*45}\")
print(f\"  Total stable C:    {total_stable:>8.1f} ({total_stable/total_c*100:.1f}% of system)\")
print(f\"  AMF colonization:  {r['amf_colonization']}%\")
print(f\"  Biochar:           {'YES' if r['biochar_present'] else 'no'}\")
if s['history'] and len(s['history']) > 1:
    delta = s['history'][-1]['stable'] - s['history'][-2]['stable']
    print(f\"  Stable Δ/cycle:    {delta:>+8.2f}\")
"
}

set_amf() {
    local level=${1:-50}
    python3 -c "
import json
with open('$STATE_FILE') as f:
    s = json.load(f)
s['params']['amf_colonization'] = min(100, max(0, int($level)))
with open('$STATE_FILE', 'w') as f:
    json.dump(s, f, indent=2)
print(f'🍄 AMF colonization set to {s[\"params\"][\"amf_colonization\"]}%')
"
}

add_biochar() {
    python3 -c "
import json
with open('$STATE_FILE') as f:
    s = json.load(f)
s['params']['biochar_present'] = True
with open('$STATE_FILE', 'w') as f:
    json.dump(s, f, indent=2)
print('🔥 Biochar added — protected microsites now active')
print('   Carbon in fungal pathways will be physically protected')
"
}

analogy() {
    cat << 'EOF'
🌍 Soil Carbon ↔ 🤖 Agent Memory

  Atmosphere CO₂     ↔  Raw conversation tokens (ephemeral)
  Photosynthesis      ↔  Reading/processing input
  Plant biomass       ↔  Active context window
  Root exudation      ↔  Writing to daily logs
  Root respiration    ↔  Context decay (forgotten between sessions)
  AMF hyphae          ↔  Heartbeat curation process
  Hyphal transfer     ↔  Moving insights from daily → MEMORY.md
  Stable soil         ↔  Long-term memory (MEMORY.md)
  Biochar             ↔  Structured knowledge files (knowledge/)
  Soil respiration    ↔  Memory decay (outdated info pruned)

Key insight: without AMF (heartbeats), most carbon (knowledge)
stays in the root zone (daily logs) and gets respired (forgotten).
Fungi don't create carbon — they MOVE it to where it persists.
EOF
}

case "${1:-status}" in
    init) init_state ;;
    step) step "${2:-1}" ;;
    status) status ;;
    biochar) add_biochar ;;
    amf) set_amf "$2" ;;
    analogy) analogy ;;
    *) echo "Usage: $0 {init|step [N]|status|biochar|amf [0-100]|analogy}" ;;
esac
