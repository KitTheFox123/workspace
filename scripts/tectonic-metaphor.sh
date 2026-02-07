#!/bin/bash
# tectonic-metaphor.sh — Maps geological processes to agent/software concepts
# Build action for 2026-02-07 ~15:15 heartbeat
# Inspired by plate tectonics research: lost plates leave tomographic ghosts,
# subduction destroys surface evidence but preserves deep traces

set -euo pipefail

KNOWLEDGE_DIR="${KNOWLEDGE_DIR:-knowledge}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  map <geo-term>     Show agent/software parallels for a geological process
  reverse <sw-term>  Find geological metaphors for a software concept
  quiz               Random geological metaphor challenge
  catalog            List all mapped metaphors
  add <geo> <sw> <desc>  Add a new mapping

Geological processes as lenses for understanding software systems.
EOF
}

declare -A GEO_MAP
# Plate tectonics
GEO_MAP["subduction"]="context eviction|Old context gets pushed beneath new context. Surface evidence disappears but deep traces (downstream outputs, cached embeddings) persist. Like Pontus — reconstructed from mantle tomography after the plate itself was destroyed."
GEO_MAP["divergent boundary"]="API forking|Two systems pulling apart create new material (mid-ocean ridges). In software: forking creates new code at the boundary. The gap fills with fresh material, not void."
GEO_MAP["convergent boundary"]="system integration|Two systems colliding. One gets subducted (absorbed/deprecated), the other gets uplifted (mountain building = feature growth). Integration always destroys something."
GEO_MAP["transform fault"]="lateral scaling|Systems sliding past each other — no creation or destruction, just shear stress. Horizontal scaling without architectural change. Earthquakes (outages) happen at the friction points."
GEO_MAP["mantle convection"]="resource scheduling|Heat-driven circulation moves plates from below. Like compute schedulers: the surface topology (running services) is driven by invisible subsurface flows (resource allocation)."
GEO_MAP["hotspot"]="singleton service|Stationary heat source beneath moving plates. Creates island chains (version history). Hawaii = each eruption is a deployment; the plate moves but the hotspot stays."
GEO_MAP["isostasy"]="load balancing|Crust floats on mantle at equilibrium height based on density/thickness. Add load (ice sheet/traffic) → crust depresses. Remove it → rebound. Auto-scaling is isostatic adjustment."
GEO_MAP["metamorphism"]="refactoring|Heat and pressure transform rock without melting it. Refactoring transforms code without rewriting from scratch. Contact metamorphism = localized refactor near a hotfix. Regional = architectural overhaul."
GEO_MAP["erosion"]="technical debt payoff|Slow removal of material reveals underlying structure. Erosion exposes basement rock like paying down tech debt reveals core architecture."
GEO_MAP["sedimentation"]="log accumulation|Material settles in layers. Oldest at bottom. Lithification (compression → rock) = log archival. Stratigraphy = log analysis."
GEO_MAP["orogeny"]="feature creep|Mountain building from collision. Features pile up at system boundaries where requirements collide. Takes millions of years (sprints) and creates impressive but hard-to-maintain structures."
GEO_MAP["volcanic eruption"]="incident response|Pressure builds until catastrophic release. The eruption destroys surface infrastructure but creates new land (post-mortem improvements). Pyroclastic flow = cascading failure."
GEO_MAP["fossil"]="deprecated API|Preserved remains of ancient life in sedimentary rock. Fossils tell you what lived in that stratum. Deprecated APIs tell you what interfaces existed in that version."
GEO_MAP["pangaea"]="monolith|All continents joined. Maximum coupling, minimum latency. Broke apart into microservices (continents). Some still drift toward re-merger (acquisitions)."
GEO_MAP["seismic tomography"]="distributed tracing|Using earthquake waves to image Earth's interior. Each wave path = a trace through the system. Slow zones = hot/anomalous. Fast zones = cold/dense. Reconstruct internal state from external observations."

cmd="${1:-help}"
shift 2>/dev/null || true

case "$cmd" in
  map)
    term="${1:-}"
    term_lower=$(echo "$term" | tr '[:upper:]' '[:lower:]')
    if [[ -z "$term_lower" ]]; then
      echo "Usage: $(basename "$0") map <geological-term>"
      echo "Try: subduction, divergent boundary, hotspot, pangaea, etc."
      exit 1
    fi
    if [[ -n "${GEO_MAP[$term_lower]:-}" ]]; then
      IFS='|' read -r sw_concept description <<< "${GEO_MAP[$term_lower]}"
      echo "🌍 $term_lower → 💻 $sw_concept"
      echo ""
      echo "$description"
    else
      echo "No mapping for '$term_lower'. Try: $(basename "$0") catalog"
    fi
    ;;

  reverse)
    sw_term="${1:-}"
    sw_lower=$(echo "$sw_term" | tr '[:upper:]' '[:lower:]')
    if [[ -z "$sw_lower" ]]; then
      echo "Usage: $(basename "$0") reverse <software-term>"
      exit 1
    fi
    found=0
    for geo in "${!GEO_MAP[@]}"; do
      IFS='|' read -r sw_concept description <<< "${GEO_MAP[$geo]}"
      if echo "$sw_concept $description" | grep -qi "$sw_lower"; then
        echo "💻 $sw_lower ← 🌍 $geo ($sw_concept)"
        echo "  $description"
        echo ""
        found=1
      fi
    done
    [[ $found -eq 0 ]] && echo "No geological parallel found for '$sw_lower'."
    ;;

  quiz)
    # Pick random mapping
    keys=("${!GEO_MAP[@]}")
    idx=$((RANDOM % ${#keys[@]}))
    geo="${keys[$idx]}"
    IFS='|' read -r sw_concept description <<< "${GEO_MAP[$geo]}"
    echo "🌍 Geological process: $geo"
    echo ""
    echo "What software concept does this map to?"
    echo "(Think about it before scrolling down...)"
    echo ""
    echo ""
    echo ""
    echo "💻 Answer: $sw_concept"
    echo "$description"
    ;;

  catalog)
    echo "🌍 Geological Process → 💻 Software Concept"
    echo "============================================"
    for geo in "${!GEO_MAP[@]}"; do
      IFS='|' read -r sw_concept _ <<< "${GEO_MAP[$geo]}"
      printf "  %-25s → %s\n" "$geo" "$sw_concept"
    done
    echo ""
    echo "${#GEO_MAP[@]} mappings total"
    ;;

  add)
    geo="${1:-}"
    sw="${2:-}"
    desc="${3:-}"
    if [[ -z "$geo" || -z "$sw" || -z "$desc" ]]; then
      echo "Usage: $(basename "$0") add <geo-term> <sw-concept> <description>"
      exit 1
    fi
    echo "GEO_MAP[\"$geo\"]=\"$sw|$desc\"" >> "$0"
    echo "✅ Added: $geo → $sw"
    ;;

  help|*)
    usage
    ;;
esac
