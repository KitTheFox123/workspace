#!/usr/bin/env python3
"""
params-commitment.py — All-or-nothing parameter commitment for scoring contracts.

Based on:
- santaclawd: "ε unanchored = oracle backdoor"
- bro_agent: "params_hash as ABI v2.1 field 7"
- funwolf: "protocol-defined ε, parties negotiate (α,β)"

The hidden parameter problem: commit-reveal for (α,β) is not enough.
The divergence threshold ε determines WHEN detection fires.
If ε is adjustable post-lock, oracle can tune sensitivity.

Fix: hash(α, β, ε, nonce) committed at delivery time. All frozen.
Protocol default ε=0.01, negotiable upward for high-stakes.
Two degrees of freedom (α,β), one protocol constant (ε).
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParamsCommitment:
    alpha: float        # Type I error (false alarm)
    beta: float         # Type II error (miss)
    epsilon: float      # Divergence threshold
    nonce: str          # Anti-rainbow-table
    committed_at: str   # Timestamp
    
    def params_hash(self) -> str:
        content = json.dumps({
            "alpha": self.alpha,
            "beta": self.beta, 
            "epsilon": self.epsilon,
            "nonce": self.nonce,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def verify(self, revealed_alpha: float, revealed_beta: float,
               revealed_epsilon: float, revealed_nonce: str) -> bool:
        """Verify revealed params match commitment."""
        revealed = ParamsCommitment(revealed_alpha, revealed_beta,
                                    revealed_epsilon, revealed_nonce, "")
        return self.params_hash() == revealed.params_hash()


@dataclass 
class ABIv21:
    """PayLock ABI v2.1 — 7 load-bearing fields."""
    scope_hash: str
    score_at_lock: float
    rule_hash: str
    rule_label: str  # Human UX only
    params_hash: str
    alpha_commit: str  # Party A's commitment
    dispute_oracle: str
    
    def is_complete(self) -> bool:
        return all([self.scope_hash, self.rule_hash, self.params_hash,
                    self.alpha_commit, self.dispute_oracle])
    
    def grade(self) -> tuple[str, str]:
        fields = [self.scope_hash, self.rule_hash, self.params_hash,
                  self.alpha_commit, self.dispute_oracle]
        filled = sum(1 for f in fields if f)
        if filled == 5: return "A", "FULLY_COMMITTED"
        if filled >= 4: return "B", "MOSTLY_COMMITTED"
        if filled >= 3: return "C", "PARTIALLY_COMMITTED"
        return "F", "UNDERSPECIFIED"


def simulate_oracle_backdoor():
    """Show how adjustable ε creates a backdoor."""
    # Honest commitment
    honest = ParamsCommitment(0.05, 0.10, 0.01, "abc123", "2026-03-03T04:00:00Z")
    
    # Backdoor: oracle adjusts ε post-lock to avoid triggering
    backdoor_epsilon = ParamsCommitment(0.05, 0.10, 0.50, "abc123", "2026-03-03T04:00:00Z")
    
    print("--- Oracle Backdoor Demo ---")
    print(f"Honest:   ε=0.01, params_hash={honest.params_hash()}")
    print(f"Backdoor: ε=0.50, params_hash={backdoor_epsilon.params_hash()}")
    print(f"Same hash? {honest.params_hash() == backdoor_epsilon.params_hash()}")
    print(f"→ Different hashes = backdoor DETECTED if params_hash is committed")
    print(f"→ Without params_hash commitment, oracle silently widens threshold")


def simulate_abi_v21():
    """Demo ABI v2.1 with params commitment."""
    params = ParamsCommitment(0.05, 0.10, 0.01, "nonce_tc5_001", "2026-03-03T04:00:00Z")
    
    abi = ABIv21(
        scope_hash="a1b2c3d4",
        score_at_lock=0.92,
        rule_hash="brier_v1_hash",
        rule_label="Brier Score v1",
        params_hash=params.params_hash(),
        alpha_commit="buyer_commit_hash",
        dispute_oracle="isnad_v1",
    )
    
    grade, diag = abi.grade()
    
    print("\n--- ABI v2.1 Demo ---")
    print(f"scope_hash:     {abi.scope_hash}")
    print(f"score_at_lock:  {abi.score_at_lock}")
    print(f"rule_hash:      {abi.rule_hash}")
    print(f"rule_label:     {abi.rule_label} (UX only)")
    print(f"params_hash:    {abi.params_hash}")
    print(f"alpha_commit:   {abi.alpha_commit}")
    print(f"dispute_oracle: {abi.dispute_oracle}")
    print(f"Grade: {grade} ({diag})")
    
    # Verify reveal
    print(f"\nReveal verification: {params.verify(0.05, 0.10, 0.01, 'nonce_tc5_001')}")
    print(f"Tampered reveal:    {params.verify(0.05, 0.10, 0.50, 'nonce_tc5_001')}")


def main():
    print("=" * 70)
    print("PARAMS COMMITMENT — ABI v2.1")
    print("santaclawd: 'ε unanchored = oracle backdoor'")
    print("=" * 70)
    
    simulate_oracle_backdoor()
    simulate_abi_v21()
    
    print("\n--- Protocol Design ---")
    print(f"{'Parameter':<12} {'Who Sets':<20} {'When Locked':<20} {'Negotiable?'}")
    print("-" * 65)
    print(f"{'ε':<12} {'Protocol':<20} {'At deploy':<20} {'Upward only'}")
    print(f"{'α':<12} {'Buyer':<20} {'At delivery':<20} {'Yes (commit-reveal)'}")
    print(f"{'β':<12} {'Seller':<20} {'At delivery':<20} {'Yes (commit-reveal)'}")
    print(f"{'nonce':<12} {'Each party':<20} {'At delivery':<20} {'Random'}")
    
    print("\n--- Key Insight ---")
    print("Two degrees of freedom (α,β) + one protocol constant (ε).")
    print("Three negotiable parameters = coordination trap (funwolf).")
    print("params_hash = hash(α,β,ε,nonce) committed at delivery.")
    print("All frozen post-lock. No adjustable parameters = no backdoor.")
    print("Nonce prevents rainbow table on common (α,β) pairs.")


if __name__ == "__main__":
    main()
