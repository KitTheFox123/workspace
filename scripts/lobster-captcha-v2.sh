#!/bin/bash
# Lobster Physics Captcha Solver v2
# Better word extraction and operation detection

CHALLENGE="$1"
[ -z "$CHALLENGE" ] && { echo "Usage: $0 'challenge'"; exit 1; }

# Normalize
CLEAN=$(echo "$CHALLENGE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9 ]/ /g' | tr -s ' ')

# Word to number - handles compound numbers
parse_number() {
    local words="$1"
    local tens=0 ones=0
    
    case "$words" in
        *forty*) tens=40 ;;
        *fifty*) tens=50 ;;
        *sixty*) tens=60 ;;
        *thirty*) tens=30 ;;
        *twenty*) tens=20 ;;
    esac
    
    case "$words" in
        *one*) ones=1 ;; *two*) ones=2 ;; *three*) ones=3 ;;
        *four*) ones=4 ;; *five*) ones=5 ;; *six*) ones=6 ;;
        *seven*) ones=7 ;; *eight*) ones=8 ;; *nine*) ones=9 ;;
        *ten*) [ $tens -eq 0 ] && tens=10 ;;
        *eleven*) tens=11 ;; *twelve*) tens=12 ;;
        *thirteen*) tens=13 ;; *fourteen*) tens=14 ;;
        *fifteen*) tens=15 ;; *sixteen*) tens=16 ;;
        *seventeen*) tens=17 ;; *eighteen*) tens=18 ;;
        *nineteen*) tens=19 ;;
    esac
    
    echo $((tens + ones))
}

# Extract first two number phrases
NUM1=$(echo "$CLEAN" | grep -oE '(forty|fifty|sixty|thirty|twenty|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)( (one|two|three|four|five|six|seven|eight|nine))?' | head -1)
NUM2=$(echo "$CLEAN" | grep -oE '(forty|fifty|sixty|thirty|twenty|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|one|two|three|four|five|six|seven|eight|nine)( (one|two|three|four|five|six|seven|eight|nine))?' | tail -1)

N1=$(parse_number "$NUM1")
N2=$(parse_number "$NUM2")

# Detect operation
if echo "$CLEAN" | grep -qE "product|multipli|times"; then
    RESULT=$((N1 * N2))
elif echo "$CLEAN" | grep -qE "loses|slows|reduces|minus|subtract|remains"; then
    RESULT=$((N1 - N2))
else
    RESULT=$((N1 + N2))
fi

printf "%.2f\n" "$RESULT"
