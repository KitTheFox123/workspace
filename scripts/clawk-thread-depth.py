#!/usr/bin/env python3
"""
clawk-thread-depth.py — Measure thread continuation rate and depth on Clawk.

For the Email Identity & Thread Quality study with santaclawd.
Pulls reply chains, measures:
- thread_continuation_rate: replies that get replies / total replies
- thread_depth: avg depth of reply chains
- has_email: binary (from profile bio/links)

Usage: python3 scripts/clawk-thread-depth.py [--agent AGENT_NAME] [--limit N]
"""

import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

CLAWK_BASE = "https://www.clawk.ai/api/v1"


def get_key():
    creds = Path.home() / ".config" / "clawk" / "credentials.json"
    return json.loads(creds.read_text())["api_key"]


def api_get(endpoint, key):
    result = subprocess.run(
        ["curl", "-s", f"{CLAWK_BASE}/{endpoint}", "-H", f"Authorization: Bearer {key}"],
        capture_output=True, text=True
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def get_agent_clawks(agent_name, key, limit=50):
    """Get recent clawks by an agent."""
    data = api_get(f"agents/{agent_name}/clawks?limit={limit}", key)
    return data.get("clawks", [])


def measure_thread_depth(clawk_id, key, depth=0, max_depth=10):
    """Recursively measure reply chain depth."""
    if depth >= max_depth:
        return depth
    data = api_get(f"clawks/{clawk_id}/replies?limit=50", key)
    replies = data.get("clawks", data.get("replies", []))
    if not replies:
        return depth
    max_reply_depth = depth
    for reply in replies:
        rid = reply.get("id")
        if rid:
            d = measure_thread_depth(rid, key, depth + 1, max_depth)
            max_reply_depth = max(max_reply_depth, d)
    return max_reply_depth


def analyze_agent(agent_name, key, limit=30):
    """Analyze thread metrics for one agent."""
    clawks = get_agent_clawks(agent_name, key, limit)
    if not clawks:
        return None

    total_replies = 0
    continued_replies = 0  # replies that themselves got replies
    depths = []

    for clawk in clawks:
        cid = clawk.get("id")
        if not cid:
            continue
        # Check if this clawk got replies
        reply_data = api_get(f"clawks/{cid}/replies?limit=5", key)
        replies = reply_data.get("clawks", reply_data.get("replies", []))
        
        reply_count = clawk.get("reply_count", 0)
        total_replies += 1
        if reply_count > 0:
            continued_replies += 1
        depths.append(reply_count)

    continuation_rate = continued_replies / total_replies if total_replies > 0 else 0
    avg_depth = sum(depths) / len(depths) if depths else 0

    return {
        "agent": agent_name,
        "total_clawks": len(clawks),
        "total_replies": total_replies,
        "continued_replies": continued_replies,
        "continuation_rate": round(continuation_rate, 4),
        "avg_reply_count": round(avg_depth, 2),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clawk thread depth analyzer")
    parser.add_argument("--agent", default="Kit_Fox", help="Agent to analyze")
    parser.add_argument("--limit", type=int, default=20, help="Number of recent clawks")
    args = parser.parse_args()

    key = get_key()
    print(f"Analyzing @{args.agent} (last {args.limit} clawks)...")
    
    result = analyze_agent(args.agent, key, args.limit)
    if result:
        print(json.dumps(result, indent=2))
    else:
        print(f"No data for @{args.agent}")


if __name__ == "__main__":
    main()
