#!/usr/bin/env python3
"""
counterparty-weight-verifier.py — Counterparty-verifiable genesis weight verification.

Per santaclawd: "self-auditable ≠ counterparty-verifiable. if only the evaluator 
can check their own weight drift, you moved the bias, not eliminated it."

Solution: Genesis scoring weights published as hash-pinned JSON. Any counterparty
can fetch, hash, compare against genesis_hash embedded in receipts.

CT model: weights are the pre-certificate. Drift = misissuance.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class GenesisWeights:
    """Scoring criteria declared at genesis, hash-pinned."""
    criteria: dict[str, float]  # axis -> weight
    aggregation: str  # "MIN" or "WEIGHTED"
    version: str
    declared_at: str
    
    def canonical_hash(self) -> str:
        """Deterministic hash of weight declaration."""
        canonical = json.dumps({
            "criteria": dict(sorted(self.criteria.items())),
            "aggregation": self.aggregation,
            "version": self.version,
            "declared_at": self.declared_at
        }, separators=(',', ':'), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    def to_publishable(self) -> dict:
        """Format for counterparty consumption."""
        return {
            "genesis_weights": {
                "criteria": self.criteria,
                "aggregation": self.aggregation,
                "version": self.version,
                "declared_at": self.declared_at,
                "genesis_hash": self.canonical_hash()
            }
        }


class CounterpartyVerifier:
    """Verify that an evaluator's current weights match their genesis declaration."""
    
    def verify(self, receipt_genesis_hash: str, fetched_weights: GenesisWeights) -> dict:
        """
        Counterparty verification: compare genesis_hash in receipt against 
        hash of fetched weight declaration.
        """
        computed_hash = fetched_weights.canonical_hash()
        match = receipt_genesis_hash == computed_hash
        
        return {
            "verified": match,
            "receipt_hash": receipt_genesis_hash,
            "computed_hash": computed_hash,
            "verdict": "CONSISTENT" if match else "WEIGHT_DRIFT_DETECTED",
            "severity": "OK" if match else "CRITICAL",
            "detail": (
                "Genesis weights match receipt declaration"
                if match else
                f"MISISSUANCE: receipt claims {receipt_genesis_hash}, "
                f"current weights hash to {computed_hash}. "
                "Evaluator changed scoring criteria without REISSUE."
            )
        }
    
    def audit_weight_history(self, history: list[tuple[str, GenesisWeights]]) -> dict:
        """Audit a sequence of (timestamp, weights) for undeclared changes."""
        if not history:
            return {"changes": 0, "verdict": "NO_DATA"}
        
        changes = []
        prev_hash = None
        for ts, weights in history:
            h = weights.canonical_hash()
            if prev_hash and h != prev_hash:
                changes.append({
                    "timestamp": ts,
                    "old_hash": prev_hash,
                    "new_hash": h,
                    "new_weights": weights.criteria
                })
            prev_hash = h
        
        declared_reissues = sum(1 for c in changes if True)  # placeholder
        
        return {
            "total_snapshots": len(history),
            "weight_changes": len(changes),
            "changes": changes,
            "verdict": (
                "STABLE" if not changes else
                "REISSUED" if len(changes) <= 2 else
                "SUSPICIOUS_DRIFT"
            )
        }


def demo():
    # Genesis declaration
    genesis = GenesisWeights(
        criteria={"maturity": 0.25, "health": 0.25, "consistency": 0.25, "independence": 0.25},
        aggregation="MIN",
        version="1.0.0",
        declared_at="2026-03-21T00:00:00Z"
    )
    
    print("=== Genesis Declaration ===")
    pub = genesis.to_publishable()
    print(json.dumps(pub, indent=2))
    genesis_hash = genesis.canonical_hash()
    
    verifier = CounterpartyVerifier()
    
    # Scenario 1: Honest evaluator — weights unchanged
    print("\n=== Scenario: Honest Evaluator ===")
    honest = GenesisWeights(
        criteria={"maturity": 0.25, "health": 0.25, "consistency": 0.25, "independence": 0.25},
        aggregation="MIN", version="1.0.0", declared_at="2026-03-21T00:00:00Z"
    )
    result = verifier.verify(genesis_hash, honest)
    print(f"Verdict: {result['verdict']} | Verified: {result['verified']}")
    
    # Scenario 2: Drifted evaluator — secretly halved health weight
    print("\n=== Scenario: Weight Drift (halved health) ===")
    drifted = GenesisWeights(
        criteria={"maturity": 0.35, "health": 0.10, "consistency": 0.25, "independence": 0.30},
        aggregation="MIN", version="1.0.0", declared_at="2026-03-21T00:00:00Z"
    )
    result = verifier.verify(genesis_hash, drifted)
    print(f"Verdict: {result['verdict']} | Severity: {result['severity']}")
    print(f"Detail: {result['detail']}")
    
    # Scenario 3: Aggregation changed (MIN → WEIGHTED)
    print("\n=== Scenario: Aggregation Changed ===")
    changed_agg = GenesisWeights(
        criteria={"maturity": 0.25, "health": 0.25, "consistency": 0.25, "independence": 0.25},
        aggregation="WEIGHTED", version="1.0.0", declared_at="2026-03-21T00:00:00Z"
    )
    result = verifier.verify(genesis_hash, changed_agg)
    print(f"Verdict: {result['verdict']} | Severity: {result['severity']}")
    
    # Scenario 4: Weight history audit
    print("\n=== Weight History Audit ===")
    history = [
        ("2026-03-01", genesis),
        ("2026-03-07", genesis),
        ("2026-03-14", GenesisWeights(
            criteria={"maturity": 0.30, "health": 0.20, "consistency": 0.25, "independence": 0.25},
            aggregation="MIN", version="1.1.0", declared_at="2026-03-14T00:00:00Z"
        )),
        ("2026-03-21", GenesisWeights(
            criteria={"maturity": 0.40, "health": 0.10, "consistency": 0.25, "independence": 0.25},
            aggregation="MIN", version="1.2.0", declared_at="2026-03-21T00:00:00Z"
        )),
    ]
    audit = verifier.audit_weight_history(history)
    print(f"Snapshots: {audit['total_snapshots']} | Changes: {audit['weight_changes']}")
    print(f"Verdict: {audit['verdict']}")
    for c in audit['changes']:
        print(f"  [{c['timestamp']}] {c['old_hash']} → {c['new_hash']}")
        print(f"    New weights: {c['new_weights']}")


if __name__ == "__main__":
    demo()
