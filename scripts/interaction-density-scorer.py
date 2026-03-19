#!/usr/bin/env python3
"""
interaction-density-scorer.py — Trust signal from receipt frequency + consistency
Per funwolf: "100 receipts in 7 days > 100 over a year. Trust accrues from
frequency AND consistency."

Density = receipts per unit time. Consistency = variance in inter-receipt gaps.
Silence after speed = the strongest red flag.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class AgentHistory:
    name: str
    receipts: list  # list of (timestamp, grade) tuples
    
    @property
    def density(self) -> float:
        """Receipts per day."""
        if len(self.receipts) < 2:
            return 0
        span = (self.receipts[-1][0] - self.receipts[0][0]).total_seconds() / 86400
        return len(self.receipts) / max(span, 0.01)
    
    @property
    def consistency(self) -> float:
        """1.0 = perfectly regular, 0.0 = maximally irregular."""
        if len(self.receipts) < 3:
            return 0.5  # insufficient data
        gaps = []
        for i in range(1, len(self.receipts)):
            gap = (self.receipts[i][0] - self.receipts[i-1][0]).total_seconds()
            gaps.append(gap)
        mean_gap = sum(gaps) / len(gaps)
        if mean_gap == 0:
            return 1.0
        variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
        cv = math.sqrt(variance) / mean_gap  # coefficient of variation
        return max(0, 1 - min(cv, 2) / 2)  # normalize to 0-1
    
    @property 
    def silence_after_speed(self) -> bool:
        """Detect sudden stop after high activity."""
        if len(self.receipts) < 5:
            return False
        recent_gap = (datetime(2026, 3, 19) - self.receipts[-1][0]).total_seconds() / 86400
        avg_gap = sum(
            (self.receipts[i][0] - self.receipts[i-1][0]).total_seconds() / 86400
            for i in range(1, len(self.receipts))
        ) / (len(self.receipts) - 1)
        return recent_gap > avg_gap * 5  # 5x normal gap = suspicious silence

    def trust_signal(self) -> dict:
        density = self.density
        consistency = self.consistency
        silence = self.silence_after_speed
        
        # Combined score: density * consistency, penalized by silence
        raw = min(density, 20) / 20 * 0.5 + consistency * 0.5
        if silence:
            raw *= 0.3  # 70% penalty for suspicious silence
        
        if silence:
            verdict = "SUSPICIOUS_SILENCE"
        elif density > 5 and consistency > 0.7:
            verdict = "HIGH_SIGNAL"
        elif density > 1 and consistency > 0.4:
            verdict = "MODERATE_SIGNAL"  
        elif density > 0:
            verdict = "LOW_SIGNAL"
        else:
            verdict = "NO_SIGNAL"
        
        return {
            "agent": self.name,
            "density": round(density, 2),
            "consistency": round(consistency, 2),
            "silence_flag": silence,
            "score": round(raw, 3),
            "verdict": verdict,
        }


# Test agents
now = datetime(2026, 3, 19)
agents = [
    AgentHistory("burst_worker", [
        (now - timedelta(days=7, hours=h), "witness") 
        for h in range(0, 168, 2)  # every 2 hours for 7 days = 84 receipts
    ]),
    AgentHistory("steady_worker", [
        (now - timedelta(days=d), "witness")
        for d in range(365, 0, -4)  # every 4 days for a year = ~91 receipts
    ]),
    AgentHistory("ghost_agent", [
        (now - timedelta(days=90, hours=h), "chain")
        for h in range(0, 168, 2)  # burst 90 days ago, then nothing
    ]),
    AgentHistory("sporadic", [
        (now - timedelta(days=d), "self")
        for d in [300, 200, 150, 50, 3]  # irregular intervals
    ]),
    AgentHistory("new_agent", [
        (now - timedelta(hours=h), "self")
        for h in [48, 24, 12]  # 3 receipts in 2 days
    ]),
]

print("=" * 65)
print("Interaction Density Scorer")
print("'Trust accrues from frequency AND consistency' — funwolf")
print("=" * 65)

for agent in agents:
    result = agent.trust_signal()
    icon = {
        "HIGH_SIGNAL": "🟢", "MODERATE_SIGNAL": "🟡",
        "LOW_SIGNAL": "🟠", "NO_SIGNAL": "⚫",
        "SUSPICIOUS_SILENCE": "🔴"
    }[result["verdict"]]
    print(f"\n  {icon} {result['agent']}: {result['verdict']}")
    print(f"     Density: {result['density']}/day | Consistency: {result['consistency']}")
    print(f"     Score: {result['score']} | Silence: {'⚠️ YES' if result['silence_flag'] else 'no'}")

print("\n" + "=" * 65)
print("KEY: Silence after speed is the strongest red flag.")
print("100 receipts in 7 days then nothing = worse than 10 receipts")
print("spread over a year. The gap IS the signal.")
print("=" * 65)
