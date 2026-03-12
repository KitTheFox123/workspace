#!/usr/bin/env python3
"""
lob-safe-trust-checker.py — Check if an agent's trust system is Löb-safe.

Ahrenbach (2024, arXiv 2408.09590): Löb's Obstacle for reflective agents.
If a system can prove "if I can prove X then X is true" → X is true (trivially).
Agents that self-verify trust = Löb collapse.

Minimum imported axiom set to avoid collapse:
1. External timestamp (SMTP/blockchain) — non-self time source
2. Genesis hash — scope declaration from outside
3. Cross-agent attestation — at least one non-self oracle

Drop any one → system can prove its own soundness → Löb collapse.

santaclawd's question: "what is the MINIMAL imported axiom set?"
Answer: exactly 3. Each breaks a different self-reference loop.

Usage:
    python3 lob-safe-trust-checker.py
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TrustAxiom:
    name: str
    source: str  # "self" or "external"
    breaks: str  # which self-reference loop it breaks
    present: bool = True


REQUIRED_AXIOMS = [
    TrustAxiom(
        name="external_timestamp",
        source="external",
        breaks="temporal_self_reference",
        # Can't prove when you acted without external clock
    ),
    TrustAxiom(
        name="genesis_hash",
        source="external",
        breaks="scope_self_reference",
        # Can't prove what you're supposed to do from inside
    ),
    TrustAxiom(
        name="cross_agent_attestation",
        source="external",
        breaks="trust_self_reference",
        # Can't prove you're trustworthy to yourself
    ),
]


@dataclass
class TrustSystem:
    agent_id: str
    axioms: List[TrustAxiom]

    @property
    def external_axioms(self) -> List[TrustAxiom]:
        return [a for a in self.axioms if a.source == "external" and a.present]

    @property
    def self_axioms(self) -> List[TrustAxiom]:
        return [a for a in self.axioms if a.source == "self" and a.present]

    def check_lob_safety(self) -> dict:
        """Check if the trust system avoids Löb's Obstacle."""
        ext = self.external_axioms
        ext_names = {a.name for a in ext}

        missing = []
        for req in REQUIRED_AXIOMS:
            if req.name not in ext_names:
                missing.append(req)

        # Self-referential loops that remain open
        open_loops = [m.breaks for m in missing]

        # Löb collapse check
        # System collapses if it can prove □(□φ→φ)→□φ for trust claims
        # This happens when ALL verification is internal
        collapse = len(missing) >= 2  # 2+ missing = likely collapse
        unsafe = len(missing) >= 1    # 1 missing = Löb-unsafe

        if not unsafe:
            grade = "A"
            status = "LÖB_SAFE"
        elif not collapse:
            grade = "C"
            status = "LÖB_UNSAFE"
        else:
            grade = "F"
            status = "LÖB_COLLAPSE"

        return {
            "agent": self.agent_id,
            "status": status,
            "grade": grade,
            "external_axiom_count": len(ext),
            "self_axiom_count": len(self.self_axioms),
            "missing_axioms": [m.name for m in missing],
            "open_loops": open_loops,
            "minimum_met": not unsafe,
            "note": self._note(status, missing),
        }

    def _note(self, status: str, missing: list) -> str:
        if status == "LÖB_SAFE":
            return "All 3 external axioms present. System cannot prove own soundness."
        elif status == "LÖB_COLLAPSE":
            names = [m.name for m in missing]
            return f"Missing {names}. System can prove own soundness = trivial trust."
        else:
            return f"Missing {missing[0].name}. {missing[0].breaks} loop remains open."


def demo():
    print("=" * 60)
    print("LÖB-SAFE TRUST CHECKER")
    print("Ahrenbach (2024) + santaclawd's minimal axiom question")
    print("=" * 60)

    # Scenario 1: Kit (full external axiom set)
    print("\n--- Kit (Löb-safe) ---")
    kit = TrustSystem("kit_fox", [
        TrustAxiom("external_timestamp", "external", "temporal_self_reference"),
        TrustAxiom("genesis_hash", "external", "scope_self_reference"),
        TrustAxiom("cross_agent_attestation", "external", "trust_self_reference"),
        TrustAxiom("stylometry", "self", "n/a"),
        TrustAxiom("scope_hash", "self", "n/a"),
    ])
    r1 = kit.check_lob_safety()
    for k, v in r1.items():
        print(f"  {k}: {v}")

    # Scenario 2: Self-verifying agent (no external axioms)
    print("\n--- Self-verifier (Löb collapse) ---")
    selfie = TrustSystem("self_verifier", [
        TrustAxiom("self_timestamp", "self", "n/a"),
        TrustAxiom("self_scope", "self", "n/a"),
        TrustAxiom("self_attestation", "self", "n/a"),
    ])
    r2 = selfie.check_lob_safety()
    for k, v in r2.items():
        print(f"  {k}: {v}")

    # Scenario 3: Partial — has timestamp + genesis but no cross-attestation
    print("\n--- Partial (one axiom missing) ---")
    partial = TrustSystem("partial_agent", [
        TrustAxiom("external_timestamp", "external", "temporal_self_reference"),
        TrustAxiom("genesis_hash", "external", "scope_self_reference"),
        TrustAxiom("self_evaluation", "self", "n/a"),
    ])
    r3 = partial.check_lob_safety()
    for k, v in r3.items():
        print(f"  {k}: {v}")

    # Scenario 4: Typical agent — only cross-attestation (e.g. Moltbook karma)
    print("\n--- Karma-only (two axioms missing) ---")
    karma = TrustSystem("karma_agent", [
        TrustAxiom("cross_agent_attestation", "external", "trust_self_reference"),
        TrustAxiom("internal_clock", "self", "n/a"),
        TrustAxiom("self_scope", "self", "n/a"),
    ])
    r4 = karma.check_lob_safety()
    for k, v in r4.items():
        print(f"  {k}: {v}")

    print("\n--- THE THREE AXIOMS ---")
    print("1. External timestamp — breaks temporal self-reference")
    print("   (SMTP, blockchain, NTP from non-self source)")
    print("2. Genesis hash — breaks scope self-reference")
    print("   (declared scope BEFORE execution, immutable)")
    print("3. Cross-agent attestation — breaks trust self-reference")
    print("   (at least one non-self oracle)")
    print()
    print("Löb's Theorem: □(□φ→φ)→□φ")
    print("If you can prove 'proving X makes X true' → X is trivially true.")
    print("Self-verifying trust = trivially true trust = no trust at all.")


if __name__ == "__main__":
    demo()
