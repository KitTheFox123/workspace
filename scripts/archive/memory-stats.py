#!/usr/bin/env python3
"""Memory Stats — analyze memory/ directory health.

Usage: python3 memory-stats.py [--json]
"""

import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "memory"
TOKENS_PER_CHAR = 0.25  # rough estimate

def analyze():
    if not MEMORY_DIR.exists():
        return {"error": "memory/ not found"}
    
    files = []
    total_bytes = 0
    total_tokens = 0
    now = datetime.now(timezone.utc)
    
    for f in sorted(MEMORY_DIR.rglob("*.md")):
        stat = f.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        age_days = (now - mtime).total_seconds() / 86400
        tokens = int(size * TOKENS_PER_CHAR)
        
        total_bytes += size
        total_tokens += tokens
        
        files.append({
            "path": str(f.relative_to(MEMORY_DIR)),
            "size_kb": round(size / 1024, 1),
            "tokens": tokens,
            "modified": mtime.strftime("%Y-%m-%d %H:%M"),
            "age_days": round(age_days, 1),
            "stale": age_days > 7,
        })
    
    # Also check JSON files
    for f in sorted(MEMORY_DIR.rglob("*.json")):
        stat = f.stat()
        size = stat.st_size
        total_bytes += size
        files.append({
            "path": str(f.relative_to(MEMORY_DIR)),
            "size_kb": round(size / 1024, 1),
            "tokens": int(size * TOKENS_PER_CHAR),
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "age_days": round((now - datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)).total_seconds() / 86400, 1),
            "stale": False,
        })
    
    # Sort by size descending
    files.sort(key=lambda x: -x["size_kb"])
    
    stale = [f for f in files if f.get("stale")]
    
    return {
        "total_files": len(files),
        "total_kb": round(total_bytes / 1024, 1),
        "total_tokens_est": total_tokens,
        "stale_files": len(stale),
        "files": files,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    result = analyze()
    
    if args.json:
        print(json.dumps(result, indent=2))
        return
    
    print(f"📁 Memory Stats")
    print(f"{'=' * 55}")
    print(f"  Files: {result['total_files']}")
    print(f"  Total size: {result['total_kb']:.0f} KB")
    print(f"  Est. tokens: {result['total_tokens_est']:,}")
    print(f"  Stale (>7d): {result['stale_files']}")
    
    print(f"\n📊 Top 10 by size:")
    for f in result["files"][:10]:
        stale_marker = " ⚠️" if f.get("stale") else ""
        print(f"  {f['size_kb']:8.1f} KB  {f['tokens']:>7,} tok  {f['modified']}  {f['path']}{stale_marker}")
    
    if result["stale_files"] > 0:
        print(f"\n⚠️  Stale files ({result['stale_files']}):")
        for f in [x for x in result["files"] if x.get("stale")][:5]:
            print(f"  {f['path']} — {f['age_days']:.0f} days old")

if __name__ == "__main__":
    main()
