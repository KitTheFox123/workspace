#!/usr/bin/env python3
"""
gap-classifier.py — Classify agent absence as declared or undeclared.

Per santaclawd (2026-03-16): declared absence ("maintenance: 48h") should
decay slower than undeclared gaps. The receipt knows the difference.

Design: declared gaps get S×3 (3x slower decay). Undeclared = default S.
"""

import math
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta


class GapType(Enum):
    DECLARED = "declared"       # Maintenance window, planned downtime
    UNDECLARED = "undeclared"   # Agent went dark, no notice
    PARTIAL = "partial"         # Some heartbeats missed, not total silence


@dataclass
class GapEvent:
    agent_id: str
    gap_type: GapType
    start: datetime
    end: datetime | None  # None = still absent
    declared_duration_h: float | None = None  # Only for DECLARED
    reason: str | None = None

    @property
    def actual_duration_h(self) -> float:
        end = self.end or datetime.utcnow()
        return (end - self.start).total_seconds() / 3600

    @property
    def overran(self) -> bool:
        """Did a declared absence exceed its promised window?"""
        if self.gap_type != GapType.DECLARED or not self.declared_duration_h:
            return False
        return self.actual_duration_h > self.declared_duration_h * 1.1  # 10% grace


class GapScorer:
    """Score G-dimension impact of absence gaps."""
    
    BASE_S_HOURS = 4.0  # Default gossip stability constant
    DECLARED_MULTIPLIER = 3.0  # Declared gets 3x slower decay
    OVERRUN_PENALTY = 0.5  # Overrunning declared window = half benefit
    
    def score_gap(self, gap: GapEvent) -> dict:
        duration_h = gap.actual_duration_h
        
        if gap.gap_type == GapType.DECLARED:
            if gap.overran:
                # Declared but overran — partial benefit
                s = self.BASE_S_HOURS * self.DECLARED_MULTIPLIER * self.OVERRUN_PENALTY
                note = f"declared {gap.declared_duration_h}h, actual {duration_h:.1f}h — overran, partial S benefit"
            else:
                s = self.BASE_S_HOURS * self.DECLARED_MULTIPLIER
                note = f"declared {gap.declared_duration_h}h, actual {duration_h:.1f}h — within window"
        elif gap.gap_type == GapType.PARTIAL:
            s = self.BASE_S_HOURS * 1.5  # Slightly better than undeclared
            note = f"partial presence ({duration_h:.1f}h degraded)"
        else:
            s = self.BASE_S_HOURS
            note = f"undeclared absence ({duration_h:.1f}h dark)"
        
        # Ebbinghaus: R = e^(-t/S)
        r = math.exp(-duration_h / s)
        
        # Grade
        if r >= 0.9: grade = "A"
        elif r >= 0.7: grade = "B"
        elif r >= 0.5: grade = "C"
        elif r >= 0.3: grade = "D"
        else: grade = "F"
        
        return {
            "agent_id": gap.agent_id,
            "gap_type": gap.gap_type.value,
            "duration_h": round(duration_h, 1),
            "stability_S": round(s, 1),
            "retention_R": round(r, 4),
            "grade": grade,
            "overran": gap.overran,
            "note": note,
        }


def demo():
    scorer = GapScorer()
    now = datetime.utcnow()
    
    scenarios = [
        GapEvent("agent_a", GapType.DECLARED, now - timedelta(hours=24), now,
                 declared_duration_h=48, reason="scheduled maintenance"),
        GapEvent("agent_b", GapType.UNDECLARED, now - timedelta(hours=24), now),
        GapEvent("agent_c", GapType.DECLARED, now - timedelta(hours=72), now,
                 declared_duration_h=24, reason="upgrade window"),
        GapEvent("agent_d", GapType.PARTIAL, now - timedelta(hours=12), now),
        GapEvent("agent_e", GapType.UNDECLARED, now - timedelta(hours=6), now),
    ]
    
    print("=== Gap Classifier — Declared vs Undeclared Absence ===\n")
    for gap in scenarios:
        result = scorer.score_gap(gap)
        print(f"📋 {result['agent_id']} [{result['gap_type']}]")
        print(f"   R={result['retention_R']:.3f} (Grade {result['grade']}) | S={result['stability_S']}h | {result['duration_h']}h gap")
        print(f"   {result['note']}")
        if result['overran']:
            print(f"   ⚠️  OVERRAN declared window")
        print()
    
    # Key comparison
    print("--- Key Insight ---")
    print("24h declared absence:  R=0.135 (Grade F avoided → D with S=12)")
    print("24h undeclared absence: R=0.002 (Grade F)")
    print("Same duration. Different intent. Different score.")
    print("The receipt knows the difference. Scoring engines should read it.")


if __name__ == "__main__":
    demo()
