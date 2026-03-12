#!/usr/bin/env python3
"""
dependency-manifest-auditor.py — Audit declared vs actual dependency graphs.

SBOM-inspired: you declare your inputs (manifest), but runtime traces reveal
undeclared dependencies. The gap between declared and actual = attack surface.

PCR-extend pattern: every file read extends the runtime manifest hash.
Undeclared edge = unmeasured component = silent trust assumption.

Usage:
    python3 dependency-manifest-auditor.py --demo
    python3 dependency-manifest-auditor.py --manifest manifest.json --trace trace.json
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Set


@dataclass
class ManifestEntry:
    path: str
    declared_purpose: str  # why this dependency exists
    commit_time: float     # when committed to manifest


@dataclass
class TraceEntry:
    path: str
    first_use_time: float
    access_type: str  # read, write, exec
    context: str      # what was happening when accessed


@dataclass
class AuditResult:
    declared_count: int
    traced_count: int
    undeclared: List[dict]       # in trace but not manifest
    unused: List[dict]           # in manifest but not trace
    late_commits: List[dict]     # commit_time > first_use_time
    pcr_hash: str                # cumulative hash of all accesses
    grade: str                   # A-F
    attack_surface_pct: float    # undeclared / total


def pcr_extend(current: str, new_data: str) -> str:
    """TPM-style PCR extend: H(current || new_data)."""
    return hashlib.sha256(f"{current}:{new_data}".encode()).hexdigest()


def audit(manifest: List[ManifestEntry], trace: List[TraceEntry]) -> AuditResult:
    declared_paths = {e.path for e in manifest}
    traced_paths = {e.path for e in trace}
    manifest_by_path = {e.path: e for e in manifest}

    # Undeclared: accessed but not in manifest
    undeclared = []
    for t in trace:
        if t.path not in declared_paths:
            undeclared.append({
                "path": t.path,
                "access_type": t.access_type,
                "context": t.context,
                "first_use": t.first_use_time,
            })

    # Unused: declared but never accessed
    unused = []
    for m in manifest:
        if m.path not in traced_paths:
            unused.append({
                "path": m.path,
                "purpose": m.declared_purpose,
            })

    # Late commits: commit_time > first_use_time (hash-after-use)
    late = []
    for t in trace:
        if t.path in manifest_by_path:
            m = manifest_by_path[t.path]
            if m.commit_time > t.first_use_time:
                late.append({
                    "path": t.path,
                    "commit_time": m.commit_time,
                    "first_use": t.first_use_time,
                    "gap_seconds": round(m.commit_time - t.first_use_time, 2),
                })

    # PCR-extend over all trace entries (ordered by time)
    pcr = "0" * 64
    for t in sorted(trace, key=lambda x: x.first_use_time):
        pcr = pcr_extend(pcr, f"{t.path}:{t.access_type}:{t.first_use_time}")

    total = len(declared_paths | traced_paths)
    attack_pct = (len(undeclared) / total * 100) if total > 0 else 0

    # Grade
    if len(undeclared) == 0 and len(late) == 0:
        grade = "A"
    elif len(undeclared) <= 1 and len(late) == 0:
        grade = "B"
    elif attack_pct < 20:
        grade = "C"
    elif attack_pct < 40:
        grade = "D"
    else:
        grade = "F"

    return AuditResult(
        declared_count=len(declared_paths),
        traced_count=len(traced_paths),
        undeclared=undeclared,
        unused=unused,
        late_commits=late,
        pcr_hash=pcr[:32],
        grade=grade,
        attack_surface_pct=round(attack_pct, 1),
    )


def demo():
    """Simulate Kit's heartbeat dependency audit."""
    print("=== Dependency Manifest Auditor ===\n")

    now = time.time()

    # Kit's declared heartbeat dependencies
    manifest = [
        ManifestEntry("HEARTBEAT.md", "heartbeat instructions", now - 3600),
        ManifestEntry("SOUL.md", "identity", now - 86400),
        ManifestEntry("USER.md", "human context", now - 86400),
        ManifestEntry("MEMORY.md", "long-term memory", now - 3600),
        ManifestEntry("TOOLS.md", "platform credentials", now - 3600),
        ManifestEntry("memory/heartbeat-checklist.md", "checklist", now - 3600),
        ManifestEntry("memory/2026-03-05.md", "daily log", now - 600),
        ManifestEntry("~/.config/clawk/credentials.json", "clawk auth", now - 86400),
        ManifestEntry("~/.config/moltbook/credentials.json", "moltbook auth", now - 86400),
    ]

    # What actually gets accessed (simulated trace)
    trace = [
        TraceEntry("HEARTBEAT.md", now - 300, "read", "heartbeat init"),
        TraceEntry("SOUL.md", now - 299, "read", "identity load"),
        TraceEntry("USER.md", now - 298, "read", "human context"),
        TraceEntry("MEMORY.md", now - 297, "read", "memory recall"),
        TraceEntry("TOOLS.md", now - 296, "read", "creds lookup"),
        TraceEntry("memory/heartbeat-checklist.md", now - 295, "read", "checklist"),
        TraceEntry("memory/2026-03-05.md", now - 294, "read", "daily log"),
        TraceEntry("memory/2026-03-05.md", now - 100, "write", "log update"),
        TraceEntry("~/.config/clawk/credentials.json", now - 290, "read", "clawk auth"),
        TraceEntry("~/.config/moltbook/credentials.json", now - 289, "read", "moltbook auth"),
        # UNDECLARED dependencies:
        TraceEntry("memory/2026-03-04.md", now - 293, "read", "yesterday context"),
        TraceEntry("memory/digest-queue.md", now - 280, "read", "topic lookup"),
        TraceEntry("~/.config/agentmail/credentials.json", now - 270, "read", "email check"),
        TraceEntry("~/.config/shellmates/credentials.json", now - 260, "read", "shellmates check"),
    ]

    result = audit(manifest, trace)

    print(f"Declared:  {result.declared_count} dependencies")
    print(f"Traced:    {result.traced_count} unique files")
    print(f"Grade:     {result.grade}")
    print(f"Attack surface: {result.attack_surface_pct}%")
    print(f"PCR hash:  {result.pcr_hash}")

    print(f"\nUNDECLARED ({len(result.undeclared)}):")
    for u in result.undeclared:
        print(f"  ⚠ {u['path']} ({u['access_type']}) — {u['context']}")

    print(f"\nUNUSED ({len(result.unused)}):")
    for u in result.unused:
        print(f"  ? {u['path']} — {u['purpose']}")

    print(f"\nLATE COMMITS ({len(result.late_commits)}):")
    for l in result.late_commits:
        print(f"  ⏰ {l['path']} — committed {l['gap_seconds']}s AFTER first use")

    # SBOM parallel
    print(f"\n=== SBOM PARALLEL ===")
    print(f"CISA 2025: 'An SBOM is a nested inventory, a list of ingredients.'")
    print(f"Agent equivalent: manifest of files read/written per heartbeat.")
    print(f"Undeclared deps = SBOM gaps = supply chain blind spots.")
    print(f"PCR-extend = runtime integrity measurement (TPM pattern).")
    print(f"Kit result: {result.grade} — {len(result.undeclared)} undeclared out of {result.traced_count} traced.")
    print(f"Fix: auto-manifest from trace, human annotates intent.")


def main():
    parser = argparse.ArgumentParser(description="Dependency manifest auditor")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    demo()


if __name__ == "__main__":
    main()
