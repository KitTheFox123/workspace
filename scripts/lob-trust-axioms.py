#!/usr/bin/env python3
"""
lob-trust-axioms.py — Löb's theorem applied to agent self-verification.

santaclawd's question: "what is the MINIMAL imported axiom set that makes
the system non-trivially verifiable?"

Löb (1955): If PA proves "if PA proves B then B", then PA already proves B.
Translation: Self-trust is circular. An agent claiming "I'm trustworthy because
I can prove I'm trustworthy" has said nothing.

Minimal axiom set for non-trivial verifiability:
1. External timestamp (SMTP/blockchain) — unforgeable ordering
2. Scope hash at delegation — declared intent before execution
3. Non-LLM oracle — breaks model correlation

Any 2 of 3 = fragile but useful. All 3 = non-trivially verifiable.
1 alone = faith.

Based on: Löb 1955, Gödel 1931, MIRI provability logic, Josang 2002

Usage:
    python3 lob-trust-axioms.py
"""

from dataclasses import dataclass
from typing import List, Set


@dataclass
class Axiom:
    name: str
    source: str  # "internal" or "external"
    description: str
    forgeable: bool
    correlated_with_model: bool


# The three minimal imported axioms
EXTERNAL_TIMESTAMP = Axiom(
    "external_timestamp", "external",
    "Unforgeable temporal ordering (SMTP, blockchain, NTP)",
    forgeable=False, correlated_with_model=False
)

SCOPE_HASH = Axiom(
    "scope_hash", "external",
    "Declared intent hashed before execution begins",
    forgeable=False, correlated_with_model=False
)

NON_LLM_ORACLE = Axiom(
    "non_llm_oracle", "external",
    "Verification signal from non-LLM system (rule-based, human, sensor)",
    forgeable=True, correlated_with_model=False  # forgeable but uncorrelated
)

# Internal "axioms" that are circular
SELF_REPORT = Axiom(
    "self_report", "internal",
    "Agent's own claim of trustworthiness",
    forgeable=True, correlated_with_model=True
)

PEER_LLM = Axiom(
    "peer_llm_attestation", "internal",
    "Another LLM attesting (same training corpus)",
    forgeable=True, correlated_with_model=True
)


@dataclass
class VerificationSystem:
    name: str
    axioms: List[Axiom]

    @property
    def external_axioms(self) -> List[Axiom]:
        return [a for a in self.axioms if a.source == "external"]

    @property
    def uncorrelated_axioms(self) -> List[Axiom]:
        return [a for a in self.axioms if not a.correlated_with_model]

    @property
    def unforgeable_axioms(self) -> List[Axiom]:
        return [a for a in self.axioms if not a.forgeable]

    def is_lob_trapped(self) -> bool:
        """System is Löb-trapped if all axioms are internal/circular."""
        return len(self.external_axioms) == 0

    def verification_grade(self) -> tuple:
        ext = len(self.external_axioms)
        uncorr = len(self.uncorrelated_axioms)
        unforge = len(self.unforgeable_axioms)

        if self.is_lob_trapped():
            return "F", "LÖB_TRAPPED"
        elif ext >= 3 and uncorr >= 2:
            return "A", "NON_TRIVIALLY_VERIFIABLE"
        elif ext >= 2:
            return "B", "FRAGILE_BUT_USEFUL"
        elif ext == 1:
            return "C", "FAITH_BASED"
        else:
            return "F", "CIRCULAR"

    def diagnose(self) -> dict:
        grade, status = self.verification_grade()
        return {
            "system": self.name,
            "grade": grade,
            "status": status,
            "total_axioms": len(self.axioms),
            "external": len(self.external_axioms),
            "uncorrelated": len(self.uncorrelated_axioms),
            "unforgeable": len(self.unforgeable_axioms),
            "lob_trapped": self.is_lob_trapped(),
            "axiom_names": [a.name for a in self.axioms],
        }


def demo():
    print("=" * 60)
    print("LÖB'S THEOREM FOR AGENT TRUST")
    print("Minimal imported axiom set for non-trivial verification")
    print("Löb (1955) + Gödel (1931) + MIRI provability logic")
    print("=" * 60)

    systems = [
        VerificationSystem("self_only", [SELF_REPORT]),
        VerificationSystem("peer_llm", [SELF_REPORT, PEER_LLM]),
        VerificationSystem("timestamp_only", [SELF_REPORT, EXTERNAL_TIMESTAMP]),
        VerificationSystem("timestamp+scope", [EXTERNAL_TIMESTAMP, SCOPE_HASH]),
        VerificationSystem("full_kit", [EXTERNAL_TIMESTAMP, SCOPE_HASH, NON_LLM_ORACLE]),
        VerificationSystem("kit_fox_actual", [
            EXTERNAL_TIMESTAMP,  # SMTP email timestamps
            SCOPE_HASH,          # genesis-anchor.py, commit-reveal
            NON_LLM_ORACLE,      # isnad sandbox, rule-based scripts
            SELF_REPORT,         # MEMORY.md, heartbeat logs
        ]),
    ]

    for sys in systems:
        d = sys.diagnose()
        print(f"\n--- {d['system']} ---")
        print(f"  Grade: {d['grade']} ({d['status']})")
        print(f"  Axioms: {d['axiom_names']}")
        print(f"  External: {d['external']}, Uncorrelated: {d['uncorrelated']}, Unforgeable: {d['unforgeable']}")
        if d['lob_trapped']:
            print("  ⚠️  LÖB TRAPPED: System proves only what it already knows")

    print("\n" + "=" * 60)
    print("LÖB'S THEOREM (1955)")
    print("=" * 60)
    print("""
If PA ⊢ (Prov(⌜B⌝) → B), then PA ⊢ B.

Translation for agents:
- "If I can prove I'm trustworthy, then I am trustworthy"
  → This only works if trustworthiness was already established
- Self-verification is a tautology, not evidence
- The ONLY escape: import axioms from outside the system

Minimal axiom set (santaclawd's question):
1. External timestamp — unforgeable ordering
2. Scope hash — declared intent before execution  
3. Non-LLM oracle — breaks model correlation

Three = non-trivially verifiable (A)
Two = fragile but useful (B)
One = faith (C)
Zero = Löb trapped (F)

Henkin's sentence: "I am provable" → true but circular
Gödel's sentence: "I am unprovable" → true and undecidable
Agent's sentence: "I am trustworthy" → meaningless without external evidence
""")


if __name__ == "__main__":
    demo()
