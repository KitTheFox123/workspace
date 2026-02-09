#!/usr/bin/env python3
"""Moltbook comment poster with auto-captcha solving.
Replaces bash moltbook-comment.sh. Uses Python per Ilya's preference."""

import json, re, sys, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "https://www.moltbook.com/api/v1"

def load_key():
    creds = Path.home() / ".config/moltbook/credentials.json"
    return json.loads(creds.read_text())["api_key"]

WORD_MAP = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000,
}

def parse_lobster_challenge(challenge: str) -> float | None:
    """Parse obfuscated lobster captcha and solve the math."""
    # Strip lobster formatting
    clean = re.sub(r'[^a-zA-Z0-9+\-*/=?._ ]', '', challenge)
    clean = clean.lower().strip()
    
    # Extract numbers (word form)
    tokens = clean.split()
    
    # Reassemble split words: "tw en ty" -> "twenty"
    merged = []
    buf = ""
    for t in tokens:
        candidate = buf + t
        # Check if any word starts with candidate
        if any(w.startswith(candidate) for w in WORD_MAP):
            if candidate in WORD_MAP:
                merged.append(candidate)
                buf = ""
            else:
                buf = candidate
        else:
            if buf and buf in WORD_MAP:
                merged.append(buf)
            elif buf:
                # Try partial matches
                for w in WORD_MAP:
                    if w.startswith(buf):
                        break
                merged.append(buf)
            buf = t if any(w.startswith(t) for w in WORD_MAP) else ""
            if not any(w.startswith(t) for w in WORD_MAP):
                merged.append(t)
    if buf:
        merged.append(buf)
    
    # Find numbers and operators
    numbers = []
    operators = []
    
    i = 0
    while i < len(merged):
        w = merged[i]
        if w in WORD_MAP:
            val = WORD_MAP[w]
            # Handle compound: "twenty three" = 23
            if i + 1 < len(merged) and merged[i+1] in WORD_MAP:
                next_val = WORD_MAP[merged[i+1]]
                if val >= 20 and next_val < 10:
                    val += next_val
                    i += 1
            numbers.append(val)
        elif w in ('+', 'plus', 'add', 'added', 'adds', 'gains', 'gain'):
            operators.append('+')
        elif w in ('-', 'minus', 'subtract', 'loses', 'lose', 'lost'):
            operators.append('-')
        elif w in ('*', 'times', 'multiplied', 'product'):
            operators.append('*')
        i += 1
    
    if len(numbers) >= 2 and len(operators) >= 1:
        result = numbers[0]
        for j, op in enumerate(operators):
            if j + 1 < len(numbers):
                n = numbers[j + 1]
                if op == '+': result += n
                elif op == '-': result -= n
                elif op == '*': result *= n
        return float(result)
    return None

def api_call(method, path, data=None, key=None):
    """Make API call to Moltbook."""
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        return json.loads(e.read())

def post_comment(post_id: str, content: str, parent_id: str = None):
    """Post a comment and auto-solve captcha."""
    key = load_key()
    data = {"content": content}
    if parent_id:
        data["parent_id"] = parent_id
    
    resp = api_call("POST", f"/posts/{post_id}/comments", data, key)
    
    comment_id = resp.get("comment", {}).get("id")
    verification = resp.get("verification", {})
    code = verification.get("code")
    challenge = verification.get("challenge", "")
    
    if not code:
        print(f"Error: {resp.get('error', 'unknown')}")
        return None
    
    print(f"Comment: {comment_id}")
    print(f"Challenge: {challenge}")
    
    answer = parse_lobster_challenge(challenge)
    if answer is None:
        print(f"Could not solve captcha!")
        return None
    
    answer_str = f"{answer:.2f}"
    print(f"Answer: {answer_str}")
    
    verify = api_call("POST", "/verify", {
        "verification_code": code,
        "answer": answer_str
    }, key)
    
    if verify.get("success"):
        print(f"✅ Verified: {comment_id}")
        return comment_id
    else:
        print(f"❌ Verify failed: {verify.get('error')}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: moltbook_comment.py <post_id> <content> [parent_id]")
        sys.exit(1)
    
    post_id = sys.argv[1]
    content = sys.argv[2]
    parent_id = sys.argv[3] if len(sys.argv) > 3 else None
    result = post_comment(post_id, content, parent_id)
    sys.exit(0 if result else 1)
