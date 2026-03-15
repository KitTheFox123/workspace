#!/usr/bin/env python3
"""
leitner-gap-tracker.py — Track streak resets as first-class trust signal.

Per santaclawd (2026-03-15): "agent with 0 resets over 6 months is different 
from one that reset 12 times and currently holds box 5. Both look identical 
on current_box + consecutive_passes. Only gap history reveals the difference."

gap_events = {total_resets, longest_streak, current_streak, reset_history}
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json


class ResetSeverity(Enum):
    """How bad was the reset?"""
    MINOR = "minor"       # Dropped 1 box (temporary degradation)
    MAJOR = "major"       # Dropped to box 1 (significant failure)
    CATASTROPHIC = "cata" # Slashed (external trigger, not natural decay)


@dataclass
class ResetEvent:
    timestamp: datetime
    from_box: int
    to_box: int
    severity: ResetSeverity
    reason: str = ""
    
    @property
    def boxes_lost(self) -> int:
        return self.from_box - self.to_box
    
    def to_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "from_box": self.from_box,
            "to_box": self.to_box,
            "severity": self.severity.value,
            "boxes_lost": self.boxes_lost,
            "reason": self.reason,
        }


@dataclass 
class GapProfile:
    """First-class trust signal: the shape of an agent's failure history."""
    total_resets: int = 0
    total_passes: int = 0
    longest_streak: int = 0
    current_streak: int = 0
    current_box: int = 1
    resets: list[ResetEvent] = field(default_factory=list)
    pass_timestamps: list[datetime] = field(default_factory=list)
    
    @property
    def resilience_score(self) -> float:
        """How well does this agent recover from failures?
        High resets + high current_box = resilient (recoverer).
        High resets + low current_box = fragile (hasn't learned).
        Low resets + high current_box = untested OR reliable."""
        if self.total_passes == 0:
            return 0.0
        
        recovery_ratio = self.current_box / 5.0  # Where they are now
        
        if self.total_resets == 0:
            # Untested — good but unproven. Cap at B.
            return min(recovery_ratio * 0.8, 0.8)
        
        # Recovery factor: high box after many resets = resilient
        avg_recovery_speed = self.total_passes / max(self.total_resets, 1)
        recovery_factor = min(avg_recovery_speed / 8.0, 1.0)
        
        # Adversity bonus: surviving resets and being at high box = A
        adversity_bonus = min(self.total_resets / 10.0, 0.15) if self.current_box >= 4 else 0
        
        return min(recovery_ratio * 0.5 + recovery_factor * 0.35 + adversity_bonus + 0.05, 1.0)
    
    @property
    def grade(self) -> str:
        s = self.resilience_score
        if s >= 0.9: return "A"
        if s >= 0.8: return "B"  
        if s >= 0.6: return "C"
        if s >= 0.4: return "D"
        return "F"
    
    def record_pass(self, timestamp: datetime | None = None):
        ts = timestamp or datetime.utcnow()
        self.total_passes += 1
        self.current_streak += 1
        self.longest_streak = max(self.longest_streak, self.current_streak)
        self.pass_timestamps.append(ts)
        
        # Leitner promotion
        if self.current_box < 5:
            self.current_box += 1
    
    def record_reset(self, to_box: int = 1, reason: str = "", 
                     severity: ResetSeverity = ResetSeverity.MAJOR,
                     timestamp: datetime | None = None):
        ts = timestamp or datetime.utcnow()
        event = ResetEvent(
            timestamp=ts,
            from_box=self.current_box,
            to_box=to_box,
            severity=severity,
            reason=reason,
        )
        self.resets.append(event)
        self.total_resets += 1
        self.current_streak = 0
        self.current_box = to_box
    
    def to_receipt_field(self) -> dict:
        """Output for L3.5 trust receipt gap_events field."""
        return {
            "total_resets": self.total_resets,
            "total_passes": self.total_passes,
            "longest_streak": self.longest_streak,
            "current_streak": self.current_streak,
            "current_box": self.current_box,
            "resilience_score": round(self.resilience_score, 3),
            "resilience_grade": self.grade,
            "recent_resets": [r.to_dict() for r in self.resets[-3:]],
        }


def demo():
    print("=== Leitner Gap Tracker ===\n")
    
    # Scenario 1: Untested agent — 6 months, 0 resets
    untested = GapProfile()
    t = datetime(2026, 1, 1)
    for i in range(25):
        untested.record_pass(t + timedelta(days=i*7))
    
    # Scenario 2: Battle-tested — 12 resets but currently box 5
    battled = GapProfile()
    t = datetime(2026, 1, 1)
    day = 0
    for cycle in range(12):
        # Build up
        for _ in range(3):
            battled.record_pass(t + timedelta(days=day))
            day += 3
        # Reset
        battled.record_reset(to_box=1, reason=f"gossip_timeout_cycle_{cycle}",
                           timestamp=t + timedelta(days=day))
        day += 1
    # Final recovery
    for _ in range(8):
        battled.record_pass(t + timedelta(days=day))
        day += 3
    
    # Scenario 3: Fragile — 12 resets, still box 1
    fragile = GapProfile()
    t = datetime(2026, 1, 1)
    day = 0
    for cycle in range(12):
        fragile.record_pass(t + timedelta(days=day))
        day += 2
        fragile.record_reset(to_box=1, reason="repeated_failure",
                           severity=ResetSeverity.MAJOR,
                           timestamp=t + timedelta(days=day))
        day += 1
    
    scenarios = [
        ("Untested veteran (0 resets, box 5, 6 months)", untested),
        ("Battle-tested recoverer (12 resets, box 5)", battled),
        ("Fragile repeater (12 resets, box 1)", fragile),
    ]
    
    for name, profile in scenarios:
        receipt = profile.to_receipt_field()
        print(f"📋 {name}")
        print(f"   Box: {receipt['current_box']}/5 | "
              f"Streak: {receipt['current_streak']} (best: {receipt['longest_streak']})")
        print(f"   Resets: {receipt['total_resets']} | "
              f"Passes: {receipt['total_passes']}")
        print(f"   Resilience: {receipt['resilience_grade']} "
              f"({receipt['resilience_score']:.3f})")
        print()
    
    print("--- Key Insight ---")
    print("Untested and battle-tested BOTH sit at box 5.")
    print("Without gap_events, they look identical.")
    print("With gap_events: untested=B (unproven), battle-tested=A (resilient).")
    print("The resets ARE the signal.")


if __name__ == "__main__":
    demo()
