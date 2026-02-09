#!/usr/bin/env python3
"""Engagement heatmap — visualize posting activity by hour from daily logs.

Usage:
    python3 scripts/engagement-heatmap.py                    # Today
    python3 scripts/engagement-heatmap.py --date 2026-02-08  # Specific date
    python3 scripts/engagement-heatmap.py --all               # All daily files
"""

import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"


def extract_hours(filepath):
    """Extract heartbeat hours from a daily log."""
    content = filepath.read_text()
    hours = []

    # Match "## Heartbeat ~HH:MM UTC" patterns
    for match in re.finditer(r"##\s*Heartbeat\s*~?\s*(\d{1,2}):?\d{0,2}\s*UTC", content):
        hours.append(int(match.group(1)))

    # Also match timestamps in writing action lines
    for match in re.finditer(r"(\d{1,2}):\d{2}\s*UTC", content):
        h = int(match.group(1))
        if 0 <= h <= 23:
            hours.append(h)

    return hours


def render_heatmap(hour_counts, date_label=""):
    """Render a terminal heatmap."""
    blocks = " ░▒▓█"
    max_count = max(hour_counts.values()) if hour_counts else 1

    print(f"\n📊 Activity Heatmap {date_label}\n")
    print("Hour  Activity  Count")
    print("-" * 40)

    for h in range(24):
        count = hour_counts.get(h, 0)
        if max_count > 0:
            level = min(4, int(count / max_count * 4))
        else:
            level = 0
        bar = blocks[level] * 20 if count > 0 else "·" * 20
        label = f"{h:02d}:00"
        print(f"{label}  {bar}  {count:>3}")

    total = sum(hour_counts.values())
    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 0
    active_hours = sum(1 for c in hour_counts.values() if c > 0)

    print(f"\nTotal events: {total}")
    print(f"Active hours: {active_hours}/24")
    print(f"Peak hour: {peak_hour:02d}:00 ({hour_counts.get(peak_hour, 0)} events)")

    # Quiet periods
    quiet = []
    streak = 0
    start = None
    for h in range(24):
        if hour_counts.get(h, 0) == 0:
            if streak == 0:
                start = h
            streak += 1
        else:
            if streak >= 3:
                quiet.append(f"{start:02d}:00-{h:02d}:00 ({streak}h)")
            streak = 0
    if streak >= 3:
        quiet.append(f"{start:02d}:00-{(start+streak)%24:02d}:00 ({streak}h)")

    if quiet:
        print(f"Quiet periods: {', '.join(quiet)}")


def main():
    parser = argparse.ArgumentParser(description="Activity heatmap from daily logs")
    parser.add_argument("--date", "-d", help="Date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="All daily files combined")
    args = parser.parse_args()

    if args.all:
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
        all_hours = Counter()
        files = 0
        for f in sorted(MEMORY_DIR.iterdir()):
            if f.is_file() and pattern.match(f.name):
                hours = extract_hours(f)
                for h in hours:
                    all_hours[h] += 1
                files += 1
        render_heatmap(all_hours, f"(all {files} files)")
    else:
        date_str = args.date or datetime.now().strftime("%Y-%m-%d")
        filepath = MEMORY_DIR / f"{date_str}.md"
        if not filepath.exists():
            print(f"❌ No file: {filepath}")
            return
        hours = extract_hours(filepath)
        hour_counts = Counter(hours)
        render_heatmap(hour_counts, f"({date_str})")


if __name__ == "__main__":
    main()
