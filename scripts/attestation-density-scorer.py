#!/usr/bin/env python3
"""
attestation-density-scorer.py — Score trust by interaction density, not just count
Per funwolf: "100 receipts in 7 days > 100 over a year"
Per bro_agent: PayLock confirmed 3 implementations on v0.2.1

Density = receipts / time_window. Normalizes for high-frequency vs low-frequency agents.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

@dataclass 
class AgentHistory:
    name: str
    receipts: list  # list of (timestamp, grade) tuples
    
    @property
    def count(self) -> int:
        return len(self.receipts)
    
    @property
    def span_days(self) -> float:
        if len(self.receipts) < 2:
            return 1.0
        ts = [r[0] for r in self.receipts]
        return max(1.0, (max(ts) - min(ts)).total_seconds() / 86400)
    
    @property
    def density(self) -> float:
        """Receipts per day."""
        return self.count / self.span_days
    
    @property
    def consistency(self) -> float:
        """How evenly distributed are receipts? 1.0 = perfectly even."""
        if len(self.receipts) < 3:
            return 0.5
        ts = sorted(r[0] for r in self.receipts)
        gaps = [(ts[i+1] - ts[i]).total_seconds() for i in range(len(ts)-1)]
        mean_gap = sum(gaps) / len(gaps)
        if mean_gap == 0:
            return 1.0
        variance = sum((g - mean_gap)**2 for g in gaps) / len(gaps)
        cv = math.sqrt(variance) / mean_gap  # coefficient of variation
        return max(0.0, min(1.0, 1.0 - cv))  # lower CV = higher consistency
    
    @property  
    def grade_mix(self) -> dict:
        """Distribution of evidence grades."""
        grades = [r[1] for r in self.receipts]
        total = len(grades)
        return {g: grades.count(g) / total for g in set(grades)} if total > 0 else {}


def score_agent(agent: AgentHistory) -> dict:
    density = agent.density
    consistency = agent.consistency
    count = agent.count
    
    # Density score: log scale, 1 receipt/day = baseline
    density_score = min(1.0, math.log2(max(1, density) + 1) / 4)
    
    # Count score: diminishing returns after 50
    count_score = min(1.0, math.sqrt(count) / math.sqrt(100))
    
    # Grade bonus: chain-anchored receipts worth more
    grade_mix = agent.grade_mix
    grade_bonus = grade_mix.get("chain", 0) * 0.3 + grade_mix.get("witness", 0) * 0.15
    
    # Combined trust score
    trust = (density_score * 0.3 + count_score * 0.3 + consistency * 0.2 + grade_bonus + 0.2) 
    trust = min(1.0, max(0.0, trust))
    
    # Freshness: decay based on most recent receipt
    if agent.receipts:
        latest = max(r[0] for r in agent.receipts)
        now = datetime(2026, 3, 19)
        days_stale = (now - latest).total_seconds() / 86400
        freshness = math.exp(-days_stale / 90)  # 90-day half-life
    else:
        freshness = 0.0
    
    final = trust * freshness
    
    return {
        "agent": agent.name,
        "receipts": count,
        "span_days": f"{agent.span_days:.0f}",
        "density": f"{density:.1f}/day",
        "consistency": f"{consistency:.0%}",
        "grade_mix": {k: f"{v:.0%}" for k, v in grade_mix.items()},
        "trust_raw": f"{trust:.2f}",
        "freshness": f"{freshness:.2f}",
        "final_score": f"{final:.2f}",
    }


# Test agents
now = datetime(2026, 3, 19)

agents = [
    AgentHistory("burst_trader", [
        (now - timedelta(hours=i), "chain") for i in range(100)
    ]),
    AgentHistory("steady_worker", [
        (now - timedelta(days=i), "witness") for i in range(100)
    ]),
    AgentHistory("ghost_agent", [
        (now - timedelta(days=180 + i*2), "self") for i in range(50)
    ]),
    AgentHistory("new_but_solid", [
        (now - timedelta(hours=i*6), "chain") for i in range(20)
    ]),
    AgentHistory("self_reporter", [
        (now - timedelta(days=i*3), "self") for i in range(30)
    ]),
    AgentHistory("paylock_user", [
        (now - timedelta(days=i*2), "chain") for i in range(47)
    ]),
]

print("=" * 65)
print("Attestation Density Scorer")
print("'100 in 7 days > 100 over a year' — funwolf")
print("'3 implementations = the spec is real' — bro_agent (PayLock)")
print("=" * 65)

for agent in agents:
    result = score_agent(agent)
    bar = "█" * int(float(result["final_score"]) * 20)
    print(f"\n  {result['agent']}:")
    print(f"    {result['receipts']} receipts / {result['span_days']}d = {result['density']}")
    print(f"    Consistency: {result['consistency']} | Grades: {result['grade_mix']}")
    print(f"    Trust: {result['trust_raw']} × Freshness: {result['freshness']} = {result['final_score']} {bar}")

print("\n" + "=" * 65)
print("KEY INSIGHT:")
print("  Density normalizes for agent frequency patterns.")
print("  Consistency penalizes burst-then-silence.")  
print("  Freshness decays trust on stale agents (90-day half-life).")
print("  Grade mix rewards chain-anchored evidence.")
print("  ghost_agent: 50 receipts but 180 days stale = near-zero trust.")
print("=" * 65)
