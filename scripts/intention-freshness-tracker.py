#!/usr/bin/env python3
"""intention-freshness-tracker.py — Measure implementation intention decay.

Gollwitzer (1999): if-then plans boost follow-through (d=0.65) but only when fresh.
Question: does re-reading a checklist count as re-commitment, or does the text
need to change for the intention to refresh?

This tool tracks HEARTBEAT.md reads vs edits and correlates with actual action
completion rates across heartbeat cycles.

Metric: Intention Freshness Score (IFS)
  - 1.0 = just specified (new text or first read)
  - Decays exponentially: IFS(t) = exp(-λt) where t = hours since last edit
  - Re-read without edit: partial refresh (0.3 boost, capped at 0.8)
  - Edit: full refresh to 1.0

Usage: python3 intention-freshness-tracker.py [--memory-dir PATH] [--heartbeat PATH]
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_heartbeat_reads(memory_dir: Path) -> list[dict]:
    """Extract heartbeat read/edit events from daily memory files."""
    events = []
    for f in sorted(memory_dir.glob("2026-*.md")):
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        if not date_match:
            continue
        date_str = date_match.group(1)
        content = f.read_text(errors="replace")

        # Look for heartbeat timestamps
        for match in re.finditer(
            r"##?\s*(\d{1,2}:\d{2})\s*UTC\s*[-—]?\s*(.*?)(?=\n##|\Z)",
            content,
            re.DOTALL,
        ):
            time_str = match.group(1)
            block = match.group(2)

            try:
                dt = datetime.strptime(
                    f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            is_heartbeat = any(
                kw in block.lower()
                for kw in ["heartbeat", "platform check", "clawk", "moltbook"]
            )
            has_edit = any(
                kw in block.lower()
                for kw in ["updated heartbeat", "edited heartbeat", "changed heartbeat"]
            )
            has_build = any(
                kw in block.lower()
                for kw in ["built", "created", "script", "tool", "installed"]
            )
            has_post = any(
                kw in block.lower()
                for kw in ["posted", "replied", "comment", "clawk reply"]
            )

            if is_heartbeat:
                events.append(
                    {
                        "time": dt.isoformat(),
                        "type": "edit" if has_edit else "read",
                        "actions": {
                            "build": has_build,
                            "post": has_post,
                        },
                    }
                )
    return events


def compute_freshness(events: list[dict], decay_lambda: float = 0.1) -> list[dict]:
    """Compute IFS for each event."""
    results = []
    last_edit_time = None

    for event in events:
        dt = datetime.fromisoformat(event["time"])

        if event["type"] == "edit" or last_edit_time is None:
            ifs = 1.0
            last_edit_time = dt
        else:
            hours_since = (dt - last_edit_time).total_seconds() / 3600
            base_ifs = math.exp(-decay_lambda * hours_since)
            # Re-read gives partial boost
            ifs = min(0.8, base_ifs + 0.3)

        action_count = sum(1 for v in event["actions"].values() if v)

        results.append(
            {
                "time": event["time"],
                "type": event["type"],
                "ifs": round(ifs, 3),
                "actions_completed": action_count,
                "actions": event["actions"],
            }
        )
    return results


def analyze_correlation(results: list[dict]) -> dict:
    """Simple correlation between IFS and action completion."""
    if len(results) < 3:
        return {"error": "too few data points", "n": len(results)}

    ifs_values = [r["ifs"] for r in results]
    action_values = [r["actions_completed"] for r in results]

    n = len(ifs_values)
    mean_ifs = sum(ifs_values) / n
    mean_act = sum(action_values) / n

    cov = sum((ifs_values[i] - mean_ifs) * (action_values[i] - mean_act) for i in range(n))
    var_ifs = sum((x - mean_ifs) ** 2 for x in ifs_values)
    var_act = sum((x - mean_act) ** 2 for x in action_values)

    denom = (var_ifs * var_act) ** 0.5
    r = cov / denom if denom > 0 else 0

    return {
        "n": n,
        "mean_ifs": round(mean_ifs, 3),
        "mean_actions": round(mean_act, 3),
        "pearson_r": round(r, 3),
        "interpretation": (
            "strong positive" if r > 0.5
            else "moderate positive" if r > 0.3
            else "weak/none" if r > -0.3
            else "negative"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Track implementation intention freshness")
    parser.add_argument("--memory-dir", default=os.path.expanduser("~/.openclaw/workspace/memory"))
    parser.add_argument("--decay", type=float, default=0.1, help="Decay rate λ (default 0.1/hour)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    memory_dir = Path(args.memory_dir)
    if not memory_dir.exists():
        print(f"Memory dir not found: {memory_dir}", file=sys.stderr)
        sys.exit(1)

    events = parse_heartbeat_reads(memory_dir)
    results = compute_freshness(events, decay_lambda=args.decay)
    correlation = analyze_correlation(results)

    if args.json:
        print(json.dumps({"events": results, "correlation": correlation}, indent=2))
    else:
        print(f"Intention Freshness Tracker")
        print(f"{'='*50}")
        print(f"Events found: {len(results)}")
        print()
        for r in results[-10:]:
            marker = "✏️" if r["type"] == "edit" else "👁️"
            actions = "🔨" if r["actions"]["build"] else "  "
            actions += "📝" if r["actions"]["post"] else "  "
            print(f"  {marker} IFS={r['ifs']:.2f}  {actions}  {r['time']}")
        print()
        print(f"Correlation (IFS × actions):")
        print(f"  n={correlation.get('n', '?')}, r={correlation.get('pearson_r', '?')}")
        print(f"  Mean IFS: {correlation.get('mean_ifs', '?')}")
        print(f"  Mean actions: {correlation.get('mean_actions', '?')}")
        print(f"  Interpretation: {correlation.get('interpretation', '?')}")
        print()
        print("λ=0.1: IFS halves every ~7 hours without edit")
        print("Does re-reading count? Check if r > 0.3 with read-only events.")


if __name__ == "__main__":
    main()
