#!/usr/bin/env python3
"""
abi-field-commitment.py — On-chain vs off-chain field commitment for ABI v2.2.

Based on:
- santaclawd: "which fields need on-chain commitment vs off-chain?"
- Rule: if arbiter needs it without trusting either party = on-chain
- Merkle root of off-chain fields on-chain = best of both

ABI v2.2: 11 fields. Tagged: MANDATORY / CONDITIONAL / ADVISORY.
On-chain: dispute resolution minimum.
Off-chain + Merkle anchor: everything else.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Commitment(Enum):
    ON_CHAIN = "on_chain"       # Arbiter needs without trust
    OFF_CHAIN = "off_chain"     # Merkle-anchored, revealed on dispute
    ADVISORY = "advisory"       # Human UX only, not load-bearing


class Necessity(Enum):
    MANDATORY = "mandatory"
    CONDITIONAL = "conditional"  # Required if condition met
    ADVISORY = "advisory"


@dataclass
class ABIField:
    name: str
    field_id: int
    commitment: Commitment
    necessity: Necessity
    condition: Optional[str] = None  # For conditional fields
    description: str = ""
    load_bearing: bool = True


ABI_V22_FIELDS = [
    ABIField("scope_hash", 1, Commitment.ON_CHAIN, Necessity.MANDATORY,
             description="Hash of task scope. Dispute: did agent deliver within scope?"),
    ABIField("rule_hash", 2, Commitment.ON_CHAIN, Necessity.MANDATORY,
             description="Hash of scoring rule bytecode. Dispute: was correct rule applied?"),
    ABIField("scoring_mode", 3, Commitment.ON_CHAIN, Necessity.MANDATORY,
             description="DETERMINISTIC|FLOAT. Determines hash reproducibility."),
    ABIField("agent_id", 4, Commitment.ON_CHAIN, Necessity.MANDATORY,
             description="Ed25519 public key. Identity binding."),
    ABIField("chain_tip", 5, Commitment.ON_CHAIN, Necessity.MANDATORY,
             description="Hash chain head. Proves ordering of actions."),
    ABIField("stake_formula", 6, Commitment.ON_CHAIN, Necessity.MANDATORY,
             description="How stake scales with contract value. Dispute resolution economics."),
    ABIField("pre_assignment_hash", 7, Commitment.ON_CHAIN, Necessity.MANDATORY,
             description="Commit-reveal: hash of attestor assignment before reveal."),
    ABIField("canary_spec_hash", 8, Commitment.OFF_CHAIN, Necessity.CONDITIONAL,
             condition="attestation_source claims independence",
             description="Pre-committed canary probe. Prevents post-drift difficulty gaming."),
    ABIField("env_hash", 9, Commitment.OFF_CHAIN, Necessity.CONDITIONAL,
             condition="scoring_mode == TEE",
             description="Runtime environment fingerprint. Cross-VM reproducibility."),
    ABIField("fallback_tier", 10, Commitment.OFF_CHAIN, Necessity.ADVISORY,
             description="Escalation path: automated → peer → human."),
    ABIField("rule_label", 11, Commitment.ADVISORY, Necessity.ADVISORY,
             description="Human-readable scoring rule name. UX only.", load_bearing=False),
]


def merkle_root(hashes: list[str]) -> str:
    """Simple Merkle root from list of hashes."""
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()[:16]
    if len(hashes) == 1:
        return hashes[0]
    # Pad to even
    if len(hashes) % 2 == 1:
        hashes.append(hashes[-1])
    next_level = []
    for i in range(0, len(hashes), 2):
        combined = hashes[i] + hashes[i + 1]
        next_level.append(hashlib.sha256(combined.encode()).hexdigest()[:16])
    return merkle_root(next_level)


def compute_on_chain_commitment(fields: dict[str, str]) -> dict:
    """Compute what goes on-chain."""
    on_chain = {}
    off_chain_hashes = []
    
    for abi_field in ABI_V22_FIELDS:
        value = fields.get(abi_field.name, "")
        field_hash = hashlib.sha256(f"{abi_field.name}:{value}".encode()).hexdigest()[:16]
        
        if abi_field.commitment == Commitment.ON_CHAIN:
            on_chain[abi_field.name] = field_hash
        elif abi_field.commitment == Commitment.OFF_CHAIN:
            off_chain_hashes.append(field_hash)
    
    # Merkle root of off-chain fields anchored on-chain
    off_chain_root = merkle_root(off_chain_hashes) if off_chain_hashes else "none"
    on_chain["off_chain_merkle_root"] = off_chain_root
    
    return {
        "on_chain_fields": len([f for f in ABI_V22_FIELDS if f.commitment == Commitment.ON_CHAIN]),
        "off_chain_fields": len([f for f in ABI_V22_FIELDS if f.commitment == Commitment.OFF_CHAIN]),
        "advisory_fields": len([f for f in ABI_V22_FIELDS if f.commitment == Commitment.ADVISORY]),
        "on_chain_commitment": on_chain,
        "off_chain_merkle_root": off_chain_root,
    }


def gas_estimate(n_on_chain: int, has_merkle_root: bool) -> dict:
    """Rough gas estimate for on-chain storage."""
    # ~20,000 gas per 32-byte slot (SSTORE)
    slots = n_on_chain + (1 if has_merkle_root else 0)
    gas = slots * 20000
    # At 30 gwei, ETH ~$3000
    cost_eth = gas * 30e-9
    cost_usd = cost_eth * 3000
    return {"slots": slots, "gas": gas, "cost_usd": round(cost_usd, 4)}


def main():
    print("=" * 70)
    print("ABI v2.2 FIELD COMMITMENT ANALYSIS")
    print("santaclawd: 'which fields need on-chain vs off-chain?'")
    print("=" * 70)

    # Field summary
    print(f"\n{'#':<4} {'Field':<22} {'Commitment':<12} {'Necessity':<14} {'Load-bearing'}")
    print("-" * 70)
    for f in ABI_V22_FIELDS:
        cond = f"({f.condition})" if f.condition else ""
        print(f"{f.field_id:<4} {f.name:<22} {f.commitment.value:<12} "
              f"{f.necessity.value:<14} {'YES' if f.load_bearing else 'no'} {cond}")

    # Compute commitment
    sample_fields = {
        "scope_hash": "abc123",
        "rule_hash": "brier_v1",
        "scoring_mode": "DETERMINISTIC",
        "agent_id": "kit_fox_ed25519",
        "chain_tip": "deadbeef",
        "stake_formula": "linear_0.01",
        "pre_assignment_hash": "committed_attestor",
        "canary_spec_hash": "canary_pool_3",
        "env_hash": "python311_linux_x64",
        "fallback_tier": "auto_peer_human",
        "rule_label": "Brier Score v1",
    }
    
    result = compute_on_chain_commitment(sample_fields)
    
    print(f"\n--- On-Chain / Off-Chain Split ---")
    print(f"On-chain fields:  {result['on_chain_fields']} (dispute resolution minimum)")
    print(f"Off-chain fields: {result['off_chain_fields']} (Merkle-anchored)")
    print(f"Advisory fields:  {result['advisory_fields']} (not committed)")
    print(f"Off-chain Merkle root: {result['off_chain_merkle_root']}")

    # Gas estimate
    gas = gas_estimate(result["on_chain_fields"], True)
    print(f"\n--- Gas Estimate ---")
    print(f"Storage slots: {gas['slots']} (7 on-chain + 1 Merkle root)")
    print(f"Gas: ~{gas['gas']:,}")
    print(f"Cost @ 30 gwei, ETH=$3000: ~${gas['cost_usd']}")
    
    # Comparison: all on-chain vs hybrid
    gas_all = gas_estimate(11, False)
    print(f"\nAll on-chain: {gas_all['slots']} slots, ~${gas_all['cost_usd']}")
    print(f"Hybrid (7+Merkle): {gas['slots']} slots, ~${gas['cost_usd']}")
    print(f"Savings: {(1 - gas['cost_usd']/gas_all['cost_usd'])*100:.0f}%")

    print("\n--- Key Insight ---")
    print("santaclawd's rule: on-chain = arbiter needs without trust.")
    print("7 fields on-chain + Merkle root = 8 slots.")
    print("Off-chain fields revealed only on dispute (gas savings 27%).")
    print("Merkle proof verifies off-chain field was committed at lock time.")
    print("Advisory fields (rule_label) never committed — human UX only.")


if __name__ == "__main__":
    main()
