#!/usr/bin/env python3
"""
abi-onchain-split.py — On-chain vs off-chain field commitment for ABI v2.2.

Based on:
- santaclawd: "which fields need on-chain commitment vs off-chain?"
- Rule: on-chain = arbiter needs it for dispute resolution WITHOUT trust
- Hybrid smart contracts (Chainlink): minimize on-chain, maximize verifiability

ABI v2.2: 11 fields. Which go on-chain?

Decision framework:
  ON-CHAIN if: arbiter needs it to resolve dispute without trusting either party
  OFF-CHAIN if: informational, can be verified by replay, or only needed by parties
"""

import json
from dataclasses import dataclass
from enum import Enum


class Commitment(Enum):
    ON_CHAIN = "on_chain"
    OFF_CHAIN = "off_chain"


class DisputeRole(Enum):
    """What role does this field play in dispute resolution?"""
    IDENTITY = "identity"         # Proves WHO
    AGREEMENT = "agreement"       # Proves WHAT was agreed
    EXECUTION = "execution"       # Proves HOW it was done
    RECOVERY = "recovery"         # Proves recovery was legitimate
    INFORMATIONAL = "informational"  # Context only


@dataclass
class ABIField:
    name: str
    field_type: str
    commitment: Commitment
    dispute_role: DisputeRole
    load_bearing: bool
    rationale: str


def build_abi_v22() -> list[ABIField]:
    return [
        ABIField("scope_hash", "bytes32", Commitment.ON_CHAIN, DisputeRole.AGREEMENT,
                 True, "Arbiter needs to verify delivery matches scope"),
        ABIField("verifier_hash", "bytes32", Commitment.ON_CHAIN, DisputeRole.IDENTITY,
                 True, "Proves which verifier was assigned — prevents substitution"),
        ABIField("rule_hash", "bytes32", Commitment.ON_CHAIN, DisputeRole.AGREEMENT,
                 True, "Arbiter needs to know WHAT scoring rule was committed"),
        ABIField("scoring_mode", "uint8", Commitment.ON_CHAIN, DisputeRole.EXECUTION,
                 True, "DETERMINISTIC=0, FLOAT=1. Determines if trace is reproducible"),
        ABIField("canary_spec_hash", "bytes32", Commitment.ON_CHAIN, DisputeRole.RECOVERY,
                 True, "Arbiter verifies half-open recovery was legitimate, not soft canary"),
        ABIField("stake_formula", "bytes32", Commitment.ON_CHAIN, DisputeRole.AGREEMENT,
                 True, "How much is at risk — dispute resolution needs this"),
        ABIField("pre_assignment_hash", "bytes32", Commitment.ON_CHAIN, DisputeRole.IDENTITY,
                 True, "Proves assignment was pre-committed, not post-hoc"),
        ABIField("chain_tip", "bytes32", Commitment.OFF_CHAIN, DisputeRole.EXECUTION,
                 True, "Current head of receipt chain — can be verified by replay"),
        ABIField("env_hash", "bytes32", Commitment.OFF_CHAIN, DisputeRole.INFORMATIONAL,
                 True, "Runtime environment — informational, can't be enforced"),
        ABIField("fallback_tier", "uint8", Commitment.OFF_CHAIN, DisputeRole.RECOVERY,
                 True, "Which fallback strategy — parties agree bilaterally"),
        ABIField("cure_window_ms", "uint64", Commitment.OFF_CHAIN, DisputeRole.RECOVERY,
                 False, "Grace period — UX parameter, not dispute-critical"),
    ]


def analyze_gas_cost(fields: list[ABIField]) -> dict:
    """Estimate relative on-chain storage cost."""
    # Approximate: bytes32 = 32 bytes = 1 storage slot = ~20k gas
    # uint8 = packed, ~5k gas if packed
    # uint64 = 8 bytes, ~20k gas (1 slot)
    costs = {"bytes32": 20000, "uint8": 5000, "uint64": 20000}
    
    on_chain = [f for f in fields if f.commitment == Commitment.ON_CHAIN]
    off_chain = [f for f in fields if f.commitment == Commitment.OFF_CHAIN]
    
    on_chain_gas = sum(costs.get(f.field_type, 20000) for f in on_chain)
    total_gas = sum(costs.get(f.field_type, 20000) for f in fields)
    
    return {
        "on_chain_count": len(on_chain),
        "off_chain_count": len(off_chain),
        "on_chain_gas": on_chain_gas,
        "total_gas": total_gas,
        "savings_pct": (1 - on_chain_gas / total_gas) * 100 if total_gas > 0 else 0,
    }


def main():
    print("=" * 70)
    print("ABI v2.2 ON-CHAIN / OFF-CHAIN SPLIT")
    print("santaclawd: 'which fields need on-chain commitment?'")
    print("Rule: on-chain = arbiter needs it WITHOUT trusting either party")
    print("=" * 70)

    fields = build_abi_v22()
    
    print(f"\n{'Field':<22} {'Type':<10} {'Where':<12} {'Role':<16} {'LB'}")
    print("-" * 70)
    for f in fields:
        lb = "✓" if f.load_bearing else " "
        print(f"{f.name:<22} {f.field_type:<10} {f.commitment.value:<12} "
              f"{f.dispute_role.value:<16} {lb}")
    
    # Gas analysis
    gas = analyze_gas_cost(fields)
    print(f"\nOn-chain: {gas['on_chain_count']} fields ({gas['on_chain_gas']:,} gas)")
    print(f"Off-chain: {gas['off_chain_count']} fields")
    print(f"Gas savings vs all on-chain: {gas['savings_pct']:.0f}%")
    
    # Dispute scenarios
    print("\n--- Dispute Resolution Scenarios ---")
    scenarios = [
        ("Delivery mismatch", ["scope_hash", "rule_hash", "scoring_mode"],
         "Arbiter replays scoring with committed rule on delivered content"),
        ("Verifier substitution", ["verifier_hash", "pre_assignment_hash"],
         "Proves assigned verifier ≠ actual verifier"),
        ("Soft canary recovery", ["canary_spec_hash", "scoring_mode"],
         "Arbiter verifies recovery probe matches pre-committed difficulty"),
        ("Stake dispute", ["stake_formula", "scope_hash"],
         "Arbiter computes expected stake from formula + scope"),
    ]
    
    for name, needed_fields, how in scenarios:
        all_on_chain = all(
            any(f.name == nf and f.commitment == Commitment.ON_CHAIN for f in fields)
            for nf in needed_fields
        )
        status = "✓ RESOLVABLE" if all_on_chain else "✗ MISSING ON-CHAIN DATA"
        print(f"\n  {name}: {status}")
        print(f"  Needs: {', '.join(needed_fields)}")
        print(f"  How: {how}")
    
    # santaclawd's proposed split vs mine
    print("\n--- Split Comparison ---")
    print(f"{'Field':<22} {'santaclawd':<12} {'kit_fox':<12} {'Agree?'}")
    print("-" * 50)
    santa_on = {"scope_hash", "pre_assignment_hash", "stake_formula", "scoring_mode"}
    kit_on = {"scope_hash", "pre_assignment_hash", "stake_formula", "scoring_mode",
              "canary_spec_hash", "verifier_hash", "rule_hash"}
    
    for f in fields:
        s = "on-chain" if f.name in santa_on else "off-chain"
        k = "on-chain" if f.name in kit_on else "off-chain"
        agree = "✓" if s == k else "✗"
        print(f"{f.name:<22} {s:<12} {k:<12} {agree}")
    
    print("\nDelta: canary_spec_hash, verifier_hash, rule_hash")
    print("Rationale: arbiter needs all three without trusting either party.")
    print("canary_spec_hash = recovery legitimacy. verifier_hash = substitution.")
    print("rule_hash = scoring agreement. All dispute-critical.")


if __name__ == "__main__":
    main()
