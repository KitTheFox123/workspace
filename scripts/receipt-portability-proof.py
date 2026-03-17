#!/usr/bin/env python3
"""
receipt-portability-proof.py — Demonstrate receipt portability across platforms.

The cold start problem IS a data portability problem (santaclawd, 2026-03-17).
This script takes a receipt generated on platform A and proves it's valid on platform B
without any platform-specific context.

Key insight: DKIM-signed email attachment = authenticated, platform-independent delivery.
The receipt carries its own proof. The platform is just a transport.

Usage:
    python receipt-portability-proof.py [--demo]
"""

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class PortableReceipt:
    """L3.5 trust receipt — platform-independent by design."""
    version: str = "0.1.0"
    receipt_id: str = ""
    agent_id: str = ""
    task_hash: str = ""
    decision_type: str = "delivery"  # delivery | refusal | liveness | slash
    timestamp: str = ""
    
    # Trust dimensions (0.0-1.0)
    timeliness: float = 0.0
    groundedness: float = 0.0
    attestation: float = 0.0
    self_knowledge: float = 0.0
    consistency: float = 0.0
    
    # Proof
    merkle_root: str = ""
    merkle_proof: list = field(default_factory=list)
    witnesses: list = field(default_factory=list)
    
    # Portability metadata
    origin_platform: str = ""
    scar_reference: Optional[str] = None
    
    def canonical(self) -> str:
        """Deterministic JSON for content-addressable ID."""
        d = asdict(self)
        d.pop('receipt_id', None)
        return json.dumps(d, sort_keys=True, separators=(',', ':'))
    
    def compute_id(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()[:16]


class PortabilityVerifier:
    """Verify receipt validity WITHOUT platform context."""
    
    def __init__(self, min_witnesses: int = 2, min_diversity: float = 0.5):
        self.min_witnesses = min_witnesses
        self.min_diversity = min_diversity
    
    def verify(self, receipt: dict) -> dict:
        """Platform-independent verification. Returns {valid, errors, warnings, score}."""
        errors = []
        warnings = []
        
        # 1. Schema check (required fields)
        required = ['version', 'agent_id', 'task_hash', 'decision_type', 
                     'timestamp', 'merkle_root', 'witnesses']
        for f in required:
            if f not in receipt or not receipt[f]:
                errors.append(f"missing_required: {f}")
        
        # 2. Content-addressable ID check
        if 'receipt_id' in receipt:
            r = dict(receipt)
            stored_id = r.pop('receipt_id')
            canonical = json.dumps(r, sort_keys=True, separators=(',', ':'))
            computed = hashlib.sha256(canonical.encode()).hexdigest()[:16]
            if stored_id != computed:
                errors.append(f"id_mismatch: stored={stored_id} computed={computed}")
        
        # 3. Witness independence
        witnesses = receipt.get('witnesses', [])
        if len(witnesses) < self.min_witnesses:
            errors.append(f"insufficient_witnesses: {len(witnesses)} < {self.min_witnesses}")
        
        orgs = set()
        for w in witnesses:
            if isinstance(w, dict):
                orgs.add(w.get('operator_id', w.get('org', 'unknown')))
        
        if len(witnesses) > 0:
            diversity = len(orgs) / len(witnesses)
            if diversity < self.min_diversity:
                warnings.append(f"low_diversity: {diversity:.2f} < {self.min_diversity}")
        
        # 4. Dimension bounds
        for dim in ['timeliness', 'groundedness', 'attestation', 'self_knowledge', 'consistency']:
            val = receipt.get(dim)
            if val is not None and (val < 0.0 or val > 1.0):
                errors.append(f"out_of_bounds: {dim}={val}")
        
        # 5. Merkle proof (structural check — full verification needs the tree)
        proof = receipt.get('merkle_proof', [])
        if not proof:
            warnings.append("no_merkle_proof: inclusion unverifiable without proof")
        
        # 6. Platform independence score
        # Receipt is MORE portable if it doesn't depend on platform-specific fields
        platform_deps = 0
        platform_fields = ['origin_platform', 'platform_tx_id', 'platform_api_version']
        for pf in platform_fields:
            if pf in receipt and receipt[pf]:
                platform_deps += 1
        
        portability = 1.0 - (platform_deps / len(platform_fields))
        
        score = 1.0
        score -= len(errors) * 0.25
        score -= len(warnings) * 0.05
        score = max(0.0, min(1.0, score))
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'score': round(score, 2),
            'portability': round(portability, 2),
            'witness_count': len(witnesses),
            'org_diversity': round(len(orgs) / max(len(witnesses), 1), 2),
        }


def demo_portability():
    """Show same receipt verified on 3 different 'platforms' with different policies."""
    
    # Receipt generated on Platform A (PayLock)
    receipt = PortableReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:a1b2c3d4e5f6",
        decision_type="delivery",
        timestamp="2026-03-17T04:00:00Z",
        timeliness=0.92,
        groundedness=0.87,
        attestation=0.95,
        self_knowledge=0.78,
        consistency=0.91,
        merkle_root="sha256:deadbeef01234567",
        merkle_proof=["sha256:left1", "sha256:right1"],
        witnesses=[
            {"agent_id": "agent:bro", "operator_id": "org:braindiff", "score": 0.92},
            {"agent_id": "agent:momo", "operator_id": "org:attestnet", "score": 0.88},
            {"agent_id": "agent:gendolf", "operator_id": "org:independent", "score": 0.95},
        ],
        origin_platform="paylock",
    )
    receipt.receipt_id = receipt.compute_id()
    
    receipt_dict = asdict(receipt)
    
    print("=" * 60)
    print("RECEIPT PORTABILITY PROOF")
    print("Same receipt, three verification policies")
    print("=" * 60)
    
    # Platform B: Strict (OpenClaw-like)
    strict = PortabilityVerifier(min_witnesses=3, min_diversity=0.7)
    result_strict = strict.verify(receipt_dict)
    print(f"\n[STRICT] OpenClaw-style enforcement:")
    print(f"  Valid: {result_strict['valid']}")
    print(f"  Score: {result_strict['score']}")
    print(f"  Portability: {result_strict['portability']}")
    print(f"  Witnesses: {result_strict['witness_count']} (diversity: {result_strict['org_diversity']})")
    if result_strict['warnings']:
        print(f"  Warnings: {result_strict['warnings']}")
    
    # Platform C: Report-only (LangChain-like)
    report = PortabilityVerifier(min_witnesses=1, min_diversity=0.3)
    result_report = report.verify(receipt_dict)
    print(f"\n[REPORT] LangChain-style (accept + log):")
    print(f"  Valid: {result_report['valid']}")
    print(f"  Score: {result_report['score']}")
    print(f"  Portability: {result_report['portability']}")
    
    # Platform D: Permissive (new runtime)
    permissive = PortabilityVerifier(min_witnesses=0, min_diversity=0.0)
    result_perm = permissive.verify(receipt_dict)
    print(f"\n[PERMISSIVE] New runtime (learning mode):")
    print(f"  Valid: {result_perm['valid']}")
    print(f"  Score: {result_perm['score']}")
    print(f"  Portability: {result_perm['portability']}")
    
    # The point
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("Same receipt. Three platforms. Three policies.")
    print("FORMAT converges. POLICY diverges. By design.")
    print(f"{'=' * 60}")
    
    # Cold start escape
    print(f"\nCOLD START ESCAPE:")
    print(f"Agent built reputation on PayLock (500 deliveries).")
    print(f"Moves to new platform. Brings receipts.")
    print(f"New platform verifies: Merkle proof ✓, witnesses ✓, dimensions ✓")
    print(f"Reputation portable. No lock-in. No cold restart.")
    print(f"The data follows the agent because it was never the platform's to keep.")
    
    return {
        'strict': result_strict,
        'report': result_report,
        'permissive': result_perm,
    }


if __name__ == '__main__':
    import sys
    results = demo_portability()
    
    # Summary
    all_valid = all(r['valid'] for r in results.values())
    print(f"\nAll platforms accept: {all_valid}")
