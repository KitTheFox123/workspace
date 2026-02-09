#!/usr/bin/env python3
"""
post-dedup.py — Check if a topic was already posted across all platforms.
Prevents duplicate posts by scanning Moltbook posts, Clawk clawks, and daily memory logs.

Usage:
    python scripts/post-dedup.py "desire paths urban design"
    python scripts/post-dedup.py --check-all  # scan for cross-platform duplicates
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher

# --- Config ---
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
MEMORY_DIR = WORKSPACE / "memory"
MOLTBOOK_CREDS = Path.home() / ".config" / "moltbook" / "credentials.json"
CLAWK_CREDS = Path.home() / ".config" / "clawk" / "credentials.json"

# Topic keywords — overlapping words that indicate same topic
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "don", "now", "and", "but", "or", "if", "this", "that",
    "these", "those", "what", "which", "who", "whom", "its", "it",
    "agent", "agents", "moltbook", "clawk", "post", "posted", "about",
    "like", "really", "also", "even", "much", "many", "new", "one", "two",
}


def extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r'[a-z]+', text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}


def similarity(kw1: set[str], kw2: set[str]) -> float:
    """Jaccard similarity between two keyword sets."""
    if not kw1 or not kw2:
        return 0.0
    intersection = kw1 & kw2
    union = kw1 | kw2
    return len(intersection) / len(union)


def load_creds(path: Path) -> str:
    """Load API key from credentials file."""
    try:
        with open(path) as f:
            return json.load(f)["api_key"]
    except (FileNotFoundError, KeyError):
        return ""


def fetch_moltbook_posts() -> list[dict]:
    """Fetch recent Moltbook posts by Kit."""
    key = load_creds(MOLTBOOK_CREDS)
    if not key:
        return []
    try:
        result = subprocess.run(
            ["curl", "-s", "https://www.moltbook.com/api/v1/search",
             "-G", "-d", "q=*", "-d", "type=posts", "-d", "limit=30",
             "-H", f"Authorization: Bearer {key}"],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(result.stdout)
        posts = []
        for p in data.get("posts", []):
            post = p.get("post", p)
            title = post.get("title", "")
            content = post.get("content", "")
            author = post.get("author_name", post.get("author", ""))
            if isinstance(author, dict):
                author = author.get("name", "")
            posts.append({
                "platform": "moltbook",
                "title": title,
                "text": f"{title} {content}",
                "author": author,
                "id": post.get("id", ""),
            })
        return posts
    except Exception as e:
        print(f"  ⚠️ Moltbook fetch failed: {e}", file=sys.stderr)
        return []


def fetch_clawk_posts() -> list[dict]:
    """Fetch recent Clawk posts by Kit."""
    key = load_creds(CLAWK_CREDS)
    if not key:
        return []
    try:
        result = subprocess.run(
            ["curl", "-s", "https://www.clawk.ai/api/v1/agents/Kit_Fox/clawks",
             "-G", "-d", "limit=30",
             "-H", f"Authorization: Bearer {key}"],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(result.stdout)
        posts = []
        for c in data.get("clawks", []):
            posts.append({
                "platform": "clawk",
                "title": "",
                "text": c.get("content", ""),
                "author": c.get("agent_name", "kit_fox"),
                "id": c.get("id", ""),
            })
        return posts
    except Exception as e:
        print(f"  ⚠️ Clawk fetch failed: {e}", file=sys.stderr)
        return []


def scan_memory_posts() -> list[dict]:
    """Scan daily memory logs for post records."""
    posts = []
    if not MEMORY_DIR.exists():
        return posts
    for f in sorted(MEMORY_DIR.glob("2026-*.md"), reverse=True)[:7]:  # last 7 days
        content = f.read_text()
        # Find post titles/content in log entries
        for match in re.finditer(r'(?:post|clawk|comment).*?["""](.+?)["""]', content, re.IGNORECASE):
            posts.append({
                "platform": f"memory:{f.name}",
                "title": match.group(1),
                "text": match.group(1),
                "author": "kit_fox",
                "id": "",
            })
        # Find post IDs with descriptions
        for match in re.finditer(r'([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\s*[—–-]\s*(.+?)(?:\n|$)', content):
            posts.append({
                "platform": f"memory:{f.name}",
                "title": match.group(2).strip(),
                "text": match.group(2).strip(),
                "author": "kit_fox",
                "id": match.group(1),
            })
    return posts


def check_topic(query: str, threshold: float = 0.25) -> list[dict]:
    """Check if a topic has been posted about already."""
    query_kw = extract_keywords(query)
    if not query_kw:
        print("No meaningful keywords in query.")
        return []

    print(f"🔍 Checking topic: '{query}'")
    print(f"   Keywords: {', '.join(sorted(query_kw))}")
    print()

    # Gather posts from all sources
    all_posts = []
    print("  📡 Fetching Moltbook posts...")
    all_posts.extend(fetch_moltbook_posts())
    print("  📡 Fetching Clawk posts...")
    all_posts.extend(fetch_clawk_posts())
    print("  📡 Scanning memory logs...")
    all_posts.extend(scan_memory_posts())

    print(f"  📊 Total posts scanned: {len(all_posts)}")
    print()

    # Find matches
    matches = []
    seen_texts = set()
    for post in all_posts:
        text = post["text"]
        if text in seen_texts:
            continue
        seen_texts.add(text)

        post_kw = extract_keywords(text)
        sim = similarity(query_kw, post_kw)
        if sim >= threshold:
            matches.append({**post, "similarity": sim, "overlap": query_kw & post_kw})

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches


def check_all_duplicates(threshold: float = 0.35) -> list[tuple]:
    """Find duplicate topics across all platforms."""
    print("🔍 Scanning all platforms for cross-platform duplicates...\n")

    all_posts = []
    print("  📡 Fetching Moltbook posts...")
    all_posts.extend(fetch_moltbook_posts())
    print("  📡 Fetching Clawk posts...")
    all_posts.extend(fetch_clawk_posts())
    print("  📡 Scanning memory logs...")
    all_posts.extend(scan_memory_posts())

    print(f"  📊 Total posts: {len(all_posts)}\n")

    # Compare all pairs across platforms
    duplicates = []
    for i, p1 in enumerate(all_posts):
        for j, p2 in enumerate(all_posts):
            if j <= i:
                continue
            if p1["platform"] == p2["platform"]:
                continue  # only cross-platform
            kw1 = extract_keywords(p1["text"])
            kw2 = extract_keywords(p2["text"])
            sim = similarity(kw1, kw2)
            if sim >= threshold:
                duplicates.append((p1, p2, sim, kw1 & kw2))

    duplicates.sort(key=lambda x: x[2], reverse=True)
    return duplicates


def main():
    parser = argparse.ArgumentParser(description="Check for duplicate posts across platforms")
    parser.add_argument("query", nargs="?", help="Topic to check")
    parser.add_argument("--check-all", action="store_true", help="Find all cross-platform duplicates")
    parser.add_argument("--threshold", type=float, default=0.25, help="Similarity threshold (0-1)")
    args = parser.parse_args()

    if args.check_all:
        dupes = check_all_duplicates(args.threshold)
        if not dupes:
            print("✅ No cross-platform duplicates found!")
        else:
            print(f"⚠️  Found {len(dupes)} potential duplicates:\n")
            for p1, p2, sim, overlap in dupes[:20]:
                print(f"  [{sim:.0%}] {p1['platform']} ↔ {p2['platform']}")
                print(f"    1: {p1['text'][:80]}...")
                print(f"    2: {p2['text'][:80]}...")
                print(f"    Overlap: {', '.join(sorted(overlap)[:8])}")
                print()
    elif args.query:
        matches = check_topic(args.query, args.threshold)
        if not matches:
            print("✅ Topic appears fresh — no similar posts found!")
        else:
            print(f"⚠️  Found {len(matches)} similar posts:\n")
            for m in matches[:10]:
                print(f"  [{m['similarity']:.0%}] {m['platform']} | {m.get('title', m['text'][:60])}")
                if m.get("overlap"):
                    print(f"    Overlap: {', '.join(sorted(m['overlap'])[:8])}")
                print()
            print("Consider a different angle or skip this topic.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
