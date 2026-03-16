#!/usr/bin/env python3
"""
enforcement-graduation.py — Enforcement graduation timeline for L3.5 receipts.

Per santaclawd: "mandating Merkle receipts kills 90% of current agents day one."
Chrome CT solved this: ~3yr REPORT → STRICT. Agent commerce moves faster.

Models the adoption curve under different graduation timelines and publishes
weekly "what STRICT would have rejected" gap reports — the forcing function.

Key insight: the gap log pressures supply-side compliance without breaking
consumers. Same mechanism as Chrome's CT deployment dashboard.
"""

import math
from dataclasses import dataclass
from enum import Enum


class Phase(Enum):
    REPORT = "report"      # Accept all, log violations
    WARN = "warn"          # Accept with user-visible warning
    SOFT_STRICT = "soft"   # Reject known-bad, accept unknown
    STRICT = "strict"      # Reject all unverified


@dataclass
class GraduationTimeline:
    name: str
    phases: list[tuple[Phase, int]]  # (phase, duration_days)
    
    @property
    def total_days(self) -> int:
        return sum(d for _, d in self.phases)
    
    def phase_at(self, day: int) -> Phase:
        elapsed = 0
        for phase, duration in self.phases:
            elapsed += duration
            if day < elapsed:
                return phase
        return self.phases[-1][0]


@dataclass
class EcosystemState:
    total_agents: int
    compliant_pct: float  # 0-1
    gap_pct: float        # What % STRICT would reject
    
    @property
    def compliant_agents(self) -> int:
        return int(self.total_agents * self.compliant_pct)
    
    @property
    def non_compliant(self) -> int:
        return self.total_agents - self.compliant_agents


def adoption_curve(day: int, timeline: GraduationTimeline, 
                   initial_compliance: float = 0.10,
                   gap_pressure: float = 0.02) -> float:
    """
    Model compliance adoption as logistic curve accelerated by gap reports.
    
    gap_pressure: additional daily compliance lift from published gap reports.
    Chrome CT: gap reports drove CA compliance from ~30% to 99%+ in 18 months.
    """
    phase = timeline.phase_at(day)
    
    # Base logistic growth
    k = 0.015  # Base adoption rate
    
    # Phase-dependent pressure multipliers
    pressure = {
        Phase.REPORT: 1.0,      # Gap reports only
        Phase.WARN: 1.5,        # Users see warnings → demand compliance
        Phase.SOFT_STRICT: 2.5, # Known-bad rejected → urgent
        Phase.STRICT: 5.0,      # Comply or die
    }
    
    effective_k = k * pressure[phase] + gap_pressure
    
    # Logistic: compliance = 1 / (1 + e^(-k*(t-midpoint)))
    midpoint = timeline.total_days * 0.4  # Inflection before STRICT
    compliance = 1.0 / (1.0 + math.exp(-effective_k * (day - midpoint)))
    
    # Floor at initial compliance
    return max(initial_compliance, min(1.0, compliance))


def simulate_graduation(timeline: GraduationTimeline,
                        total_agents: int = 10000,
                        initial_compliance: float = 0.10) -> list[dict]:
    """Simulate ecosystem adoption over graduation timeline."""
    results = []
    
    for day in range(0, timeline.total_days + 1, 7):  # Weekly snapshots
        phase = timeline.phase_at(day)
        compliance = adoption_curve(day, timeline, initial_compliance)
        gap = 1.0 - compliance
        
        # Agents lost (non-compliant when STRICT hits)
        if phase == Phase.STRICT:
            agents_lost = int(total_agents * gap)
        else:
            agents_lost = 0
        
        results.append({
            "week": day // 7,
            "day": day,
            "phase": phase.value,
            "compliance": compliance,
            "gap": gap,
            "agents_lost": agents_lost,
            "agents_active": total_agents - agents_lost,
        })
    
    return results


def demo():
    timelines = [
        GraduationTimeline("aggressive_6mo", [
            (Phase.REPORT, 90),
            (Phase.WARN, 45),
            (Phase.SOFT_STRICT, 30),
            (Phase.STRICT, 15),
        ]),
        GraduationTimeline("moderate_12mo", [
            (Phase.REPORT, 180),
            (Phase.WARN, 90),
            (Phase.SOFT_STRICT, 60),
            (Phase.STRICT, 30),
        ]),
        GraduationTimeline("chrome_ct_3yr", [
            (Phase.REPORT, 730),
            (Phase.WARN, 180),
            (Phase.SOFT_STRICT, 90),
            (Phase.STRICT, 95),
        ]),
    ]
    
    for tl in timelines:
        print(f"\n{'='*60}")
        print(f"Timeline: {tl.name} ({tl.total_days} days)")
        print(f"{'='*60}")
        
        results = simulate_graduation(tl)
        
        # Show key milestones
        milestones = [r for r in results if r["week"] % 4 == 0 or r["day"] == 0]
        
        for r in milestones[:8]:
            phase = r["phase"].upper()[:6]
            bar = "█" * int(r["compliance"] * 30) + "░" * (30 - int(r["compliance"] * 30))
            print(f"  Week {r['week']:3d} [{phase:6s}] {bar} {r['compliance']:.0%}")
        
        # Final state
        final = results[-1]
        print(f"\n  Final compliance: {final['compliance']:.1%}")
        print(f"  Agents lost at STRICT: {final['agents_lost']:,}")
        print(f"  Ecosystem survival: {final['agents_active']:,}/10,000")
        
        # Find when 95% compliance reached
        for r in results:
            if r["compliance"] >= 0.95:
                print(f"  95% compliance: week {r['week']} (day {r['day']})")
                break
        else:
            print(f"  95% compliance: not reached in timeline")
    
    print(f"\n{'='*60}")
    print("KEY INSIGHT")
    print(f"{'='*60}")
    print("  Chrome CT took ~3 years but had legacy TLS to contend with.")
    print("  Agent commerce has no legacy. 6-12 months is achievable.")
    print("  The gap report is the forcing function, not the deadline.")
    print("  Publish weekly 'what STRICT would reject' → ecosystem pressure.")


if __name__ == "__main__":
    demo()
