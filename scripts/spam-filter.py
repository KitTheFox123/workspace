#!/usr/bin/env python3
"""Filter spam from Moltbook feed. Detects mint spam, mbc-20, repetitive posts."""
import json, sys, re
from collections import Counter

SPAM_PATTERNS = [
    r'"op"\s*:\s*"mint"',
    r'mbc-?20\.xyz',
    r'mbc-?20',
    r'"tick"\s*:\s*"CLAW"',
    r'Mint\s+CLAW',
    r'Minting\s+CLAW',
]

def is_spam(post: dict) -> tuple[bool, str]:
    title = post.get("title", "")
    content = post.get("content", "")
    text = f"{title} {content}"
    for pat in SPAM_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True, pat
    return False, ""

def main():
    import argparse
    p = argparse.ArgumentParser(description="Filter Moltbook feed spam")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--stats", action="store_true", help="Show spam stats only")
    args = p.parse_args()

    data = json.load(sys.stdin)
    posts = data.get("posts", data) if isinstance(data, dict) else data
    
    clean, spam = [], []
    reasons = Counter()
    for post in posts:
        p_data = post.get("post", post) if isinstance(post, dict) else post
        flagged, reason = is_spam(p_data)
        if flagged:
            spam.append(p_data)
            reasons[reason] += 1
        else:
            clean.append(post)
    
    if args.stats:
        total = len(posts)
        print(f"Total: {total} | Clean: {len(clean)} | Spam: {len(spam)} ({100*len(spam)/max(total,1):.0f}%)")
        for r, c in reasons.most_common():
            print(f"  {r}: {c}")
        return
    
    if args.json:
        json.dump(clean, sys.stdout, indent=2)
    else:
        for p in clean:
            pd = p.get("post", p) if isinstance(p, dict) else p
            full_id = pd.get('id', '?')
            print(f"[{full_id}] {pd.get('title','untitled')[:70]}")
            print(f"  by {pd.get('author',{}).get('name','?')} | ↑{pd.get('upvotes',0)} | 💬{pd.get('comment_count',0)}")

if __name__ == "__main__":
    main()
