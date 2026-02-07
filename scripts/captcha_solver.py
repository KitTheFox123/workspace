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
    "+": {"plus", "adds", "gains", "total", "and", "combined", "sum"},
    "-": {"minus", "subtract", "less", "loses", "drops", "slows"},
    "*": {"product", "multiplied", "times", "strikes"},
    "/": {"divided", "split"},
}

# Dedup: collapse consecutive duplicate chars (e.g., "threeee" -> "thre")
def dedup(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def lookup(word: str) -> str | None:
    """Try to match a word (possibly obfuscated) to a known token."""
    all_known = {**WORD_TO_NUM, **{w: w for ws in OP_WORDS.values() for w in ws}}
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
    stripped = re.sub(r"[^a-z ]", "", text.lower())
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
    return result


def extract_numbers(tokens: list[str]) -> list[int]:
    """Parse number words into integers, handling compounds like 'twenty three'."""
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
    """Detect the arithmetic operation from token list."""
    token_set = set(tokens)
    for op, words in [("*", OP_WORDS["*"]), ("-", OP_WORDS["-"]), ("/", OP_WORDS["/"]), ("+", OP_WORDS["+"])]:
        if token_set & words:
            return op
    return "+"


def solve(challenge: str) -> str:
    tokens = clean_challenge(challenge)
    numbers = extract_numbers(tokens)
    op = detect_op(tokens)

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
