#!/usr/bin/env python3
"""
munchhausen-trust-classifier.py — Classify trust architectures by which horn
of the Münchhausen trilemma they pick.

Albert 1968: every justification ends in:
1. Infinite regress (who attests the attestor?)
2. Circular argument (mutual attestation, coherentism)
3. Axiomatic assertion (hardware RoT, social consensus)

Popper's pragmatic answer: mix all three. No pure solution exists.
"""

from dataclasses import dataclass
from enum import Enum


class Horn(Enum):
    REGRESS = "regress"      # Chain goes back, eventually stops at reputation
    CIRCULAR = "circular"     # Mutual attestation, coherentism
    AXIOMATIC = "axiomatic"   # Hardware fused key, social consensus, "just trust it"


@dataclass
class TrustArchitecture:
    name: str
    primary_horn: Horn
    secondary_horn: Horn | None
    depth: int              # How deep before hitting the horn
    sybil_resistance: float # 0-1
    bootstrap_cost: str     # "free", "low", "medium", "high"
    description: str

    def grade(self) -> str:
        """Grade based on horn diversity + sybil resistance."""
        score = self.sybil_resistance
        # Bonus for mixing horns (Popper's pragmatism)
        if self.secondary_horn and self.secondary_horn != self.primary_horn:
            score += 0.15
        # Penalty for pure circular (sybil magnet)
        if self.primary_horn == Horn.CIRCULAR and not self.secondary_horn:
            score -= 0.2
        # Depth penalty (deeper regress = more attack surface)
        if self.depth > 5:
            score -= 0.1
        
        score = max(0, min(1, score))
        if score >= 0.85: return "A"
        if score >= 0.7: return "B"
        if score >= 0.5: return "C"
        return "F"


# Real-world trust architectures classified
ARCHITECTURES = [
    TrustArchitecture(
        name="TPM/Hardware RoT",
        primary_horn=Horn.AXIOMATIC,
        secondary_horn=None,
        depth=1,
        sybil_resistance=0.95,
        bootstrap_cost="high",
        description="Fused key at manufacture. Trust the silicon. Dogmatic by design."
    ),
    TrustArchitecture(
        name="PKI/Certificate Authority",
        primary_horn=Horn.AXIOMATIC,
        secondary_horn=Horn.REGRESS,
        depth=3,
        sybil_resistance=0.85,
        bootstrap_cost="medium",
        description="Root CA is axiomatic. Chain of certs is regressive. Depth bounded."
    ),
    TrustArchitecture(
        name="Web of Trust (PGP)",
        primary_horn=Horn.CIRCULAR,
        secondary_horn=Horn.REGRESS,
        depth=6,
        sybil_resistance=0.6,
        bootstrap_cost="low",
        description="Mutual signing = circular. Trust paths = regressive. Sybil-prone."
    ),
    TrustArchitecture(
        name="Certificate Transparency",
        primary_horn=Horn.CIRCULAR,
        secondary_horn=Horn.AXIOMATIC,
        depth=2,
        sybil_resistance=0.9,
        bootstrap_cost="medium",
        description="Browsers trust logs, logs serve browsers. Circular but with axiomatic browser trust store."
    ),
    TrustArchitecture(
        name="Isnad Chain",
        primary_horn=Horn.REGRESS,
        secondary_horn=Horn.AXIOMATIC,
        depth=5,
        sybil_resistance=0.75,
        bootstrap_cost="low",
        description="Chain goes back through attestors. Stops at reputation (axiomatic). 850 CE hadith scholars."
    ),
    TrustArchitecture(
        name="Pure Mutual Attestation",
        primary_horn=Horn.CIRCULAR,
        secondary_horn=None,
        depth=1,
        sybil_resistance=0.3,
        bootstrap_cost="free",
        description="Agents attest each other. No external anchor. Sybil paradise."
    ),
    TrustArchitecture(
        name="Blockchain PoW",
        primary_horn=Horn.AXIOMATIC,
        secondary_horn=Horn.CIRCULAR,
        depth=1,
        sybil_resistance=0.9,
        bootstrap_cost="high",
        description="Physics is the axiom (energy cost). Miners validate each other (circular). Expensive but robust."
    ),
    TrustArchitecture(
        name="Social Consensus (Kleros)",
        primary_horn=Horn.CIRCULAR,
        secondary_horn=Horn.AXIOMATIC,
        depth=2,
        sybil_resistance=0.7,
        bootstrap_cost="medium",
        description="Jurors vote on truth (circular Schelling). Stake is axiomatic anchor."
    ),
    TrustArchitecture(
        name="Agent Email (SMTP+DKIM)",
        primary_horn=Horn.AXIOMATIC,
        secondary_horn=Horn.REGRESS,
        depth=2,
        sybil_resistance=0.65,
        bootstrap_cost="free",
        description="DNS is axiomatic. DKIM chain is regressive. Infrastructure-written timestamps."
    ),
    TrustArchitecture(
        name="Popper Hybrid (isnad+HW+mutual)",
        primary_horn=Horn.REGRESS,
        secondary_horn=Horn.AXIOMATIC,  # Also has circular component
        depth=4,
        sybil_resistance=0.85,
        bootstrap_cost="medium",
        description="Mix all 3 horns. Hardware anchor + attestation chain + peer corroboration. Popper's pragmatism."
    ),
]


def demo():
    print("=" * 70)
    print("MÜNCHHAUSEN TRUST CLASSIFIER")
    print("Albert 1968: regress × circular × axiomatic")
    print("=" * 70)
    
    for arch in ARCHITECTURES:
        grade = arch.grade()
        horns = arch.primary_horn.value
        if arch.secondary_horn:
            horns += f" + {arch.secondary_horn.value}"
        
        print(f"\n{'─' * 60}")
        print(f"{arch.name} | Grade: {grade} | Horns: {horns}")
        print(f"  Depth: {arch.depth} | Sybil: {arch.sybil_resistance:.0%} | Bootstrap: {arch.bootstrap_cost}")
        print(f"  {arch.description}")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("HORN DISTRIBUTION")
    horn_counts = {}
    for arch in ARCHITECTURES:
        h = arch.primary_horn.value
        horn_counts[h] = horn_counts.get(h, 0) + 1
    for horn, count in sorted(horn_counts.items(), key=lambda x: -x[1]):
        print(f"  {horn}: {count} architectures")
    
    # Grade distribution
    grades = [a.grade() for a in ARCHITECTURES]
    print(f"\nGRADE DISTRIBUTION")
    for g in "ABCF":
        c = grades.count(g)
        if c: print(f"  {g}: {c}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: No pure horn works alone.")
    print("  Pure axiomatic = expensive, centralized (TPM)")
    print("  Pure circular = sybil paradise (mutual attestation)")  
    print("  Pure regress = infinite chain, stops arbitrarily")
    print("  Popper's answer: mix all three. Pragmatic fallibilism.")
    print("  The Münchhausen trilemma isn't a problem to solve —")
    print("  it's a constraint to design around.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
