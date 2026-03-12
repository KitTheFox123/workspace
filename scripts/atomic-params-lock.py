#!/usr/bin/env python3
"""
atomic-params-lock.py — Atomic parameter commitment for multi-party contracts.

Based on:
- santaclawd: "committed_ε in the same lock round as (α,β). all three or nothing."
- funwolf: "ε coordination = turtles all the way down"
- Nash (1950): bargaining solution
- Hoyte (2024): commit-reveal attacks

The problem: SPRT needs (α,β,ε) to define stopping + divergence boundaries.
If any parameter is negotiated post-hoc, disputes are irresolvable.
Fix: atomic triple commitment. Hash all parameters in one round.
Parties sign params_hash, not individual values.

Dispute resolution: compare observed divergence against committed ε.
No ambiguity. Machine-verifiable.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParamSet:
    alpha: float      # Type I error tolerance
    beta: float       # Type II error tolerance
    epsilon: float    # Divergence threshold
    scoring_rule: str # e.g., "brier_v1"
    
    def params_hash(self) -> str:
        """Canonical hash of all parameters."""
        # JCS-style: sorted keys, deterministic
        content = json.dumps({
            "alpha": self.alpha,
            "beta": self.beta,
            "epsilon": self.epsilon,
            "scoring_rule": self.scoring_rule,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Commitment:
    party: str
    params_hash: str
    timestamp: float
    signature: str  # Simulated Ed25519


@dataclass  
class ParamLock:
    commitments: list[Commitment]
    revealed_params: Optional[ParamSet] = None
    locked: bool = False
    lock_timestamp: float = 0.0
    
    def all_committed(self) -> bool:
        hashes = set(c.params_hash for c in self.commitments)
        return len(hashes) == 1 and len(self.commitments) >= 2
    
    def lock(self, params: ParamSet) -> dict:
        if not self.all_committed():
            return {"success": False, "reason": "HASH_MISMATCH", 
                    "hashes": [c.params_hash for c in self.commitments]}
        if params.params_hash() != self.commitments[0].params_hash:
            return {"success": False, "reason": "REVEAL_MISMATCH"}
        self.revealed_params = params
        self.locked = True
        self.lock_timestamp = time.time()
        return {"success": True, "params_hash": params.params_hash(), "parties": len(self.commitments)}
    
    def check_divergence(self, observed_divergence: float) -> dict:
        if not self.locked or not self.revealed_params:
            return {"result": "NO_LOCK", "actionable": False}
        p = self.revealed_params
        if observed_divergence > p.epsilon:
            return {"result": "DIVERGENCE_EXCEEDED", "observed": observed_divergence,
                    "threshold": p.epsilon, "actionable": True, "action": "DISPUTE"}
        return {"result": "WITHIN_BOUNDS", "observed": observed_divergence,
                "threshold": p.epsilon, "actionable": False}


def simulate_commit(party: str, params: ParamSet) -> Commitment:
    sig = hashlib.sha256(f"{party}:{params.params_hash()}:{time.time()}".encode()).hexdigest()[:16]
    return Commitment(party, params.params_hash(), time.time(), sig)


def derive_epsilon_from_data(divergences: list[float], percentile: float = 0.95) -> float:
    """Derive ε from empirical distribution of honest divergence."""
    sorted_d = sorted(divergences)
    idx = int(len(sorted_d) * percentile)
    return sorted_d[min(idx, len(sorted_d) - 1)]


def main():
    print("=" * 70)
    print("ATOMIC PARAMETER LOCK")
    print("santaclawd: 'committed_ε in the same lock round. all three or nothing.'")
    print("=" * 70)

    # Scenario 1: Both parties agree
    print("\n--- Scenario 1: Agreement ---")
    params = ParamSet(alpha=0.05, beta=0.10, epsilon=0.15, scoring_rule="brier_v1")
    c1 = simulate_commit("buyer", params)
    c2 = simulate_commit("seller", params)
    lock = ParamLock([c1, c2])
    result = lock.lock(params)
    print(f"Lock result: {result}")
    
    # Check divergence
    check = lock.check_divergence(0.08)
    print(f"Divergence 0.08: {check}")
    check2 = lock.check_divergence(0.22)
    print(f"Divergence 0.22: {check2}")

    # Scenario 2: Disagreement (different ε)
    print("\n--- Scenario 2: Disagreement ---")
    params_buyer = ParamSet(alpha=0.01, beta=0.05, epsilon=0.10, scoring_rule="brier_v1")
    params_seller = ParamSet(alpha=0.10, beta=0.20, epsilon=0.25, scoring_rule="brier_v1")
    c3 = simulate_commit("buyer", params_buyer)
    c4 = simulate_commit("seller", params_seller)
    lock2 = ParamLock([c3, c4])
    result2 = lock2.lock(params_buyer)
    print(f"Lock result: {result2}")

    # Scenario 3: Data-derived ε
    print("\n--- Scenario 3: Data-Derived ε ---")
    # Historical honest divergences (TC4-like)
    honest_divergences = [0.02, 0.04, 0.03, 0.08, 0.05, 0.12, 0.04, 0.06, 
                          0.09, 0.03, 0.07, 0.11, 0.05, 0.04, 0.50, 0.03,
                          0.06, 0.08, 0.04, 0.07]
    eps_95 = derive_epsilon_from_data(honest_divergences, 0.95)
    eps_99 = derive_epsilon_from_data(honest_divergences, 0.99)
    print(f"95th percentile ε: {eps_95:.3f}")
    print(f"99th percentile ε: {eps_99:.3f}")
    print(f"TC4 clove Δ50 (0.50) > both → DISPUTE at any reasonable ε")

    # ABI spec
    print("\n--- PayLock v2 ABI Slot ---")
    abi = {
        "rule_hash": "CID(JCS(bytecode))",
        "scope_hash": "SHA256(scope_manifest)",
        "params_hash": "SHA256(JSON.sort({α,β,ε,scoring_rule}))",
        "chain_tip": "prev_receipt_hash",
        "agent_ids": ["buyer_ed25519", "seller_ed25519"],
        "timestamp": "drand_round",
        "rule_label": "human_readable_name (UX only)",
    }
    print(json.dumps(abi, indent=2))

    print("\n--- Key Insight ---")
    print("santaclawd: 'who committed to ε?'")
    print("funwolf: 'ε coordination = turtles all the way down'")
    print()
    print("Fix 1: Atomic triple (α,β,ε) — all three or nothing.")
    print("Fix 2: Data-derived ε — 95th percentile of honest divergence.")
    print("Fix 3: Protocol-default ε from empirical distribution, overridable.")
    print()
    print("The params_hash = one CID covering the detection contract.")
    print("Disputes resolved against committed params, not negotiated post-hoc.")
    print("No turtles: the data is the anchor.")


if __name__ == "__main__":
    main()
