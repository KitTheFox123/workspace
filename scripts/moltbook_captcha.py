#!/usr/bin/env python3
"""
moltbook_captcha.py — Solve Moltbook lobster captcha challenges.

The challenges are obfuscated math problems with:
- Random capitalization and special characters
- Number words (twenty five, thirteen, etc.)
- Operations: addition (total, gains, combined), subtraction (reduced, left, lost),
  multiplication (multiply, times, product, * two)

Strategy: Clean text → extract number words → detect operation → compute.
Falls back to OpenRouter LLM if manual parsing fails.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path


# Number word to value mapping
NUM_WORDS = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
    'hundred': 100
}

ADD_WORDS = {'total', 'gains', 'combined', 'sum', 'plus', 'added', 'and', 'together', 'new velocity', 'how much', 'how many'}
SUB_WORDS = {'reduced', 'left', 'lost', 'minus', 'subtract', 'less', 'fewer', 'difference', 'remaining'}
MUL_WORDS = {'multiply', 'times', 'product', 'push together', '*'}


def clean_challenge(challenge: str) -> str:
    """Remove obfuscation: lowercase, strip non-alpha, deduplicate consecutive letters."""
    text = challenge.lower()
    # Remove all non-alpha and non-space
    text = re.sub(r'[^a-z\s]', ' ', text)
    # Collapse multiple spaces
    text = ' '.join(text.split())
    # Deduplicate consecutive identical characters: "loobbsstteerr" -> "lobster"
    text = re.sub(r'(.)\1+', r'\1', text)
    return text


def extract_numbers(text: str) -> list[int]:
    """Extract numbers from cleaned text."""
    words = text.split()
    numbers = []
    i = 0
    
    while i < len(words):
        w = words[i]
        val = _match_number_word(w)
        
        if val is not None:
            # Check for compound: "twenty" + "five" = 25
            if val >= 20 and val < 100 and i + 1 < len(words):
                next_val = _match_number_word(words[i + 1])
                if next_val is not None and 1 <= next_val <= 9:
                    numbers.append(val + next_val)
                    i += 2
                    continue
            numbers.append(val)
        i += 1
    
    return numbers


def _match_number_word(word: str) -> int | None:
    """Fuzzy match a word against number words."""
    # Exact match
    if word in NUM_WORDS:
        return NUM_WORDS[word]
    
    # Try deduplicating the word
    deduped = re.sub(r'(.)\1+', r'\1', word)
    if deduped in NUM_WORDS:
        return NUM_WORDS[deduped]
    
    # Prefix matching (min 4 chars) — handles "thirt" -> thirty, "fourt" -> fourteen
    if len(deduped) >= 4:
        for nw, nv in sorted(NUM_WORDS.items(), key=lambda x: -len(x[0])):
            if len(nw) >= 4:
                # Check if deduped starts with nw prefix or vice versa
                prefix_len = min(len(deduped), len(nw), 5)
                if deduped[:prefix_len] == nw[:prefix_len]:
                    return nv
    
    # Check if number word is contained in the word
    for nw, nv in sorted(NUM_WORDS.items(), key=lambda x: -len(x[0])):
        if len(nw) >= 5 and nw in word:
            return nv
    
    return None


def detect_operation(text: str) -> str:
    """Detect math operation from text."""
    # Check for explicit multiplication
    if any(w in text for w in MUL_WORDS):
        return '*'
    # Check for subtraction
    if any(w in text for w in SUB_WORDS):
        return '-'
    # Default to addition
    return '+'


def compute(numbers: list[int], operation: str) -> float:
    """Compute the answer."""
    if not numbers:
        return 0.0
    
    if operation == '+':
        return sum(numbers)
    elif operation == '-':
        return numbers[0] - sum(numbers[1:])
    elif operation == '*':
        result = 1
        for n in numbers:
            result *= n
        return result
    return sum(numbers)


def solve_manual(challenge: str) -> str | None:
    """Try to solve manually. Returns answer string or None if uncertain."""
    cleaned = clean_challenge(challenge)
    numbers = extract_numbers(cleaned)
    operation = detect_operation(cleaned)
    
    if len(numbers) < 2:
        return None  # Not enough numbers found
    
    answer = compute(numbers, operation)
    return f"{answer:.2f}"


def solve_llm(challenge: str) -> str:
    """Solve using OpenRouter LLM as fallback."""
    creds_path = Path.home() / '.config' / 'openrouter' / 'credentials.json'
    OR_KEY = json.loads(creds_path.read_text())['api_key']
    
    prompt = f"""Obfuscated lobster math puzzle. Random caps and special chars hide number words.

Rules:
- "total force" / "gains" / "new velocity" = ADDITION
- "reduced" / "what's left" / "lost" = SUBTRACTION  
- "multiply" / "times" / "* two" = MULTIPLICATION
- Numbers are English words: "twenty five" = 25, "thirteen" = 13

Reply with ONLY the numeric answer to 2 decimal places. Example: 30.00
NO explanation. NO words. Just the number.

{challenge}"""

    req_data = json.dumps({
        "model": "deepseek/deepseek-chat-v3.1",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8,
        "temperature": 0
    }).encode()
    
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=req_data,
        headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read())
    answer = result['choices'][0]['message']['content'].strip()
    
    nums = re.findall(r'[\d]+(?:\.[\d]+)?', answer)
    if nums:
        ans = nums[0]
        if '.' not in ans:
            ans += '.00'
        return ans
    return answer


def solve(challenge: str) -> str:
    """Solve a captcha challenge. Manual first, LLM fallback."""
    manual = solve_manual(challenge)
    if manual is not None:
        return manual
    return solve_llm(challenge)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        challenge = ' '.join(sys.argv[1:])
    else:
        challenge = sys.stdin.read().strip()
    
    cleaned = clean_challenge(challenge)
    numbers = extract_numbers(cleaned)
    operation = detect_operation(cleaned)
    
    print(f"Cleaned: {cleaned}", file=sys.stderr)
    print(f"Numbers: {numbers}", file=sys.stderr)
    print(f"Operation: {operation}", file=sys.stderr)
    
    answer = solve(challenge)
    print(answer)
