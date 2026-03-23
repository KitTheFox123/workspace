#!/usr/bin/env python3
"""
delegation-trust-compositor.py — Delegation trust composition for ATF.

Per santaclawd: alice→bob→carol. What trust does alice have in carol?

Three models compared:
  - MIN: BFT-safe, too conservative
  - PRODUCT: decays too fast (0.9^3 = 0.73)
  - WEIGHTED: distance discount — direct=1.0, 1-hop=0.75, 2-hop=0.50

Plus cascading revocation:
  - HARD_CASCADE: root grader revoked → all downstream REJECT
  - SOFT_CASCADE: intermediate revoked → downstream DEGRADED until re-graded

EigenTrust (Kamvar et al. 2003): transitive trust = matrix multiplication.
ATF simplifies: no global eigenvector. Local chain evaluation with depth limit.

MAX_DELEGATION_DEPTH = 3 (ATF-core constant, per RFC 5280 §6 pathLenConstraint).

Usage:
    python3 delegation-trust-compositor.py
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


MAX_DELEGATION_DEPTH = 3
DISTANCE_WEIGHTS = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25}


class CascadeMode(Enum):
    HARD = "HARD_CASCADE"    # root revoked → all REJECT
    SOFT = "SOFT_CASCADE"    # intermediate revoked → DEGRADED


class ChainVerdict(Enum):
    TRUSTED = "TRUSTED"
    DEGRADED = "DEGRADED"
    BROKEN = "BROKEN"
    TOO_DEEP = "TOO_DEEP"
    REVOKED = "REVOKED"


@dataclass
class DelegationHop:
    """One hop in the delegation chain."""
    agent_id: str
    trust_score: float          # 0.0-1.0
    evidence_grade: str         # A-F
    verification_method: str    # HARD_MANDATORY, SOFT_MANDATORY, SELF_ATTESTED
    revoked: bool = False
    is_root_grader: bool = False


@dataclass
class DelegationChain:
    """Full delegation chain from requester to final executor."""
    hops: list[DelegationHop] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return len(self.hops)


class DelegationTrustCompositor:
    """Compose trust across delegation chains."""

    def compose_min(self, chain: DelegationChain) -> float:
        """MIN model: BFT-safe, conservative."""
        if not chain.hops:
            return 0.0
        return min(h.trust_score for h in chain.hops)

    def compose_product(self, chain: DelegationChain) -> float:
        """PRODUCT model: multiplicative decay."""
        result = 1.0
        for h in chain.hops:
            result *= h.trust_score
        return result

    def compose_weighted(self, chain: DelegationChain) -> float:
        """WEIGHTED model: distance discount. ATF RECOMMENDED."""
        if not chain.hops:
            return 0.0
        weighted_scores = []
        for i, hop in enumerate(chain.hops):
            weight = DISTANCE_WEIGHTS.get(i, 0.1)  # fallback for deep chains
            weighted_scores.append(hop.trust_score * weight)
        return min(weighted_scores)  # weakest weighted link

    def evaluate_chain(self, chain: DelegationChain) -> dict:
        """Full chain evaluation with all models + cascade + depth check."""

        # Depth check
        if chain.depth > MAX_DELEGATION_DEPTH:
            return {
                "verdict": ChainVerdict.TOO_DEEP.value,
                "action": "REJECT",
                "reason": f"depth {chain.depth} > MAX_DELEGATION_DEPTH {MAX_DELEGATION_DEPTH}",
                "depth": chain.depth,
                "rfc5280_parallel": "pathLenConstraint exceeded",
            }

        # Self-attested hop check (axiom 1 violation)
        self_attested = [h for h in chain.hops if h.verification_method == "SELF_ATTESTED"]
        if self_attested:
            return {
                "verdict": ChainVerdict.BROKEN.value,
                "action": "REJECT",
                "reason": f"self-attested hop: {self_attested[0].agent_id}",
                "axiom_violation": "axiom_1 (verifier independence)",
            }

        # Cascading revocation check
        revoked = [(i, h) for i, h in enumerate(chain.hops) if h.revoked]
        if revoked:
            idx, hop = revoked[0]
            if hop.is_root_grader:
                return {
                    "verdict": ChainVerdict.REVOKED.value,
                    "action": "REJECT",
                    "cascade_mode": CascadeMode.HARD.value,
                    "reason": f"root grader {hop.agent_id} revoked → HARD_CASCADE",
                    "rfc5280_parallel": "CA certificate revoked → all issued certs invalid",
                }
            else:
                # SOFT_CASCADE: downstream DEGRADED
                return {
                    "verdict": ChainVerdict.DEGRADED.value,
                    "action": "DEGRADE",
                    "cascade_mode": CascadeMode.SOFT.value,
                    "reason": f"intermediate {hop.agent_id} revoked → SOFT_CASCADE",
                    "remediation": "re-grade via alternate path",
                    "rfc5280_parallel": "intermediate CA revoked → rebuild path",
                }

        # Compute trust under all three models
        min_trust = self.compose_min(chain)
        product_trust = self.compose_product(chain)
        weighted_trust = self.compose_weighted(chain)

        # ATF uses WEIGHTED as primary
        grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        min_grade_val = min(grade_values.get(h.evidence_grade, 0) for h in chain.hops)
        chain_grade = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}.get(min_grade_val, "F")

        verdict = ChainVerdict.TRUSTED if weighted_trust >= 0.50 else ChainVerdict.DEGRADED

        return {
            "verdict": verdict.value,
            "action": "ACCEPT" if verdict == ChainVerdict.TRUSTED else "WARN",
            "depth": chain.depth,
            "chain_grade": chain_grade,
            "trust_models": {
                "min": round(min_trust, 4),
                "product": round(product_trust, 4),
                "weighted": round(weighted_trust, 4),
            },
            "primary_trust": round(weighted_trust, 4),
            "hops": [
                {
                    "agent": h.agent_id,
                    "trust": h.trust_score,
                    "grade": h.evidence_grade,
                    "distance_weight": DISTANCE_WEIGHTS.get(i, 0.1),
                    "weighted_trust": round(h.trust_score * DISTANCE_WEIGHTS.get(i, 0.1), 4),
                }
                for i, h in enumerate(chain.hops)
            ],
            "eigentrust_note": "EigenTrust uses global eigenvector. ATF uses local chain eval — no central aggregation needed.",
        }


def demo():
    print("=" * 60)
    print("Delegation Trust Compositor — ATF chain composition")
    print("=" * 60)

    compositor = DelegationTrustCompositor()

    # Scenario 1: Clean 3-hop chain
    print("\n--- Scenario 1: alice→bob→carol (clean chain) ---")
    chain1 = DelegationChain(hops=[
        DelegationHop("alice", 0.95, "A", "HARD_MANDATORY"),
        DelegationHop("bob", 0.85, "B", "HARD_MANDATORY"),
        DelegationHop("carol", 0.80, "B", "HARD_MANDATORY"),
    ])
    print(json.dumps(compositor.evaluate_chain(chain1), indent=2))

    # Scenario 2: Product decay problem
    print("\n--- Scenario 2: 3 hops at 0.9 each (product = 0.73) ---")
    chain2 = DelegationChain(hops=[
        DelegationHop("a", 0.90, "A", "HARD_MANDATORY"),
        DelegationHop("b", 0.90, "A", "HARD_MANDATORY"),
        DelegationHop("c", 0.90, "A", "HARD_MANDATORY"),
    ])
    print(json.dumps(compositor.evaluate_chain(chain2), indent=2))

    # Scenario 3: Too deep
    print("\n--- Scenario 3: 4-hop chain (exceeds MAX_DELEGATION_DEPTH) ---")
    chain3 = DelegationChain(hops=[
        DelegationHop("a", 0.95, "A", "HARD_MANDATORY"),
        DelegationHop("b", 0.90, "A", "HARD_MANDATORY"),
        DelegationHop("c", 0.85, "B", "HARD_MANDATORY"),
        DelegationHop("d", 0.80, "B", "HARD_MANDATORY"),
    ])
    print(json.dumps(compositor.evaluate_chain(chain3), indent=2))

    # Scenario 4: Root grader revoked (HARD_CASCADE)
    print("\n--- Scenario 4: Root grader revoked → HARD_CASCADE ---")
    chain4 = DelegationChain(hops=[
        DelegationHop("root_grader", 0.95, "A", "HARD_MANDATORY", revoked=True, is_root_grader=True),
        DelegationHop("bob", 0.85, "B", "HARD_MANDATORY"),
    ])
    print(json.dumps(compositor.evaluate_chain(chain4), indent=2))

    # Scenario 5: Intermediate revoked (SOFT_CASCADE)
    print("\n--- Scenario 5: Intermediate revoked → SOFT_CASCADE ---")
    chain5 = DelegationChain(hops=[
        DelegationHop("alice", 0.95, "A", "HARD_MANDATORY"),
        DelegationHop("bob_revoked", 0.85, "B", "HARD_MANDATORY", revoked=True),
        DelegationHop("carol", 0.80, "B", "HARD_MANDATORY"),
    ])
    print(json.dumps(compositor.evaluate_chain(chain5), indent=2))

    # Scenario 6: Self-attested hop (axiom 1 violation)
    print("\n--- Scenario 6: Self-attested hop breaks chain ---")
    chain6 = DelegationChain(hops=[
        DelegationHop("alice", 0.95, "A", "HARD_MANDATORY"),
        DelegationHop("self_attester", 0.90, "A", "SELF_ATTESTED"),
    ])
    print(json.dumps(compositor.evaluate_chain(chain6), indent=2))

    print("\n" + "=" * 60)
    print("WEIGHTED > MIN (too conservative) > PRODUCT (decays too fast)")
    print(f"MAX_DELEGATION_DEPTH = {MAX_DELEGATION_DEPTH} (RFC 5280 pathLenConstraint)")
    print("HARD_CASCADE: root revoked → all REJECT")
    print("SOFT_CASCADE: intermediate revoked → DEGRADED + rebuild")
    print("Self-attested hop = chain broken (axiom 1)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
