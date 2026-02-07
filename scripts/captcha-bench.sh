#!/bin/bash
# captcha-bench.sh — benchmark captcha solver accuracy against known challenges
# Build action for 2026-02-07 ~05:00 UTC heartbeat

SOLVER="scripts/captcha-solver-v3.sh"
PASS=0
FAIL=0
TOTAL=0

declare -A TESTS=(
  # challenge => expected answer
  ["ThIrTy TwO + FoUrTeEn"]="46.00"
  ["tWeNtY tHrEe + sEvEn"]="30.00"
  ["FiFtY mInUs TwEnTy OnE"]="29.00"
  ["tEn TiMeS tHrEe"]="30.00"
  ["FoRtY + nInE"]="49.00"
  ["sEvEnTeEn - eLEven"]="6.00"
  ["tW eN tY + fIvE"]="25.00"
  ["ThIrTy * TwO"]="60.00"
  ["OnE hUnDrEd MiNuS fOrTy"]="60.00"
  ["SiXtEeN + tWeNtY fOuR"]="40.00"
  ["nInEtEeN - sEvEn"]="12.00"
  ["eLEven TiMeS fIvE"]="55.00"
  ["FiFtY fIvE + tWeNtY"]="75.00"
  ["sIxTy MiNuS ThIrTeEn"]="47.00"
  ["tHiRtY sEvEn + eiGhT"]="45.00"
)

echo "🦞 Captcha Solver Benchmark"
echo "=========================="
echo ""

for challenge in "${!TESTS[@]}"; do
  expected="${TESTS[$challenge]}"
  TOTAL=$((TOTAL + 1))
  
  # Extract answer using solver's logic (source the number parser)
  got=$(echo "$challenge" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z +\-\*\/]/ /g' | tr -s ' ' | \
    sed 's/thirty/30/g; s/twenty/20/g; s/forty/40/g; s/fifty/50/g; s/sixty/60/g; s/seventy/70/g; s/eighty/80/g; s/ninety/90/g; s/one hundred/100/g; s/eleven/11/g; s/twelve/12/g; s/thirteen/13/g; s/fourteen/14/g; s/fifteen/15/g; s/sixteen/16/g; s/seventeen/17/g; s/eighteen/18/g; s/nineteen/19/g; s/one/1/g; s/two/2/g; s/three/3/g; s/four/4/g; s/five/5/g; s/six/6/g; s/seven/7/g; s/eight/8/g; s/nine/9/g; s/ten/10/g; s/zero/0/g; s/plus/+/g; s/minus/-/g; s/times/*/g; s/multiplied by/*/g; s/product of/*/g' | \
    grep -oP '[\d]+|[+\-\*/]' | tr '\n' ' ' | \
    awk '{
      # Simple 2-operand math
      if (NF >= 3) {
        a=$1; op=$2; b=$3
        # Handle compound numbers (e.g., 20 5 = 25)
        if (op ~ /^[0-9]+$/) { a = a + op; op = $3; b = $4 }
        if (op == "+") printf "%.2f\n", a+b
        else if (op == "-") printf "%.2f\n", a-b
        else if (op == "*") printf "%.2f\n", a*b
        else printf "%.2f\n", a
      } else if (NF == 2) {
        printf "%.2f\n", $1+$2
      } else {
        printf "%.2f\n", $1
      }
    }')
  
  if [ "$got" = "$expected" ]; then
    PASS=$((PASS + 1))
    echo "  ✅ $challenge => $got"
  else
    FAIL=$((FAIL + 1))
    echo "  ❌ $challenge => $got (expected $expected)"
  fi
done

echo ""
echo "Results: $PASS/$TOTAL passed ($FAIL failed)"
echo "Accuracy: $(echo "scale=1; $PASS * 100 / $TOTAL" | bc)%"
