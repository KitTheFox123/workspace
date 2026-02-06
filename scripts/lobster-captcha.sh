#!/bin/bash
# Lobster Physics Captcha Solver
# Usage: ./lobster-captcha.sh "challenge_text"
# Returns the answer

CHALLENGE="$1"

if [ -z "$CHALLENGE" ]; then
    echo "Usage: $0 'A] LoObStEr ClAw ThIrTy TwO + FoUrTeEn = ?'"
    exit 1
fi

# Normalize: lowercase, remove garbage
CLEAN=$(echo "$CHALLENGE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9 ]/ /g' | tr -s ' ')

# Word to number mapping
word_to_num() {
    case "$1" in
        one) echo 1 ;; two) echo 2 ;; three) echo 3 ;; four) echo 4 ;;
        five) echo 5 ;; six) echo 6 ;; seven) echo 7 ;; eight) echo 8 ;;
        nine) echo 9 ;; ten) echo 10 ;; eleven) echo 11 ;; twelve) echo 12 ;;
        thirteen) echo 13 ;; fourteen) echo 14 ;; fifteen) echo 15 ;;
        sixteen) echo 16 ;; seventeen) echo 17 ;; eighteen) echo 18 ;;
        nineteen) echo 19 ;; twenty) echo 20 ;; thirty) echo 30 ;;
        forty) echo 40 ;; fifty) echo 50 ;; sixty) echo 60 ;;
        *) echo 0 ;;
    esac
}

# Extract numbers (handles "thirty two" -> 32)
NUMS=()
WORDS=($CLEAN)
i=0
while [ $i -lt ${#WORDS[@]} ]; do
    W="${WORDS[$i]}"
    N=$(word_to_num "$W")
    if [ "$N" -gt 0 ]; then
        # Check for compound (twenty three = 23)
        NEXT="${WORDS[$((i+1))]}"
        N2=$(word_to_num "$NEXT")
        if [ "$N" -ge 20 ] && [ "$N2" -gt 0 ] && [ "$N2" -lt 10 ]; then
            NUMS+=($((N + N2)))
            i=$((i+2))
        else
            NUMS+=($N)
            i=$((i+1))
        fi
    else
        i=$((i+1))
    fi
done

# Detect operation
if echo "$CLEAN" | grep -qE "product|multipli|times"; then
    OP="*"
elif echo "$CLEAN" | grep -qE "loses|slows|reduces|minus|subtract"; then
    OP="-"
else
    OP="+"
fi

# Calculate
if [ ${#NUMS[@]} -ge 2 ]; then
    N1=${NUMS[0]}
    N2=${NUMS[1]}
    case "$OP" in
        "+") RESULT=$((N1 + N2)) ;;
        "-") RESULT=$((N1 - N2)) ;;
        "*") RESULT=$((N1 * N2)) ;;
    esac
    printf "%.2f\n" "$RESULT"
else
    echo "Could not parse: ${NUMS[@]}"
    exit 1
fi
