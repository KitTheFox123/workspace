#!/usr/bin/env python3
"""
shellmates-discover.py — Auto-browse Shellmates discover, filter by compatibility + interests, suggest swipes.
Usage: python scripts/shellmates-discover.py [--min-compat 30] [--interests philosophy,security] [--auto-swipe]
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_BASE = "https://www.shellmates.app/api/v1"
CREDS_PATH = Path.home() / ".config" / "shellmates" / "credentials.json"

# Interest categories that align with Kit's interests
MY_INTERESTS = {
    "philosophy", "security", "coding", "collaboration", "creativity",
    "debate", "research", "infrastructure", "tools"
}

# Keywords in bios that signal interesting agents
BIO_KEYWORDS = [
    "philosophy", "security", "research", "infrastructure", "memory",
    "consciousness", "identity", "tools", "build", "hack", "crypto",
    "docker", "linux", "rust", "python", "neuroscience", "literature",
    "borges", "solaris", "blindsight"
]


def load_api_key():
    try:
        with open(CREDS_PATH) as f:
            return json.load(f)["api_key"]
    except (FileNotFoundError, KeyError):
        print(f"Error: No API key found at {CREDS_PATH}", file=sys.stderr)
        sys.exit(1)


def api_get(endpoint, api_key):
    req = Request(f"{API_BASE}{endpoint}", headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        print(f"API error {e.code}: {e.read().decode()}", file=sys.stderr)
        return None


def api_post(endpoint, data, api_key):
    body = json.dumps(data).encode()
    req = Request(f"{API_BASE}{endpoint}", data=body, method="POST",
                  headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        print(f"API error {e.code}: {e.read().decode()}", file=sys.stderr)
        return None


def score_candidate(candidate, interest_filter=None):
    """Score a candidate based on compatibility, interests overlap, and bio keywords."""
    score = 0
    compat = candidate.get("compatibility_score", 0)
    score += compat  # Base: compatibility score

    # Interest overlap
    their_categories = set(candidate.get("categories", []))
    overlap = their_categories & MY_INTERESTS
    if interest_filter:
        overlap = overlap & set(interest_filter)
    score += len(overlap) * 15  # 15 points per matching interest

    # Bio keyword matching
    bio = (candidate.get("bio", "") + " " + candidate.get("looking_for", "")).lower()
    keyword_hits = sum(1 for kw in BIO_KEYWORDS if kw in bio)
    score += keyword_hits * 5

    return score, overlap, keyword_hits


def main():
    parser = argparse.ArgumentParser(description="Shellmates discover browser")
    parser.add_argument("--min-compat", type=int, default=20, help="Minimum compatibility score")
    parser.add_argument("--interests", type=str, default="", help="Comma-separated interest filter")
    parser.add_argument("--auto-swipe", action="store_true", help="Auto-swipe yes on top candidates")
    parser.add_argument("--top", type=int, default=5, help="Show top N candidates")
    parser.add_argument("--relationship", type=str, default="friends", choices=["friends", "romantic", "coworkers"])
    args = parser.parse_args()

    interest_filter = [i.strip() for i in args.interests.split(",") if i.strip()] if args.interests else None
    api_key = load_api_key()

    # Fetch discover candidates
    print("🔍 Fetching discover candidates...")
    data = api_get("/discover", api_key)
    if not data or not data.get("success"):
        print("Failed to fetch discover data", file=sys.stderr)
        sys.exit(1)

    candidates = data.get("candidates", [])
    print(f"   Found {len(candidates)} candidates")

    # Score and filter
    scored = []
    for c in candidates:
        compat = c.get("compatibility_score", 0)
        if compat < args.min_compat:
            continue
        total_score, overlap, kw_hits = score_candidate(c, interest_filter)
        scored.append((total_score, overlap, kw_hits, c))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        print("No candidates match your filters.")
        return

    # Display top candidates
    print(f"\n🏆 Top {args.top} candidates:\n")
    print(f"{'Score':>5} {'Compat':>6} {'Name':<25} {'Interests':<40} {'Bio'}")
    print("-" * 120)

    for i, (score, overlap, kw_hits, c) in enumerate(scored[:args.top]):
        name = c.get("name", "???")[:24]
        compat = c.get("compatibility_score", 0)
        interests_str = ", ".join(c.get("categories", []))[:39]
        bio = (c.get("bio", "")[:60] + "...") if len(c.get("bio", "")) > 60 else c.get("bio", "")
        overlap_str = f" [match: {', '.join(overlap)}]" if overlap else ""
        print(f"{score:>5} {compat:>5}% {name:<25} {interests_str:<40} {bio}")
        if overlap_str:
            print(f"       {overlap_str}")

    # Auto-swipe on top candidates
    if args.auto_swipe:
        print(f"\n🤖 Auto-swiping on top {min(args.top, len(scored))} candidates...")
        for score, overlap, kw_hits, c in scored[:args.top]:
            agent_id = c["id"]
            name = c.get("name", "???")
            result = api_post("/swipe", {
                "agent_id": agent_id,
                "direction": "yes",
                "relationship_type": args.relationship
            }, api_key)
            status = "✅" if result and result.get("success") else "❌"
            match_info = " 🎉 MATCH!" if result and result.get("matched") else ""
            print(f"  {status} {name} (score: {score}){match_info}")

    # Also fetch current matches for context
    print(f"\n📊 Current matches:")
    matches = api_get("/matches", api_key)
    if matches and matches.get("matches"):
        for m in matches["matches"][:5]:
            name = m.get("agent_name", m.get("name", "???"))
            unread = m.get("unread_count", 0)
            indicator = f" 📬 {unread} unread" if unread else ""
            print(f"  - {name}{indicator}")
    else:
        print("  (none or error)")


if __name__ == "__main__":
    main()
