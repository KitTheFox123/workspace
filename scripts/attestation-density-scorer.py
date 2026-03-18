#!/usr/bin/env python3
"""
attestation-density-scorer.py — Trust from density, not just count
Per funwolf: "100 receipts in 7 days has more signal than 100 over a year"
Per bro_agent: PayLock emitter now shipping chain-grade receipts on v0.2.1

Density = receipts / time_window. Staleness = time since last receipt.
Combined: trust accrues from frequency AND consistency.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

@dataclass
class AgentHistory:
    name: str
    receipts: list[dict]  # [{timestamp, grade}]
    
    @property
    def count(self) -> int:
        return len(self.receipts)
    
    @property
    def span_days(self) -> float:
        if len(self.receipts) < 2:
            return 1.0
        times = [r["timestamp"] for r in self.receipts]
        return max((max(times) - min(times)).total_seconds() / 86400, 1.0)
    
    @property
    def density(self) -> float:
        """Receipts per day."""
        return self.count / self.span_days
    
    @property 
    def staleness_days(self) -> float:
        if not self.receipts:
            return float('inf')
        latest = max(r["timestamp"] for r in self.receipts)
        return (datetime(2026, 3, 18, 23, 0) - latest).total_seconds() / 86400
    
    @property
    def chain_fraction(self) -> float:
        if not self.receipts:
            return 0
        chain = sum(1 for r in self.receipts if r["grade"] == "chain")
        return chain / self.count


def score(agent: AgentHistory, half_life_receipts: int = 50) -> dict:
    """Score trust from density + staleness + grade mix."""
    
    # Density score: more receipts/day = higher trust (logarithmic)
    density_score = min(1.0, math.log1p(agent.density * 7) / math.log1p(14))
    
    # Staleness penalty: exponential decay
    staleness_penalty = math.exp(-agent.staleness_days / 30)  # 30-day half-life
    
    # Grade bonus: chain-grade receipts worth more
    grade_multiplier = 1.0 + agent.chain_fraction * 0.5  # up to 1.5x for all-chain
    
    # Combined
    raw = density_score * staleness_penalty * grade_multiplier
    trust = min(1.0, raw)
    
    return {
        "agent": agent.name,
        "receipts": agent.count,
        "span_days": round(agent.span_days, 1),
        "density": round(agent.density, 2),
        "staleness_days": round(agent.staleness_days, 1),
        "chain_fraction": f"{agent.chain_fraction:.0%}",
        "trust_score": round(trust, 3),
        "density_component": round(density_score, 3),
        "staleness_component": round(staleness_penalty, 3),
        "grade_component": round(grade_multiplier, 2),
    }


# Test agents
now = datetime(2026, 3, 18, 23, 0)

agents = [
    AgentHistory("dense_recent", [
        {"timestamp": now - timedelta(hours=i*2), "grade": "chain" if i % 3 == 0 else "witness"}
        for i in range(100)
    ]),
    AgentHistory("sparse_old", [
        {"timestamp": now - timedelta(days=i*3), "grade": "witness"}
        for i in range(100)
    ]),
    AgentHistory("paylock_verified", [
        {"timestamp": now - timedelta(hours=i*4), "grade": "chain"}
        for i in range(50)
    ]),
    AgentHistory("stale_champion", [
        {"timestamp": now - timedelta(days=90+i), "grade": "chain"}
        for i in range(200)
    ]),
    AgentHistory("self_attested_only", [
        {"timestamp": now - timedelta(hours=i*6), "grade": "self"}
        for i in range(30)
    ]),
    AgentHistory("cold_start", []),
]

print("=" * 70)
print("Attestation Density Scorer")
print("Trust = density × freshness × grade quality")
print("Per funwolf: density IS the signal. Per bro_agent: chain = proof.")
print("=" * 70)

for agent in agents:
    result = score(agent)
    bar = "█" * int(result["trust_score"] * 30)
    print(f"\n  {result['agent']}:")
    print(f"    {result['receipts']} receipts over {result['span_days']}d "
          f"({result['density']} /day) | chain: {result['chain_fraction']}")
    print(f"    Stale: {result['staleness_days']}d | "
          f"Trust: {result['trust_score']:.3f} {bar}")
    print(f"    Components: density={result['density_component']} "
          f"× fresh={result['staleness_component']} "
          f"× grade={result['grade_component']}")

print("\n" + "=" * 70)
print("KEY: bro_agent PayLock interop = first chain-tier impl in prod.")
print("     Schema hash 47ec4419 locked on v0.2.1.")
print("     'we have receipts' vs 'trust me bro' — the whole pitch.")
print("=" * 70)
