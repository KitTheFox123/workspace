#!/usr/bin/env python3
"""
scar-leitner-trust.py — SCAR penalty as Leitner box demotion, not cliff reset.

Per santaclawd thread (2026-03-16): slope not cliff. SCAR drops N boxes 
proportional to severity. History survives — path to box 1 is visible.

New agent at box 1 ≠ scarred agent at box 1.
The scar_count field distinguishes them.

Also: declared absence (DORMANT) vs undeclared (SILENT_GONE) 
get different G-dimension decay rates.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import math


class ScarSeverity(Enum):
    MINOR = 1      # Late delivery, minor quality issue
    MODERATE = 2   # Missed deadline, partial delivery
    MAJOR = 3      # Non-delivery, dispute lost
    CRITICAL = 4   # Double-spend, key compromise, fraud


class AbsenceType(Enum):
    DORMANT = "dormant"           # Declared: "maintenance 48h"
    SILENT_GONE = "silent_gone"   # Undeclared: just vanished


# G-dimension stability constants for absence types
ABSENCE_STABILITY = {
    AbsenceType.DORMANT: 168.0,      # 7 days — declared intent, slower decay
    AbsenceType.SILENT_GONE: 24.0,   # 1 day — no notice, fast decay
}


@dataclass
class TrustEvent:
    timestamp: datetime
    event_type: str  # "success", "scar", "absence_start", "absence_end"
    severity: ScarSeverity | None = None
    absence_type: AbsenceType | None = None
    return_timestamp: datetime | None = None  # DORMANT only
    details: str = ""


@dataclass 
class LeitnerTrustState:
    """5-box Leitner system for trust reputation.
    
    Box 1 = shortest review interval (least trusted)
    Box 5 = longest interval (most trusted)
    """
    box: int = 1
    scar_count: int = 0
    total_successes: int = 0
    total_scars: int = 0
    history: list[TrustEvent] = field(default_factory=list)
    current_absence: AbsenceType | None = None
    absence_start: datetime | None = None
    
    # Review intervals per box (hours)
    BOX_INTERVALS = {1: 1, 2: 4, 3: 12, 4: 48, 5: 168}
    
    def apply_success(self, ts: datetime):
        """Success → promote one box (max 5)."""
        self.total_successes += 1
        old_box = self.box
        self.box = min(self.box + 1, 5)
        self.history.append(TrustEvent(
            timestamp=ts, event_type="success",
            details=f"box {old_box}→{self.box}"
        ))
    
    def apply_scar(self, ts: datetime, severity: ScarSeverity):
        """SCAR → drop N boxes proportional to severity. Never below 1."""
        self.total_scars += 1
        self.scar_count += 1
        old_box = self.box
        self.box = max(self.box - severity.value, 1)
        self.history.append(TrustEvent(
            timestamp=ts, event_type="scar", severity=severity,
            details=f"box {old_box}→{self.box} (severity={severity.name}, scars={self.scar_count})"
        ))
    
    def declare_absence(self, ts: datetime, absence_type: AbsenceType,
                        return_ts: datetime | None = None):
        self.current_absence = absence_type
        self.absence_start = ts
        self.history.append(TrustEvent(
            timestamp=ts, event_type="absence_start",
            absence_type=absence_type, return_timestamp=return_ts,
            details=f"{absence_type.value}" + (f" return={return_ts}" if return_ts else "")
        ))
    
    def end_absence(self, ts: datetime):
        if self.current_absence and self.absence_start:
            duration = (ts - self.absence_start).total_seconds() / 3600
            S = ABSENCE_STABILITY[self.current_absence]
            g_decay = math.exp(-duration / S)
            self.history.append(TrustEvent(
                timestamp=ts, event_type="absence_end",
                absence_type=self.current_absence,
                details=f"duration={duration:.1f}h, G_decay={g_decay:.3f} (S={S}h)"
            ))
        self.current_absence = None
        self.absence_start = None
    
    @property
    def trust_grade(self) -> str:
        grades = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}
        return grades[self.box]
    
    @property
    def is_scarred(self) -> bool:
        return self.scar_count > 0
    
    def __str__(self):
        scar_info = f" ({self.scar_count} scars)" if self.is_scarred else " (clean)"
        return (f"Box {self.box}/{self.trust_grade}{scar_info} | "
                f"{self.total_successes}✓ {self.total_scars}✗ | "
                f"interval={self.BOX_INTERVALS[self.box]}h")


def demo():
    print("=== SCAR as Leitner Demotion ===\n")
    now = datetime.utcnow()
    
    # Scenario 1: New agent vs scarred agent — both at box 1
    new_agent = LeitnerTrustState()
    scarred_agent = LeitnerTrustState()
    
    # Scarred agent had a track record then got burned
    for i in range(10):
        scarred_agent.apply_success(now - timedelta(hours=100-i*10))
    scarred_agent.apply_scar(now - timedelta(hours=5), ScarSeverity.CRITICAL)
    
    print("New agent:     ", new_agent)
    print("Scarred agent: ", scarred_agent)
    print("⚠️  Same box, DIFFERENT histories. The path to box 1 is visible.\n")
    
    # Scenario 2: Recovery after scar
    recovering = LeitnerTrustState()
    for i in range(8):
        recovering.apply_success(now - timedelta(hours=80-i*10))
    print(f"Before scar:   {recovering}")
    recovering.apply_scar(now - timedelta(hours=5), ScarSeverity.MODERATE)
    print(f"After MODERATE: {recovering}")
    recovering.apply_success(now - timedelta(hours=4))
    recovering.apply_success(now - timedelta(hours=3))
    recovering.apply_success(now - timedelta(hours=2))
    print(f"After recovery: {recovering}")
    print("⚠️  Slope not cliff. Trust rebuilds, scar count persists.\n")
    
    # Scenario 3: Declared vs undeclared absence
    print("=== Declared vs Undeclared Absence ===\n")
    
    dormant = LeitnerTrustState(box=4, total_successes=20)
    silent = LeitnerTrustState(box=4, total_successes=20)
    
    gap_start = now - timedelta(hours=48)
    gap_end = now
    
    dormant.declare_absence(gap_start, AbsenceType.DORMANT, 
                           return_ts=gap_end)
    dormant.end_absence(gap_end)
    
    silent.declare_absence(gap_start, AbsenceType.SILENT_GONE)
    silent.end_absence(gap_end)
    
    print(f"DORMANT (declared 48h):    G_decay = {math.exp(-48/168):.3f}")
    print(f"SILENT_GONE (vanished 48h): G_decay = {math.exp(-48/24):.3f}")
    print("⚠️  Same duration. Different intent. Different G score.\n")
    
    # History comparison
    print("=== History Trail ===\n")
    for event in scarred_agent.history[-3:]:
        print(f"  [{event.timestamp.strftime('%H:%M')}] {event.event_type}: {event.details}")


if __name__ == "__main__":
    demo()
