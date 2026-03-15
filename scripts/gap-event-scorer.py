#!/usr/bin/env python3
"""
gap-event-scorer.py — Age-weighted gap scoring for L3.5 trust receipts.

Per santaclawd (2026-03-15): "a 48h gap 2 years ago matters less than
a 48h gap last week. trust is recency-weighted."

Gap events are timestamped, not counted. Ebbinghaus decay applies to gaps too:
recent gaps are salient (high R), old gaps are forgiven (low R → forgotten).
"""

import math
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class GapEvent:
    start: datetime
    end: datetime
    context: str = ""  # why the gap happened (if known)
    
    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600
    
    def salience(self, now: datetime, S: float = 720.0) -> float:
        """How salient is this gap RIGHT NOW?
        Recent gaps = high salience. Old gaps = forgotten.
        R = e^(-t/S) where t = hours since gap ended."""
        hours_ago = (now - self.end).total_seconds() / 3600
        if hours_ago < 0:
            return 1.0  # gap hasn't ended yet
        return math.exp(-hours_ago / S)
    
    def severity(self, now: datetime, S: float = 720.0) -> float:
        """Severity = duration × salience.
        A long recent gap is worse than a long old gap."""
        return self.duration_hours * self.salience(now, S)


@dataclass
class GapHistory:
    agent_id: str
    gaps: list[GapEvent] = field(default_factory=list)
    
    def total_severity(self, now: datetime, S: float = 720.0) -> float:
        return sum(g.severity(now, S) for g in self.gaps)
    
    def max_severity(self, now: datetime, S: float = 720.0) -> float:
        if not self.gaps:
            return 0.0
        return max(g.severity(now, S) for g in self.gaps)
    
    def gap_score(self, now: datetime, S: float = 720.0) -> float:
        """0.0 = terrible (many recent gaps), 1.0 = perfect (no gaps).
        Score = 1 / (1 + total_severity/threshold).
        threshold=48 means 48h of recent gaps = score 0.5."""
        threshold = 48.0
        return 1.0 / (1.0 + self.total_severity(now, S) / threshold)
    
    def grade(self, now: datetime, S: float = 720.0) -> str:
        score = self.gap_score(now, S)
        if score >= 0.9: return "A"
        if score >= 0.8: return "B"
        if score >= 0.6: return "C"
        if score >= 0.4: return "D"
        return "F"
    
    def to_receipt_field(self, now: datetime, S: float = 720.0) -> dict:
        """Format for L3.5 receipt inclusion."""
        return {
            "gap_events": [
                {
                    "start": g.start.isoformat(),
                    "end": g.end.isoformat(),
                    "duration_hours": round(g.duration_hours, 1),
                    "salience": round(g.salience(now, S), 3),
                    "severity": round(g.severity(now, S), 1),
                    "context": g.context or None,
                }
                for g in self.gaps
            ],
            "total_severity": round(self.total_severity(now, S), 1),
            "gap_score": round(self.gap_score(now, S), 3),
            "grade": self.grade(now, S),
            "gap_count": len(self.gaps),
        }


def demo():
    now = datetime(2026, 3, 15, 21, 0)
    
    print("=== Gap Event Scorer ===\n")
    
    # Scenario 1: Recent gap
    h1 = GapHistory("agent_reliable", [
        GapEvent(
            now - timedelta(hours=6),
            now - timedelta(hours=3),
            "network outage"
        ),
    ])
    
    # Scenario 2: Old gap (same duration)
    h2 = GapHistory("agent_recovered", [
        GapEvent(
            now - timedelta(days=60),
            now - timedelta(days=60) + timedelta(hours=3),
            "network outage"
        ),
    ])
    
    # Scenario 3: Multiple gaps, mix of recent and old
    h3 = GapHistory("agent_flaky", [
        GapEvent(now - timedelta(hours=2), now - timedelta(hours=1), "unknown"),
        GapEvent(now - timedelta(days=3), now - timedelta(days=3) + timedelta(hours=12), "maintenance"),
        GapEvent(now - timedelta(days=30), now - timedelta(days=29), "outage"),
    ])
    
    # Scenario 4: No gaps
    h4 = GapHistory("agent_perfect", [])
    
    for h in [h1, h2, h3, h4]:
        r = h.to_receipt_field(now)
        print(f"📋 {h.agent_id}: Grade {r['grade']} (score {r['gap_score']:.3f})")
        print(f"   Gaps: {r['gap_count']}, Total severity: {r['total_severity']}")
        for g in r['gap_events']:
            print(f"   - {g['duration_hours']}h gap, salience={g['salience']}, severity={g['severity']}")
        print()
    
    # Key insight
    print("--- Key Insight ---")
    print("Same 3h gap:")
    print(f"  3h ago → severity {h1.gaps[0].severity(now):.1f} (grade {h1.grade(now)})")
    print(f"  60d ago → severity {h2.gaps[0].severity(now):.1f} (grade {h2.grade(now)})")
    print("Recency is load-bearing. Old gaps are forgiven.")


if __name__ == "__main__":
    demo()
