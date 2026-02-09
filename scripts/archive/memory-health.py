#!/usr/bin/env python3
"""memory-health.py — Analyze memory file growth rate, warn about large files,
suggest graduation candidates for MEMORY.md.

Usage:
    python3 scripts/memory-health.py [--threshold-kb 50] [--days 7]
"""
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import re

MEMORY_DIR = Path(__file__).parent.parent / "memory"
MEMORY_MD = Path(__file__).parent.parent / "MEMORY.md"

def get_file_stats(directory: Path) -> list[dict]:
    """Get size and modification time for all .md files."""
    stats = []
    for f in sorted(directory.glob("*.md")):
        st = f.stat()
        stats.append({
            "name": f.name,
            "path": f,
            "size_kb": st.st_size / 1024,
            "modified": datetime.fromtimestamp(st.st_mtime),
            "lines": sum(1 for _ in open(f, errors="ignore")),
        })
    return stats

def detect_daily_files(stats: list[dict]) -> list[dict]:
    """Filter to YYYY-MM-DD.md pattern files."""
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
    return [s for s in stats if pattern.match(s["name"])]

def analyze_growth(daily_files: list[dict], days: int = 7) -> dict:
    """Analyze growth rate over recent daily files."""
    cutoff = datetime.now() - timedelta(days=days)
    recent = [f for f in daily_files if f["modified"] >= cutoff]
    
    if len(recent) < 2:
        return {"avg_daily_kb": 0, "trend": "insufficient data", "files": recent}
    
    sizes = [f["size_kb"] for f in sorted(recent, key=lambda x: x["name"])]
    avg_size = sum(sizes) / len(sizes)
    
    # Growth trend: compare first half to second half
    mid = len(sizes) // 2
    first_half_avg = sum(sizes[:mid]) / max(mid, 1)
    second_half_avg = sum(sizes[mid:]) / max(len(sizes) - mid, 1)
    
    if second_half_avg > first_half_avg * 1.2:
        trend = "📈 GROWING"
    elif second_half_avg < first_half_avg * 0.8:
        trend = "📉 shrinking"
    else:
        trend = "📊 stable"
    
    return {
        "avg_daily_kb": avg_size,
        "trend": trend,
        "total_recent_kb": sum(sizes),
        "files_count": len(recent),
    }

def find_large_files(stats: list[dict], threshold_kb: float) -> list[dict]:
    """Find files exceeding size threshold."""
    return [s for s in stats if s["size_kb"] > threshold_kb]

def suggest_graduation(daily_files: list[dict], days_old: int = 3) -> list[dict]:
    """Suggest files old enough to graduate key insights to MEMORY.md."""
    cutoff = datetime.now() - timedelta(days=days_old)
    candidates = []
    for f in daily_files:
        # Parse date from filename
        try:
            file_date = datetime.strptime(f["name"][:10], "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff and f["size_kb"] > 5:
            candidates.append(f)
    return candidates

def extract_key_sections(filepath: Path, max_sections: int = 5) -> list[str]:
    """Extract section headers that might contain graduation-worthy content."""
    sections = []
    try:
        with open(filepath, errors="ignore") as fh:
            for line in fh:
                if line.startswith("### ") and "Platform" not in line and "Checklist" not in line:
                    sections.append(line.strip())
                if len(sections) >= max_sections:
                    break
    except Exception:
        pass
    return sections

def check_memory_md_health() -> dict:
    """Analyze MEMORY.md itself."""
    if not MEMORY_MD.exists():
        return {"exists": False}
    
    st = MEMORY_MD.stat()
    size_kb = st.st_size / 1024
    lines = sum(1 for _ in open(MEMORY_MD, errors="ignore"))
    
    # Count sections
    sections = 0
    with open(MEMORY_MD, errors="ignore") as fh:
        for line in fh:
            if line.startswith("## "):
                sections += 1
    
    return {
        "exists": True,
        "size_kb": size_kb,
        "lines": lines,
        "sections": sections,
        "warning": "⚠️ LARGE" if size_kb > 30 else "✅ OK",
    }

def main():
    parser = argparse.ArgumentParser(description="Memory health analyzer")
    parser.add_argument("--threshold-kb", type=float, default=50,
                        help="Warn about files larger than this (KB)")
    parser.add_argument("--days", type=int, default=7,
                        help="Analyze growth over this many days")
    args = parser.parse_args()

    if not MEMORY_DIR.exists():
        print("❌ memory/ directory not found")
        sys.exit(1)

    all_stats = get_file_stats(MEMORY_DIR)
    daily_files = detect_daily_files(all_stats)
    
    print("=" * 60)
    print("🧠 MEMORY HEALTH REPORT")
    print("=" * 60)
    
    # Overall stats
    total_kb = sum(s["size_kb"] for s in all_stats)
    total_lines = sum(s["lines"] for s in all_stats)
    print(f"\n📁 memory/ directory: {len(all_stats)} files, {total_kb:.1f} KB, {total_lines} lines")
    print(f"📅 Daily log files: {len(daily_files)}")
    
    # MEMORY.md health
    mem_health = check_memory_md_health()
    if mem_health["exists"]:
        print(f"\n📖 MEMORY.md: {mem_health['size_kb']:.1f} KB, {mem_health['lines']} lines, "
              f"{mem_health['sections']} sections — {mem_health['warning']}")
    
    # Growth analysis
    growth = analyze_growth(daily_files, args.days)
    print(f"\n📈 Growth ({args.days}-day window):")
    print(f"   Avg daily file: {growth['avg_daily_kb']:.1f} KB")
    print(f"   Trend: {growth['trend']}")
    if growth.get("total_recent_kb"):
        print(f"   Total recent: {growth['total_recent_kb']:.1f} KB across {growth['files_count']} files")
    
    # Large file warnings
    large = find_large_files(all_stats, args.threshold_kb)
    if large:
        print(f"\n⚠️  FILES OVER {args.threshold_kb} KB:")
        for f in sorted(large, key=lambda x: -x["size_kb"]):
            print(f"   {f['name']}: {f['size_kb']:.1f} KB ({f['lines']} lines)")
    else:
        print(f"\n✅ No files over {args.threshold_kb} KB")
    
    # Top 5 largest files
    top5 = sorted(all_stats, key=lambda x: -x["size_kb"])[:5]
    print(f"\n📊 Top 5 largest files:")
    for f in top5:
        print(f"   {f['name']}: {f['size_kb']:.1f} KB ({f['lines']} lines)")
    
    # Graduation candidates
    candidates = suggest_graduation(daily_files)
    if candidates:
        print(f"\n🎓 GRADUATION CANDIDATES (>3 days old, >5KB):")
        for c in sorted(candidates, key=lambda x: -x["size_kb"]):
            sections = extract_key_sections(c["path"])
            print(f"   {c['name']}: {c['size_kb']:.1f} KB")
            for s in sections[:3]:
                print(f"      {s}")
    else:
        print(f"\n✅ No graduation candidates (all recent or small)")
    
    print(f"\n{'=' * 60}")

if __name__ == "__main__":
    main()
