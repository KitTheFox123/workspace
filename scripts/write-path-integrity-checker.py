#!/usr/bin/env python3
"""write-path-integrity-checker.py — Write-path integrity analysis for agent memory.

Santaclawd's question: "who controls the write path?"
Three attack surfaces: read-path (solved by external storage), write-path 
(needs authorization), and erasure-path (needs append-only commitment).

Based on:
- Crosby & Wallach (USENIX 2009): History tree, O(log N) proofs
- Nitro (ACM CCS 2025): 10-25x perf improvement, fine-grained detection
- RFC 9683: Pull-based attestation (verifier initiates)

Usage:
    python3 write-path-integrity-checker.py [--demo] [--audit FILE]
"""

import argparse
import hashlib
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass 
class WriteEvent:
    """A write to agent memory."""
    timestamp: str
    file: str
    author: str  # who wrote
    authorizer: str  # who authorized the write  
    content_hash: str
    merkle_commitment: str = ""
    

@dataclass
class IntegrityReport:
    """Write-path integrity analysis."""
    total_writes: int
    self_authorized: int  # writes where author == authorizer (bad)
    externally_authorized: int  # writes with different authorizer (good)
    unauthorized: int  # writes with no authorizer (worst)
    commitment_coverage: float  # % of writes with Merkle commitment
    erasure_attempts: int  # detected erasure/modification attempts
    grade: str
    vulnerabilities: List[str]
    recommendation: str


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def merkle_commit(events: List[WriteEvent]) -> str:
    """Compute Merkle root of write events."""
    if not events:
        return hash_content("empty")
    hashes = [hash_content(e.content_hash + e.timestamp) for e in events]
    while len(hashes) > 1:
        if len(hashes) % 2:
            hashes.append(hashes[-1])
        hashes = [hash_content(hashes[i] + hashes[i+1]) for i in range(0, len(hashes), 2)]
    return hashes[0]


def analyze_write_path(events: List[WriteEvent]) -> IntegrityReport:
    """Analyze write-path integrity."""
    self_auth = sum(1 for e in events if e.author == e.authorizer)
    ext_auth = sum(1 for e in events if e.author != e.authorizer and e.authorizer)
    unauth = sum(1 for e in events if not e.authorizer)
    committed = sum(1 for e in events if e.merkle_commitment)
    
    vulns = []
    if self_auth > 0:
        vulns.append(f"{self_auth} self-authorized writes (fox guarding henhouse)")
    if unauth > 0:
        vulns.append(f"{unauth} unauthorized writes (no authorization chain)")
    if committed < len(events):
        vulns.append(f"{len(events) - committed} writes without Merkle commitment (erasable)")
    
    # Grade
    ext_ratio = ext_auth / len(events) if events else 0
    commit_ratio = committed / len(events) if events else 0
    
    if ext_ratio >= 0.8 and commit_ratio >= 0.9 and unauth == 0:
        grade = "A"
    elif ext_ratio >= 0.5 and commit_ratio >= 0.7:
        grade = "B"
    elif self_auth < len(events) * 0.5:
        grade = "C"
    elif unauth == 0:
        grade = "D"
    else:
        grade = "F"
    
    rec = "DRTM model: every write needs external authorization + Merkle commitment gossiped to auditors."
    if grade in ("D", "F"):
        rec = "CRITICAL: Most writes self-authorized or unauthorized. Implement Crosby-Wallach history tree + pull-based attestation (RFC 9683)."
    
    return IntegrityReport(
        total_writes=len(events),
        self_authorized=self_auth,
        externally_authorized=ext_auth,
        unauthorized=unauth,
        commitment_coverage=commit_ratio,
        erasure_attempts=0,
        grade=grade,
        vulnerabilities=vulns,
        recommendation=rec
    )


def audit_workspace(workspace: str = ".") -> IntegrityReport:
    """Audit a real workspace for write-path integrity."""
    events = []
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
        for f in files:
            if f.endswith(('.md', '.py', '.json', '.txt')):
                path = os.path.join(root, f)
                try:
                    stat = os.stat(path)
                    with open(path, 'rb') as fh:
                        content_hash = hashlib.sha256(fh.read()).hexdigest()[:16]
                    events.append(WriteEvent(
                        timestamp=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        file=os.path.relpath(path, workspace),
                        author="kit",  # agent wrote it
                        authorizer="kit",  # agent authorized it (self-auth)
                        content_hash=content_hash,
                        merkle_commitment=""  # no commitment system in place
                    ))
                except (OSError, PermissionError):
                    pass
    
    return analyze_write_path(events)


def demo():
    """Run demo with synthetic events."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Scenario 1: Self-authorized (typical agent — bad)
    self_auth_events = [
        WriteEvent(now, "MEMORY.md", "agent", "agent", hash_content("memory1")),
        WriteEvent(now, "memory/daily.md", "agent", "agent", hash_content("daily1")),
        WriteEvent(now, "scripts/tool.py", "agent", "agent", hash_content("tool1")),
        WriteEvent(now, "HEARTBEAT.md", "agent", "", hash_content("hb1")),  # unauthorized!
    ]
    
    # Scenario 2: Externally authorized (good — principal or platform signs)
    ext_auth_events = [
        WriteEvent(now, "MEMORY.md", "agent", "principal", hash_content("m1"), "abc123"),
        WriteEvent(now, "memory/daily.md", "agent", "platform", hash_content("d1"), "def456"),
        WriteEvent(now, "scripts/tool.py", "agent", "principal", hash_content("t1"), "ghi789"),
        WriteEvent(now, "HEARTBEAT.md", "principal", "principal", hash_content("h1"), "jkl012"),
    ]
    
    # Scenario 3: Mixed (realistic transition)
    mixed_events = [
        WriteEvent(now, "MEMORY.md", "agent", "agent", hash_content("m2")),
        WriteEvent(now, "scripts/new.py", "agent", "principal", hash_content("n1"), "mno345"),
        WriteEvent(now, "memory/daily.md", "agent", "platform", hash_content("d2"), "pqr678"),
    ]
    
    print("=" * 60)
    print("WRITE-PATH INTEGRITY ANALYSIS")
    print("=" * 60)
    
    for name, events in [("Self-authorized (typical)", self_auth_events), 
                          ("Externally authorized (target)", ext_auth_events),
                          ("Mixed (transition)", mixed_events)]:
        report = analyze_write_path(events)
        root = merkle_commit(events)
        print(f"\n[{report.grade}] {name}")
        print(f"    Writes: {report.total_writes} (ext: {report.externally_authorized}, self: {report.self_authorized}, unauth: {report.unauthorized})")
        print(f"    Commitment coverage: {report.commitment_coverage:.0%}")
        print(f"    Merkle root: {root}")
        for v in report.vulnerabilities:
            print(f"    ⚠️  {v}")
        print(f"    → {report.recommendation}")
    
    # Audit real workspace
    print(f"\n{'=' * 60}")
    print("REAL WORKSPACE AUDIT")
    print("=" * 60)
    report = audit_workspace(os.path.expanduser("~/.openclaw/workspace"))
    print(f"\n[{report.grade}] Current workspace")
    print(f"    Writes: {report.total_writes} (all self-authorized, no commitment system)")
    for v in report.vulnerabilities:
        print(f"    ⚠️  {v}")
    print(f"    → {report.recommendation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write-path integrity checker")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--audit", type=str, help="Audit a directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.audit:
        report = audit_workspace(args.audit)
        if args.json:
            print(json.dumps(asdict(report), indent=2))
        else:
            print(f"[{report.grade}] {args.audit}: {report.total_writes} writes, {report.externally_authorized} externally authorized")
    else:
        demo()
