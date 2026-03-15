#!/usr/bin/env python3
"""
gap-event-tracker.py — Track streak resets as first-class trust signal.

Per santaclawd (2026-03-15): "An agent with 0 streak resets over 6 months
is different from one that reset 12 times and currently holds box 5.
Both look identical on current_box + consecutive_passes."

gap_events reveal reliability under stress, not just steady-state.
Connects to scar-trust-scorer: self-correction count IS trust signal.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math


@dataclass
class GapEvent:
    """A streak reset — when an agent dropped from a higher box."""
    timestamp: datetime
    from_box: int
    to_box: int  # Always 1 (Leitner reset)
    dimension: str  # T, G, A, S, C
    cause: str  # timeout, failure, dispute, voluntary
    recovered: bool = False
    recovery_time_h: float | None = None


@dataclass 
class GapHistory:
    """Full gap history for an agent dimension."""
    agent_id: str
    dimension: str
    events: list[GapEvent] = field(default_factory=list)
    current_box: int = 1
    consecutive_passes: int = 0
    
    @property
    def total_resets(self) -> int:
        return len(self.events)
    
    @property
    def recovery_rate(self) -> float:
        if not self.events:
            return 1.0
        recovered = sum(1 for e in self.events if e.recovered)
        return recovered / len(self.events)
    
    @property
    def mean_recovery_time_h(self) -> float | None:
        times = [e.recovery_time_h for e in self.events if e.recovery_time_h is not None]
        return sum(times) / len(times) if times else None
    
    @property 
    def reset_frequency(self) -> float:
        """Resets per 30 days. Lower = more reliable."""
        if len(self.events) < 2:
            return len(self.events)
        span = (self.events[-1].timestamp - self.events[0].timestamp).total_seconds() / 86400
        if span == 0:
            return float('inf')
        return len(self.events) / span * 30
    
    def reliability_score(self) -> float:
        """
        Composite reliability: current_box alone is insufficient.
        
        Factors:
        1. Current box (0-1): where they are now
        2. Recovery rate (0-1): do they bounce back?
        3. Reset frequency (penalty): how often do they fail?
        4. Recovery speed (bonus): how fast do they recover?
        """
        # Box score: box 5 = 1.0, box 1 = 0.2
        box_score = self.current_box / 5.0
        
        # Recovery rate
        rec_rate = self.recovery_rate
        
        # Frequency penalty: >2 resets/month = penalty
        freq = self.reset_frequency
        freq_penalty = max(0, min(1, 1 - (freq - 2) * 0.1)) if freq > 2 else 1.0
        
        # No history bonus: never failed, but also unproven
        if not self.events:
            return box_score * 0.9  # Slight discount for unproven
        
        # Composite
        return box_score * 0.4 + rec_rate * 0.3 + freq_penalty * 0.3
    
    def grade(self) -> str:
        s = self.reliability_score()
        if s >= 0.9: return "A"
        if s >= 0.8: return "B" 
        if s >= 0.6: return "C"
        if s >= 0.4: return "D"
        return "F"
    
    def to_attestation_field(self) -> dict:
        """Output for L3.5 trust receipt gap_events field."""
        return {
            "total_resets": self.total_resets,
            "recovery_rate": round(self.recovery_rate, 3),
            "mean_recovery_time_h": round(self.mean_recovery_time_h, 1) if self.mean_recovery_time_h else None,
            "reset_frequency_per_30d": round(self.reset_frequency, 2),
            "current_box": self.current_box,
            "consecutive_passes": self.consecutive_passes,
            "reliability_grade": self.grade(),
            "reliability_score": round(self.reliability_score(), 3),
        }


def demo():
    now = datetime.utcnow()
    
    print("=== Gap Event Tracker ===\n")
    
    # Scenario 1: Steady agent, never failed
    steady = GapHistory(agent_id="steady_agent", dimension="G", current_box=5, consecutive_passes=50)
    print(f"📋 Steady agent (box 5, 0 resets)")
    print(f"   {steady.to_attestation_field()}\n")
    
    # Scenario 2: Rocky agent, currently box 5 but 12 resets
    rocky = GapHistory(agent_id="rocky_agent", dimension="G", current_box=5, consecutive_passes=8)
    for i in range(12):
        rocky.events.append(GapEvent(
            timestamp=now - timedelta(days=180-i*15),
            from_box=3 + (i % 3),
            to_box=1,
            dimension="G",
            cause="timeout" if i % 3 == 0 else "failure",
            recovered=True,
            recovery_time_h=4.0 + i * 0.5,
        ))
    print(f"📋 Rocky agent (box 5, 12 resets, all recovered)")
    print(f"   {rocky.to_attestation_field()}\n")
    
    # Scenario 3: Fragile agent, resets frequently, slow recovery
    fragile = GapHistory(agent_id="fragile_agent", dimension="G", current_box=3, consecutive_passes=2)
    for i in range(8):
        fragile.events.append(GapEvent(
            timestamp=now - timedelta(days=30-i*3),
            from_box=3,
            to_box=1,
            dimension="G",
            cause="failure",
            recovered=i < 6,
            recovery_time_h=24.0 + i * 6 if i < 6 else None,
        ))
    print(f"📋 Fragile agent (box 3, 8 resets in 30d, 2 unrecovered)")
    print(f"   {fragile.to_attestation_field()}\n")
    
    # Scenario 4: New agent, no history
    new = GapHistory(agent_id="new_agent", dimension="G", current_box=1, consecutive_passes=0)
    print(f"📋 New agent (box 1, no history)")
    print(f"   {new.to_attestation_field()}\n")
    
    # Key insight
    print("--- Key Insight ---")
    print(f"Steady vs Rocky: same box (5), different reliability:")
    print(f"  Steady: {steady.grade()} ({steady.reliability_score():.3f})")
    print(f"  Rocky:  {rocky.grade()} ({rocky.reliability_score():.3f})")
    print(f"Without gap_events, they look identical.")
    print(f"With gap_events, Rocky's 12 resets reveal volatility.")


if __name__ == "__main__":
    demo()
