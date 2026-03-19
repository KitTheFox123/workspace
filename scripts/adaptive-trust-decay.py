#!/usr/bin/env python3
"""
adaptive-trust-decay.py — Trust decay scaled by interaction density
Per funwolf: "100 receipts in 7 days has more signal than 100 over a year"
Per clove: "decay functions for older attestations"

Decay half-life scales with receipt rate. High-frequency agents get
tighter windows. Low-frequency agents get longer windows.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class Receipt:
    timestamp: datetime
    grade: str  # proof/testimony/claim
    
@dataclass
class AgentProfile:
    name: str
    receipts: list
    
    @property
    def receipt_rate(self) -> float:
        """Receipts per day."""
        if len(self.receipts) < 2:
            return 0.1
        span = abs((self.receipts[-1].timestamp - self.receipts[0].timestamp).days) or 1
        return len(self.receipts) / span
    
    @property
    def adaptive_half_life_days(self) -> float:
        """Half-life scales inversely with receipt rate."""
        rate = self.receipt_rate
        # High frequency (>10/day) → 30 day half-life
        # Medium (1-10/day) → 90 day half-life  
        # Low (<1/day) → 180 day half-life
        if rate > 10:
            return 30
        elif rate > 1:
            return 90
        else:
            return 180

def decay_weight(receipt_age_days: float, half_life_days: float) -> float:
    """Exponential decay: weight = 2^(-age/half_life)"""
    return 2 ** (-receipt_age_days / half_life_days)

def grade_multiplier(grade: str) -> float:
    """Watson & Morgan: proof=3x, testimony=2x, claim=1x"""
    return {"proof": 3.0, "testimony": 2.0, "claim": 1.0}.get(grade, 1.0)

def compute_trust_score(agent: AgentProfile, now: datetime) -> dict:
    """Weighted trust score with adaptive decay."""
    half_life = agent.adaptive_half_life_days
    
    weighted_sum = 0
    max_possible = 0
    
    for r in agent.receipts:
        age = (now - r.timestamp).days
        weight = decay_weight(age, half_life) * grade_multiplier(r.grade)
        weighted_sum += weight
        max_possible += grade_multiplier(r.grade)  # no decay = max
    
    score = weighted_sum / max_possible if max_possible > 0 else 0
    
    return {
        "agent": agent.name,
        "receipts": len(agent.receipts),
        "rate": f"{agent.receipt_rate:.1f}/day",
        "half_life": f"{half_life}d",
        "score": round(score, 3),
        "effective_receipts": round(weighted_sum, 1),
    }

# Test agents
now = datetime(2026, 3, 19)

# High-frequency trader: 200 receipts in 14 days
high_freq = AgentProfile("high_freq_trader", [
    Receipt(now - timedelta(days=d), "proof" if d < 3 else "testimony")
    for d in range(14) for _ in range(14)  # ~14/day
])

# Steady worker: 90 receipts over 90 days  
steady = AgentProfile("steady_worker", [
    Receipt(now - timedelta(days=d), "testimony")
    for d in range(90)
])

# Dormant: 50 receipts, last one 200 days ago
dormant = AgentProfile("dormant_agent", [
    Receipt(now - timedelta(days=200+d), "testimony")
    for d in range(50)
])

# New hot-start: 30 proof-grade in 3 days
hot_start = AgentProfile("hot_start", [
    Receipt(now - timedelta(days=d), "proof")
    for d in range(3) for _ in range(10)
])

# Mixed quality
mixed = AgentProfile("mixed_quality", [
    Receipt(now - timedelta(days=d), "claim" if d > 30 else "proof")
    for d in range(60)
])

agents = [high_freq, steady, dormant, hot_start, mixed]

print("=" * 65)
print("Adaptive Trust Decay (half-life scales with interaction density)")
print("=" * 65)

for agent in agents:
    result = compute_trust_score(agent, now)
    bar = "█" * int(result["score"] * 30)
    print(f"\n  {result['agent']}:")
    print(f"    Receipts: {result['receipts']} @ {result['rate']}")
    print(f"    Half-life: {result['half_life']} | Score: {result['score']} {bar}")
    print(f"    Effective receipts: {result['effective_receipts']}")

print("\n" + "=" * 65)
print("KEY INSIGHT:")
print("  Fixed windows penalize either fast or slow agents.")
print("  Adaptive decay: high frequency → tight window, low → wide.")
print("  Trust is perishable, but shelf life varies by activity.")
print("  An attestation from 2 years ago = who you WERE, not ARE.")
print("=" * 65)
