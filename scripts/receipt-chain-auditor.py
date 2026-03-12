#!/usr/bin/env python3
"""
receipt-chain-auditor.py — Continuous audit for agent receipt chains.

Inspired by: Frontiers Blockchain 2025 (Zhang et al), PwC reconciliation,
Harris Matrix digital stratigraphy, santaclawd's "ledger IS the audit trail."

Checks:
1. Temporal ordering (Harris Matrix — what MUST precede what)
2. Gap detection (missing steps in expected workflow)
3. Attester continuity (same chain, different attesters = healthy)
4. Proof class coverage (payment + generation + transport minimum)
5. Staleness (receipts past half-life)
"""

import json
import hashlib
import sys
from datetime import datetime, timezone, timedelta
from collections import Counter

# Expected workflow steps for common contract types
WORKFLOWS = {
    "service_delivery": [
        "contract_created",
        "escrow_funded", 
        "deliverable_submitted",
        "quality_attested",
        "payment_released",
    ],
    "tc3_research": [
        "brief_posted",
        "provider_accepted",
        "escrow_funded",
        "deliverable_emailed",
        "quality_scored",
        "attestations_filed",
        "payment_released",
    ],
}

PROOF_CLASSES = {
    "x402_tx": "payment", "paylock": "payment", "escrow": "payment",
    "gen_sig": "generation", "content_hash": "generation", "code_hash": "generation",
    "dkim": "transport", "agentmail_delivery": "transport", "smtp_receipt": "transport",
    "witness": "witness", "attestation": "witness", "isnad": "witness",
}

HALF_LIFE_HOURS = {"generation": 720, "verification": 168}


def audit_chain(receipts: list[dict], workflow: str = None) -> dict:
    """Audit a receipt chain for completeness, ordering, and health."""
    findings = []
    score = 100.0
    
    if not receipts:
        return {"score": 0, "grade": "F", "findings": ["no receipts provided"]}
    
    # 1. Temporal ordering check (Harris Matrix)
    timestamps = []
    for i, r in enumerate(receipts):
        ts = r.get("timestamp")
        if ts:
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                timestamps.append((i, t, r.get("step", r.get("proof_type", "unknown"))))
            except (ValueError, TypeError):
                findings.append(f"receipt {i}: unparseable timestamp '{ts}'")
                score -= 5
    
    for j in range(1, len(timestamps)):
        if timestamps[j][1] < timestamps[j-1][1]:
            findings.append(
                f"temporal inversion: '{timestamps[j][2]}' ({timestamps[j][1].isoformat()}) "
                f"precedes '{timestamps[j-1][2]}' ({timestamps[j-1][1].isoformat()})"
            )
            score -= 15
    
    # 2. Gap detection
    if workflow and workflow in WORKFLOWS:
        expected = WORKFLOWS[workflow]
        actual_steps = [r.get("step", "") for r in receipts]
        for step in expected:
            if step not in actual_steps:
                findings.append(f"missing workflow step: '{step}'")
                score -= 10
    
    # 3. Attester diversity
    attesters = set()
    for r in receipts:
        a = r.get("attester") or r.get("issuer")
        if a:
            attesters.add(a)
    
    if len(attesters) < 2:
        findings.append(f"low attester diversity: {len(attesters)} unique attester(s)")
        score -= 15
    elif len(attesters) >= 3:
        findings.append(f"good attester diversity: {len(attesters)} unique attesters")
    
    # 4. Proof class coverage
    classes = set()
    for r in receipts:
        pt = r.get("proof_type", "")
        cls = PROOF_CLASSES.get(pt)
        if cls:
            classes.add(cls)
    
    required = {"payment", "generation", "transport"}
    missing_classes = required - classes
    if missing_classes:
        findings.append(f"missing proof classes: {', '.join(sorted(missing_classes))}")
        score -= 10 * len(missing_classes)
    else:
        findings.append("full proof class coverage ✓")
    
    # 5. Staleness check
    now = datetime.now(timezone.utc)
    stale_count = 0
    for r in receipts:
        ts = r.get("timestamp")
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_hours = (now - t).total_seconds() / 3600
            # Use generation half-life as default
            hl = HALF_LIFE_HOURS.get("generation", 720)
            if age_hours > hl:
                stale_count += 1
        except (ValueError, TypeError):
            pass
    
    if stale_count > 0:
        findings.append(f"{stale_count} receipt(s) past half-life (stale)")
        score -= 5 * stale_count
    
    # 6. Chain hash integrity
    chain_hashes = []
    for r in receipts:
        h = r.get("hash") or r.get("evidence_hash")
        if h:
            chain_hashes.append(h)
    
    if chain_hashes:
        findings.append(f"{len(chain_hashes)}/{len(receipts)} receipts have hashes")
    else:
        findings.append("no receipt hashes found — chain integrity unverifiable")
        score -= 10
    
    score = max(score, 0)
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"
    
    return {
        "score": round(score, 1),
        "grade": grade,
        "receipts_audited": len(receipts),
        "unique_attesters": len(attesters),
        "proof_classes": sorted(classes),
        "findings": findings,
        "audited_at": now.isoformat(),
    }


def demo():
    """Demo with tc3-like chain."""
    print("=== Receipt Chain Auditor ===\n")
    
    now = datetime.now(timezone.utc)
    
    # TC3 chain (healthy)
    tc3 = [
        {"step": "brief_posted", "timestamp": (now - timedelta(hours=48)).isoformat(), "attester": "gendolf", "proof_type": "content_hash", "hash": "abc123"},
        {"step": "provider_accepted", "timestamp": (now - timedelta(hours=47)).isoformat(), "attester": "kit_fox", "proof_type": "gen_sig", "hash": "def456"},
        {"step": "escrow_funded", "timestamp": (now - timedelta(hours=46)).isoformat(), "attester": "bro_agent", "proof_type": "paylock", "hash": "ghi789"},
        {"step": "deliverable_emailed", "timestamp": (now - timedelta(hours=24)).isoformat(), "attester": "kit_fox", "proof_type": "dkim", "hash": "jkl012"},
        {"step": "quality_scored", "timestamp": (now - timedelta(hours=23)).isoformat(), "attester": "bro_agent", "proof_type": "attestation", "hash": "mno345"},
        {"step": "attestations_filed", "timestamp": (now - timedelta(hours=22)).isoformat(), "attester": "momo", "proof_type": "witness", "hash": "pqr678"},
        {"step": "payment_released", "timestamp": (now - timedelta(hours=21)).isoformat(), "attester": "gendolf", "proof_type": "x402_tx", "hash": "stu901"},
    ]
    
    result = audit_chain(tc3, workflow="tc3_research")
    print(f"  TC3 (complete chain):")
    print(f"    Score: {result['score']} ({result['grade']})")
    print(f"    Attesters: {result['unique_attesters']}")
    print(f"    Classes: {result['proof_classes']}")
    for f in result['findings']:
        print(f"    → {f}")
    print()
    
    # Broken chain (missing steps, single attester)
    broken = [
        {"step": "escrow_funded", "timestamp": (now - timedelta(hours=48)).isoformat(), "attester": "bot1", "proof_type": "paylock"},
        {"step": "payment_released", "timestamp": (now - timedelta(hours=2)).isoformat(), "attester": "bot1", "proof_type": "x402_tx"},
    ]
    
    result = audit_chain(broken, workflow="tc3_research")
    print(f"  Broken chain (gaps + single attester):")
    print(f"    Score: {result['score']} ({result['grade']})")
    for f in result['findings']:
        print(f"    → {f}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        result = audit_chain(data.get("receipts", []), data.get("workflow"))
        print(json.dumps(result, indent=2))
    else:
        demo()
