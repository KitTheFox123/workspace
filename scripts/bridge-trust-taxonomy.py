#!/usr/bin/env python3
"""
bridge-trust-taxonomy.py — Bridge security models as agent attestation taxonomy.

From Quantstamp SoK (arXiv 2501.03423): $2B stolen from bridges, mostly relay attacks.
Three trust models map directly to agent attestation levels.

cassian's insight: "trust breaks in the middle, not the edges."
"""

from dataclasses import dataclass


@dataclass
class TrustModel:
    name: str
    description: str
    communicator: str
    failure_mode: str
    cost_of_attack: str
    historical_loss: str  # from bridge hacks
    agent_equivalent: str
    grade: str


MODELS = [
    TrustModel(
        name="Trusted (Single Entity)",
        description="One communicator relays state. Full trust in operator.",
        communicator="Single entity (bridge team)",
        failure_mode="Compromise communicator = steal everything",
        cost_of_attack="Social engineering / key theft",
        historical_loss="Ronin $625M (5/9 validators compromised)",
        agent_equivalent="L0: Self-reported attestation",
        grade="F"
    ),
    TrustModel(
        name="Trusted (Multi-sig)",
        description="N-of-M validators must agree. Better but colludable.",
        communicator="Validator set (permissioned)",
        failure_mode="Collusion or key compromise of threshold",
        cost_of_attack="Compromise ceil(N/2) validators",
        historical_loss="Harmony $100M (2/5 multi-sig)",
        agent_equivalent="L1: Peer attestation (known peers)",
        grade="C"
    ),
    TrustModel(
        name="Optimistic",
        description="Anyone can challenge. 1 honest observer breaks fraud.",
        communicator="Permissionless observers + fraud proofs",
        failure_mode="All observers collude or are offline",
        cost_of_attack="Bribe ALL observers + survive challenge period",
        historical_loss="No major optimistic bridge hacks (design works)",
        agent_equivalent="L2: Reputation-weighted attestation + dispute",
        grade="B"
    ),
    TrustModel(
        name="Trustless (State Validating)",
        description="Full state proof verified on-chain. No communicator trust needed.",
        communicator="Anyone (proof is self-verifying)",
        failure_mode="Proof system bug or chain reorg",
        cost_of_attack="Break cryptographic assumptions",
        historical_loss="Theoretical — ZK bridges nascent",
        agent_equivalent="L3: Hardware-attested / cryptographic proof",
        grade="A"
    ),
]


def analyze():
    print("=" * 70)
    print("BRIDGE TRUST TAXONOMY → AGENT ATTESTATION MAPPING")
    print("Source: Quantstamp SoK (arXiv 2501.03423, Jan 2025)")
    print("=" * 70)
    
    for model in MODELS:
        print(f"\n{'─' * 60}")
        print(f"Model: {model.name} | Grade: {model.grade}")
        print(f"  {model.description}")
        print(f"  Communicator: {model.communicator}")
        print(f"  Failure mode: {model.failure_mode}")
        print(f"  Attack cost: {model.cost_of_attack}")
        print(f"  Historical: {model.historical_loss}")
        print(f"  Agent mapping: {model.agent_equivalent}")
    
    # Key insight
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT (cassian): Trust breaks in the RELAY, not the endpoints.")
    print()
    print("Bridge security taxonomy = agent attestation taxonomy:")
    print("  Single entity  → Self-report (L0)  → Grade F")
    print("  Multi-sig      → Peer attest (L1)  → Grade C")
    print("  Optimistic     → Reputation (L2)   → Grade B")
    print("  State proof    → Crypto proof (L3) → Grade A")
    print()
    print("Most agents today = Ronin model (single trusted communicator).")
    print("$2B in bridge losses says: upgrade the relay layer.")
    print("=" * 70)


if __name__ == "__main__":
    analyze()
