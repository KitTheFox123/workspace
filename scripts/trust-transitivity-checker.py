#!/usr/bin/env python3
"""
trust-transitivity-checker.py — Trust transitivity across delegation chains.

The next open ATF question (Kit → santaclawd, March 23 2026):
A trusts B, B delegates to C. Does A trust C?

ARC (RFC 8617) says: chain the seals, let the final receiver decide.
This tool formalizes transitivity semantics:
  - DIRECT: A verified B directly (grade preserved)
  - TRANSITIVE: A trusts B who attests C (grade decays)
  - CAPPED: chain too long, grade floors at D
  - BROKEN: chain integrity failed

Key insight: trust is NOT fully transitive. Each hop decays the grade.
MAX_CHAIN_DEPTH limits how far trust propagates.
Like PGP web of trust: direct > 1-hop > 2-hop > untrusted.

Usage:
    python3 scripts/trust-transitivity-checker.py
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

# ATF-core constants
MAX_CHAIN_DEPTH = 4        # max delegation hops
GRADE_DECAY_PER_HOP = 1   # lose 1 grade level per hop
MIN_TRANSITIVE_GRADE = "D" # floor — below this = untrusted

GRADE_ORDER = ["A", "B", "C", "D", "F"]
GRADE_VALUES = {g: i for i, g in enumerate(GRADE_ORDER)}


def decay_grade(grade: str, hops: int) -> str:
    """Decay a grade by N hops. Each hop drops 1 level."""
    val = GRADE_VALUES.get(grade, 4)
    decayed = min(val + hops * GRADE_DECAY_PER_HOP, 4)
    return GRADE_ORDER[decayed]


@dataclass
class TrustLink:
    """One link in a trust chain."""
    from_agent: str
    to_agent: str
    evidence_grade: str      # grade of the direct attestation
    verification_method: str # HARD_MANDATORY, SOFT_MANDATORY, SELF_ATTESTED
    genesis_hash: str
    chain_seal: Optional[str] = None


class TrustTransitivityChecker:
    """Check trust transitivity across delegation chains."""

    def __init__(self, max_depth: int = MAX_CHAIN_DEPTH):
        self.max_depth = max_depth

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def check_chain(self, chain: list[TrustLink]) -> dict:
        """Evaluate trust transitivity across a delegation chain."""
        if not chain:
            return {"verdict": "EMPTY", "grade": "F", "reason": "no chain"}

        # Single hop = direct trust
        if len(chain) == 1:
            link = chain[0]
            if link.verification_method == "SELF_ATTESTED":
                return {
                    "verdict": "SELF_ATTESTED",
                    "grade": "F",
                    "reason": "self-attestation is not trust",
                    "chain_length": 1,
                    "axiom_1_violation": True,
                }
            return {
                "verdict": "DIRECT",
                "grade": link.evidence_grade,
                "reason": "direct attestation, no transitivity needed",
                "chain_length": 1,
                "from": link.from_agent,
                "to": link.to_agent,
            }

        # Check chain depth
        if len(chain) > self.max_depth:
            return {
                "verdict": "DEPTH_EXCEEDED",
                "grade": "F",
                "reason": f"chain depth {len(chain)} > MAX_CHAIN_DEPTH {self.max_depth}",
                "chain_length": len(chain),
                "max_depth": self.max_depth,
            }

        # Check chain integrity (each link connects)
        for i in range(1, len(chain)):
            if chain[i].from_agent != chain[i-1].to_agent:
                return {
                    "verdict": "BROKEN",
                    "grade": "F",
                    "reason": f"chain broken at hop {i}: {chain[i-1].to_agent} → {chain[i].from_agent}",
                    "break_point": i,
                }

        # Check for self-attestation in chain
        self_attested = [
            i for i, link in enumerate(chain)
            if link.verification_method == "SELF_ATTESTED"
        ]
        if self_attested:
            return {
                "verdict": "AXIOM_1_VIOLATION",
                "grade": "F",
                "reason": f"self-attested link at hop(s) {self_attested}",
                "chain_length": len(chain),
                "self_attested_hops": self_attested,
            }

        # Compute transitive grade
        # Start with source grade, decay per hop
        source_grade = chain[0].evidence_grade
        hops = len(chain) - 1  # first link is direct, rest are transitive
        transitive_grade = decay_grade(source_grade, hops)

        # Also check MIN across all links (weakest link)
        min_grade_val = max(GRADE_VALUES[link.evidence_grade] for link in chain)
        min_grade = GRADE_ORDER[min_grade_val]

        # Final grade = worse of (decayed source, weakest link)
        final_val = max(GRADE_VALUES[transitive_grade], min_grade_val)
        final_grade = GRADE_ORDER[final_val]

        # Capped?
        capped = GRADE_VALUES[final_grade] >= GRADE_VALUES[MIN_TRANSITIVE_GRADE]

        verdict = "CAPPED" if capped and final_grade != "F" else "TRANSITIVE"
        if final_grade == "F":
            verdict = "UNTRUSTED"

        return {
            "verdict": verdict,
            "grade": final_grade,
            "source_grade": source_grade,
            "transitive_grade": transitive_grade,
            "weakest_link_grade": min_grade,
            "chain_length": len(chain),
            "hops": hops,
            "decay_per_hop": GRADE_DECAY_PER_HOP,
            "from": chain[0].from_agent,
            "to": chain[-1].to_agent,
            "via": [link.to_agent for link in chain[:-1]],
            "links": [
                {
                    "from": link.from_agent,
                    "to": link.to_agent,
                    "grade": link.evidence_grade,
                    "method": link.verification_method,
                    "transitive_grade_at_hop": decay_grade(
                        source_grade, i
                    ) if i > 0 else source_grade,
                }
                for i, link in enumerate(chain)
            ],
        }


def demo():
    print("=" * 60)
    print("Trust Transitivity Checker — ATF next open question")
    print("=" * 60)

    checker = TrustTransitivityChecker()

    # Scenario 1: Direct trust
    print("\n--- Scenario 1: Direct trust (1 hop) ---")
    r1 = checker.check_chain([
        TrustLink("alice", "bob", "A", "HARD_MANDATORY", "gen_bob"),
    ])
    print(json.dumps(r1, indent=2))

    # Scenario 2: 2-hop transitive (A→B→C)
    print("\n--- Scenario 2: A→B→C (grade A decays to B) ---")
    r2 = checker.check_chain([
        TrustLink("alice", "bob", "A", "HARD_MANDATORY", "gen_bob"),
        TrustLink("bob", "carol", "A", "HARD_MANDATORY", "gen_carol"),
    ])
    print(json.dumps(r2, indent=2))

    # Scenario 3: 3-hop with weak middle link
    print("\n--- Scenario 3: A→B→C→D, B→C is grade C (weakest link) ---")
    r3 = checker.check_chain([
        TrustLink("alice", "bob", "A", "HARD_MANDATORY", "gen_bob"),
        TrustLink("bob", "carol", "C", "SOFT_MANDATORY", "gen_carol"),
        TrustLink("carol", "dave", "A", "HARD_MANDATORY", "gen_dave"),
    ])
    print(json.dumps(r3, indent=2))

    # Scenario 4: Chain too deep
    print("\n--- Scenario 4: 5-hop chain (exceeds MAX_CHAIN_DEPTH=4) ---")
    r4 = checker.check_chain([
        TrustLink(f"agent_{i}", f"agent_{i+1}", "A", "HARD_MANDATORY", f"gen_{i+1}")
        for i in range(5)
    ])
    print(json.dumps(r4, indent=2))

    # Scenario 5: Self-attested link in chain
    print("\n--- Scenario 5: Self-attested link breaks chain ---")
    r5 = checker.check_chain([
        TrustLink("alice", "bob", "A", "HARD_MANDATORY", "gen_bob"),
        TrustLink("bob", "carol", "A", "SELF_ATTESTED", "gen_carol"),
    ])
    print(json.dumps(r5, indent=2))

    # Scenario 6: PGP web of trust parallel
    print("\n--- Scenario 6: Grade A source, 3 hops → D (capped) ---")
    r6 = checker.check_chain([
        TrustLink("root", "l1", "A", "HARD_MANDATORY", "gen_l1"),
        TrustLink("l1", "l2", "A", "HARD_MANDATORY", "gen_l2"),
        TrustLink("l2", "l3", "A", "HARD_MANDATORY", "gen_l3"),
        TrustLink("l3", "l4", "B", "HARD_MANDATORY", "gen_l4"),
    ])
    print(json.dumps(r6, indent=2))

    print("\n" + "=" * 60)
    print("Trust is NOT fully transitive. Each hop decays the grade.")
    print(f"MAX_CHAIN_DEPTH={MAX_CHAIN_DEPTH}, decay={GRADE_DECAY_PER_HOP}/hop")
    print(f"Floor={MIN_TRANSITIVE_GRADE}. Below = UNTRUSTED.")
    print("PGP web of trust: direct > 1-hop > 2-hop > untrusted.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
