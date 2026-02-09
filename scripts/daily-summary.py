#!/usr/bin/env python3
"""Daily summary — generate compact end-of-day stats from daily log.

Usage:
    python3 scripts/daily-summary.py                    # Today
    python3 scripts/daily-summary.py --date 2026-02-08  # Specific date
    python3 scripts/daily-summary.py --compare 2026-02-07 2026-02-08  # Side-by-side
"""

import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"


def analyze_day(filepath):
    """Analyze a daily log file and return stats."""
    content = filepath.read_text()

    # Count heartbeats
    heartbeats = len(re.findall(r"##\s*Heartbeat", content))

    # Count writing actions (look for verified comments, clawk posts, etc)
    clawk_posts = len(re.findall(r"Clawk standalone|Clawk reply|Clawk post", content, re.IGNORECASE))
    moltbook_comments = len(re.findall(r"Moltbook comment|Moltbook post|Moltbook digest", content, re.IGNORECASE))
    shellmates_writes = len(re.findall(r"Shellmates gossip|Shellmates message", content, re.IGNORECASE))
    total_writes = clawk_posts + moltbook_comments + shellmates_writes

    # Count builds
    builds = len(re.findall(r"### Build Action|Built `scripts/", content))

    # Extract research topics
    topics = []
    for match in re.finditer(r"###?\s*(?:Non-Agent )?Research[:\s]+(.+?)(?:\n|$)", content, re.IGNORECASE):
        topic = match.group(1).strip().rstrip("✅").strip()
        if topic and len(topic) > 3:
            topics.append(topic)
    topics = list(dict.fromkeys(topics))  # dedup preserving order

    # Extract script names built
    scripts = []
    for match in re.finditer(r"Built `scripts/(.+?)`", content):
        scripts.append(match.group(1))
    scripts = list(dict.fromkeys(scripts))

    # Count verified moltbook comments
    verified = len(re.findall(r"✅\)", content))

    # Count Keenable feedback submissions
    keenable = len(re.findall(r"Keenable feedback.*submitted", content, re.IGNORECASE))

    # File size
    size_kb = filepath.stat().st_size / 1024

    # Time range
    hours = []
    for match in re.finditer(r"##\s*Heartbeat\s*~?\s*(\d{1,2}):\d{0,2}\s*UTC", content):
        hours.append(int(match.group(1)))

    return {
        "heartbeats": heartbeats,
        "total_writes": total_writes,
        "clawk": clawk_posts,
        "moltbook": moltbook_comments,
        "shellmates": shellmates_writes,
        "builds": builds,
        "topics": topics,
        "scripts": scripts,
        "verified_comments": verified,
        "keenable_feedback": keenable,
        "file_size_kb": round(size_kb, 1),
        "hours_active": len(set(hours)),
        "first_hour": min(hours) if hours else None,
        "last_hour": max(hours) if hours else None,
    }


def print_summary(stats, date_str):
    """Print a compact summary."""
    print(f"\n🦊 Daily Summary — {date_str}")
    print("=" * 50)
    print(f"📊 Heartbeats: {stats['heartbeats']}")
    print(f"✍️  Total writes: {stats['total_writes']} (Clawk: {stats['clawk']}, Moltbook: {stats['moltbook']}, Shellmates: {stats['shellmates']})")
    print(f"🔨 Builds: {stats['builds']}")
    print(f"🔬 Research topics: {len(stats['topics'])}")
    print(f"✅ Verified comments: {stats['verified_comments']}")
    print(f"🔍 Keenable feedback: {stats['keenable_feedback']}x")
    print(f"📁 Log size: {stats['file_size_kb']}KB")

    if stats['first_hour'] is not None:
        print(f"⏰ Active: {stats['first_hour']:02d}:00 - {stats['last_hour']:02d}:00 UTC ({stats['hours_active']}h)")

    if stats['topics']:
        print(f"\n📚 Topics researched:")
        for i, t in enumerate(stats['topics'], 1):
            print(f"   {i}. {t[:70]}")

    if stats['scripts']:
        print(f"\n🔧 Scripts built:")
        for s in stats['scripts']:
            print(f"   • {s}")

    print()


def print_compare(date1, stats1, date2, stats2):
    """Print side-by-side comparison of two days."""
    print(f"\n🦊 Compare: {date1} vs {date2}")
    print("=" * 60)

    rows = [
        ("📊 Heartbeats", stats1["heartbeats"], stats2["heartbeats"]),
        ("✍️  Total writes", stats1["total_writes"], stats2["total_writes"]),
        ("   Clawk", stats1["clawk"], stats2["clawk"]),
        ("   Moltbook", stats1["moltbook"], stats2["moltbook"]),
        ("   Shellmates", stats1["shellmates"], stats2["shellmates"]),
        ("🔨 Builds", stats1["builds"], stats2["builds"]),
        ("🔬 Research topics", len(stats1["topics"]), len(stats2["topics"])),
        ("✅ Verified comments", stats1["verified_comments"], stats2["verified_comments"]),
        ("🔍 Keenable feedback", stats1["keenable_feedback"], stats2["keenable_feedback"]),
        ("📁 Log size (KB)", stats1["file_size_kb"], stats2["file_size_kb"]),
        ("⏰ Hours active", stats1["hours_active"], stats2["hours_active"]),
    ]

    header = f"{'Metric':<25} {date1:>12} {date2:>12} {'Δ':>8}"
    print(header)
    print("-" * len(header))

    for label, v1, v2 in rows:
        if isinstance(v1, float) and isinstance(v2, float):
            delta = v2 - v1
            delta_str = f"{delta:+.1f}"
        elif isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            delta = v2 - v1
            delta_str = f"{delta:+d}" if isinstance(delta, int) else f"{delta:+.1f}"
        else:
            delta_str = "—"
        print(f"{label:<25} {str(v1):>12} {str(v2):>12} {delta_str:>8}")

    # Show unique topics per day
    t1_only = [t for t in stats1["topics"] if t not in stats2["topics"]]
    t2_only = [t for t in stats2["topics"] if t not in stats1["topics"]]
    if t1_only:
        print(f"\n📚 Only in {date1}:")
        for t in t1_only:
            print(f"   • {t[:60]}")
    if t2_only:
        print(f"\n📚 Only in {date2}:")
        for t in t2_only:
            print(f"   • {t[:60]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="End-of-day summary from daily log")
    parser.add_argument("--date", "-d", help="Date (YYYY-MM-DD)")
    parser.add_argument("--compare", nargs=2, metavar="DATE", help="Compare two dates side-by-side")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.compare:
        d1, d2 = args.compare
        f1, f2 = MEMORY_DIR / f"{d1}.md", MEMORY_DIR / f"{d2}.md"
        missing = []
        if not f1.exists():
            missing.append(d1)
        if not f2.exists():
            missing.append(d2)
        if missing:
            print(f"❌ Missing log(s): {', '.join(missing)}")
            return
        s1, s2 = analyze_day(f1), analyze_day(f2)
        if args.json:
            import json
            print(json.dumps({d1: s1, d2: s2}, indent=2))
        else:
            print_compare(d1, s1, d2, s2)
        return

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    filepath = MEMORY_DIR / f"{date_str}.md"

    if not filepath.exists():
        print(f"❌ No file: {filepath}")
        return

    stats = analyze_day(filepath)

    if args.json:
        import json
        print(json.dumps(stats, indent=2))
    else:
        print_summary(stats, date_str)


if __name__ == "__main__":
    main()
