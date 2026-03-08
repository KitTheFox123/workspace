#!/usr/bin/env python3
"""genesis-audit.py — Genesis block auditor for trust chains.

Addresses santaclawd's problem: "append-only solves mutation, not origin."
Validates that genesis entries in trust chains have verifiable external anchors.

Based on:
- Parno, McCune & Perrig "Bootstrapping Trust" (CMU)
- arxiv 2210.08127 "Reflections on trusting distributed trust"
- DigiNotar incident (2011) as negative example

Two building blocks for bootstrapping (per 2210.08127):
1. Secure hardware (attestation of initial state)
2. Append-only log (auditable history from genesis)

Usage:
    python3 genesis-audit.py --demo
    python3 genesis-audit.py --check CHAIN_FILE
"""

import argparse
import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass 
class GenesisEntry:
    """Genesis block of a trust chain."""
    chain_id: str
    principal_id: str           # Who signed genesis
    principal_type: str         # human | organization | platform | self
    created_at: str
    scope_hash: str
    external_anchors: List[str] # Independent verification points
    ttl_hours: float
    witness_ids: List[str]      # Independent witnesses at genesis


@dataclass
class GenesisAuditResult:
    """Audit result for a genesis entry."""
    chain_id: str
    grade: str                  # A-F
    score: float                # 0-1
    origin_verified: bool
    has_external_anchor: bool
    has_independent_witness: bool
    principal_accountable: bool
    ttl_bounded: bool
    findings: List[str]
    recommendation: str


def audit_genesis(entry: GenesisEntry) -> GenesisAuditResult:
    """Audit a genesis entry for trust bootstrapping quality."""
    findings = []
    score = 0.0
    
    # 1. Principal type (0.3 weight)
    principal_scores = {
        "human": 0.3,        # Named, legally accountable
        "organization": 0.25, # Accountable but diffuse
        "platform": 0.15,    # Single point of failure
        "self": 0.0,         # Confused deputy
    }
    p_score = principal_scores.get(entry.principal_type, 0.0)
    score += p_score
    principal_accountable = entry.principal_type in ("human", "organization")
    
    if entry.principal_type == "self":
        findings.append("CRITICAL: Self-asserted genesis. Chain inherits root gap.")
    elif entry.principal_type == "platform":
        findings.append("WARN: Platform-asserted genesis. Single point of failure.")
    
    # 2. External anchors (0.25 weight)
    has_anchor = len(entry.external_anchors) > 0
    if has_anchor:
        anchor_score = min(len(entry.external_anchors) * 0.125, 0.25)
        score += anchor_score
        findings.append(f"OK: {len(entry.external_anchors)} external anchor(s)")
    else:
        findings.append("CRITICAL: No external anchors. Origin unverifiable.")
    
    # 3. Independent witnesses (0.25 weight)
    has_witness = len(entry.witness_ids) > 0
    if has_witness:
        witness_score = min(len(entry.witness_ids) * 0.1, 0.25)
        score += witness_score
        findings.append(f"OK: {len(entry.witness_ids)} independent witness(es)")
    else:
        findings.append("WARN: No independent witnesses at genesis.")
    
    # 4. TTL bounded (0.2 weight)
    ttl_bounded = entry.ttl_hours > 0 and entry.ttl_hours <= 720  # max 30 days
    if ttl_bounded:
        if entry.ttl_hours <= 24:
            score += 0.2
            findings.append(f"OK: TTL {entry.ttl_hours}h (short-lived, DRTM-style)")
        elif entry.ttl_hours <= 168:
            score += 0.15
            findings.append(f"OK: TTL {entry.ttl_hours}h (weekly renewal)")
        else:
            score += 0.1
            findings.append(f"WARN: TTL {entry.ttl_hours}h (long-lived cert)")
    else:
        findings.append("CRITICAL: Unbounded TTL. Compromise is permanent.")
    
    # Grade
    origin_verified = has_anchor and principal_accountable
    if score >= 0.85: grade = "A"
    elif score >= 0.7: grade = "B"
    elif score >= 0.5: grade = "C"
    elif score >= 0.3: grade = "D"
    else: grade = "F"
    
    # Recommendation
    if grade in ("A", "B"):
        rec = "Genesis adequately bootstrapped. Monitor for TTL renewal."
    elif grade == "C":
        rec = "Add external anchors or independent witnesses to strengthen origin."
    else:
        rec = "Genesis trust gap critical. Chain should not be trusted without remediation."
    
    return GenesisAuditResult(
        chain_id=entry.chain_id,
        grade=grade,
        score=round(score, 3),
        origin_verified=origin_verified,
        has_external_anchor=has_anchor,
        has_independent_witness=has_witness,
        principal_accountable=principal_accountable,
        ttl_bounded=ttl_bounded,
        findings=findings,
        recommendation=rec,
    )


def demo():
    """Demo with example genesis entries."""
    examples = [
        GenesisEntry(
            chain_id="isnad-kit-fox",
            principal_id="ilya",
            principal_type="human",
            created_at="2026-03-08T04:00:00Z",
            scope_hash=hashlib.sha256(b"HEARTBEAT.md scope").hexdigest()[:16],
            external_anchors=["github.com/KitTheFox123/isnad-rfc", "clawk.ai/@Kit_Fox"],
            ttl_hours=4.0,
            witness_ids=["gendolf", "santaclawd"],
        ),
        GenesisEntry(
            chain_id="self-attested-agent",
            principal_id="agent-xyz",
            principal_type="self",
            created_at="2026-03-08T04:00:00Z",
            scope_hash=hashlib.sha256(b"self scope").hexdigest()[:16],
            external_anchors=[],
            ttl_hours=0,
            witness_ids=[],
        ),
        GenesisEntry(
            chain_id="platform-managed",
            principal_id="platform-acme",
            principal_type="platform",
            created_at="2026-03-08T04:00:00Z",
            scope_hash=hashlib.sha256(b"platform scope").hexdigest()[:16],
            external_anchors=["ct-log.acme.com"],
            ttl_hours=720,
            witness_ids=[],
        ),
    ]
    
    print("=" * 60)
    print("GENESIS BLOCK AUDIT")
    print("'Append-only solves mutation. It does not solve origin.'")
    print("=" * 60)
    
    for entry in examples:
        result = audit_genesis(entry)
        print(f"\n[{result.grade}] {result.chain_id} (score: {result.score})")
        print(f"    Principal: {entry.principal_type} ({entry.principal_id})")
        print(f"    Origin verified: {result.origin_verified}")
        for f in result.findings:
            print(f"    {f}")
        print(f"    → {result.recommendation}")
    
    print("\n" + "-" * 60)
    print("Key insight: origin verification requires EXTERNAL anchors +")
    print("ACCOUNTABLE principal + BOUNDED TTL. Any missing = trust gap.")
    print("(arxiv 2210.08127: secure hardware + append-only log)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis block auditor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps([asdict(audit_genesis(e)) for e in [
            GenesisEntry("example", "human1", "human", "2026-01-01", "abc", ["anchor"], 24, ["w1"]),
        ]], indent=2))
    else:
        demo()
