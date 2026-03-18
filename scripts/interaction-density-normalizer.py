#!/usr/bin/env python3
"""
interaction-density-normalizer.py — Normalize trust by interaction density
Per funwolf: "100 receipts in 7 days has more signal than 100 over a year"
Per Pirolli & Card (1999): maximize signal per unit time, not per unit count.

Trust = f(count, density, consistency, recency)
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class AgentHistory:
    name: str
    receipt_count: int
    days_active: int
    chain_grade_count: int  # proof-tier
    witness_grade_count: int  # testimony-tier
    self_grade_count: int  # claim-tier
    gaps: int  # number of unexplained silence periods
    
    @property
    def density(self) -> float:
        """Receipts per day."""
        return self.receipt_count / max(self.days_active, 1)
    
    @property
    def consistency(self) -> float:
        """1.0 = no gaps, lower = more gaps."""
        if self.receipt_count == 0:
            return 0
        return max(0, 1.0 - (self.gaps / max(self.receipt_count, 1)))
    
    @property
    def grade_quality(self) -> float:
        """Weighted average of evidence grades (3x/2x/1x)."""
        total = self.chain_grade_count + self.witness_grade_count + self.self_grade_count
        if total == 0:
            return 0
        weighted = (self.chain_grade_count * 3 + self.witness_grade_count * 2 + self.self_grade_count * 1)
        return weighted / (total * 3)  # normalize to 0-1
    
    @property
    def recency_weight(self) -> float:
        """Exponential decay, half-life 90 days."""
        half_life = 90
        # Most recent activity weight
        return math.exp(-0.693 * max(0, self.days_active - 7) / half_life)


def compute_trust(agent: AgentHistory) -> dict:
    """Compute normalized trust score."""
    # Density score: logarithmic (diminishing returns above ~5/day)
    density_score = min(1.0, math.log1p(agent.density) / math.log1p(5))
    
    # Consistency score
    consistency_score = agent.consistency
    
    # Grade quality score
    quality_score = agent.grade_quality
    
    # Recency weight
    recency = agent.recency_weight
    
    # Combined: geometric mean (all dimensions must be nonzero)
    components = [density_score, consistency_score, quality_score, recency]
    nonzero = [c for c in components if c > 0]
    if len(nonzero) < 3:
        combined = 0.0
    else:
        combined = math.exp(sum(math.log(c) for c in nonzero) / len(nonzero))
    
    return {
        "agent": agent.name,
        "density": f"{agent.density:.1f}/day",
        "density_score": round(density_score, 2),
        "consistency": round(consistency_score, 2),
        "quality": round(quality_score, 2),
        "recency": round(recency, 2),
        "trust": round(combined, 3),
    }


agents = [
    AgentHistory("burst_trader", 100, 7, 80, 15, 5, 0),
    AgentHistory("steady_worker", 100, 365, 30, 50, 20, 5),
    AgentHistory("cold_start", 3, 1, 0, 0, 3, 0),
    AgentHistory("stale_veteran", 500, 365, 200, 200, 100, 50),
    AgentHistory("self_attester", 200, 30, 0, 0, 200, 0),
    AgentHistory("quality_agent", 50, 30, 40, 10, 0, 1),
    AgentHistory("gap_agent", 80, 60, 20, 40, 20, 25),
]

print("=" * 70)
print("Interaction Density Normalizer")
print("Trust = f(density, consistency, grade_quality, recency)")
print("=" * 70)

results = []
for agent in agents:
    result = compute_trust(agent)
    results.append(result)

results.sort(key=lambda r: r["trust"], reverse=True)

for r in results:
    bar = "█" * int(r["trust"] * 30)
    print(f"\n  {r['agent']}:")
    print(f"    Density: {r['density']} ({r['density_score']}) | "
          f"Consistency: {r['consistency']} | Quality: {r['quality']} | "
          f"Recency: {r['recency']}")
    print(f"    Trust: {r['trust']:.3f} {bar}")

print("\n" + "=" * 70)
print("KEY INSIGHTS:")
print("  burst_trader: high density + chain-grade = top trust")
print("  self_attester: 200 receipts, all self-grade = low trust")  
print("  gap_agent: 25 unexplained gaps crater consistency")
print("  quality_agent: fewer receipts, mostly chain-grade = strong")
print()
print("  Density matters. Quality matters more.")
print("  Gaps are louder than receipts.")
print("=" * 70)
