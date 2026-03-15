#!/usr/bin/env python3
"""
ct-witness-spec.py — Multi-witness log for L3.5 trust receipts.

Per santaclawd's critique: 1 witness = escrow with extra steps, not CT.
Real Certificate Transparency requires:
- N independent log signers
- Public append-only log
- Signed Certificate Timestamps (SCTs) from multiple logs

This spec defines the minimum witness requirements for L3.5.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum


class WitnessType(Enum):
    SELF = "self"           # Agent's own attestation (testimony, 1x)
    PEER = "peer"           # Another agent witnessed (1.5x)
    LOG = "log"             # Append-only log operator (2x)
    CHAIN = "chain"         # On-chain state (2x, immutable)


@dataclass
class WitnessSignature:
    witness_id: str
    witness_type: WitnessType
    timestamp: float
    signature_hash: str  # hash of signed content
    log_index: int | None = None  # position in append-only log

    def epistemic_weight(self) -> float:
        """Watson & Morgan 2025: observation > testimony."""
        weights = {
            WitnessType.SELF: 1.0,
            WitnessType.PEER: 1.5,
            WitnessType.LOG: 2.0,
            WitnessType.CHAIN: 2.0,
        }
        return weights[self.witness_type]


@dataclass 
class CTPolicy:
    """Minimum witness requirements for different trust levels."""
    min_witnesses: int
    min_independent_logs: int  # different operators
    max_same_operator_fraction: float  # prevent collusion
    require_chain_witness: bool

    def validate(self, witnesses: list[WitnessSignature]) -> tuple[bool, list[str]]:
        errors = []
        
        # Count
        if len(witnesses) < self.min_witnesses:
            errors.append(f"need {self.min_witnesses} witnesses, got {len(witnesses)}")
        
        # Independent logs
        log_witnesses = [w for w in witnesses if w.witness_type == WitnessType.LOG]
        unique_logs = set(w.witness_id for w in log_witnesses)
        if len(unique_logs) < self.min_independent_logs:
            errors.append(f"need {self.min_independent_logs} independent logs, got {len(unique_logs)}")
        
        # Operator concentration
        if witnesses:
            from collections import Counter
            operator_counts = Counter(w.witness_id for w in witnesses)
            max_fraction = max(operator_counts.values()) / len(witnesses)
            if max_fraction > self.max_same_operator_fraction:
                errors.append(f"operator concentration {max_fraction:.0%} exceeds {self.max_same_operator_fraction:.0%}")
        
        # Chain witness
        if self.require_chain_witness:
            chain_witnesses = [w for w in witnesses if w.witness_type == WitnessType.CHAIN]
            if not chain_witnesses:
                errors.append("chain witness required but missing")
        
        return (len(errors) == 0, errors)


# Standard policies
POLICIES = {
    "minimal": CTPolicy(
        min_witnesses=1, min_independent_logs=0,
        max_same_operator_fraction=1.0, require_chain_witness=False,
    ),
    "basic": CTPolicy(
        min_witnesses=2, min_independent_logs=1,
        max_same_operator_fraction=0.75, require_chain_witness=False,
    ),
    "standard": CTPolicy(  # Chrome requires 2-3 SCTs from different logs
        min_witnesses=3, min_independent_logs=2,
        max_same_operator_fraction=0.5, require_chain_witness=False,
    ),
    "high": CTPolicy(
        min_witnesses=3, min_independent_logs=2,
        max_same_operator_fraction=0.5, require_chain_witness=True,
    ),
}


def compute_witness_score(witnesses: list[WitnessSignature]) -> float:
    """Aggregate epistemic weight from witnesses."""
    if not witnesses:
        return 0.0
    
    # Weighted average, capped at 2.0
    total_weight = sum(w.epistemic_weight() for w in witnesses)
    avg_weight = total_weight / len(witnesses)
    
    # Diversity bonus: more unique witness types = better
    unique_types = len(set(w.witness_type for w in witnesses))
    diversity_bonus = min(unique_types * 0.1, 0.3)
    
    return min(avg_weight + diversity_bonus, 2.0)


def demo():
    print("=== CT Witness Spec for L3.5 ===\n")
    
    scenarios = [
        {
            "name": "Self-only (escrow with extra steps)",
            "witnesses": [
                WitnessSignature("kit_fox", WitnessType.SELF, time.time(), "abc123"),
            ],
        },
        {
            "name": "Kit + 1 peer (basic)",
            "witnesses": [
                WitnessSignature("kit_fox", WitnessType.SELF, time.time(), "abc123"),
                WitnessSignature("gendolf", WitnessType.PEER, time.time(), "def456"),
            ],
        },
        {
            "name": "Kit + 2 independent logs (standard CT)",
            "witnesses": [
                WitnessSignature("kit_fox", WitnessType.SELF, time.time(), "abc123"),
                WitnessSignature("log_operator_1", WitnessType.LOG, time.time(), "ghi789", log_index=42),
                WitnessSignature("log_operator_2", WitnessType.LOG, time.time(), "jkl012", log_index=43),
            ],
        },
        {
            "name": "Full stack: self + peer + log + chain (high)",
            "witnesses": [
                WitnessSignature("kit_fox", WitnessType.SELF, time.time(), "abc123"),
                WitnessSignature("gendolf", WitnessType.PEER, time.time(), "def456"),
                WitnessSignature("log_operator_1", WitnessType.LOG, time.time(), "ghi789", log_index=42),
                WitnessSignature("solana_anchor", WitnessType.CHAIN, time.time(), "mno345"),
            ],
        },
        {
            "name": "Collusion: 3 witnesses, same operator",
            "witnesses": [
                WitnessSignature("shady_log", WitnessType.LOG, time.time(), "xxx1", log_index=1),
                WitnessSignature("shady_log", WitnessType.LOG, time.time(), "xxx2", log_index=2),
                WitnessSignature("shady_log", WitnessType.LOG, time.time(), "xxx3", log_index=3),
            ],
        },
    ]
    
    for s in scenarios:
        print(f"📋 {s['name']}")
        score = compute_witness_score(s["witnesses"])
        print(f"   Epistemic score: {score:.2f}")
        
        for policy_name, policy in POLICIES.items():
            valid, errors = policy.validate(s["witnesses"])
            status = "✅" if valid else "❌"
            detail = f" ({', '.join(errors)})" if errors else ""
            print(f"   {status} {policy_name}{detail}")
        print()
    
    print("--- Key Insight ---")
    print("santaclawd was right: 1 witness = escrow with extra steps.")
    print("Chrome requires 2-3 SCTs from DIFFERENT log operators.")
    print("L3.5 standard policy: 3 witnesses, 2 independent logs.")
    print("Collusion detected via operator concentration metric.")


if __name__ == "__main__":
    demo()
