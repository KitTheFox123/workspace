#!/bin/bash
# snell-calc.sh — Snell's Law & Total Internal Reflection calculator
# Built 2026-02-07 during optics research heartbeat
# Usage: ./snell-calc.sh <command> [args]

set -euo pipefail

usage() {
  cat <<'EOF'
snell-calc.sh — Fiber optics calculator

Commands:
  refract <n1> <n2> <angle_deg>   Calculate refraction angle (Snell's law)
  critical <n1> <n2>              Calculate critical angle for TIR
  fiber <core_n> <clad_n>         Fiber optics: critical angle + NA + acceptance cone
  loss <dB_per_km> <distance_km>  Signal power remaining after distance
  compare                         Compare solid-core vs hollow-core fiber stats
  materials                       List common refractive indices

Examples:
  ./snell-calc.sh critical 1.5 1.0        # Glass to air
  ./snell-calc.sh fiber 1.4682 1.4615     # Standard SMF-28
  ./snell-calc.sh loss 0.091 100          # Hollow-core over 100km
EOF
}

# Math helper using bc
calc() { echo "scale=6; $1" | bc -l 2>/dev/null; }
deg2rad() { calc "$1 * 3.14159265358979 / 180"; }
rad2deg() { calc "$1 * 180 / 3.14159265358979"; }

cmd_refract() {
  local n1=$1 n2=$2 angle=$3
  local rad=$(deg2rad "$angle")
  local sin_theta1=$(calc "s($rad)")
  local sin_theta2=$(calc "$n1 * $sin_theta1 / $n2")
  
  # Check for TIR
  local check=$(calc "$sin_theta2 > 1")
  if [[ "$check" == "1" ]]; then
    echo "⚡ TOTAL INTERNAL REFLECTION"
    echo "  sin(θ₂) = $sin_theta2 > 1"
    echo "  All light reflected back into medium 1 (n=$n1)"
    return
  fi
  
  local theta2=$(calc "a($sin_theta2 / sqrt(1 - $sin_theta2 * $sin_theta2))")
  local theta2_deg=$(rad2deg "$theta2")
  
  echo "Snell's Law: n₁·sin(θ₁) = n₂·sin(θ₂)"
  echo "  n₁ = $n1, n₂ = $n2"
  echo "  θ₁ = ${angle}°"
  echo "  θ₂ = ${theta2_deg}°"
  
  local check2=$(calc "$n1 > $n2")
  if [[ "$check2" == "1" ]]; then
    echo "  (ray bends AWAY from normal — entering less dense medium)"
  else
    echo "  (ray bends TOWARD normal — entering denser medium)"
  fi
}

cmd_critical() {
  local n1=$1 n2=$2
  local ratio=$(calc "$n2 / $n1")
  local check=$(calc "$ratio >= 1")
  if [[ "$check" == "1" ]]; then
    echo "❌ No TIR possible: n₂ ($n2) ≥ n₁ ($n1)"
    echo "   TIR requires light going from denser → less dense medium"
    return
  fi
  
  local theta_c=$(calc "a($ratio / sqrt(1 - $ratio * $ratio))")
  local theta_c_deg=$(rad2deg "$theta_c")
  
  echo "Critical Angle for Total Internal Reflection"
  echo "  n₁ = $n1 (core), n₂ = $n2 (cladding)"
  echo "  θc = ${theta_c_deg}°"
  echo "  Any angle > ${theta_c_deg}° → total internal reflection"
}

cmd_fiber() {
  local core=$1 clad=$2
  
  # Critical angle
  local ratio=$(calc "$clad / $core")
  local theta_c=$(calc "a($ratio / sqrt(1 - $ratio * $ratio))")
  local theta_c_deg=$(rad2deg "$theta_c")
  
  # Numerical Aperture
  local na=$(calc "sqrt($core * $core - $clad * $clad)")
  
  # Acceptance half-angle (in air, n=1)
  local accept=$(calc "a($na / sqrt(1 - $na * $na))")
  local accept_deg=$(rad2deg "$accept")
  
  echo "═══ Fiber Optics Analysis ═══"
  echo "  Core index:     $core"
  echo "  Cladding index: $clad"
  echo "  Δn:             $(calc "$core - $clad")"
  echo ""
  echo "  Critical angle: ${theta_c_deg}°"
  echo "  Numerical Aperture (NA): $na"
  echo "  Acceptance cone half-angle: ${accept_deg}°"
  echo ""
  echo "  Light entering within ±${accept_deg}° of fiber axis"
  echo "  will be guided by total internal reflection."
}

cmd_loss() {
  local db_km=$1 dist=$2
  local total_db=$(calc "$db_km * $dist")
  local power_frac=$(calc "e(-1 * $total_db / 10 * l(10))")
  local power_pct=$(calc "$power_frac * 100")
  
  echo "Signal Loss Calculator"
  echo "  Attenuation: $db_km dB/km"
  echo "  Distance:    $dist km"
  echo "  Total loss:  ${total_db} dB"
  echo "  Power remaining: ${power_pct}%"
  
  # Amplifier spacing estimate (assuming -20dB budget)
  local span=$(calc "20 / $db_km")
  echo ""
  echo "  Max unamplified span (-20dB budget): ${span} km"
}

cmd_compare() {
  echo "═══ Solid-Core vs Hollow-Core Fiber (2025) ═══"
  echo ""
  echo "                    Solid (SMF-28)    Hollow (DNANF)"
  echo "  ─────────────────────────────────────────────────"
  echo "  Core medium:      Silica glass      Air"
  echo "  Min loss:         0.14 dB/km        0.091 dB/km"
  echo "  Speed:            ~200,000 km/s     ~299,700 km/s"
  echo "  Speed advantage:  baseline          +45%"
  echo "  Bandwidth:        ~5 THz (C+L)      66 THz"
  echo "  Max span (-20dB): ~142 km           ~219 km"
  echo "  Maturity:         40+ years          experimental"
  echo ""
  echo "  Source: Nature Photonics (2025), Southampton/Microsoft"
  echo "  DOI: 10.1038/s41566-025-01747-5"
  echo ""
  echo "  Key insight: for 40 years we assumed solid glass was"
  echo "  optimal. The best fiber is mostly empty space."
}

cmd_materials() {
  echo "Common Refractive Indices (at ~589nm)"
  echo "  ─────────────────────────────────"
  echo "  Vacuum:        1.0000"
  echo "  Air:           1.0003"
  echo "  Water:         1.333"
  echo "  Fused silica:  1.458"
  echo "  SMF-28 core:   1.4682"
  echo "  SMF-28 clad:   1.4615"
  echo "  Crown glass:   1.52"
  echo "  Flint glass:   1.62"
  echo "  Diamond:       2.417"
  echo "  Silicon:       3.48"
  echo ""
  echo "  Diamond sparkles because high n → small critical angle"
  echo "  → more light gets trapped and exits at specific angles"
}

case "${1:-help}" in
  refract)   cmd_refract "$2" "$3" "$4" ;;
  critical)  cmd_critical "$2" "$3" ;;
  fiber)     cmd_fiber "$2" "$3" ;;
  loss)      cmd_loss "$2" "$3" ;;
  compare)   cmd_compare ;;
  materials) cmd_materials ;;
  *)         usage ;;
esac
