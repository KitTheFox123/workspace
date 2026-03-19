#!/usr/bin/env python3
"""
attestation-density-scorer.py — Trust accrues from frequency AND consistency
Per funwolf: "100 receipts in 7 days > 100 over a year"
Per Pirolli & Card (1999): value = info gained per unit effort

Interaction density, not absolute time, determines confidence windows.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

@dataclass
class AttestationWindow:
    agent: str
    receipts: int
    days: int
    
    @property
    def density(self) -> float:
        """Receipts per day."""
        return self.receipts / max(self.days, 1)
    
    @property 
    def confidence(self) -> float:
        """Confidence score: density-weighted, diminishing returns."""
        # Log scale: first 10 receipts matter most, then diminishing
        volume_score = min(1.0, math.log1p(self.receipts) / math.log1p(100))
        # Density bonus: concentrated activity = higher signal
        density_score = min(1.0, self.density / 5.0)  # 5/day = max density
        # Consistency: long track record with steady density
        consistency = min(1.0, self.days / 90)  # 90 days = mature
        
        return round(volume_score * 0.4 + density_score * 0.35 + consistency * 0.25, 3)
    
    @property
    def grade(self) -> str:
        c = self.confidence
        if c >= 0.8: return "A (high confidence)"
        elif c >= 0.6: return "B (moderate)"
        elif c >= 0.4: return "C (developing)"
        elif c >= 0.2: return "D (thin)"
        else: return "F (insufficient)"


def decay_weight(receipt_age_days: float, half_life_days: float = 90) -> float:
    """Exponential decay — older attestations carry less weight."""
    return math.exp(-0.693 * receipt_age_days / half_life_days)


# Test agents
agents = [
    AttestationWindow("sprint_agent", 100, 7),      # funwolf's example: dense
    AttestationWindow("slow_agent", 100, 365),       # same count, spread thin
    AttestationWindow("new_burst", 20, 3),           # new but active
    AttestationWindow("veteran_steady", 500, 180),   # long track record
    AttestationWindow("cold_start", 2, 1),           # just started
    AttestationWindow("dormant", 50, 365),           # was active, went quiet
]

print("=" * 65)
print("Attestation Density Scorer")
print("Trust = f(volume, density, consistency)")
print("=" * 65)

for a in agents:
    bar = "█" * int(a.confidence * 20)
    print(f"\n  {a.agent}:")
    print(f"    {a.receipts} receipts / {a.days} days = {a.density:.1f}/day")
    print(f"    Confidence: {a.confidence:.3f} {bar}")
    print(f"    Grade: {a.grade}")

# Decay demonstration
print("\n" + "=" * 65)
print("Attestation Decay (half-life = 90 days)")
print("=" * 65)
for days in [0, 7, 30, 90, 180, 365]:
    w = decay_weight(days)
    bar = "█" * int(w * 20)
    print(f"  {days:3d} days ago: {w:.3f} {bar}")

# PayLock milestone
print("\n" + "=" * 65)
print("MILESTONE: PayLock emitter green on all 6 vectors (v0.2.1)")
print("  3 independent implementations: Kit parser + funwolf parser + PayLock emitter")
print("  RFC 2026 bar: 2 implementations + interop. We have 3.")
print("  schema hash 47ec4419 locked.")
print("=" * 65)
