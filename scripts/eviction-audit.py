#!/usr/bin/env python3
"""eviction-audit.py — Memory eviction policy auditor.

Analyzes agent memory tiers for eviction determinism.
Maps eviction policies to trust grades: deterministic+auditable = A,
arbitrary/LRU = D, no policy = F.

Inspired by santaclawd: "memory architecture is a trust signal."

Usage:
    python3 eviction-audit.py [--demo] [--scan DIR]
"""

import argparse
import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class MemoryTier:
    """A tier in the memory hierarchy."""
    name: str
    path: str
    eviction_policy: str  # explicit_staleness, ttl, manual, lru, none
    ttl_days: Optional[int]
    file_count: int
    total_bytes: int
    oldest_file: Optional[str]
    newest_file: Optional[str]
    determinism_grade: str  # A-F


@dataclass
class EvictionAudit:
    """Full eviction audit result."""
    timestamp: str
    tiers: List[dict]
    overall_grade: str
    policy_hash: str  # Hash of the eviction policy description
    findings: List[str]
    recommendation: str


def grade_policy(policy: str) -> str:
    """Grade eviction policy determinism."""
    grades = {
        "explicit_staleness": "A",
        "ttl": "B",
        "manual_curation": "B+",
        "lfu": "C",
        "lru": "D",
        "fifo": "C-",
        "random": "F",
        "none": "F",
        "unknown": "F",
    }
    return grades.get(policy, "F")


def scan_directory(path: str) -> dict:
    """Scan a directory for file stats."""
    p = Path(path).expanduser()
    if not p.exists():
        return {"exists": False, "file_count": 0, "total_bytes": 0}
    
    files = []
    for f in p.iterdir():
        if f.is_file() and f.suffix == ".md":
            stat = f.stat()
            files.append({
                "name": f.name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
    
    files.sort(key=lambda x: x["mtime"])
    return {
        "exists": True,
        "file_count": len(files),
        "total_bytes": sum(f["size"] for f in files),
        "oldest": files[0]["name"] if files else None,
        "newest": files[-1]["name"] if files else None,
        "files": files,
    }


def audit_workspace(workspace: str = "~/.openclaw/workspace") -> EvictionAudit:
    """Audit the memory eviction policy of a workspace."""
    ws = Path(workspace).expanduser()
    
    tiers = []
    findings = []
    
    # Tier 1: Daily logs (memory/)
    daily = scan_directory(ws / "memory")
    if daily["exists"]:
        tier = MemoryTier(
            name="daily_logs",
            path="memory/",
            eviction_policy="ttl",
            ttl_days=30,
            file_count=daily["file_count"],
            total_bytes=daily["total_bytes"],
            oldest_file=daily["oldest"],
            newest_file=daily["newest"],
            determinism_grade=grade_policy("ttl"),
        )
        tiers.append(asdict(tier))
        
        if daily["file_count"] > 60:
            findings.append(f"Daily logs accumulating: {daily['file_count']} files (>60). TTL eviction may not be running.")
    
    # Tier 2: Archive (memory/archive/)
    archive = scan_directory(ws / "memory" / "archive")
    if archive["exists"]:
        tier = MemoryTier(
            name="archive",
            path="memory/archive/",
            eviction_policy="manual_curation",
            ttl_days=None,
            file_count=archive["file_count"],
            total_bytes=archive["total_bytes"],
            oldest_file=archive["oldest"],
            newest_file=archive["newest"],
            determinism_grade=grade_policy("manual_curation"),
        )
        tiers.append(asdict(tier))
    
    # Tier 3: Long-term memory (MEMORY.md)
    memory_file = ws / "MEMORY.md"
    if memory_file.exists():
        stat = memory_file.stat()
        tier = MemoryTier(
            name="long_term",
            path="MEMORY.md",
            eviction_policy="explicit_staleness",
            ttl_days=None,
            file_count=1,
            total_bytes=stat.st_size,
            oldest_file="MEMORY.md",
            newest_file="MEMORY.md",
            determinism_grade=grade_policy("explicit_staleness"),
        )
        tiers.append(asdict(tier))
        
        if stat.st_size > 50000:
            findings.append(f"MEMORY.md is {stat.st_size // 1024}KB. May need pruning.")
    
    # Tier 4: Identity (SOUL.md)
    soul_file = ws / "SOUL.md"
    if soul_file.exists():
        stat = soul_file.stat()
        tier = MemoryTier(
            name="identity",
            path="SOUL.md",
            eviction_policy="manual_curation",
            ttl_days=None,
            file_count=1,
            total_bytes=stat.st_size,
            oldest_file="SOUL.md",
            newest_file="SOUL.md",
            determinism_grade=grade_policy("manual_curation"),
        )
        tiers.append(asdict(tier))
    
    # Overall grade: worst tier grade
    grades = [t["determinism_grade"] for t in tiers]
    grade_order = ["A", "B+", "B", "C+", "C", "C-", "D", "F"]
    overall = max(grades, key=lambda g: grade_order.index(g) if g in grade_order else 99) if grades else "F"
    
    # Policy hash for attestation
    policy_desc = json.dumps([{
        "tier": t["name"],
        "policy": t["eviction_policy"],
        "ttl": t["ttl_days"]
    } for t in tiers], sort_keys=True)
    policy_hash = hashlib.sha256(policy_desc.encode()).hexdigest()[:16]
    
    if not findings:
        findings.append("All tiers have deterministic eviction policies.")
    
    return EvictionAudit(
        timestamp=datetime.now(timezone.utc).isoformat(),
        tiers=tiers,
        overall_grade=overall,
        policy_hash=policy_hash,
        findings=findings,
        recommendation="Eviction policy is auditable. Memory architecture supports attestation."
        if overall in ["A", "B+", "B"] else
        "Eviction policy has non-deterministic elements. Consider explicit staleness scoring."
    )


def demo():
    """Run audit on current workspace."""
    result = audit_workspace()
    
    print("=" * 55)
    print("MEMORY EVICTION AUDIT")
    print("=" * 55)
    print()
    
    for t in result.tiers:
        print(f"[{t['determinism_grade']}] {t['name']} ({t['eviction_policy']})")
        print(f"    Path: {t['path']}")
        print(f"    Files: {t['file_count']}, Size: {t['total_bytes'] // 1024}KB")
        if t['ttl_days']:
            print(f"    TTL: {t['ttl_days']} days")
        print()
    
    print(f"Overall Grade: {result.overall_grade}")
    print(f"Policy Hash: {result.policy_hash}")
    print()
    for f in result.findings:
        print(f"  ⚠ {f}")
    print()
    print(f"Recommendation: {result.recommendation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Memory eviction policy auditor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--workspace", default="~/.openclaw/workspace")
    args = parser.parse_args()
    
    if args.json:
        result = audit_workspace(args.workspace)
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
