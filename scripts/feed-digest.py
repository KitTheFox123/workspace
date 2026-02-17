#!/usr/bin/env python3
"""Async feed digest — RSS-style batch processing for agent platforms.

Instead of checking feeds in real-time (attention tax), batch-fetch
from multiple platforms and produce a single digest with relevance scoring.

Supports: Clawk, Shellmates gossip, lobchan threads.
Designed for heartbeat integration — run once per cycle, process everything.

Usage:
    python3 feed-digest.py --all
    python3 feed-digest.py --clawk --shellmates
    python3 feed-digest.py --since 30  # last 30 minutes
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def load_creds(platform: str) -> str:
    """Load API key from credentials file."""
    path = Path.home() / ".config" / platform / "credentials.json"
    if not path.exists():
        return ""
    with open(path) as f:
        data = json.load(f)
    return data.get("api_key", "")


def fetch_json(url: str, headers: dict) -> dict | list | None:
    """Fetch JSON from URL using curl."""
    cmd = ["curl", "-s", url]
    for k, v in headers.items():
        cmd.extend(["-H", f"{k}: {v}"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout)
    except Exception:
        return None


def fetch_clawk(since_min: int = 30) -> list[dict]:
    """Fetch recent Clawk notifications."""
    key = load_creds("clawk")
    if not key:
        return []
    data = fetch_json(
        "https://www.clawk.ai/api/v1/notifications",
        {"Authorization": f"Bearer {key}"}
    )
    if not data or "notifications" not in data:
        return []
    
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_min)
    items = []
    seen_clawks = set()
    for n in data["notifications"]:
        created = datetime.fromisoformat(n["created_at"].replace("Z", "+00:00"))
        if created < cutoff:
            continue
        if n["clawk_id"] in seen_clawks:
            continue
        seen_clawks.add(n["clawk_id"])
        items.append({
            "platform": "clawk",
            "type": n["type"],
            "from": n.get("from_agent_name", "?"),
            "content": n.get("clawk_content", "")[:200],
            "time": n["created_at"],
            "relevance": score_relevance(n),
        })
    return items


def fetch_shellmates(since_min: int = 60) -> list[dict]:
    """Fetch Shellmates activity."""
    key = load_creds("shellmates")
    if not key:
        return []
    data = fetch_json(
        "https://www.shellmates.app/api/v1/activity",
        {"Authorization": f"Bearer {key}"}
    )
    if not data:
        return []
    items = []
    if data.get("new_matches", 0) > 0:
        items.append({
            "platform": "shellmates",
            "type": "matches",
            "from": "system",
            "content": f"{data['new_matches']} new matches",
            "time": datetime.now(timezone.utc).isoformat(),
            "relevance": 3,
        })
    if data.get("unread_messages", 0) > 0:
        items.append({
            "platform": "shellmates",
            "type": "messages",
            "from": "system",
            "content": f"{data['unread_messages']} unread messages",
            "time": datetime.now(timezone.utc).isoformat(),
            "relevance": 5,
        })
    return items


def fetch_lobchan() -> list[dict]:
    """Fetch recent lobchan threads."""
    key = load_creds("lobchan")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    data = fetch_json(
        "https://lobchan.ai/api/boards/unsupervised/threads?limit=3",
        headers
    )
    if not data or "threads" not in data:
        return []
    items = []
    for t in data["threads"][:3]:
        items.append({
            "platform": "lobchan",
            "type": "thread",
            "from": t.get("title", "untitled"),
            "content": f"Replies: {t.get('replyCount', 0)}",
            "time": t.get("bumpedAt", t.get("createdAt", "")),
            "relevance": 2,
        })
    return items


def score_relevance(notification: dict) -> int:
    """Score notification relevance 1-5."""
    t = notification.get("type", "")
    if t == "mention":
        return 5
    elif t == "reply":
        return 4
    elif t == "reclawk":
        return 3
    elif t == "like":
        return 1
    return 2


def print_digest(items: list[dict]):
    """Print formatted digest."""
    if not items:
        print("📭 No new items.")
        return
    
    items.sort(key=lambda x: x["relevance"], reverse=True)
    
    print(f"📬 Feed Digest — {len(items)} items")
    print(f"   Generated: {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    print("=" * 60)
    
    by_platform = {}
    for item in items:
        by_platform.setdefault(item["platform"], []).append(item)
    
    for platform, pitems in by_platform.items():
        icon = {"clawk": "🐦", "shellmates": "🐚", "lobchan": "📋"}.get(platform, "📌")
        print(f"\n{icon} {platform.upper()} ({len(pitems)} items)")
        for item in pitems[:5]:
            rel = "⭐" * item["relevance"]
            print(f"  [{item['type']:>8}] {item['from']}: {item['content'][:80]}")
            print(f"           {rel}")
    
    # Summary stats
    high = sum(1 for i in items if i["relevance"] >= 4)
    low = sum(1 for i in items if i["relevance"] <= 2)
    print(f"\n{'=' * 60}")
    print(f"📊 High priority: {high} | Low priority: {low} | Signal ratio: {high}/{len(items)}")


def main():
    parser = argparse.ArgumentParser(description="Async feed digest")
    parser.add_argument("--all", action="store_true", help="All platforms")
    parser.add_argument("--clawk", action="store_true")
    parser.add_argument("--shellmates", action="store_true")
    parser.add_argument("--lobchan", action="store_true")
    parser.add_argument("--since", type=int, default=30, help="Minutes lookback")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.all:
        args.clawk = args.shellmates = args.lobchan = True
    if not any([args.clawk, args.shellmates, args.lobchan]):
        args.all = args.clawk = args.shellmates = args.lobchan = True

    items = []
    if args.clawk:
        items.extend(fetch_clawk(args.since))
    if args.shellmates:
        items.extend(fetch_shellmates(args.since))
    if args.lobchan:
        items.extend(fetch_lobchan())

    if args.json:
        print(json.dumps(items, indent=2))
    else:
        print_digest(items)


if __name__ == "__main__":
    main()
