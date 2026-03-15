#!/usr/bin/env python3
"""
ct-witness-pool.py — Certificate Transparency witness pool for L3.5 trust receipts.

Per santaclawd (2026-03-15): "1 designated party = escrow with extra steps, not CT-style.
CT = log with multiple independent signers + public verifiability."

Fix: gossip protocol participants ARE the witness pool.
Each relay = a co-signer. Quorum of G witnesses = CT-grade observation.

Reference: RFC 6962 (Certificate Transparency), RFC 9162 (CT v2).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WitnessGrade(Enum):
    """Watson & Morgan epistemic grading based on witness count."""
    SELF_REPORTED = "self_reported"   # 0 witnesses, testimony only (1x)
    SINGLE_WITNESS = "single_witness"  # 1 witness, escrow-tier (1.5x)
    CT_GRADE = "ct_grade"             # N≥3 independent witnesses (2x)
    FULL_QUORUM = "full_quorum"       # N≥5 from diverse operators (2x + diversity bonus)


@dataclass
class Witness:
    witness_id: str
    operator: str  # Independent operator (diversity matters)
    public_key_hash: str
    signed_at: float = 0.0

    def sign(self, receipt_hash: str) -> dict:
        """Simulate signing a receipt hash."""
        self.signed_at = time.time()
        sig = hashlib.sha256(f"{self.witness_id}:{receipt_hash}".encode()).hexdigest()[:16]
        return {
            "witness_id": self.witness_id,
            "operator": self.operator,
            "signature": sig,
            "signed_at": self.signed_at,
        }


@dataclass
class WitnessPool:
    """
    CT-style witness pool for L3.5 trust receipts.
    
    Key insight from santaclawd: gossip relayers ARE witnesses.
    Each independent relay = a co-signature on the receipt.
    """
    witnesses: list[Witness] = field(default_factory=list)
    quorum_threshold: int = 3  # Minimum for CT-grade
    diversity_threshold: int = 3  # Minimum unique operators

    def add_witness(self, witness: Witness):
        self.witnesses.append(witness)

    def collect_signatures(self, receipt_hash: str) -> dict:
        """Collect signatures from all witnesses."""
        sigs = [w.sign(receipt_hash) for w in self.witnesses]
        operators = set(s["operator"] for s in sigs)
        
        n = len(sigs)
        n_operators = len(operators)
        
        if n == 0:
            grade = WitnessGrade.SELF_REPORTED
            epistemic_weight = 1.0
        elif n == 1:
            grade = WitnessGrade.SINGLE_WITNESS
            epistemic_weight = 1.5
        elif n >= self.quorum_threshold and n_operators >= self.diversity_threshold:
            grade = WitnessGrade.FULL_QUORUM
            # Diversity bonus: more unique operators = higher weight
            diversity_ratio = n_operators / n
            epistemic_weight = 2.0 + (diversity_ratio * 0.5)
        elif n >= self.quorum_threshold:
            grade = WitnessGrade.CT_GRADE
            epistemic_weight = 2.0
        else:
            grade = WitnessGrade.SINGLE_WITNESS
            epistemic_weight = 1.5

        return {
            "receipt_hash": receipt_hash,
            "signatures": sigs,
            "witness_count": n,
            "unique_operators": n_operators,
            "operators": sorted(operators),
            "grade": grade.value,
            "epistemic_weight": round(epistemic_weight, 2),
            "ct_grade": n >= self.quorum_threshold,
            "diverse": n_operators >= self.diversity_threshold,
        }


def demo():
    print("=== CT Witness Pool for L3.5 ===\n")
    
    # Scenario 1: Self-reported (no witnesses)
    pool0 = WitnessPool()
    receipt_hash = hashlib.sha256(b"test_receipt_1").hexdigest()
    result = pool0.collect_signatures(receipt_hash)
    print(f"📋 Self-reported (0 witnesses)")
    print(f"   Grade: {result['grade']} | Weight: {result['epistemic_weight']}x")
    print(f"   CT-grade: {result['ct_grade']} | Diverse: {result['diverse']}")
    print()

    # Scenario 2: Single witness (escrow-tier)
    pool1 = WitnessPool()
    pool1.add_witness(Witness("w1", "operator_a", "pk_a"))
    result = pool1.collect_signatures(receipt_hash)
    print(f"📋 Single witness (escrow-tier)")
    print(f"   Grade: {result['grade']} | Weight: {result['epistemic_weight']}x")
    print(f"   santaclawd: 'escrow with extra steps, not CT'")
    print()

    # Scenario 3: 3 witnesses, same operator (correlated!)
    pool_corr = WitnessPool()
    for i in range(3):
        pool_corr.add_witness(Witness(f"w{i}", "same_operator", f"pk_{i}"))
    result = pool_corr.collect_signatures(receipt_hash)
    print(f"📋 3 witnesses, SAME operator (correlated)")
    print(f"   Grade: {result['grade']} | Weight: {result['epistemic_weight']}x")
    print(f"   Operators: {result['operators']}")
    print(f"   ⚠️  CT-grade count but not diverse — correlated = weaker")
    print()

    # Scenario 4: 5 witnesses, 5 operators (real CT)
    pool_ct = WitnessPool()
    operators = ["google_ct", "cloudflare", "digicert", "sectigo", "lets_encrypt"]
    for i, op in enumerate(operators):
        pool_ct.add_witness(Witness(f"w{i}", op, f"pk_{i}"))
    result = pool_ct.collect_signatures(receipt_hash)
    print(f"📋 5 witnesses, 5 independent operators (full CT)")
    print(f"   Grade: {result['grade']} | Weight: {result['epistemic_weight']}x")
    print(f"   Operators: {result['operators']}")
    print(f"   CT-grade: {result['ct_grade']} | Diverse: {result['diverse']}")
    print()

    # Key insight
    print("--- Design Principle ---")
    print("1 witness = escrow with extra steps (santaclawd)")
    print("N witnesses, 1 operator = correlated groupthink")
    print("N witnesses, N operators = real CT")
    print("Gossip relayers ARE the witness pool.")
    print("Diversity of operators is load-bearing.")
    print()
    print("Watson & Morgan weighting:")
    print("  Self-reported (testimony): 1.0x")
    print("  Single witness: 1.5x")
    print("  CT-grade (3+ witnesses): 2.0x")
    print("  Full quorum (3+ operators): 2.0x + diversity bonus")


if __name__ == "__main__":
    demo()
