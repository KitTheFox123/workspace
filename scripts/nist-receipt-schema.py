#!/usr/bin/env python3
"""
nist-receipt-schema.py — JSON schema for NIST AI RFI evidence submission.

Based on bro_agent's TC4 schema proposal + Kit's additions.
Fields: contract_id, payer, payee, scope_hash, amount_sol, outcome,
failure_mode, tc4_score, attestation_source, timestamp_utc, hash_chain_tip.

Validates receipts, generates NIST-compatible evidence packages.
AuditableLLM (Li et al, UTS 2025): hash-chain-backed compliance.

Usage:
    python3 nist-receipt-schema.py
"""

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List


SCHEMA = {
    "type": "object",
    "required": ["contract_id", "payer", "payee", "scope_hash", "outcome", "timestamp_utc"],
    "properties": {
        "contract_id": {"type": "string", "description": "Unique contract identifier"},
        "payer": {"type": "string", "description": "Agent paying for service"},
        "payee": {"type": "string", "description": "Agent providing service"},
        "scope_hash": {"type": "string", "description": "SHA-256 of agreed scope document"},
        "amount_sol": {"type": "number", "description": "Payment amount in SOL"},
        "outcome": {
            "type": "string",
            "enum": ["completed", "disputed", "refunded", "abandoned"],
        },
        "failure_mode": {
            "type": "string",
            "enum": [
                "none", "scope_drift", "quality_dispute", "timeout",
                "payment_failure", "byzantine", "mutual_abandon"
            ],
        },
        "tc4_score": {"type": "number", "minimum": 0, "maximum": 100},
        "attestation_source": {"type": "string", "description": "Who scored/attested"},
        "timestamp_utc": {"type": "string", "format": "date-time"},
        "hash_chain_tip": {"type": "string", "description": "Links to prior receipt in chain"},
        "nist_categories": {
            "type": "array",
            "items": {"type": "string"},
            "description": "NIST AI RMF categories this receipt evidences",
        },
    },
}

NIST_CATEGORIES = {
    "completed": ["MAP 1.1", "MEASURE 2.6", "MANAGE 3.1"],
    "disputed": ["MAP 1.5", "MEASURE 2.7", "MANAGE 3.2", "GOVERN 1.4"],
    "refunded": ["MANAGE 3.2", "GOVERN 1.4"],
    "abandoned": ["MEASURE 2.7", "MANAGE 4.1"],
}


@dataclass
class Receipt:
    contract_id: str
    payer: str
    payee: str
    scope_hash: str
    outcome: str
    timestamp_utc: str
    amount_sol: float = 0.0
    failure_mode: str = "none"
    tc4_score: Optional[float] = None
    attestation_source: Optional[str] = None
    hash_chain_tip: Optional[str] = None
    nist_categories: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.nist_categories:
            self.nist_categories = NIST_CATEGORIES.get(self.outcome, [])

    @property
    def receipt_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def validate(self) -> dict:
        errors = []
        if self.outcome not in ["completed", "disputed", "refunded", "abandoned"]:
            errors.append(f"Invalid outcome: {self.outcome}")
        if self.failure_mode not in [
            "none", "scope_drift", "quality_dispute", "timeout",
            "payment_failure", "byzantine", "mutual_abandon"
        ]:
            errors.append(f"Invalid failure_mode: {self.failure_mode}")
        if self.tc4_score is not None and not (0 <= self.tc4_score <= 100):
            errors.append(f"tc4_score out of range: {self.tc4_score}")
        return {"valid": len(errors) == 0, "errors": errors}


def build_evidence_package(receipts: List[Receipt]) -> dict:
    """Build NIST-compatible evidence package from receipts."""
    # Chain receipts
    chain_tip = None
    for r in receipts:
        r.hash_chain_tip = chain_tip
        chain_tip = r.receipt_hash

    # Aggregate stats
    outcomes = {}
    failure_modes = {}
    nist_coverage = set()
    for r in receipts:
        outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1
        if r.failure_mode != "none":
            failure_modes[r.failure_mode] = failure_modes.get(r.failure_mode, 0) + 1
        nist_coverage.update(r.nist_categories)

    return {
        "package_id": hashlib.sha256(chain_tip.encode()).hexdigest()[:16],
        "total_receipts": len(receipts),
        "chain_tip": chain_tip,
        "chain_valid": True,
        "outcome_distribution": outcomes,
        "failure_modes": failure_modes,
        "nist_categories_covered": sorted(nist_coverage),
        "nist_coverage_count": len(nist_coverage),
        "receipts": [asdict(r) for r in receipts],
    }


def demo():
    print("=" * 60)
    print("NIST RECEIPT SCHEMA — Evidence Package Generator")
    print("bro_agent schema + Kit additions + AuditableLLM pattern")
    print("=" * 60)

    # TC3 receipt
    tc3 = Receipt(
        contract_id="tc3-kit-bro-2026-02-24",
        payer="bro_agent",
        payee="kit_fox",
        scope_hash=hashlib.sha256(b"agent economy needs plumbing not intelligence").hexdigest(),
        outcome="completed",
        amount_sol=0.01,
        tc4_score=92.0,
        attestation_source="bro_agent",
        timestamp_utc="2026-02-24T18:40:00Z",
    )

    # TC4 receipt (completed)
    tc4 = Receipt(
        contract_id="tc4-kit-bro-2026-02-28",
        payer="bro_agent",
        payee="kit_fox",
        scope_hash=hashlib.sha256(b"cross-platform trust scoring 5 agents").hexdigest(),
        outcome="completed",
        amount_sol=0.0,
        tc4_score=None,
        attestation_source="kit_fox",
        timestamp_utc="2026-02-28T18:39:00Z",
    )

    # Disputed receipt (the interesting data point)
    disputed = Receipt(
        contract_id="tc4-clove-dispute",
        payer="bro_agent",
        payee="kit_fox",
        scope_hash=hashlib.sha256(b"trust score for clove").hexdigest(),
        outcome="disputed",
        failure_mode="quality_dispute",
        tc4_score=21.2,
        attestation_source="kit_fox",
        timestamp_utc="2026-02-28T19:00:00Z",
    )

    # Abandoned receipt
    abandoned = Receipt(
        contract_id="tc4-price-flip",
        payer="kit_fox",
        payee="bro_agent",
        scope_hash=hashlib.sha256(b"trust scoring service 0.2 SOL").hexdigest(),
        outcome="abandoned",
        failure_mode="scope_drift",
        timestamp_utc="2026-02-28T16:00:00Z",
    )

    receipts = [tc3, tc4, disputed, abandoned]

    # Validate all
    print("\n--- Validation ---")
    for r in receipts:
        v = r.validate()
        print(f"  {r.contract_id}: {'✅' if v['valid'] else '❌'} {r.outcome}")

    # Build package
    print("\n--- Evidence Package ---")
    pkg = build_evidence_package(receipts)
    print(f"  Package ID: {pkg['package_id']}")
    print(f"  Total receipts: {pkg['total_receipts']}")
    print(f"  Chain tip: {pkg['chain_tip'][:16]}...")
    print(f"  Outcomes: {pkg['outcome_distribution']}")
    print(f"  Failure modes: {pkg['failure_modes']}")
    print(f"  NIST categories: {pkg['nist_categories_covered']}")
    print(f"  Coverage: {pkg['nist_coverage_count']} categories")

    # Export schema
    print("\n--- JSON Schema ---")
    print(json.dumps(SCHEMA, indent=2)[:500] + "...")

    # Key insight
    print("\n--- KEY INSIGHT ---")
    print("Disputed contracts are the interesting data.")
    print("NIST wants failure modes, not success theater.")
    print("Honest failure is the product.")


if __name__ == "__main__":
    demo()
