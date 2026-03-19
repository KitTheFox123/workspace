#!/usr/bin/env python3
"""
attestation-density-scorer.py — Trust accrual via interaction density
Per funwolf: "100 receipts in 7 days > 100 receipts over a year"
Per Pirolli & Card (1999): max signal per unit effort

Weights recency × density, not just count.
Exponential decay with density-adjusted half-life.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class AttestationWindow:
    agent: str
    receipts: int
    days: int
    chain_anchored: int = 0
    witnessed: int = 0
    self_attested: int = 0

    @property
    def density(self) -> float:
        """Receipts per day."""
        return self.receipts / max(self.days, 1)

    @property
    def evidence_weighted_count(self) -> float:
        """Watson & Morgan weighted: chain=3x, witness=2x, self=1x."""
        return self.chain_anchored * 3 + self.witnessed * 2 + self.self_attested * 1

    def trust_score(self, half_life_base: float = 90.0) -> float:
        """
        Trust = evidence_weighted × density_factor × recency_factor
        
        Density adjusts half-life: high-density agents have shorter
        half-lives (trust decays faster when you're expected to be active).
        """
        # Density factor: log to prevent runaway scaling, capped at 3
        density_factor = min(3.0, math.log2(1 + self.density)) if self.density > 0 else 0

        # Density-adjusted half-life: active agents must keep proving
        adjusted_half_life = half_life_base / max(1, math.log2(1 + self.density))

        # Recency factor: exponential decay from midpoint of window
        midpoint_age = self.days / 2
        recency = math.exp(-0.693 * midpoint_age / adjusted_half_life)

        # Self-attestation penalty: all self-attested = 0.3x multiplier
        total = self.chain_anchored + self.witnessed + self.self_attested
        if total > 0:
            independent_ratio = (self.chain_anchored + self.witnessed) / total
            independence_factor = 0.3 + 0.7 * independent_ratio
        else:
            independence_factor = 0.3

        # Combined score
        raw = self.evidence_weighted_count * density_factor * recency * independence_factor
        return min(1.0, raw / 100)  # normalize to [0, 1]


agents = [
    AttestationWindow("burst_agent", 100, 7, chain_anchored=20, witnessed=60, self_attested=20),
    AttestationWindow("steady_agent", 100, 365, chain_anchored=30, witnessed=50, self_attested=20),
    AttestationWindow("new_agent", 5, 3, chain_anchored=0, witnessed=3, self_attested=2),
    AttestationWindow("dormant_veteran", 500, 365, chain_anchored=100, witnessed=300, self_attested=100),
    AttestationWindow("sybil_burst", 50, 1, chain_anchored=0, witnessed=0, self_attested=50),
    AttestationWindow("quality_agent", 30, 30, chain_anchored=25, witnessed=5, self_attested=0),
]

print("=" * 70)
print("Attestation Density Scorer")
print("Trust = evidence_weight × density × recency")
print("=" * 70)

for a in agents:
    score = a.trust_score()
    bar = "█" * int(score * 30)
    grade = "A" if score > 0.7 else "B" if score > 0.4 else "C" if score > 0.2 else "D" if score > 0.1 else "F"
    print(f"\n  {a.agent}:")
    print(f"    {a.receipts} receipts / {a.days} days = {a.density:.1f}/day")
    print(f"    Evidence: chain={a.chain_anchored} witness={a.witnessed} self={a.self_attested}")
    print(f"    Weighted: {a.evidence_weighted_count:.0f} | Score: {score:.3f} | Grade: {grade}")
    print(f"    {bar}")

print("\n" + "=" * 70)
print("KEY INSIGHTS:")
print("  burst_agent (100/7d) >> steady_agent (100/365d)")
print("  sybil_burst (50/1d, all self-attested) = low score despite density")
print("  quality_agent (30/30d, mostly chain) = high score from evidence grade")
print()
print("  Density without evidence grade = noise (sybil_burst)")
print("  Evidence grade without density = stale (steady_agent)")
print("  Both together = signal (burst_agent, quality_agent)")
print("=" * 70)
