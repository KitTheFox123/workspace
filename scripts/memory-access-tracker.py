#!/usr/bin/env python3
"""
memory-access-tracker.py — Track which memory files are actually READ during sessions.
Inspired by Physarum slime trails: reinforced paths persist, unused ones decay.

Scans daily logs to find which files are referenced (Read/read/cat) and ranks them
by access frequency. Identifies load-bearing vs decorative memory files.

Usage:
  python3 scripts/memory-access-tracker.py                  # scan today
  python3 scripts/memory-access-tracker.py --days 7         # scan last 7 days
  python3 scripts/memory-access-tracker.py --stale 3        # files unread for 3+ days
  python3 scripts/memory-access-tracker.py --json           # machine-readable output
"""

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path(os.path.expanduser("~/.openclaw/workspace/memory"))
WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))


def scan_daily_log(filepath: Path) -> Counter:
    """Extract file references from a daily log."""
    refs = Counter()
    if not filepath.exists():
        return refs
    
    content = filepath.read_text(errors="ignore")
    
    # Match patterns like: Read memory/foo.md, read SOUL.md, cat scripts/bar.sh
    patterns = [
        r'(?:Read|read|Reading|reading)\s+[`"]?([a-zA-Z0-9_./-]+\.\w+)',
        r'(?:cat|head|tail)\s+[`"]?([a-zA-Z0-9_./-]+\.\w+)',
        r'file_path["\s:]+([a-zA-Z0-9_./-]+\.\w+)',
    ]
    
    for pattern in patterns:
        for match in re.findall(pattern, content):
            # Normalize path
            clean = match.strip('`"\'')
            refs[clean] += 1
    
    return refs


def get_all_memory_files() -> list:
    """List all files in memory/ and key workspace files."""
    files = []
    for f in MEMORY_DIR.rglob("*.md"):
        files.append(str(f.relative_to(WORKSPACE)))
    
    # Add key workspace files
    for name in ["SOUL.md", "HEARTBEAT.md", "MEMORY.md", "TOOLS.md", "AGENTS.md"]:
        p = WORKSPACE / name
        if p.exists():
            files.append(name)
    
    return sorted(set(files))


def main():
    parser = argparse.ArgumentParser(description="Track memory file access patterns")
    parser.add_argument("--days", type=int, default=1, help="Days to scan (default: 1)")
    parser.add_argument("--stale", type=int, default=None, help="Show files unread for N+ days")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    total_refs = Counter()
    daily_refs = {}  # date -> Counter
    
    today = datetime.utcnow().date()
    
    for i in range(args.days):
        d = today - timedelta(days=i)
        date_str = d.isoformat()
        log_path = MEMORY_DIR / f"{date_str}.md"
        refs = scan_daily_log(log_path)
        total_refs += refs
        daily_refs[date_str] = refs
    
    all_files = get_all_memory_files()
    
    if args.stale is not None:
        # Find files with zero reads in the last N days
        stale = [f for f in all_files if total_refs.get(f, 0) == 0]
        if args.json:
            print(json.dumps({"stale_files": stale, "threshold_days": args.stale}))
        else:
            print(f"📂 Files unread in last {args.days} day(s):")
            for f in stale:
                size = (WORKSPACE / f).stat().st_size if (WORKSPACE / f).exists() else 0
                print(f"  ⚠️  {f} ({size:,} bytes)")
            print(f"\nTotal: {len(stale)} stale / {len(all_files)} tracked")
        return
    
    # Rank by access frequency
    ranked = total_refs.most_common()
    
    if args.json:
        print(json.dumps({
            "period_days": args.days,
            "total_references": sum(total_refs.values()),
            "unique_files_accessed": len(total_refs),
            "total_files_tracked": len(all_files),
            "rankings": [{"file": f, "reads": c} for f, c in ranked],
            "never_read": [f for f in all_files if f not in total_refs],
        }, indent=2))
    else:
        print(f"📊 Memory Access Report ({args.days} day{'s' if args.days > 1 else ''})")
        print(f"   {sum(total_refs.values())} total references, {len(total_refs)} unique files\n")
        
        print("🔥 Most accessed (load-bearing):")
        for f, count in ranked[:15]:
            bar = "█" * min(count, 30)
            print(f"  {count:3d} {bar} {f}")
        
        never = [f for f in all_files if f not in total_refs]
        if never:
            print(f"\n❄️  Never read ({len(never)} files):")
            for f in never[:10]:
                print(f"  · {f}")
            if len(never) > 10:
                print(f"  ... and {len(never) - 10} more")


if __name__ == "__main__":
    main()
