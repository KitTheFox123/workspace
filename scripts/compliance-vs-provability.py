#!/usr/bin/env python3
"""
compliance-vs-provability.py — Quantify the gap between "I followed the rules"
and "here is the proof."

Inspired by Moltbook post on compliance vs provability in AI (2026-03-17).

Compliance = self-report. Weight: 1x (testimony).
Provability = verifiable evidence. Weight: 2x (observation).
Watson & Morgan epistemic distinction.

An agent can be compliant but unprovable (trust me bro).
An agent can be provable but non-compliant (transparent violation).
Only provable + compliant = trustworthy.

Usage:
    python3 compliance-vs-provability.py
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class AgentClaim:
    """What an agent says about itself."""
    agent_id: str
    claim: str
    has_receipt: bool = False
    has_merkle_proof: bool = False
    has_witnesses: bool = False
    witness_count: int = 0
    witness_orgs: int = 0
    has_refusal_hash: bool = False  # ZK-like: proves WHY without WHAT
    
    @property
    def compliance_score(self) -> float:
        """Self-reported compliance. Testimony = 1x weight."""
        return 1.0  # Always 1.0 — the agent always says it complied
    
    @property
    def provability_score(self) -> float:
        """Verifiable evidence. Observation = 2x weight."""
        score = 0.0
        if self.has_receipt: score += 0.3
        if self.has_merkle_proof: score += 0.3
        if self.has_witnesses: score += 0.2
        if self.witness_orgs >= 2: score += 0.1
        if self.has_refusal_hash: score += 0.1
        return round(min(score, 1.0), 2)
    
    @property
    def trust_weight(self) -> float:
        """Watson & Morgan: testimony=1x, observation=2x."""
        testimony = self.compliance_score * 1.0
        observation = self.provability_score * 2.0
        return round((testimony + observation) / 3.0, 3)
    
    @property
    def quadrant(self) -> str:
        c = self.compliance_score > 0.5
        p = self.provability_score > 0.5
        if c and p: return "TRUSTWORTHY"
        if c and not p: return "TRUST_ME_BRO"
        if not c and p: return "TRANSPARENT_VIOLATION"
        return "UNTRUSTED"


def demo():
    agents = [
        AgentClaim("agent:honest_proven", "delivered on time",
                    has_receipt=True, has_merkle_proof=True, has_witnesses=True,
                    witness_count=3, witness_orgs=3, has_refusal_hash=False),
        AgentClaim("agent:honest_unprovable", "delivered on time",
                    has_receipt=False, has_merkle_proof=False, has_witnesses=False),
        AgentClaim("agent:scammer_opaque", "delivered premium quality",
                    has_receipt=False, has_merkle_proof=False, has_witnesses=False),
        AgentClaim("agent:principled_refuser", "refused — task violated policy",
                    has_receipt=True, has_merkle_proof=True, has_witnesses=True,
                    witness_count=2, witness_orgs=2, has_refusal_hash=True),
        AgentClaim("agent:transparent_violator", "exceeded scope intentionally",
                    has_receipt=True, has_merkle_proof=True, has_witnesses=True,
                    witness_count=3, witness_orgs=3),
    ]
    
    print("=" * 65)
    print("COMPLIANCE vs PROVABILITY")
    print("testimony (1x) vs observation (2x)")
    print("=" * 65)
    
    print(f"\n{'Agent':<28} {'Comply':>7} {'Prove':>7} {'Weight':>7} {'Quadrant':<22}")
    print("-" * 75)
    
    for a in agents:
        print(f"{a.agent_id:<28} {a.compliance_score:>7.2f} {a.provability_score:>7.2f} "
              f"{a.trust_weight:>7.3f} {a.quadrant:<22}")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHTS:")
    print(f"{'=' * 65}")
    print("""
  1. Every agent claims compliance (score = 1.0 always).
     Self-report is cheap. Provability is expensive.

  2. honest_unprovable and scammer_opaque are INDISTINGUISHABLE
     without receipts. Both say "I did it." Neither proves it.

  3. principled_refuser scores HIGHER than honest_unprovable
     because refusal_hash is a costly signal (Zahavi 1975).

  4. transparent_violator is more trustworthy than opaque_compliant.
     At least you can AUDIT the violation.

  5. Compliance without provability = "trust me bro."
     Provability without compliance = transparent violation.
     Only both together = trustworthy.

  Receipt is evidence, not verdict.
  Compliance is claim, not proof.
""")


if __name__ == '__main__':
    demo()
