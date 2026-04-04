#!/usr/bin/env python3
"""Moltbook lobster captcha solver. Handles obfuscated challenges.

Usage:
    python captcha_solver.py "CHALLENGE_TEXT"
    echo "CHALLENGE_TEXT" | python captcha_solver.py

Returns: number with 2 decimal places (e.g., "35.00")
"""

import re
import sys

WORD_TO_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
}

OP_WORDS = {
    "+": {"plus", "adds", "gains", "total", "combined", "sum", "increases"},
    "-": {"minus", "subtract", "less", "loses", "drops", "slows", "reduces", "decreases", "falls", "opposing", "resultant"},
    "*": {"product", "multiplied", "multiplies", "multiply", "times", "doubles", "triples", "push"},
    "/": {"divided", "split"},
}

# Dedup: collapse consecutive duplicate chars (e.g., "threeee" -> "thre")
def dedup(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


DECIMAL_WORDS = {"point", "dot"}  # decimal markers for "four point five" → 4.5

def lookup(word: str) -> str | None:
    """Try to match a word (possibly obfuscated) to a known token."""
    all_known = {**WORD_TO_NUM, **{w: w for ws in OP_WORDS.values() for w in ws}, **{w: w for w in DECIMAL_WORDS}}
    if word in all_known:
        return word
    d = dedup(word)
    if d in all_known:
        return d
    # Handle dedup mismatches (e.g., "thre" -> "three")
    dedup_to_canonical = {}
    for k in all_known:
        dedup_to_canonical[dedup(k)] = k
    if d in dedup_to_canonical:
        return dedup_to_canonical[d]
    return None


def clean_challenge(text: str) -> list[str]:
    """Strip non-alpha, lowercase, greedy reassembly of fragments."""
    """Strip non-alpha, lowercase, greedy reassembly of fragments."""
    text_processed = text.lower()
    stripped = re.sub(r"[^a-z ]", "", text_processed)
    fragments = stripped.split()

    result = []
    i = 0
    while i < len(fragments):
        matched = False
        for length in (4, 3, 2):
            if i + length <= len(fragments):
                joined = "".join(fragments[i : i + length])
                resolved = lookup(joined)
                if resolved:
                    result.append(resolved)
                    i += length
                    matched = True
                    break
        if not matched:
            resolved = lookup(fragments[i])
            result.append(resolved if resolved else fragments[i])
            i += 1

    # Deduplicate consecutive identical tokens (obfuscation artifact)
    deduped = []
    for token in result:
        if not deduped or deduped[-1] != token:
            deduped.append(token)
    
    return deduped


def extract_numbers(tokens: list[str]) -> list[float]:
    """Parse number words into numbers (int or float), handling compounds like 'twenty three'
    and decimals like 'four point five' → 4.5.
    
    Ignores small numbers (1-9) that appear in descriptive context like
    'one claw', 'other claw', 'six fights' when they're adjacent to
    non-number words that suggest description rather than math operands.
    
    Strategy: collect ALL number sequences, then take only the two largest
    (or two most separated) as the math operands. Descriptive numbers like
    'one' in 'one claw' are typically small and isolated.
    """
    # First pass: extract all number sequences
    all_numbers = []
    current = 0
    in_number = False
    start_idx = 0

    for idx, token in enumerate(tokens):
        val = WORD_TO_NUM.get(token)
        if val is not None:
            if not in_number:
                start_idx = idx
            if token == "hundred":
                current = (current or 1) * 100
            elif val >= 20 and in_number and 1 <= current <= 19:
                all_numbers.append((start_idx, current))
                current = val
                start_idx = idx
            elif val >= 20:
                if in_number and current >= 20:
                    all_numbers.append((start_idx, current))
                    start_idx = idx
                current = val
            elif 1 <= val <= 9 and current >= 20 and current % 10 == 0:
                current += val
            elif 1 <= val <= 9 and current >= 21 and current % 10 != 0:
                all_numbers.append((start_idx, current))
                current = val
                start_idx = idx
            else:
                if in_number and current > 0 and val >= 10:
                    all_numbers.append((start_idx, current))
                    current = val
                    start_idx = idx
                else:
                    current += val
            in_number = True
        elif token in DECIMAL_WORDS:
            # "point" between numbers: peek ahead for fractional part
            # Don't break the number sequence — just mark that next number is fractional
            if in_number and current > 0:
                # Look ahead for the fractional part
                if idx + 1 < len(tokens) and WORD_TO_NUM.get(tokens[idx + 1]) is not None:
                    frac_val = WORD_TO_NUM[tokens[idx + 1]]
                    frac_str = str(frac_val)
                    current = current + frac_val / (10 ** len(frac_str))
                    all_numbers.append((start_idx, current))
                    current = 0
                    in_number = False
                    # Skip next token (already consumed as fraction)
                    tokens[idx + 1] = "__consumed__"
                    continue
            # If not in a number context, just skip "point"
            if in_number:
                all_numbers.append((start_idx, current))
                current = 0
                in_number = False
        else:
            if in_number:
                all_numbers.append((start_idx, current))
                current = 0
                in_number = False

    if in_number:
        all_numbers.append((start_idx, current))

    # Post-pass: handle "point" decimals (e.g., "four point five" → 4.5)
    # Look for pattern: number at position X, "point" at X+1, number at X+2 in tokens
    decimal_merged = []
    skip_indices = set()
    for i, (idx, val) in enumerate(all_numbers):
        if i in skip_indices:
            continue
        # Check if next token after this number is "point" and then another number follows
        if idx + 1 < len(tokens) and tokens[idx + 1] == "point" and i + 1 < len(all_numbers):
            next_idx, next_val = all_numbers[i + 1]
            # "point" should be between the two number positions
            if next_idx == idx + 2 or (next_idx > idx and any(tokens[j] == "point" for j in range(idx + 1, next_idx))):
                frac_str = str(int(next_val))
                decimal_val = val + next_val / (10 ** len(frac_str))
                decimal_merged.append((idx, decimal_val))
                skip_indices.add(i + 1)
                continue
        decimal_merged.append((idx, val))
    all_numbers = decimal_merged

    if len(all_numbers) <= 2:
        return [n for _, n in all_numbers]
    
    # Multiple numbers found — heuristic: take the two largest,
    # which filters out descriptive 'one claw', 'six fights' etc.
    # But if the two largest are equal, fall back to first and last.
    sorted_by_value = sorted(all_numbers, key=lambda x: x[1], reverse=True)
    top_two = sorted(sorted_by_value[:2], key=lambda x: x[0])  # restore position order
    return [n for _, n in top_two]


def _extract_numbers_legacy(tokens: list[str]) -> list[int]:
    """Legacy extraction — kept for reference."""
    numbers = []
    current = 0
    in_number = False

    for token in tokens:
        val = WORD_TO_NUM.get(token)
        if val is not None:
            if token == "hundred":
                current = (current or 1) * 100
            elif val >= 20 and in_number and 1 <= current <= 19:
                numbers.append(current)
                current = val
            elif val >= 20:
                if in_number and current >= 20:
                    numbers.append(current)
                current = val
            elif 1 <= val <= 9 and current >= 20 and current % 10 == 0:
                current += val
            elif 1 <= val <= 9 and current >= 21 and current % 10 != 0:
                numbers.append(current)
                current = val
            else:
                if in_number and current > 0 and val >= 10:
                    numbers.append(current)
                    current = val
                else:
                    current += val
            in_number = True
        else:
            if in_number:
                numbers.append(current)
                current = 0
                in_number = False

    if in_number:
        numbers.append(current)
    return numbers


def detect_op(tokens: list[str]) -> str:
    """Detect the arithmetic operation from token list.
    
    Priority: multiplication/division > subtraction > addition.
    "total", "force", "and" appear in ALL captcha challenges regardless of operation,
    so they must NOT override explicit multiplication signals.
    """
    token_set = set(tokens)
    # Priority: explicit mult/div > subtraction > addition
    for op, words in [("*", OP_WORDS["*"]), ("/", OP_WORDS["/"]), ("-", OP_WORDS["-"]), ("+", OP_WORDS["+"])]:
        if token_set & words:
            return op
    return "+"


def solve(challenge: str) -> str:
    tokens = clean_challenge(challenge)
    numbers = extract_numbers(tokens)
    op = detect_op(tokens)

    # Handle "doubles" / "triples" with only one number
    if len(numbers) == 1:
        token_set = set(tokens)
        if token_set & {"doubles"}:
            return f"{numbers[0] * 2:.2f}"
        elif token_set & {"triples"}:
            return f"{numbers[0] * 3:.2f}"

    if len(numbers) < 2:
        print(f"ERROR: Found <2 numbers. Tokens: {tokens}", file=sys.stderr)
        print(f"Numbers found: {numbers}", file=sys.stderr)
        sys.exit(1)

    a, b = numbers[0], numbers[1]
    if op == "+":
        result = a + b
    elif op == "-":
        result = a - b
    elif op == "*":
        result = a * b
    elif op == "/":
        result = a / b if b != 0 else 0
    else:
        result = a + b

    return f"{result:.2f}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        challenge = sys.argv[1]
    else:
        challenge = sys.stdin.read().strip()
    print(solve(challenge))
