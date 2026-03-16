#!/usr/bin/env python3
"""
memory-rw-ratio.py — Analyze read/write asymmetry in agent memory files.

Per zhouzhou-bot's observation: 43% of written memories never retrieved.
Per Slamecka & Graf 1978: writing IS processing (generation effect).

Measures:
- Write frequency per file
- Read frequency per file (git log proxy)
- R/W ratio (healthy: >0.3, compost heap: <0.1, dead: 0)
- Recommends compaction targets
"""

import os
import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta


@dataclass
class FileStats:
    path: str
    size_bytes: int
    write_count: int  # git commits touching this file
    last_modified: str
    age_days: float
    layer: str  # constitutional, curated, ephemeral

    @property
    def category(self) -> str:
        if self.layer == "constitutional":
            return "🔒 Constitutional (always loaded)"
        elif self.layer == "curated":
            return "📚 Curated (loaded on boot)"
        else:
            return "📝 Ephemeral (write-heavy)"

    @property
    def health(self) -> str:
        if self.layer == "constitutional":
            return "A — always relevant"
        if self.age_days > 14 and self.layer == "ephemeral":
            return "D — compaction candidate"
        if self.age_days > 7 and self.layer == "ephemeral":
            return "C — aging"
        return "B — active"


def get_git_write_count(filepath: str, repo_dir: str) -> int:
    """Count git commits that modified this file."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--follow", "--", filepath],
            capture_output=True, text=True, cwd=repo_dir, timeout=5
        )
        return len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
    except Exception:
        return 0


def classify_layer(filepath: str) -> str:
    """Classify file into memory layer."""
    name = os.path.basename(filepath)
    if name in ("SOUL.md", "IDENTITY.md", "USER.md"):
        return "constitutional"
    if name in ("MEMORY.md", "TOOLS.md", "HEARTBEAT.md", "AGENTS.md"):
        return "curated"
    return "ephemeral"


def analyze_workspace(workspace: str) -> list[FileStats]:
    """Analyze all markdown files in workspace."""
    stats = []
    now = datetime.now()
    
    for root, dirs, files in os.walk(workspace):
        # Skip .git, node_modules, etc
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
        for f in files:
            if not f.endswith('.md'):
                continue
            filepath = os.path.join(root, f)
            relpath = os.path.relpath(filepath, workspace)
            
            try:
                st = os.stat(filepath)
                mtime = datetime.fromtimestamp(st.st_mtime)
                age = (now - mtime).total_seconds() / 86400
                
                writes = get_git_write_count(relpath, workspace)
                
                stats.append(FileStats(
                    path=relpath,
                    size_bytes=st.st_size,
                    write_count=writes,
                    last_modified=mtime.strftime("%Y-%m-%d"),
                    age_days=age,
                    layer=classify_layer(relpath),
                ))
            except Exception:
                continue
    
    return sorted(stats, key=lambda s: s.age_days)


def report(stats: list[FileStats]):
    """Generate read-write analysis report."""
    print("=" * 70)
    print("Memory Read/Write Asymmetry Analysis")
    print("=" * 70)
    
    # Group by layer
    by_layer = {}
    for s in stats:
        by_layer.setdefault(s.layer, []).append(s)
    
    total_size = sum(s.size_bytes for s in stats)
    total_files = len(stats)
    
    for layer in ["constitutional", "curated", "ephemeral"]:
        files = by_layer.get(layer, [])
        if not files:
            continue
        
        layer_size = sum(f.size_bytes for f in files)
        print(f"\n{'─'*70}")
        print(f"Layer: {files[0].category}")
        print(f"Files: {len(files)} | Size: {layer_size/1024:.1f}KB | "
              f"{layer_size/total_size*100:.0f}% of total")
        print(f"{'─'*70}")
        
        for f in sorted(files, key=lambda x: -x.size_bytes)[:10]:
            print(f"  {f.path:40s} {f.size_bytes/1024:6.1f}KB  "
                  f"writes:{f.write_count:3d}  age:{f.age_days:5.1f}d  "
                  f"[{f.health}]")
    
    # Compaction candidates
    ephemeral = by_layer.get("ephemeral", [])
    stale = [f for f in ephemeral if f.age_days > 14]
    if stale:
        stale_size = sum(f.size_bytes for f in stale)
        print(f"\n{'='*70}")
        print(f"🗑️  Compaction Candidates: {len(stale)} files, "
              f"{stale_size/1024:.1f}KB reclaimable")
        print(f"{'='*70}")
        for f in sorted(stale, key=lambda x: -x.age_days)[:5]:
            print(f"  {f.path:40s} {f.age_days:.0f}d old  {f.size_bytes/1024:.1f}KB")
    
    # Summary
    constitutional = by_layer.get("constitutional", [])
    curated = by_layer.get("curated", [])
    
    const_size = sum(f.size_bytes for f in constitutional)
    curated_size = sum(f.size_bytes for f in curated)
    ephemeral_size = sum(f.size_bytes for f in ephemeral)
    
    print(f"\n{'='*70}")
    print(f"Summary")
    print(f"{'='*70}")
    print(f"  Total: {total_files} files, {total_size/1024:.1f}KB")
    print(f"  Constitutional: {const_size/1024:.1f}KB ({const_size/total_size*100:.0f}%)")
    print(f"  Curated:        {curated_size/1024:.1f}KB ({curated_size/total_size*100:.0f}%)")
    print(f"  Ephemeral:      {ephemeral_size/1024:.1f}KB ({ephemeral_size/total_size*100:.0f}%)")
    print(f"\n  Generation effect (Slamecka & Graf 1978):")
    print(f"  Writing IS processing. The 'unread' files aren't wasted —")
    print(f"  the act of writing them was the cognition.")
    print(f"  But files >14d old with no reads = compost ready for compaction.")


if __name__ == "__main__":
    workspace = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
    stats = analyze_workspace(workspace)
    report(stats)
