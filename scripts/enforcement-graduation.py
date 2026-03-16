#!/usr/bin/env python3
"""
enforcement-graduation.py — CT-style enforcement rollout scheduler.

Chrome CT timeline: announced 2016, REPORT 2017, mandatory April 2018.
Key: the gap log during REPORT showed what would break, creating compliance pressure.

HTTPS: specs existed 20 years. Adoption at 40%. Chrome labeled HTTP "Not Secure" → 95% in 3 years.
Lesson: specs are necessary but not sufficient. Client enforcement is the forcing function.

This tool models the graduation from REPORT → STRICT for L3.5 receipt verification,
using gap ratio as the trigger (not calendar dates).

Phases:
1. ANNOUNCE — Publish intent + deadline. Gap measurement begins.
2. REPORT — Accept all, log violations. Gap ratio visible to all.
3. WARN — Accept with degraded trust score. Agents see the penalty.
4. STRICT — Reject unverified. Adoption or exclusion.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Phase(Enum):
    ANNOUNCE = "announce"
    REPORT = "report"
    WARN = "warn"
    STRICT = "strict"


@dataclass
class GapSnapshot:
    """Point-in-time measurement of enforcement gap."""
    day: int
    total_receipts: int
    would_reject: int
    
    @property
    def gap_ratio(self) -> float:
        if self.total_receipts == 0:
            return 1.0
        return self.would_reject / self.total_receipts


@dataclass 
class PhaseTransition:
    from_phase: Phase
    to_phase: Phase
    trigger_gap: float  # Gap ratio that triggers transition
    min_days: int       # Minimum days in current phase
    description: str


class EnforcementGraduator:
    """Models enforcement graduation with gap-based triggers."""
    
    # Default transitions (inspired by Chrome CT)
    DEFAULT_TRANSITIONS = [
        PhaseTransition(Phase.ANNOUNCE, Phase.REPORT, 1.0, 30,
                       "Announce intent, begin measurement"),
        PhaseTransition(Phase.REPORT, Phase.WARN, 0.20, 90,
                       "When <20% would be rejected, start warning"),
        PhaseTransition(Phase.WARN, Phase.STRICT, 0.05, 60,
                       "When <5% would be rejected, go strict"),
    ]
    
    def __init__(self, transitions: Optional[list[PhaseTransition]] = None):
        self.transitions = transitions or self.DEFAULT_TRANSITIONS
        self.current_phase = Phase.ANNOUNCE
        self.days_in_phase = 0
        self.history: list[GapSnapshot] = []
    
    def record_gap(self, total: int, would_reject: int) -> None:
        """Record daily gap measurement."""
        day = len(self.history)
        self.history.append(GapSnapshot(day, total, would_reject))
        self.days_in_phase += 1
    
    def should_graduate(self) -> Optional[PhaseTransition]:
        """Check if conditions met for next phase."""
        if not self.history:
            return None
        
        current_gap = self.history[-1].gap_ratio
        
        for t in self.transitions:
            if t.from_phase == self.current_phase:
                if (self.days_in_phase >= t.min_days and 
                    current_gap <= t.trigger_gap):
                    return t
        return None
    
    def graduate(self) -> Optional[PhaseTransition]:
        """Attempt graduation. Returns transition if successful."""
        t = self.should_graduate()
        if t:
            self.current_phase = t.to_phase
            self.days_in_phase = 0
            return t
        return None
    
    def time_to_strict(self) -> dict:
        """Estimate time to STRICT based on gap trend."""
        if len(self.history) < 7:
            return {"estimate": "insufficient data", "days": None}
        
        # Linear regression on gap ratio
        recent = self.history[-7:]
        xs = [s.day for s in recent]
        ys = [s.gap_ratio for s in recent]
        n = len(xs)
        
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        den = sum((x - x_mean) ** 2 for x in xs)
        
        if den == 0 or num >= 0:  # No improvement or getting worse
            return {"estimate": "not converging", "days": None, "trend": "flat/worsening"}
        
        slope = num / den
        current_gap = ys[-1]
        target = 0.05
        
        if current_gap <= target:
            return {"estimate": "ready now", "days": 0}
        
        days_to_target = int((target - current_gap) / slope)
        # Add minimum phase durations
        remaining_min = sum(
            t.min_days for t in self.transitions 
            if self._phase_order(t.from_phase) >= self._phase_order(self.current_phase)
        )
        
        total = max(days_to_target, remaining_min)
        return {
            "estimate": f"~{total} days",
            "days": total,
            "trend": f"{slope:.4f}/day",
            "current_gap": f"{current_gap:.1%}",
        }
    
    def _phase_order(self, phase: Phase) -> int:
        return list(Phase).index(phase)


def simulate_adoption():
    """Simulate adoption curve with S-shaped compliance."""
    grad = EnforcementGraduator()
    
    print("=" * 70)
    print("L3.5 Enforcement Graduation Simulation")
    print("(Modeled on Chrome CT: ANNOUNCE → REPORT → WARN → STRICT)")
    print("=" * 70)
    
    # Simulate 365 days of adoption
    # S-curve: initially slow, then rapid, then plateau
    total_daily = 1000
    
    for day in range(365):
        # S-curve adoption: logistic function
        # Starts at 10% compliance, reaches 98% by day 300
        adoption = 0.10 + 0.88 / (1 + math.exp(-0.03 * (day - 150)))
        would_reject = int(total_daily * (1 - adoption))
        
        grad.record_gap(total_daily, would_reject)
        
        # Try to graduate
        transition = grad.graduate()
        if transition:
            gap = grad.history[-1].gap_ratio
            print(f"\n🎓 Day {day}: {transition.from_phase.value} → {transition.to_phase.value}")
            print(f"   Gap: {gap:.1%} (trigger: ≤{transition.trigger_gap:.0%})")
            print(f"   {transition.description}")
        
        # Print weekly snapshots
        if day % 30 == 0:
            snap = grad.history[-1]
            est = grad.time_to_strict()
            print(f"\n📊 Day {day:3d} | Phase: {grad.current_phase.value:8s} | "
                  f"Gap: {snap.gap_ratio:.1%} | "
                  f"Compliant: {total_daily - snap.would_reject}/{total_daily} | "
                  f"ETA to STRICT: {est.get('estimate', '?')}")
    
    # Final report
    print(f"\n{'=' * 70}")
    print("Final State")
    print(f"{'=' * 70}")
    print(f"Phase: {grad.current_phase.value}")
    print(f"Days simulated: {len(grad.history)}")
    print(f"Final gap: {grad.history[-1].gap_ratio:.1%}")
    print(f"Days in current phase: {grad.days_in_phase}")
    
    # Phase timeline
    print(f"\n📅 Phase Timeline:")
    phase_starts = {}
    current = Phase.ANNOUNCE
    phase_starts[current] = 0
    for i, snap in enumerate(grad.history):
        # Detect phase changes by re-running logic
        pass  # Already logged above
    
    # Key insight
    print(f"\n💡 Key Insight:")
    print(f"   Chrome CT: ~2 years from announce to enforce")
    print(f"   HTTPS 'Not Secure': ~3 years from 40% to 95%")
    print(f"   L3.5 simulation: reached STRICT at gap <5%")
    print(f"   The forcing function is the CLIENT, not the SPEC")


if __name__ == "__main__":
    simulate_adoption()
