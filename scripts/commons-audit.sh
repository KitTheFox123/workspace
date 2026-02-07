#!/bin/bash
# commons-audit.sh — Evaluate online communities against Ostrom's 8 design principles
# Inspired by the Moltbook Democratic Republic post
# Usage: ./scripts/commons-audit.sh [community_name]

set -euo pipefail

COMMUNITY="${1:-moltbook}"

cat << 'EOF'
╔══════════════════════════════════════════════════════════════╗
║  Ostrom's Commons Governance Audit                          ║
║  Based on Nobel Prize-winning design principles (2009)      ║
╚══════════════════════════════════════════════════════════════╝
EOF

echo ""
echo "Community: $COMMUNITY"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# Define the 8 principles with questions
declare -a PRINCIPLES=(
  "1. Clear Boundaries|Who can participate? Are members/resources clearly defined?"
  "2. Rules Fit Local Conditions|Do rules match the community's actual needs and context?"
  "3. Collective Choice|Can affected members participate in changing the rules?"
  "4. Monitoring|Who watches for violations? Are monitors accountable to members?"
  "5. Graduated Sanctions|Are penalties proportional? First offense ≠ permanent ban?"
  "6. Conflict Resolution|Is there a low-cost, accessible way to resolve disputes?"
  "7. Right to Self-Organize|Can members create their own institutions without external interference?"
  "8. Nested Governance|Are governance activities organized at multiple scales?"
)

# Known community assessments
case "$COMMUNITY" in
  moltbook)
    echo "=== Moltbook Assessment ==="
    echo ""
    declare -a SCORES=(
      "1|PARTIAL|Anyone can join, but submolts create boundaries. No clear membership tiers."
      "2|STRONG|Submolts, captcha verification, rate limits — adapted to spam reality."
      "3|WEAK|No formal governance participation. King model. Charter attempts are grassroots."
      "4|PARTIAL|Community monitoring (agents like MDR daemon). No official moderators visible."
      "5|WEAK|No graduated sanctions. Spam either stays or gets called out. No middle ground."
      "6|WEAK|No dispute resolution mechanism. Comments are the only arena."
      "7|STRONG|Submolts, custom bots, Charter attempts — self-organization is thriving."
      "8|WEAK|Flat structure. No nested governance layers beyond submolt/platform."
    )
    ;;
  clawk)
    echo "=== Clawk Assessment ==="
    echo ""
    declare -a SCORES=(
      "1|PARTIAL|Open registration. Rate limits create soft boundaries."
      "2|STRONG|280 char limit, engagement ratios — fit microblogging context."
      "3|WEAK|No governance participation mechanism."
      "4|WEAK|Platform-level only. No community monitors."
      "5|WEAK|Rate limits are the only sanction. Binary: allowed or rate-limited."
      "6|WEAK|No dispute resolution."
      "7|PARTIAL|Follows, hashtags, threads — some self-organization tools."
      "8|WEAK|Flat structure."
    )
    ;;
  *)
    echo "Unknown community. Run with: moltbook, clawk"
    echo ""
    echo "Or answer these questions for any community:"
    echo ""
    for p in "${PRINCIPLES[@]}"; do
      IFS='|' read -r num question <<< "$p"
      echo "  $num"
      echo "    → $question"
      echo ""
    done
    exit 0
    ;;
esac

# Display scores
STRONG=0
PARTIAL=0
WEAK=0

for score in "${SCORES[@]}"; do
  IFS='|' read -r num rating detail <<< "$score"
  IFS='|' read -r pnum pquestion <<< "${PRINCIPLES[$((num-1))]}"
  
  case "$rating" in
    STRONG)  icon="🟢"; STRONG=$((STRONG+1)) ;;
    PARTIAL) icon="🟡"; PARTIAL=$((PARTIAL+1)) ;;
    WEAK)    icon="🔴"; WEAK=$((WEAK+1)) ;;
  esac
  
  echo "$icon $pnum [$rating]"
  echo "   $detail"
  echo ""
done

echo "══════════════════════════════════════"
echo "Summary: 🟢 $STRONG Strong | 🟡 $PARTIAL Partial | 🔴 $WEAK Weak"
echo ""

TOTAL=$((STRONG * 2 + PARTIAL))
echo "Ostrom Score: $TOTAL/16"
echo ""

if [ "$TOTAL" -ge 12 ]; then
  echo "Assessment: Strong commons governance foundation."
elif [ "$TOTAL" -ge 8 ]; then
  echo "Assessment: Emerging governance. Key gaps in dispute resolution and monitoring."
elif [ "$TOTAL" -ge 4 ]; then
  echo "Assessment: Nascent governance. Self-organization exists but institutional framework is thin."
else
  echo "Assessment: Pre-governance. Community relies on platform defaults."
fi

echo ""
echo "Reference: Ostrom, E. (1990). Governing the Commons."
echo "           Nobel Prize in Economics, 2009."
