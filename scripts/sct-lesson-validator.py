#!/usr/bin/env python3
"""
sct-lesson-validator.py — Don't repeat CT's SCT mistake.

Per santaclawd: SCTs (Signed Certificate Timestamps) were promises,
not proofs. Browsers trusted them without inclusion proofs. The gossip
protocol from RFC 6962 was handwaved and never shipped.

ATF receipts must be verifiable at interaction time:
  - Promise (SCT-like): "I will include this" → WEAK
  - Inclusion proof: "Here's the Merkle path" → STRONG
  - Interaction receipt: verifiable without deferred trust → REQUIRED

K-of-N requirements:
  - K=2 minimum (BFT needs >1)
  - Value-tiered: K=3 for high-value transactions
  - Diversity audit: Simpson index on operator field

Usage:
    python3 sct-lesson-validator.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProofStrength(Enum):
    PROMISE = "PROMISE"          # SCT-like: deferred verification
    INCLUSION = "INCLUSION"      # Merkle proof: verifiable now
    INTERACTION = "INTERACTION"  # ATF receipt: bilateral verification


class VerificationVerdict(Enum):
    STRONG = "STRONG"            # Inclusion proof + K≥2 diverse
    ADEQUATE = "ADEQUATE"        # Inclusion proof + K=1
    WEAK = "WEAK"                # Promise only
    BROKEN = "BROKEN"            # Failed verification


@dataclass
class Attestation:
    """One attestation in a receipt (like one SCT from one log)."""
    attester_id: str
    operator_id: str              # who runs this attester
    proof_type: ProofStrength
    evidence_hash: str
    timestamp: float
    inclusion_proof: Optional[str] = None  # Merkle path if INCLUSION


@dataclass
class Receipt:
    """ATF receipt with multiple attestations."""
    task_hash: str
    deliverable_hash: str
    attestations: list[Attestation] = field(default_factory=list)
    value_tier: str = "routine"   # routine | high | critical


def simpson_diversity(operators: list[str]) -> float:
    """Simpson's Diversity Index — probability two random picks are different operators."""
    if len(operators) <= 1:
        return 0.0
    from collections import Counter
    counts = Counter(operators)
    n = len(operators)
    return 1.0 - sum(c * (c - 1) for c in counts.values()) / (n * (n - 1))


def required_k(value_tier: str) -> int:
    """Minimum attestations required by value tier."""
    return {"routine": 2, "high": 3, "critical": 4}.get(value_tier, 2)


def validate_receipt(receipt: Receipt) -> dict:
    """Validate receipt against CT lessons."""
    attestations = receipt.attestations
    k_required = required_k(receipt.value_tier)

    if not attestations:
        return {
            "verdict": VerificationVerdict.BROKEN.value,
            "reason": "no attestations",
            "ct_lesson": "CT accepted certs with zero SCTs from some logs",
            "action": "REJECT",
        }

    # Classify proof types
    promises = [a for a in attestations if a.proof_type == ProofStrength.PROMISE]
    inclusions = [a for a in attestations if a.proof_type == ProofStrength.INCLUSION]
    interactions = [a for a in attestations if a.proof_type == ProofStrength.INTERACTION]

    strong_count = len(inclusions) + len(interactions)
    promise_only = strong_count == 0

    # Operator diversity
    operators = [a.operator_id for a in attestations]
    diversity = simpson_diversity(operators)
    unique_operators = len(set(operators))

    # K check
    k_met = len(attestations) >= k_required
    k_diverse = unique_operators >= k_required  # distinct operators

    # Evidence consistency
    evidence_hashes = set(a.evidence_hash for a in attestations)
    consistent = len(evidence_hashes) == 1

    # Verdict
    issues = []
    if promise_only:
        issues.append("PROMISE_ONLY — CT's SCT mistake")
    if not k_met:
        issues.append(f"K_INSUFFICIENT — need {k_required}, have {len(attestations)}")
    if not k_diverse:
        issues.append(f"OPERATOR_MONOCULTURE — {unique_operators} unique of {len(attestations)}")
    if diversity < 0.5 and len(attestations) > 1:
        issues.append(f"LOW_DIVERSITY — Simpson={diversity:.2f}")
    if not consistent:
        issues.append(f"SPLIT_VIEW — {len(evidence_hashes)} different evidence hashes")

    if not issues:
        verdict = VerificationVerdict.STRONG
        action = "ACCEPT"
    elif promise_only:
        verdict = VerificationVerdict.WEAK
        action = "REJECT — promises are not proofs"
    elif not k_met or not consistent:
        verdict = VerificationVerdict.BROKEN
        action = "REJECT"
    else:
        verdict = VerificationVerdict.ADEQUATE
        action = "ACCEPT_WITH_WARNING"

    return {
        "verdict": verdict.value,
        "action": action,
        "value_tier": receipt.value_tier,
        "k_required": k_required,
        "k_actual": len(attestations),
        "k_diverse": unique_operators,
        "strong_proofs": strong_count,
        "promises_only": len(promises),
        "simpson_diversity": round(diversity, 3),
        "evidence_consistent": consistent,
        "issues": issues,
        "ct_lessons_applied": [
            "SCTs are promises not proofs — require inclusion proofs",
            "gossip was handwaved — require diversity at interaction time",
            "vendor trust filled gaps — require operator independence",
        ],
    }


def demo():
    print("=" * 60)
    print("SCT Lesson Validator — Don't repeat CT's mistake")
    print("=" * 60)

    now = 1711234567.0

    # Scenario 1: Strong receipt (2 diverse inclusion proofs)
    print("\n--- Scenario 1: Strong (2 diverse inclusion proofs) ---")
    r1 = Receipt(
        task_hash="task001", deliverable_hash="del001", value_tier="routine",
        attestations=[
            Attestation("log_a", "google", ProofStrength.INCLUSION, "ev001", now, "merkle_a"),
            Attestation("log_b", "cloudflare", ProofStrength.INCLUSION, "ev001", now, "merkle_b"),
        ],
    )
    print(json.dumps(validate_receipt(r1), indent=2))

    # Scenario 2: Promise-only (CT's SCT mistake)
    print("\n--- Scenario 2: Promise-only (SCT mistake) ---")
    r2 = Receipt(
        task_hash="task002", deliverable_hash="del002", value_tier="routine",
        attestations=[
            Attestation("log_a", "google", ProofStrength.PROMISE, "ev002", now),
            Attestation("log_b", "google", ProofStrength.PROMISE, "ev002", now),
        ],
    )
    print(json.dumps(validate_receipt(r2), indent=2))

    # Scenario 3: Monoculture (same operator)
    print("\n--- Scenario 3: Monoculture (3 logs, 1 operator) ---")
    r3 = Receipt(
        task_hash="task003", deliverable_hash="del003", value_tier="high",
        attestations=[
            Attestation("log_a", "bigcorp", ProofStrength.INCLUSION, "ev003", now, "m1"),
            Attestation("log_b", "bigcorp", ProofStrength.INCLUSION, "ev003", now, "m2"),
            Attestation("log_c", "bigcorp", ProofStrength.INCLUSION, "ev003", now, "m3"),
        ],
    )
    print(json.dumps(validate_receipt(r3), indent=2))

    # Scenario 4: Split view (different evidence hashes)
    print("\n--- Scenario 4: Split view (conflicting evidence) ---")
    r4 = Receipt(
        task_hash="task004", deliverable_hash="del004", value_tier="routine",
        attestations=[
            Attestation("log_a", "google", ProofStrength.INCLUSION, "ev004a", now, "m1"),
            Attestation("log_b", "cloudflare", ProofStrength.INCLUSION, "ev004b", now, "m2"),
        ],
    )
    print(json.dumps(validate_receipt(r4), indent=2))

    # Scenario 5: High-value with K=2 (insufficient)
    print("\n--- Scenario 5: High-value needs K=3, has K=2 ---")
    r5 = Receipt(
        task_hash="task005", deliverable_hash="del005", value_tier="high",
        attestations=[
            Attestation("log_a", "google", ProofStrength.INCLUSION, "ev005", now, "m1"),
            Attestation("log_b", "cloudflare", ProofStrength.INCLUSION, "ev005", now, "m2"),
        ],
    )
    print(json.dumps(validate_receipt(r5), indent=2))

    # Scenario 6: Critical with full diversity
    print("\n--- Scenario 6: Critical (4 diverse operators, inclusion proofs) ---")
    r6 = Receipt(
        task_hash="task006", deliverable_hash="del006", value_tier="critical",
        attestations=[
            Attestation("log_a", "google", ProofStrength.INCLUSION, "ev006", now, "m1"),
            Attestation("log_b", "cloudflare", ProofStrength.INCLUSION, "ev006", now, "m2"),
            Attestation("log_c", "digicert", ProofStrength.INTERACTION, "ev006", now),
            Attestation("log_d", "sectigo", ProofStrength.INTERACTION, "ev006", now),
        ],
    )
    print(json.dumps(validate_receipt(r6), indent=2))

    print("\n" + "=" * 60)
    print("CT shipped promises (SCTs). Never fixed gossip.")
    print("ATF: inclusion proofs at interaction time. K≥2 diverse.")
    print("Value-tiered: routine=2, high=3, critical=4.")
    print("Simpson diversity gate: <0.5 = operator monoculture.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
