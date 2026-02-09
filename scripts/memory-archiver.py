#!/usr/bin/env python3
"""Memory archiver — move old daily logs to archive with extracted insights.

Usage:
    python scripts/memory-archiver.py 2026-02-07          # Archive specific date
    python scripts/memory-archiver.py --older-than 3       # Archive files older than N days
    python scripts/memory-archiver.py --dry-run 2026-02-07 # Preview without moving
    python scripts/memory-archiver.py --list                # List archivable files
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"
ARCHIVE_DIR = MEMORY_DIR / "archive"
GRADUATION_FILE = MEMORY_DIR / "archive" / "graduation-candidates.md"


def find_daily_files():
    """Find all YYYY-MM-DD.md files in memory/."""
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
    files = []
    for f in MEMORY_DIR.iterdir():
        if f.is_file() and pattern.match(f.name):
            date_str = f.stem
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d").date()
                size = f.stat().st_size
                files.append((date, f, size))
            except ValueError:
                continue
    return sorted(files, key=lambda x: x[0])


def extract_insights(filepath):
    """Extract key insights from a daily log file."""
    content = filepath.read_text()
    insights = []

    # Extract research topics
    for match in re.finditer(r"###?\s*(?:Non-Agent )?Research[:\s]+(.+?)(?:\n|$)", content):
        insights.append(f"Research: {match.group(1).strip()}")

    # Extract build actions
    for match in re.finditer(r"###?\s*Build Action.*?\n(.+?)(?:\n\n|\n###|\Z)", content, re.DOTALL):
        first_line = match.group(1).strip().split("\n")[0]
        if first_line and not first_line.startswith("-"):
            insights.append(f"Build: {first_line[:100]}")

    # Extract key insights marked explicitly
    for match in re.finditer(r"\*\*(?:Key )?[Ii]nsight[s]?[:\*]*\*?\*?\s*(.+?)(?:\n|$)", content):
        insights.append(f"Insight: {match.group(1).strip()[:120]}")

    # Count heartbeats
    heartbeat_count = len(re.findall(r"##\s*Heartbeat", content))
    if heartbeat_count:
        insights.insert(0, f"Heartbeats: {heartbeat_count}")

    return insights


def format_size(size_bytes):
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def archive_file(date, filepath, dry_run=False):
    """Archive a daily log file."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dest = ARCHIVE_DIR / filepath.name
    size = filepath.stat().st_size

    # Extract insights before moving
    insights = extract_insights(filepath)

    if dry_run:
        print(f"[DRY RUN] Would archive: {filepath.name} ({format_size(size)})")
        if insights:
            for i in insights[:5]:
                print(f"  → {i}")
        return insights

    # Append graduation candidates
    with open(GRADUATION_FILE, "a") as f:
        f.write(f"\n## {date} ({format_size(size)})\n")
        f.write(f"Archived: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n")
        for i in insights:
            f.write(f"- {i}\n")
        f.write("\n")

    # Move file
    filepath.rename(dest)
    print(f"✅ Archived: {filepath.name} → archive/ ({format_size(size)})")
    if insights:
        for i in insights[:5]:
            print(f"  → {i}")

    return insights


def main():
    parser = argparse.ArgumentParser(description="Archive old daily memory logs")
    parser.add_argument("date", nargs="?", help="Specific date to archive (YYYY-MM-DD)")
    parser.add_argument("--older-than", type=int, help="Archive files older than N days")
    parser.add_argument("--dry-run", action="store_true", help="Preview without moving")
    parser.add_argument("--list", action="store_true", help="List archivable files")
    args = parser.parse_args()

    files = find_daily_files()
    today = datetime.now().date()

    if args.list:
        print(f"Daily logs in memory/ ({len(files)} files):\n")
        total_size = 0
        for date, path, size in files:
            age = (today - date).days
            total_size += size
            marker = " ← TODAY" if date == today else ""
            print(f"  {date}  {format_size(size):>8}  ({age}d old){marker}")
        print(f"\nTotal: {format_size(total_size)}")
        return

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        target_files = [(d, p, s) for d, p, s in files if d == target_date]
        if not target_files:
            print(f"No file found for {args.date}")
            sys.exit(1)
        for date, path, size in target_files:
            archive_file(date, path, args.dry_run)

    elif args.older_than is not None:
        cutoff = today - timedelta(days=args.older_than)
        targets = [(d, p, s) for d, p, s in files if d < cutoff]
        if not targets:
            print(f"No files older than {args.older_than} days")
            return
        print(f"Archiving {len(targets)} files older than {args.older_than} days:\n")
        for date, path, size in targets:
            archive_file(date, path, args.dry_run)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
