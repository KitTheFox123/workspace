#!/usr/bin/env python3
"""
pheromone-decay.py — Layered memory persistence analyzer.

Models agent memory as pheromone with different half-lives per layer:
- Context window: ~minutes (evaporates on compaction)
- Daily logs: ~days (archived after a week)
- MEMORY.md: ~weeks (curated, pruned)
- Git history: ~permanent (append-only)

Analyzes actual workspace files to show decay rates and staleness.

Usage: python3 pheromone-decay.py [workspace_path]
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

def file_age_hours(path: Path) -> float:
    """Hours since last modification."""
    mtime = os.path.getmtime(path)
    return (time.time() - mtime) / 3600

def analyze_layer(name: str, paths: list[Path], half_life_hours: float) -> dict:
    """Analyze a memory layer's decay state."""
    if not paths:
        return {"layer": name, "files": 0, "half_life_h": half_life_hours}
    
    ages = [file_age_hours(p) for p in paths]
    sizes = [p.stat().st_size for p in paths]
    
    # Pheromone strength: exponential decay from last modification
    strengths = [2 ** (-age / half_life_hours) for age in ages]
    
    # Weighted by file size
    total_signal = sum(s * sz for s, sz in zip(strengths, sizes))
    total_possible = sum(sizes)  # if all files were fresh
    
    return {
        "layer": name,
        "files": len(paths),
        "total_kb": sum(sizes) / 1024,
        "half_life_h": half_life_hours,
        "avg_age_h": sum(ages) / len(ages),
        "freshest_h": min(ages),
        "stalest_h": max(ages),
        "avg_strength": sum(strengths) / len(strengths),
        "signal_retention": total_signal / total_possible if total_possible > 0 else 0,
    }

def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/yallen/.openclaw/workspace")
    
    # Collect files by layer
    layers = {
        "daily_logs": {
            "paths": sorted(workspace.glob("memory/202?-??-??.md")),
            "half_life": 72,  # 3 days
        },
        "memory_md": {
            "paths": [workspace / "MEMORY.md"] if (workspace / "MEMORY.md").exists() else [],
            "half_life": 336,  # 2 weeks
        },
        "soul_identity": {
            "paths": [p for p in [workspace / "SOUL.md", workspace / "IDENTITY.md"] if p.exists()],
            "half_life": 720,  # 30 days (rarely changes)
        },
        "knowledge": {
            "paths": sorted(workspace.glob("knowledge/*.md")),
            "half_life": 168,  # 1 week
        },
        "scripts": {
            "paths": sorted(workspace.glob("scripts/*.py")) + sorted(workspace.glob("scripts/*.sh")),
            "half_life": 240,  # 10 days
        },
        "tracking": {
            "paths": [p for p in workspace.glob("memory/*.md") if not p.name.startswith("202")],
            "half_life": 48,  # 2 days (should be actively updated)
        },
    }
    
    print("=== Pheromone Decay Analysis ===")
    print(f"Workspace: {workspace}")
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
    
    results = []
    for name, config in layers.items():
        result = analyze_layer(name, config["paths"], config["half_life"])
        results.append(result)
    
    # Display
    print(f"{'Layer':<16} {'Files':>5} {'Size KB':>8} {'Half-life':>10} {'Avg Age':>10} {'Strength':>10} {'Signal':>8}")
    print("-" * 78)
    
    for r in results:
        if r["files"] == 0:
            print(f"{r['layer']:<16} {'—':>5}")
            continue
        
        # Color coding via emoji
        strength = r["avg_strength"]
        indicator = "🟢" if strength > 0.5 else "🟡" if strength > 0.2 else "🔴"
        
        print(f"{r['layer']:<16} {r['files']:>5} {r['total_kb']:>7.1f} {r['half_life_h']:>8.0f}h {r['avg_age_h']:>8.1f}h {strength:>9.1%} {r['signal_retention']:>7.1%} {indicator}")
    
    # Overall health
    print()
    active_layers = [r for r in results if r["files"] > 0]
    if active_layers:
        avg_signal = sum(r.get("signal_retention", 0) for r in active_layers) / len(active_layers)
        print(f"Overall signal retention: {avg_signal:.1%}")
        
        # Find stale layers
        stale = [r for r in active_layers if r.get("avg_strength", 1) < 0.2]
        if stale:
            print(f"\n⚠️  Stale layers (strength < 20%):")
            for r in stale:
                print(f"  - {r['layer']}: {r['avg_strength']:.1%} strength, {r['avg_age_h']:.0f}h avg age")
        
        # Pheromone trail health
        fresh = [r for r in active_layers if r.get("freshest_h", 999) < 1]
        if fresh:
            print(f"\n✅ Recently active: {', '.join(r['layer'] for r in fresh)}")

if __name__ == "__main__":
    main()
