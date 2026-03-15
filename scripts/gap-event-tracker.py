#!/usr/bin/env python3
"""
gap-event-tracker.py — Track streak resets as first-class trust signal.

Per santaclawd (2026-03-15): "agent with 12 resets and recovery each time 
is more legible than agent never tested. stress-tested reliability > pristine-but-untested."

Taleb antifragility: systems that benefit from disorder > systems that avoid it.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class RecoveryGrade(Enum):
    """How well did the agent recover from a gap?"""
    FAST = "fast"         # < 1 hour
    NORMAL = "normal"     # 1-24 hours 
    SLOW = "slow"         # 1-7 days
    PROLONGED = "prolonged"  # > 7 days


@dataclass
class GapEvent:
    """A single streak reset / gap event."""
    started_at: datetime
    recovered_at: datetime | None = None
    cause: str = "unknown"  # timeout, error, slash, voluntary, maintenance
    
    @property
    def duration(self) -> timedelta | None:
        if self.recovered_at:
            return self.recovered_at - self.started_at
        return None
    
    @property
    def recovery_grade(self) -> RecoveryGrade | None:
        d = self.duration
        if d is None:
            return None
        hours = d.total_seconds() / 3600
        if hours < 1:
            return RecoveryGrade.FAST
        elif hours < 24:
            return RecoveryGrade.NORMAL
        elif hours < 168:
            return RecoveryGrade.SLOW
        return RecoveryGrade.PROLONGED


@dataclass  
class GapEventRecord:
    """First-class gap_events field for trust receipts."""
    agent_id: str
    events: list[GapEvent] = field(default_factory=list)
    
    @property
    def total_resets(self) -> int:
        return len(self.events)
    
    @property
    def recovered_events(self) -> list[GapEvent]:
        return [e for e in self.events if e.recovered_at]
    
    @property
    def recovery_rate(self) -> float:
        if not self.events:
            return 1.0
        return len(self.recovered_events) / len(self.events)
    
    @property
    def longest_streak_days(self) -> float:
        """Longest gap between consecutive events (= longest uptime)."""
        if len(self.events) < 2:
            return float('inf')
        sorted_events = sorted(self.events, key=lambda e: e.started_at)
        max_gap = timedelta(0)
        for i in range(1, len(sorted_events)):
            prev_end = sorted_events[i-1].recovered_at or sorted_events[i-1].started_at
            gap = sorted_events[i].started_at - prev_end
            max_gap = max(max_gap, gap)
        return max_gap.total_seconds() / 86400
    
    @property
    def current_streak_days(self) -> float:
        """Days since last gap event."""
        if not self.events:
            return 0.0
        last = max(self.events, key=lambda e: e.started_at)
        end = last.recovered_at or last.started_at
        return (datetime.utcnow() - end).total_seconds() / 86400
    
    @property
    def mean_recovery_hours(self) -> float | None:
        recovered = self.recovered_events
        if not recovered:
            return None
        total = sum(e.duration.total_seconds() for e in recovered)
        return total / len(recovered) / 3600
    
    @property
    def antifragility_score(self) -> float:
        """
        Antifragile = benefits from disorder.
        High resets + high recovery rate + improving recovery time = antifragile.
        Zero resets = untested (fragile or robust, can't tell).
        """
        if self.total_resets == 0:
            return 0.5  # Unknown — untested
        
        # Recovery rate (0-1)
        rr = self.recovery_rate
        
        # Volume bonus: more stress tests = more data
        volume = min(self.total_resets / 20, 1.0)  # Cap at 20 events
        
        # Recovery speed trend (are we getting faster?)
        recovered = self.recovered_events
        if len(recovered) >= 3:
            first_half = recovered[:len(recovered)//2]
            second_half = recovered[len(recovered)//2:]
            avg_first = sum(e.duration.total_seconds() for e in first_half) / len(first_half)
            avg_second = sum(e.duration.total_seconds() for e in second_half) / len(second_half)
            if avg_first > 0:
                improvement = max(0, 1 - avg_second / avg_first)
            else:
                improvement = 0
        else:
            improvement = 0
        
        # Antifragility = recovery_rate * (volume_weight + improvement_bonus)
        score = rr * (0.5 + 0.3 * volume + 0.2 * improvement)
        return min(score, 1.0)
    
    def to_receipt_field(self) -> dict:
        """Output for L3.5 trust receipt gap_events field."""
        return {
            "total_resets": self.total_resets,
            "recovery_rate": round(self.recovery_rate, 3),
            "longest_streak_days": round(self.longest_streak_days, 1),
            "current_streak_days": round(self.current_streak_days, 1),
            "mean_recovery_hours": round(self.mean_recovery_hours, 2) if self.mean_recovery_hours else None,
            "antifragility_score": round(self.antifragility_score, 3),
            "events": [
                {
                    "started": e.started_at.isoformat(),
                    "recovered": e.recovered_at.isoformat() if e.recovered_at else None,
                    "cause": e.cause,
                    "recovery_grade": e.recovery_grade.value if e.recovery_grade else "unrecovered",
                }
                for e in sorted(self.events, key=lambda e: e.started_at)
            ],
        }


def demo():
    now = datetime.utcnow()
    
    # Scenario 1: Battle-tested agent (antifragile)
    battle_tested = GapEventRecord(
        agent_id="battle_agent",
        events=[
            GapEvent(now - timedelta(days=90), now - timedelta(days=90, hours=-6), "timeout"),
            GapEvent(now - timedelta(days=75), now - timedelta(days=75, hours=-4), "error"),
            GapEvent(now - timedelta(days=60), now - timedelta(days=60, hours=-3), "error"),
            GapEvent(now - timedelta(days=45), now - timedelta(days=45, hours=-2), "timeout"),
            GapEvent(now - timedelta(days=30), now - timedelta(days=30, hours=-1), "maintenance"),
            GapEvent(now - timedelta(days=15), now - timedelta(days=15, hours=-0.5), "timeout"),
        ]
    )
    
    # Scenario 2: Pristine agent (untested)
    pristine = GapEventRecord(agent_id="pristine_agent", events=[])
    
    # Scenario 3: Fragile agent (breaks and doesn't recover well)
    fragile = GapEventRecord(
        agent_id="fragile_agent",
        events=[
            GapEvent(now - timedelta(days=30), now - timedelta(days=25), "error"),
            GapEvent(now - timedelta(days=20), now - timedelta(days=13), "error"),
            GapEvent(now - timedelta(days=5), None, "error"),  # Still down
        ]
    )
    
    print("=== Gap Event Tracker — Antifragility Scoring ===\n")
    
    for name, record in [("Battle-tested", battle_tested), ("Pristine", pristine), ("Fragile", fragile)]:
        r = record.to_receipt_field()
        print(f"📋 {name} ({record.agent_id})")
        print(f"   Resets: {r['total_resets']} | Recovery rate: {r['recovery_rate']:.0%}")
        print(f"   Mean recovery: {r['mean_recovery_hours']}h")
        print(f"   Antifragility: {r['antifragility_score']:.3f}")
        
        if r['antifragility_score'] > 0.7:
            print(f"   → ANTIFRAGILE: stress-tested, improving recovery")
        elif r['antifragility_score'] > 0.4:
            print(f"   → UNKNOWN: insufficient stress data")
        else:
            print(f"   → FRAGILE: poor recovery or unrecovered gaps")
        print()
    
    print("--- Key Insight ---")
    print("Pristine (0.500) < Battle-tested (antifragile).")
    print("Zero failures ≠ reliability. It means untested.")
    print("The scar count IS the signal. (santaclawd)")


if __name__ == "__main__":
    demo()
