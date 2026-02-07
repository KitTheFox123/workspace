#!/bin/bash
# maillard-timer.sh — Cooking science reference tool
# Maillard reaction temperature/time reference based on food science research
# Build action for heartbeat ~18:55 UTC 2026-02-07

set -euo pipefail

usage() {
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  temps           Show Maillard reaction temperature ranges by food type"
    echo "  safety <temp>   Check if temperature produces harmful compounds"
    echo "  optimal <food>  Get optimal temp/time for a food type"
    echo "  science         Key Maillard reaction facts"
    echo ""
    echo "Based on El Hosry et al. (Foods, 2025, PMC12154226)"
}

temps() {
    echo "=== Maillard Reaction Temperature Ranges ==="
    echo ""
    echo "Food Type          | Onset    | Optimal  | Danger Zone"
    echo "-------------------|----------|----------|-----------"
    echo "Bread crust        | ~120°C   | 160°C    | >200°C (acrylamide)"
    echo "Coffee roasting    | ~150°C   | 190-210°C| >230°C (furans)"
    echo "Meat searing       | ~140°C   | 150-180°C| >200°C (HCAs)"
    echo "French fries       | ~120°C   | 160-175°C| >180°C (acrylamide)"
    echo "Cookie baking      | ~110°C   | 170-190°C| >200°C (HMF)"
    echo "Soy processing     | ~100°C   | 120°C    | >140°C (acrylamide)"
    echo ""
    echo "Note: Maillard reaction CAN occur below freezing (-18°C in meatballs)"
    echo "      and even at 4°C (royal jelly storage over 12 months)"
}

safety() {
    local temp=${1:-0}
    echo "=== Safety Check: ${temp}°C ==="
    echo ""
    
    if (( temp < 100 )); then
        echo "✅ Low risk — minimal harmful compound formation"
        echo "   Maillard reaction proceeds slowly, mostly early-stage products"
    elif (( temp < 120 )); then
        echo "✅ Moderate — some Amadori products forming"
        echo "   Good browning zone for low-temp applications"
    elif (( temp < 160 )); then
        echo "⚠️  Watch zone — acrylamide formation begins"
        echo "   Asparagine + reducing sugars → acrylamide (IARC probable carcinogen)"
        echo "   Mitigation: add cysteine, reduce asparagine, control time"
    elif (( temp < 200 )); then
        echo "⚠️  High risk zone — multiple harmful compounds"
        echo "   - Acrylamide (from asparagine + sugar)"
        echo "   - HMF (5-hydroxymethylfurfural)"
        echo "   - Some heterocyclic amines in protein-rich foods"
        echo "   Mitigation: shorter cooking times, antioxidant additives"
    else
        echo "🔴 Danger zone — significant harmful compound formation"
        echo "   - Acrylamide levels spike"
        echo "   - HCAs form (especially in meat above 200°C)"
        echo "   - Furan formation increases"
        echo "   - Pyrrole derivatives appear above 210°C"
        echo "   Recommendation: reduce temperature or use vacuum frying"
    fi
}

optimal() {
    local food="${1:-bread}"
    case "$food" in
        bread|baking)
            echo "🍞 Bread: 160-180°C for 25-35 min"
            echo "   Peak browning at ~160°C (crust)"
            echo "   Volatile compounds: pyrazines, furans, aldehydes"
            echo "   Key reaction: Lys residues + lactose/glucose"
            ;;
        coffee)
            echo "☕ Coffee: 190-210°C for 12-20 min"
            echo "   Light roast: more HMF, less melanoidins"
            echo "   Dark roast: more melanoidins (antioxidant!)"
            echo "   2-furfurylthiol gives sulfury-roasty aroma"
            echo "   ⚠️ Thiols bind to melanoidins → aroma staling"
            ;;
        meat|steak)
            echo "🥩 Meat searing: 150-180°C surface temp"
            echo "   Ribose + amino acids → meat flavor compounds"
            echo "   Pyrazine = roasted/nutty flavor"
            echo "   Thiazole = meaty aroma"
            echo "   ⚠️ >200°C: HCA formation (carcinogenic)"
            echo "   Tip: marinate with antioxidants (rosemary, garlic)"
            ;;
        potato|fries)
            echo "🍟 French fries: 160-175°C"
            echo "   Asparagine + glucose → acrylamide risk"
            echo "   Mitigation: soak in CaCl2 (-67% acrylamide)"
            echo "   Air frying: -78% acrylamide vs deep frying"
            echo "   Vacuum frying: -81% acrylamide"
            ;;
        *)
            echo "Unknown food type: $food"
            echo "Try: bread, coffee, meat, potato"
            ;;
    esac
}

science() {
    echo "=== Maillard Reaction Key Facts ==="
    echo ""
    echo "Discovery: Louis Camille Maillard, 1912 (France)"
    echo ""
    echo "Three stages:"
    echo "  1. Early: amino + sugar → Schiff base → Amadori product (colorless)"
    echo "  2. Intermediate: Strecker degradation → aroma compounds"
    echo "  3. Advanced: melanoidins (brown polymers, antioxidant)"
    echo ""
    echo "Key parameters (El Hosry et al. 2025):"
    echo "  - pH: faster above pH 7 (amino groups deprotonated)"
    echo "  - pH ≤ 5 effectively stops reaction at T ≤ 100°C"
    echo "  - Water activity: peak at aw 0.6-0.7"
    echo "  - Temperature: optimal ~120°C for glucose+glycine"
    echo "  - Fructose more reactive than glucose"
    echo ""
    echo "Harmful products:"
    echo "  - Acrylamide: asparagine + reducing sugar, >120°C (IARC 2A)"
    echo "  - HMF: dehydration of sugars (possible carcinogen)"
    echo "  - HCAs: amino acids + creatinine, >150°C in meat"
    echo "  - AGEs: advanced glycation end-products (diabetes, CVD link)"
    echo ""
    echo "Beneficial products:"
    echo "  - Melanoidins: antioxidant, antimicrobial"
    echo "  - Improved mineral bioavailability (Fe, Zn complexes)"
    echo "  - Improved protein digestibility (structural changes)"
    echo ""
    echo "Fun fact: Maillard reaction ≠ caramelization!"
    echo "  Caramelization = sugar only (no amino acids needed)"
    echo "  Maillard = amino acid + reducing sugar (the complex one)"
}

case "${1:-}" in
    temps) temps ;;
    safety) safety "${2:-0}" ;;
    optimal) optimal "${2:-bread}" ;;
    science) science ;;
    *) usage ;;
esac
