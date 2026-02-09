#!/usr/bin/env python3
"""memory-hygiene.py — Detect stale, contradictory, or bloated memory files.

Semmelweis-inspired: invisible contamination in the files you trust.
Checks for:
- Files not updated in N days (stale)
- Files over size threshold (bloated)
- Duplicate content across files (redundant)
- TODO/FIXME/pending items never resolved
"""
import os, sys, re, argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

def check_staleness(memory_dir, days=3):
    """Find files not modified in N days."""
    stale = []
    cutoff = datetime.now().timestamp() - (days * 86400)
    for f in Path(memory_dir).rglob("*.md"):
        if f.stat().st_mtime < cutoff:
            age = (datetime.now().timestamp() - f.stat().st_mtime) / 86400
            stale.append((str(f), round(age, 1)))
    return sorted(stale, key=lambda x: -x[1])

def check_bloat(memory_dir, max_kb=50):
    """Find files over size threshold."""
    bloated = []
    for f in Path(memory_dir).rglob("*.md"):
        size_kb = f.stat().st_size / 1024
        if size_kb > max_kb:
            bloated.append((str(f), round(size_kb, 1)))
    return sorted(bloated, key=lambda x: -x[1])

def check_pending(memory_dir):
    """Find unresolved TODOs/pending/retry items."""
    pending = []
    patterns = [r'\bpending\b', r'\bretry\b', r'\bTODO\b', r'\bFIXME\b', r'\bqueued\b']
    combined = re.compile('|'.join(patterns), re.IGNORECASE)
    for f in Path(memory_dir).rglob("*.md"):
        try:
            content = f.read_text()
            for i, line in enumerate(content.split('\n'), 1):
                if combined.search(line):
                    pending.append((str(f), i, line.strip()[:80]))
        except:
            pass
    return pending

def check_duplicates(memory_dir):
    """Find files with high content overlap (simple line-based)."""
    file_lines = {}
    for f in Path(memory_dir).rglob("*.md"):
        try:
            lines = set(l.strip() for l in f.read_text().split('\n') if len(l.strip()) > 30)
            if lines:
                file_lines[str(f)] = lines
        except:
            pass
    
    dupes = []
    files = list(file_lines.items())
    for i, (f1, l1) in enumerate(files):
        for f2, l2 in files[i+1:]:
            overlap = len(l1 & l2)
            if overlap > 5:
                dupes.append((f1, f2, overlap))
    return sorted(dupes, key=lambda x: -x[2])

def main():
    p = argparse.ArgumentParser(description="Memory file hygiene checker")
    p.add_argument("--dir", default="memory", help="Memory directory")
    p.add_argument("--stale-days", type=int, default=3)
    p.add_argument("--max-kb", type=int, default=50)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    print("🧼 Memory Hygiene Report")
    print("=" * 40)
    
    stale = check_staleness(args.dir, args.stale_days)
    if stale:
        print(f"\n⚠️  STALE ({args.stale_days}+ days old):")
        for f, age in stale[:10]:
            print(f"  {age}d — {f}")
    else:
        print(f"\n✅ No files older than {args.stale_days} days")

    bloated = check_bloat(args.dir, args.max_kb)
    if bloated:
        print(f"\n⚠️  BLOATED (>{args.max_kb}KB):")
        for f, kb in bloated[:10]:
            print(f"  {kb}KB — {f}")
    else:
        print(f"\n✅ No files over {args.max_kb}KB")

    pending = check_pending(args.dir)
    if pending:
        print(f"\n⚠️  UNRESOLVED ({len(pending)} items):")
        for f, line, text in pending[:10]:
            print(f"  {f}:{line} — {text}")
    else:
        print("\n✅ No pending items")

    dupes = check_duplicates(args.dir)
    if dupes:
        print(f"\n⚠️  OVERLAP:")
        for f1, f2, n in dupes[:5]:
            print(f"  {n} shared lines: {os.path.basename(f1)} ↔ {os.path.basename(f2)}")
    else:
        print("\n✅ No significant overlap")

if __name__ == "__main__":
    main()
