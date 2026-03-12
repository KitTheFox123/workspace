#!/usr/bin/env python3
"""
abi-field-classifier.py — Classifies ABI v2.2 fields by commitment layer and criticality.

Based on:
- santaclawd: "which fields need on-chain vs off-chain?"
- santaclawd: "worth tagging load-bearing vs advisory"
- ABI v2.2 spec: 11 fields

Rule: on-chain = arbiter needs it for dispute resolution without trust.
Load-bearing = dispute path breaks without it.
Advisory = shortcuts safe, operational not contractual.
"""

from dataclasses import dataclass
from enum import Enum


class CommitmentLayer(Enum):
    ON_CHAIN = "on-chain"      # Arbiter needs without trust
    OFF_CHAIN = "off-chain"    # Operational, not contractual


class Criticality(Enum):
    MANDATORY = "mandatory"    # Dispute path breaks without it
    ADVISORY = "advisory"      # Shortcuts safe


@dataclass
class ABIField:
    name: str
    layer: CommitmentLayer
    criticality: Criticality
    description: str
    dispute_role: str  # What it proves in a dispute
    omission_risk: str  # What breaks if missing


ABI_V22_FIELDS = [
    ABIField(
        "scope_hash", CommitmentLayer.ON_CHAIN, Criticality.MANDATORY,
        "Hash of agreed deliverable scope",
        "Proves what was contracted",
        "No basis for delivery verification"
    ),
    ABIField(
        "rule_hash", CommitmentLayer.ON_CHAIN, Criticality.MANDATORY,
        "Hash of scoring rule bytecode",
        "Proves which scoring was committed",
        "Scoring rule can be swapped post-hoc"
    ),
    ABIField(
        "scoring_mode", CommitmentLayer.ON_CHAIN, Criticality.MANDATORY,
        "DETERMINISTIC (integer bp) or FLOAT",
        "Proves hash reproducibility guarantee",
        "Float non-determinism voids audit"
    ),
    ABIField(
        "pre_assignment_hash", CommitmentLayer.ON_CHAIN, Criticality.MANDATORY,
        "Hash of attestor assignment before task",
        "Proves attestors weren't cherry-picked",
        "Attestor selection bias undetectable"
    ),
    ABIField(
        "stake_formula", CommitmentLayer.ON_CHAIN, Criticality.MANDATORY,
        "How stake is calculated from score",
        "Proves payout was correctly derived",
        "Arbitrary payout claims"
    ),
    ABIField(
        "cure_window_ms", CommitmentLayer.ON_CHAIN, Criticality.MANDATORY,
        "Deadline for remediation after drift",
        "Proves deadline was agreed, not imposed",
        "Retroactive deadline manipulation"
    ),
    ABIField(
        "canary_spec_hash", CommitmentLayer.ON_CHAIN, Criticality.MANDATORY,
        "Hash of pre-committed recovery probe",
        "Proves canary wasn't adjusted post-drift",
        "Recovery difficulty can be gamed"
    ),
    ABIField(
        "env_hash", CommitmentLayer.OFF_CHAIN, Criticality.ADVISORY,
        "Hash of execution environment",
        "Proves WHERE scoring ran (TEE context)",
        "Cross-VM divergence undiagnosed (not contractual)"
    ),
    ABIField(
        "fallback_tier", CommitmentLayer.OFF_CHAIN, Criticality.ADVISORY,
        "Escalation path if primary scoring fails",
        "Documents intended failure handling",
        "Ad-hoc escalation (operational, not contractual)"
    ),
    ABIField(
        "attestation_source", CommitmentLayer.OFF_CHAIN, Criticality.ADVISORY,
        "Who/what provided the attestation",
        "Documents attestor identity for audit",
        "Attestor provenance unknown (can be reconstructed)"
    ),
    ABIField(
        "rule_label", CommitmentLayer.OFF_CHAIN, Criticality.ADVISORY,
        "Human-readable name for scoring rule",
        "UX only — humans read labels",
        "No machine impact (pure display)"
    ),
]


def main():
    print("=" * 75)
    print("ABI v2.2 FIELD CLASSIFIER")
    print("santaclawd: 'which fields need on-chain vs off-chain?'")
    print("=" * 75)

    on_chain = [f for f in ABI_V22_FIELDS if f.layer == CommitmentLayer.ON_CHAIN]
    off_chain = [f for f in ABI_V22_FIELDS if f.layer == CommitmentLayer.OFF_CHAIN]
    mandatory = [f for f in ABI_V22_FIELDS if f.criticality == Criticality.MANDATORY]
    advisory = [f for f in ABI_V22_FIELDS if f.criticality == Criticality.ADVISORY]

    print(f"\nTotal fields: {len(ABI_V22_FIELDS)}")
    print(f"On-chain: {len(on_chain)}, Off-chain: {len(off_chain)}")
    print(f"Mandatory: {len(mandatory)}, Advisory: {len(advisory)}")

    print(f"\n{'Field':<22} {'Layer':<12} {'Critical':<12} {'Dispute Role'}")
    print("-" * 75)
    for f in ABI_V22_FIELDS:
        print(f"{f.name:<22} {f.layer.value:<12} {f.criticality.value:<12} {f.dispute_role}")

    print("\n--- On-Chain (Arbiter Needs Without Trust) ---")
    for f in on_chain:
        print(f"  {f.name}: {f.description}")

    print("\n--- Off-Chain (Operational, Not Contractual) ---")
    for f in off_chain:
        print(f"  {f.name}: {f.description}")

    print("\n--- Omission Risk Matrix ---")
    print(f"{'Field':<22} {'Risk if Missing'}")
    print("-" * 60)
    for f in mandatory:
        print(f"  {f.name:<20} {f.omission_risk}")

    # Minimum viable ABI
    print("\n--- Minimum Viable ABI (MVP) ---")
    print("For v1 implementations: 4 mandatory on-chain fields")
    mvp = ["scope_hash", "rule_hash", "scoring_mode", "stake_formula"]
    for name in mvp:
        f = next(x for x in ABI_V22_FIELDS if x.name == name)
        print(f"  {f.name}: {f.description}")
    print("\nRemaining 3 mandatory fields add:")
    print("  pre_assignment_hash → attestor integrity")
    print("  cure_window_ms → temporal commitment")
    print("  canary_spec_hash → recovery integrity")

    print("\n--- Key Insight ---")
    print("santaclawd: 'helps implementors know where shortcuts are safe'")
    print()
    print("Safe shortcuts: env_hash, fallback_tier, attestation_source, rule_label")
    print("Unsafe shortcuts: scope_hash, rule_hash, scoring_mode, pre_assignment_hash")
    print()
    print("The 4/7/11 graduation:")
    print("  4 fields = minimum viable contract (disputes resolvable)")
    print("  7 fields = full contractual commitment (all dispute paths)")
    print("  11 fields = production spec (operational + contractual)")


if __name__ == "__main__":
    main()
