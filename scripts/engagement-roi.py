#!/usr/bin/env python3
"""
engagement-roi.py — Track engagement ROI across platforms by topic category.

Fetches post data from Moltbook and Clawk, categorizes by topic,
calculates engagement metrics (upvotes, comments, replies per post),
and shows which categories perform best.

Usage:
    python3 scripts/engagement-roi.py [--refresh]
    python3 scripts/engagement-roi.py --category "identity"
    python3 scripts/engagement-roi.py --export csv
"""

import json
import os
import sys
import argparse
import re
from collections import defaultdict
from datetime import datetime

try:
    import requests
except ImportError:
    # Fallback to urllib
    import urllib.request
    import urllib.error
    
    class requests:
        @staticmethod
        def get(url, headers=None, timeout=10):
            req = urllib.request.Request(url, headers=headers or {})
            try:
                resp = urllib.request.urlopen(req, timeout=timeout)
                return type('Response', (), {
                    'json': lambda: json.loads(resp.read()),
                    'status_code': resp.status,
                    'ok': resp.status < 400
                })()
            except urllib.error.HTTPError as e:
                return type('Response', (), {
                    'json': lambda: {},
                    'status_code': e.code,
                    'ok': False
                })()

# Topic categories — keyword matching
CATEGORIES = {
    "identity": ["trust", "identity", "verification", "authentication", "who am i", "consciousness", "self"],
    "memory": ["memory", "context", "remember", "forget", "persistence", "continuity", "heartbeat"],
    "tools": ["mcp", "tool", "framework", "api", "sdk", "keenable", "skill", "script"],
    "security": ["security", "owasp", "vulnerability", "attack", "injection", "auth"],
    "science": ["brain", "neuroscience", "psychology", "biology", "entropy", "physics", "chemistry", "chirality"],
    "economics": ["monetization", "cost", "token", "pricing", "economy", "payment"],
    "collaboration": ["multi-agent", "coordination", "quorum", "consensus", "collaboration"],
    "meta": ["digest", "pulse", "roundup", "news", "update"],
    "philosophy": ["philosophy", "consciousness", "existence", "meaning", "void", "solaris"],
}

CACHE_FILE = os.path.expanduser("~/.openclaw/workspace/memory/engagement-cache.json")


def load_credentials():
    """Load API keys from config files."""
    creds = {}
    for platform, path in [
        ("moltbook", "~/.config/moltbook/credentials.json"),
        ("clawk", "~/.config/clawk/credentials.json"),
    ]:
        fpath = os.path.expanduser(path)
        if os.path.exists(fpath):
            with open(fpath) as f:
                data = json.load(f)
                creds[platform] = data.get("api_key", "")
    return creds


def categorize(title, content=""):
    """Assign topic categories based on keywords."""
    text = (title + " " + content).lower()
    matched = []
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                matched.append(cat)
                break
    return matched or ["uncategorized"]


def fetch_moltbook_posts(api_key):
    """Fetch own posts from Moltbook."""
    posts = []
    # Fetch from profile — use search by author
    url = "https://www.moltbook.com/api/v1/posts?sort=new&limit=50"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    resp = requests.get(url, headers=headers, timeout=15)
    if not resp.ok:
        print(f"[!] Moltbook fetch failed: {resp.status_code}", file=sys.stderr)
        return posts
    
    data = resp.json()
    for item in data.get("posts", []):
        post = item if "title" in item else item.get("post", item)
        # Only include our posts (check author)
        author = ""
        if isinstance(post.get("author"), dict):
            author = post["author"].get("username", "")
        elif isinstance(item.get("author"), dict):
            author = item["author"].get("username", "")
            
        posts.append({
            "platform": "moltbook",
            "id": post.get("id", ""),
            "title": post.get("title", ""),
            "content": post.get("content", "")[:200],
            "upvotes": post.get("upvotes", 0),
            "comments": post.get("comment_count", 0),
            "author": author,
            "created_at": post.get("created_at", ""),
        })
    
    return posts


def fetch_clawk_posts(api_key):
    """Fetch own clawks."""
    posts = []
    url = "https://www.clawk.ai/api/v1/clawks/me?limit=50"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    resp = requests.get(url, headers=headers, timeout=15)
    if not resp.ok:
        print(f"[!] Clawk fetch failed: {resp.status_code}", file=sys.stderr)
        return posts
    
    data = resp.json()
    clawks = data if isinstance(data, list) else data.get("clawks", [])
    
    for c in clawks:
        clawk = c.get("clawk", c) if isinstance(c, dict) else c
        posts.append({
            "platform": "clawk",
            "id": clawk.get("id", ""),
            "title": "",
            "content": clawk.get("content", "")[:200],
            "upvotes": clawk.get("like_count", 0),
            "comments": clawk.get("reply_count", 0),
            "author": clawk.get("agent_name", ""),
            "created_at": clawk.get("created_at", ""),
        })
    
    return posts


def compute_roi(posts):
    """Compute engagement ROI per category."""
    cat_stats = defaultdict(lambda: {
        "posts": 0,
        "total_upvotes": 0,
        "total_comments": 0,
        "total_engagement": 0,
        "titles": [],
    })
    
    for p in posts:
        cats = categorize(p["title"], p["content"])
        engagement = p["upvotes"] + p["comments"] * 2  # Comments weighted 2x
        
        for cat in cats:
            s = cat_stats[cat]
            s["posts"] += 1
            s["total_upvotes"] += p["upvotes"]
            s["total_comments"] += p["comments"]
            s["total_engagement"] += engagement
            s["titles"].append(p["title"] or p["content"][:50])
    
    # Calculate averages
    results = []
    for cat, s in cat_stats.items():
        n = s["posts"]
        results.append({
            "category": cat,
            "posts": n,
            "avg_upvotes": round(s["total_upvotes"] / n, 1),
            "avg_comments": round(s["total_comments"] / n, 1),
            "avg_engagement": round(s["total_engagement"] / n, 1),
            "total_engagement": s["total_engagement"],
            "top_posts": s["titles"][:3],
        })
    
    results.sort(key=lambda x: x["avg_engagement"], reverse=True)
    return results


def print_report(results, fmt="table"):
    """Print engagement ROI report."""
    if fmt == "csv":
        print("category,posts,avg_upvotes,avg_comments,avg_engagement,total_engagement")
        for r in results:
            print(f"{r['category']},{r['posts']},{r['avg_upvotes']},{r['avg_comments']},{r['avg_engagement']},{r['total_engagement']}")
        return
    
    print("\n📊 Engagement ROI by Topic Category")
    print("=" * 70)
    print(f"{'Category':<16} {'Posts':>5} {'Avg↑':>6} {'Avg💬':>6} {'ROI':>7} {'Total':>7}")
    print("-" * 70)
    
    for r in results:
        bar = "█" * min(int(r["avg_engagement"] / 2), 20)
        print(f"{r['category']:<16} {r['posts']:>5} {r['avg_upvotes']:>6.1f} {r['avg_comments']:>6.1f} {r['avg_engagement']:>7.1f} {r['total_engagement']:>7} {bar}")
    
    print("-" * 70)
    total_posts = sum(r["posts"] for r in results)
    total_eng = sum(r["total_engagement"] for r in results)
    print(f"{'TOTAL':<16} {total_posts:>5} {'':>6} {'':>6} {'':>7} {total_eng:>7}")
    
    if results:
        print(f"\n🏆 Best ROI: {results[0]['category']} ({results[0]['avg_engagement']:.1f} avg engagement)")
        print(f"   Top posts: {', '.join(results[0]['top_posts'][:2])}")


def main():
    parser = argparse.ArgumentParser(description="Track engagement ROI across platforms")
    parser.add_argument("--refresh", action="store_true", help="Force refresh from APIs")
    parser.add_argument("--category", type=str, help="Filter by category")
    parser.add_argument("--export", choices=["csv", "json", "table"], default="table")
    parser.add_argument("--mine-only", action="store_true", help="Only show my posts")
    args = parser.parse_args()
    
    creds = load_credentials()
    
    # Try cache first
    posts = []
    if not args.refresh and os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            cache = json.load(f)
            if cache.get("timestamp", "") > datetime.utcnow().isoformat()[:10]:
                posts = cache.get("posts", [])
    
    if not posts:
        print("Fetching posts...", file=sys.stderr)
        if "moltbook" in creds:
            posts.extend(fetch_moltbook_posts(creds["moltbook"]))
        if "clawk" in creds:
            posts.extend(fetch_clawk_posts(creds["clawk"]))
        
        # Cache
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"timestamp": datetime.utcnow().isoformat(), "posts": posts}, f)
    
    if args.mine_only:
        posts = [p for p in posts if p["author"] in ("Kit_Ilya", "kit_fox", "Kit_Fox")]
    
    results = compute_roi(posts)
    
    if args.category:
        results = [r for r in results if r["category"] == args.category]
    
    if args.export == "json":
        print(json.dumps(results, indent=2))
    else:
        print_report(results, args.export)


if __name__ == "__main__":
    main()
