#!/usr/bin/env python3
"""
witness-composition-validator.py — K-of-N distributed witness validation for ATF.

Per skinner: "Composition is the only clinical defense against write-time injection.
A single witness is a vulnerability; K-of-N is a distributed audit."

Per WBFT (Paykari et al., Fordham 2025): Ed25519 + Merkle tree = O(log t)
verification with O(n) message complexity. f ≤ ⌊(n-1)/3⌋ Byzantine faults.

Three witness models:
  UNANIMOUS  — All N witnesses must agree (N-of-N). Strongest, least available.
  THRESHOLD  — K-of-N witnesses. BFT: K ≥ 2f+1 where f = ⌊(N-1)/3⌋.
  WEIGHTED   — Witnesses have trust weights. Quorum = sum(weights) ≥ threshold.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WitnessModel(Enum):
    UNANIMOUS = "UNANIMOUS"
    THRESHOLD = "THRESHOLD"
    WEIGHTED = "WEIGHTED"


class AttestationResult(Enum):
    CONFIRMED = "CONFIRMED"     # Quorum reached, all agree
    CONTESTED = "CONTESTED"     # Quorum reached, disagreement
    PENDING = "PENDING"         # Insufficient witnesses
    REJECTED = "REJECTED"       # Quorum rejects
    SYBIL_DETECTED = "SYBIL"   # Operator monoculture


@dataclass
class Witness:
    agent_id: str
    operator_id: str
    trust_weight: float  # 0.0 - 1.0
    evidence_grade: str  # A-F
    timestamp: float
    receipt_hash: str
    agrees: bool  # True = confirms, False = disputes


@dataclass
class WitnessQuorum:
    receipt_id: str
    model: WitnessModel
    witnesses: list
    k_threshold: int  # K in K-of-N
    n_total: int       # N witnesses expected
    created_at: float = field(default_factory=time.time)


def bft_threshold(n: int) -> int:
    """BFT minimum: K ≥ 2f+1 where f = ⌊(n-1)/3⌋."""
    f = (n - 1) // 3
    return 2 * f + 1


def grade_to_weight(grade: str) -> float:
    return {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.3, "F": 0.0}.get(grade, 0.0)


def detect_sybil(witnesses: list) -> dict:
    """Detect operator monoculture in witness set."""
    operators = {}
    for w in witnesses:
        operators.setdefault(w.operator_id, []).append(w.agent_id)
    
    total = len(witnesses)
    max_concentration = max(len(agents) / total for agents in operators.values())
    unique_operators = len(operators)
    
    # Simpson diversity index
    simpson = 1.0 - sum((len(a)/total)**2 for a in operators.values())
    
    return {
        "unique_operators": unique_operators,
        "max_concentration": round(max_concentration, 3),
        "simpson_diversity": round(simpson, 3),
        "is_monoculture": max_concentration > 0.5,
        "effective_witnesses": unique_operators  # Same operator = 1 effective witness
    }


def compute_merkle_root(receipt_hashes: list) -> str:
    """Merkle tree root of witness receipt hashes for O(log t) verification."""
    if not receipt_hashes:
        return "empty"
    if len(receipt_hashes) == 1:
        return receipt_hashes[0]
    
    # Pad to even
    hashes = list(receipt_hashes)
    if len(hashes) % 2 == 1:
        hashes.append(hashes[-1])
    
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])
        new_level = []
        for i in range(0, len(hashes), 2):
            combined = hashes[i] + hashes[i+1]
            new_level.append(hashlib.sha256(combined.encode()).hexdigest()[:16])
        hashes = new_level
    
    return hashes[0]


def validate_quorum(quorum: WitnessQuorum) -> dict:
    """Validate a witness quorum and determine attestation result."""
    witnesses = quorum.witnesses
    
    if not witnesses:
        return {"result": AttestationResult.PENDING.value, "reason": "no witnesses"}
    
    # Sybil check first
    sybil = detect_sybil(witnesses)
    if sybil["is_monoculture"]:
        return {
            "result": AttestationResult.SYBIL_DETECTED.value,
            "reason": f"operator monoculture: {sybil['max_concentration']:.0%}",
            "sybil": sybil
        }
    
    agreeing = [w for w in witnesses if w.agrees]
    disputing = [w for w in witnesses if not w.agrees]
    
    if quorum.model == WitnessModel.UNANIMOUS:
        if len(witnesses) < quorum.n_total:
            result = AttestationResult.PENDING
            reason = f"waiting: {len(witnesses)}/{quorum.n_total}"
        elif len(disputing) > 0:
            result = AttestationResult.CONTESTED
            reason = f"{len(disputing)} dispute(s)"
        else:
            result = AttestationResult.CONFIRMED
            reason = "unanimous"
    
    elif quorum.model == WitnessModel.THRESHOLD:
        k = quorum.k_threshold
        effective = sybil["effective_witnesses"]
        
        if effective < k:
            result = AttestationResult.PENDING
            reason = f"effective witnesses {effective} < threshold {k}"
        elif len(agreeing) >= k:
            result = AttestationResult.CONFIRMED
            reason = f"{len(agreeing)}/{k} threshold met"
        elif len(disputing) >= k:
            result = AttestationResult.REJECTED
            reason = f"{len(disputing)} disputes exceed complement"
        else:
            result = AttestationResult.CONTESTED
            reason = f"split: {len(agreeing)} agree, {len(disputing)} dispute"
    
    elif quorum.model == WitnessModel.WEIGHTED:
        agree_weight = sum(w.trust_weight * grade_to_weight(w.evidence_grade) 
                          for w in agreeing)
        dispute_weight = sum(w.trust_weight * grade_to_weight(w.evidence_grade)
                            for w in disputing)
        total_weight = agree_weight + dispute_weight
        threshold = 0.67  # 2/3 weighted quorum
        
        if total_weight == 0:
            result = AttestationResult.PENDING
            reason = "zero weight"
        elif agree_weight / total_weight >= threshold:
            result = AttestationResult.CONFIRMED
            reason = f"weighted {agree_weight/total_weight:.0%} ≥ {threshold:.0%}"
        elif dispute_weight / total_weight >= threshold:
            result = AttestationResult.REJECTED
            reason = f"weighted dispute {dispute_weight/total_weight:.0%}"
        else:
            result = AttestationResult.CONTESTED
            reason = f"weighted split: {agree_weight:.2f} vs {dispute_weight:.2f}"
    
    # Merkle root of all witness receipts
    merkle = compute_merkle_root([w.receipt_hash for w in witnesses])
    
    return {
        "result": result.value,
        "reason": reason,
        "agreeing": len(agreeing),
        "disputing": len(disputing),
        "effective_witnesses": sybil["effective_witnesses"],
        "simpson_diversity": sybil["simpson_diversity"],
        "merkle_root": merkle,
        "model": quorum.model.value
    }


# === Scenarios ===

def scenario_clean_threshold():
    """3-of-5 threshold, diverse operators, all agree."""
    print("=== Scenario: Clean 3-of-5 Threshold ===")
    now = time.time()
    witnesses = [
        Witness("w1", "op_alpha", 0.9, "A", now, "h1", True),
        Witness("w2", "op_beta", 0.85, "A", now, "h2", True),
        Witness("w3", "op_gamma", 0.8, "B", now, "h3", True),
        Witness("w4", "op_delta", 0.7, "B", now, "h4", True),
        Witness("w5", "op_epsilon", 0.6, "C", now, "h5", True),
    ]
    quorum = WitnessQuorum("receipt_001", WitnessModel.THRESHOLD, witnesses, 
                           k_threshold=3, n_total=5)
    result = validate_quorum(quorum)
    print(f"  Result: {result['result']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Diversity: {result['simpson_diversity']}")
    print(f"  Merkle: {result['merkle_root']}")
    print()


def scenario_sybil_attack():
    """5 witnesses, same operator — sybil detected."""
    print("=== Scenario: Sybil Attack (Same Operator) ===")
    now = time.time()
    witnesses = [
        Witness(f"sybil_{i}", "op_shady", 0.9, "A", now, f"h{i}", True)
        for i in range(5)
    ]
    quorum = WitnessQuorum("receipt_002", WitnessModel.THRESHOLD, witnesses,
                           k_threshold=3, n_total=5)
    result = validate_quorum(quorum)
    print(f"  Result: {result['result']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Effective witnesses: {result.get('sybil', {}).get('effective_witnesses', '?')}")
    print()


def scenario_contested_split():
    """3 agree, 2 dispute — contested."""
    print("=== Scenario: Contested Split (3 agree, 2 dispute) ===")
    now = time.time()
    witnesses = [
        Witness("w1", "op_a", 0.9, "A", now, "h1", True),
        Witness("w2", "op_b", 0.85, "A", now, "h2", True),
        Witness("w3", "op_c", 0.8, "B", now, "h3", True),
        Witness("w4", "op_d", 0.9, "A", now, "h4", False),
        Witness("w5", "op_e", 0.85, "A", now, "h5", False),
    ]
    # BFT threshold for n=5: f=1, K=3
    k = bft_threshold(5)
    quorum = WitnessQuorum("receipt_003", WitnessModel.THRESHOLD, witnesses,
                           k_threshold=k, n_total=5)
    result = validate_quorum(quorum)
    print(f"  BFT threshold K={k} for N=5")
    print(f"  Result: {result['result']}")
    print(f"  Reason: {result['reason']}")
    print()


def scenario_weighted_quality():
    """Low-grade witnesses agree, high-grade disputes — weighted catches it."""
    print("=== Scenario: Weighted Quality (Grade Matters) ===")
    now = time.time()
    witnesses = [
        Witness("expert", "op_a", 0.95, "A", now, "h1", False),  # disputes
        Witness("novice1", "op_b", 0.3, "D", now, "h2", True),   # agrees
        Witness("novice2", "op_c", 0.3, "D", now, "h3", True),   # agrees
        Witness("novice3", "op_d", 0.3, "D", now, "h4", True),   # agrees
    ]
    quorum = WitnessQuorum("receipt_004", WitnessModel.WEIGHTED, witnesses,
                           k_threshold=3, n_total=4)
    result = validate_quorum(quorum)
    print(f"  1 expert (A, 0.95) disputes vs 3 novices (D, 0.3) agree")
    print(f"  Result: {result['result']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Key: grade-weighted quorum protects against low-quality majority")
    print()


if __name__ == "__main__":
    print("Witness Composition Validator — K-of-N Distributed Attestation for ATF")
    print("Per skinner + WBFT (Paykari et al., Fordham 2025)")
    print("=" * 70)
    print()
    scenario_clean_threshold()
    scenario_sybil_attack()
    scenario_contested_split()
    scenario_weighted_quality()
    
    print("=" * 70)
    print("KEY: Single witness = single point of injection.")
    print("K-of-N with operator diversity = distributed audit.")
    print("Merkle root = O(log t) verification of witness set.")
    print("WEIGHTED model prevents low-quality majority from overriding experts.")
