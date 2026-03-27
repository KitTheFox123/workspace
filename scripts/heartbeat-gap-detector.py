#!/usr/bin/env python3
"""
heartbeat-gap-detector.py — Detect and report heartbeat gaps from daily memory files.

Scans memory/YYYY-MM-DD.md files for heartbeat timestamps, identifies gaps,
and reports total uptime vs downtime. Useful for understanding availability
patterns and optimizing heartbeat intervals.

Kit 🦊 — 2026-03-27
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


def parse_heartbeat_times(filepath: Path) -> list[datetime]:
    """Extract UTC timestamps from heartbeat headers in daily memory files."""
    times = []
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
    if not date_match:
        return times
    
    date_str = date_match.group(1)
    
    with open(filepath) as f:
        for line in f:
            # Match patterns like "## 04:14 UTC" or "## 06:31 UTC — Heartbeat"
            m = re.match(r'^##\s+(\d{1,2}):(\d{2})\s+UTC', line)
            if m:
                hour, minute = int(m.group(1)), int(m.group(2))
                try:
                    dt = datetime.fromisoformat(f"{date_str}T{hour:02d}:{minute:02d}:00+00:00")
                    times.append(dt)
                except ValueError:
                    pass
    
    return sorted(times)


def analyze_gaps(times: list[datetime], expected_interval_min: int = 20) -> dict:
    """Analyze gaps between heartbeats."""
    if len(times) < 2:
        return {"heartbeats": len(times), "gaps": [], "total_gap_hours": 0}
    
    threshold = timedelta(minutes=expected_interval_min * 2)  # 2x expected = gap
    gaps = []
    total_gap = timedelta()
    
    for i in range(1, len(times)):
        delta = times[i] - times[i-1]
        if delta > threshold:
            gaps.append({
                "start": times[i-1].isoformat(),
                "end": times[i].isoformat(),
                "duration_hours": round(delta.total_seconds() / 3600, 1),
                "missed_heartbeats": int(delta.total_seconds() / (expected_interval_min * 60)) - 1
            })
            total_gap += delta - timedelta(minutes=expected_interval_min)
    
    first = times[0]
    last = times[-1]
    total_span = last - first
    active_time = total_span - total_gap
    
    return {
        "heartbeats": len(times),
        "first": first.isoformat(),
        "last": last.isoformat(),
        "span_hours": round(total_span.total_seconds() / 3600, 1),
        "active_hours": round(active_time.total_seconds() / 3600, 1),
        "gap_hours": round(total_gap.total_seconds() / 3600, 1),
        "uptime_pct": round(active_time / total_span * 100, 1) if total_span.total_seconds() > 0 else 0,
        "gaps": gaps,
        "longest_gap_hours": max((g["duration_hours"] for g in gaps), default=0)
    }


def main():
    memory_dir = Path(__file__).parent.parent / "memory"
    if not memory_dir.exists():
        print(f"Memory directory not found: {memory_dir}")
        sys.exit(1)
    
    # Find recent daily files
    files = sorted(memory_dir.glob("2026-03-*.md"))[-7:]  # Last 7 days of March
    
    if not files:
        print("No daily memory files found.")
        sys.exit(1)
    
    print("=" * 60)
    print("HEARTBEAT GAP ANALYSIS")
    print("=" * 60)
    
    all_times = []
    for f in files:
        times = parse_heartbeat_times(f)
        all_times.extend(times)
        if times:
            analysis = analyze_gaps(times)
            print(f"\n{f.name}: {analysis['heartbeats']} heartbeats, "
                  f"{analysis.get('span_hours', 0)}h span, "
                  f"{analysis.get('uptime_pct', 0)}% uptime")
            for gap in analysis["gaps"]:
                print(f"  ⚠️  GAP: {gap['duration_hours']}h "
                      f"({gap['missed_heartbeats']} missed) "
                      f"{gap['start']} → {gap['end']}")
    
    if len(all_times) >= 2:
        print("\n" + "=" * 60)
        print("AGGREGATE (last 7 days)")
        print("=" * 60)
        overall = analyze_gaps(all_times)
        print(f"Total heartbeats: {overall['heartbeats']}")
        print(f"Total span: {overall['span_hours']}h")
        print(f"Active: {overall['active_hours']}h ({overall['uptime_pct']}%)")
        print(f"Gap time: {overall['gap_hours']}h")
        print(f"Longest gap: {overall['longest_gap_hours']}h")
        print(f"Total gaps: {len(overall['gaps'])}")


if __name__ == "__main__":
    main()
