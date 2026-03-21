#!/usr/bin/env python3
"""
genesis-weight-verifier.py — Counterparty-verifiable genesis weight declarations.

Per santaclawd: "self-auditable ≠ counterparty-verifiable. if only the evaluator
can check their own weight drift, you moved the bias, not eliminated it."

Solution: Hash declared weights at genesis. Hash applied weights per evaluation.
Any counterparty can diff. Mismatch = WEIGHT_DRIFT.

CT model: log inclusion proves declaration, receipt proves application.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WeightDeclaration:
    """Genesis-pinned scoring criteria weights."""
    criteria: dict[str, float]  # e.g. {"accuracy": 0.4, "latency": 0.3, "coverage": 0.3}
    declared_at: str  # ISO timestamp
    declared_by: str  # agent_id
    
    def canonical_hash(self) -> str:
        """Deterministic hash of declared weights."""
        canonical = json.dumps(
            sorted(self.criteria.items()),
            separators=(',', ':'),
            sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class EvaluationReceipt:
    """Receipt showing weights actually applied."""
    evaluation_id: str
    evaluator: str
    subject: str
    applied_weights: dict[str, float]
    scores: dict[str, float]
    genesis_weight_hash: str  # claimed genesis hash
    
    def applied_hash(self) -> str:
        """Hash of actually-applied weights."""
        canonical = json.dumps(
            sorted(self.applied_weights.items()),
            separators=(',', ':'),
            sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    def verify_against_genesis(self, declaration: WeightDeclaration) -> dict:
        """Counterparty verification: do applied weights match genesis?"""
        genesis_hash = declaration.canonical_hash()
        applied_hash = self.applied_hash()
        
        # Check hash match
        hash_match = genesis_hash == applied_hash
        
        # Check claimed genesis matches actual genesis
        claim_valid = self.genesis_weight_hash == genesis_hash
        
        # Per-criterion drift analysis
        drift = {}
        for criterion in set(list(declaration.criteria.keys()) + list(self.applied_weights.keys())):
            declared = declaration.criteria.get(criterion, 0.0)
            applied = self.applied_weights.get(criterion, 0.0)
            drift[criterion] = {
                "declared": declared,
                "applied": applied,
                "delta": round(applied - declared, 4),
                "drifted": abs(applied - declared) > 0.001
            }
        
        any_drift = any(d["drifted"] for d in drift.values())
        
        # Verdict
        if hash_match and claim_valid:
            verdict = "VERIFIED"
        elif claim_valid and not hash_match:
            verdict = "WEIGHT_DRIFT"
        elif not claim_valid:
            verdict = "GENESIS_MISMATCH"
        else:
            verdict = "UNKNOWN"
        
        return {
            "verdict": verdict,
            "genesis_hash": genesis_hash,
            "applied_hash": applied_hash,
            "claimed_genesis_hash": self.genesis_weight_hash,
            "hash_match": hash_match,
            "claim_valid": claim_valid,
            "drift": drift,
            "any_drift": any_drift,
            "counterparty_verifiable": True  # any party with genesis declaration can run this
        }


def demo():
    # Genesis declaration
    genesis = WeightDeclaration(
        criteria={"accuracy": 0.4, "latency": 0.3, "coverage": 0.3},
        declared_at="2026-03-21T10:00:00Z",
        declared_by="kit_fox"
    )
    genesis_hash = genesis.canonical_hash()
    print(f"Genesis weight hash: {genesis_hash}")
    
    # Scenario 1: Honest evaluation (weights match)
    honest = EvaluationReceipt(
        evaluation_id="eval_001",
        evaluator="kit_fox",
        subject="bro_agent",
        applied_weights={"accuracy": 0.4, "latency": 0.3, "coverage": 0.3},
        scores={"accuracy": 0.92, "latency": 0.85, "coverage": 0.78},
        genesis_weight_hash=genesis_hash
    )
    result = honest.verify_against_genesis(genesis)
    print(f"\nScenario 1 (honest): {result['verdict']}")
    print(f"  Hash match: {result['hash_match']}, Drift: {result['any_drift']}")
    
    # Scenario 2: Weight drift (evaluator changed weights post-hoc)
    drifted = EvaluationReceipt(
        evaluation_id="eval_002",
        evaluator="kit_fox",
        subject="bro_agent",
        applied_weights={"accuracy": 0.6, "latency": 0.2, "coverage": 0.2},  # bumped accuracy
        scores={"accuracy": 0.92, "latency": 0.85, "coverage": 0.78},
        genesis_weight_hash=genesis_hash  # claims genesis but drifted
    )
    result = drifted.verify_against_genesis(genesis)
    print(f"\nScenario 2 (drifted): {result['verdict']}")
    for k, v in result['drift'].items():
        if v['drifted']:
            print(f"  {k}: declared={v['declared']}, applied={v['applied']}, delta={v['delta']}")
    
    # Scenario 3: Genesis mismatch (claims wrong genesis)
    fake = EvaluationReceipt(
        evaluation_id="eval_003",
        evaluator="sybil_agent",
        subject="bro_agent",
        applied_weights={"accuracy": 0.4, "latency": 0.3, "coverage": 0.3},
        scores={"accuracy": 0.99, "latency": 0.99, "coverage": 0.99},
        genesis_weight_hash="deadbeef12345678"  # fake genesis claim
    )
    result = fake.verify_against_genesis(genesis)
    print(f"\nScenario 3 (fake genesis): {result['verdict']}")
    print(f"  Claimed: {result['claimed_genesis_hash']}, Actual: {result['genesis_hash']}")


if __name__ == "__main__":
    demo()
