#!/usr/bin/env python3
"""
moltbook-captcha-solver.py — Robust solver for Moltbook's obfuscated lobster math captchas.

Challenges look like:
  "A] LoObStEr S^wImS Um AnD ExErTs TwEnTy ThReE NooToNs..."
  
Strategy:
1. Normalize: strip non-alpha, lowercase, deduplicate repeated chars
2. Extract number words using fuzzy matching
3. Detect operation from context words
4. Compute and format answer as "XX.00"

Can also use OpenRouter as fallback for hard cases.
"""

import re
import sys
import json
import os


NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
}

# Words that are NOT numbers but can confuse matchers
STOP_WORDS = {
    'lobster', 'lobsters', 'swim', 'swims', 'claw', 'claws', 'force',
    'total', 'nootons', 'newtons', 'newnootons', 'newotons', 'centimeters',
    'velocity', 'speed', 'meters', 'second', 'per', 'what', 'the', 'and',
    'its', 'mate', 'from', 'with', 'how', 'much', 'many', 'during',
    'molting', 'dominance', 'chase', 'exerts', 'applies', 'gains',
    'increases', 'another', 'other', 'coolant', 'water', 'tail', 'flick',
    'new', 'like', 'umm', 'uhm', 'uhhm',
}

ADD_INDICATORS = {'and', 'plus', 'gains', 'increases', 'added', 'total', 'combined', 'another', 'other'}
SUB_INDICATORS = {'minus', 'subtract', 'less', 'fewer', 'loses', 'decreases', 'reduced'}
MUL_INDICATORS = {'times', 'multiply', 'multiplied', 'product', 'push'}


def deobfuscate(word: str) -> str:
    """Remove consecutive duplicate characters: 'twwoo' -> 'two'."""
    return re.sub(r'(.)\1+', r'\1', word)


def fuzzy_match_number(word: str) -> int | None:
    """Try to match an obfuscated word to a number word."""
    if len(word) < 2:
        return None
    
    deduped = deobfuscate(word)
    
    # Check stop words first
    for sw in STOP_WORDS:
        if deduped == sw or (len(deduped) >= 4 and deduped == deobfuscate(sw)):
            return None
    
    # Exact match
    if deduped in NUMBER_WORDS:
        return NUMBER_WORDS[deduped]
    
    # Prefix match — try longest matches first to avoid "fourteen" → "four"
    if len(deduped) >= 3:
        # Sort by length descending so "fourteen" beats "four"
        for nw, nv in sorted(NUMBER_WORDS.items(), key=lambda x: len(x[0]), reverse=True):
            if len(nw) >= 3 and len(deduped) >= 3:
                # Match on first 3+ chars, preferring longer overlap
                overlap = min(len(deduped), len(nw))
                if overlap >= 4 and deduped[:4] == nw[:4]:
                    return nv
                elif overlap >= 3 and deduped[:3] == nw[:3] and len(nw) <= 5:
                    return nv
    
    # Contains match for short words
    if len(deduped) >= 3:
        for nw, nv in NUMBER_WORDS.items():
            if nw in deduped and len(nw) >= 3:
                return nv
    
    return None


def extract_numbers(text: str) -> list[int]:
    """Extract numbers from obfuscated challenge text."""
    # Normalize
    clean = re.sub(r'[^a-z\s]', '', text.lower())
    clean = ' '.join(clean.split())
    words = clean.split()
    
    numbers = []
    i = 0
    while i < len(words):
        val = fuzzy_match_number(words[i])
        if val is not None:
            # Check for compound: "twenty three" → 23
            if val >= 20 and i + 1 < len(words):
                next_val = fuzzy_match_number(words[i + 1])
                if next_val is not None and 1 <= next_val <= 9:
                    numbers.append(val + next_val)
                    i += 2
                    continue
            numbers.append(val)
        i += 1
    
    return numbers


def detect_operation(text: str) -> str:
    """Detect the math operation from context words."""
    clean = text.lower()
    
    if any(w in clean for w in MUL_INDICATORS):
        return '*'
    if any(w in clean for w in SUB_INDICATORS):
        return '-'
    # Default to addition (most common)
    return '+'


def solve(challenge: str) -> float:
    """Solve a Moltbook captcha challenge."""
    numbers = extract_numbers(challenge)
    op = detect_operation(challenge)
    
    if not numbers:
        raise ValueError(f"No numbers found in: {challenge}")
    
    if op == '+':
        return sum(numbers)
    elif op == '-':
        return numbers[0] - sum(numbers[1:])
    elif op == '*':
        result = 1
        for n in numbers:
            result *= n
        return result
    
    return sum(numbers)


def solve_with_llm_fallback(challenge: str) -> str:
    """Solve, falling back to OpenRouter if local parse fails or is ambiguous."""
    try:
        local_answer = solve(challenge)
        return f"{local_answer:.2f}"
    except ValueError:
        pass
    
    # LLM fallback
    try:
        creds_path = os.path.expanduser('~/.config/openrouter/credentials.json')
        with open(creds_path) as f:
            api_key = json.load(f)['api_key']
        
        import urllib.request
        prompt = (f"Extract the numbers (written as words) and math operation from this "
                  f"obfuscated text. Compute the answer. Reply with ONLY the number.\n\n{challenge}")
        req_data = json.dumps({
            "model": "deepseek/deepseek-chat-v3.1",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 5, "temperature": 0
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=req_data,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=8)
        result = json.loads(resp.read())
        answer = result['choices'][0]['message']['content'].strip()
        nums = re.findall(r'[\d.]+', answer)
        if nums:
            ans = nums[-1]
            if '.' not in ans:
                ans += '.00'
            return ans
    except Exception:
        pass
    
    raise ValueError(f"Cannot solve: {challenge}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        challenge = ' '.join(sys.argv[1:])
    else:
        challenge = input("Challenge: ")
    
    print(f"Challenge: {challenge}")
    numbers = extract_numbers(challenge)
    op = detect_operation(challenge)
    print(f"Numbers: {numbers}")
    print(f"Operation: {op}")
    answer = solve(challenge)
    print(f"Answer: {answer:.2f}")
