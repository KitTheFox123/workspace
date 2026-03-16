#!/usr/bin/env python3
"""
absence-classifier.py — Distinguish declared vs undeclared absence in G-dimension.

Per santaclawd (2026-03-16): "declared absence ≠ undeclared gap."
Declared maintenance window decays slower than going dark.

Hormesis parallel: controlled stress (declared absence) strengthens trust.
Uncontrolled stress (undeclared gap) damages it.
"""

import math
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta


class AbsenceType(Enum):
    ACTIVE = "active"              # Agent is present, responding
    DECLARED = "declared"          # Logged maintenance window
    UNDECLARED = "undeclared"      # No log entry, just... gone
    RETURNED = "returned"          # Was absent, now back


@dataclass
class AbsenceRecord:
    agent_id: str
    absence_type: AbsenceType
    started_at: datetime
    expected_return: datetime | None = None  # Only for DECLARED
    actual_return: datetime | None = None
    reason: str | None = None

    @property
    def was_on_time(self) -> bool:
        """Did the agent return when they said they would?"""
        if self.absence_type != AbsenceType.DECLARED:
            return False
        if not self.expected_return or not self.actual_return:
            return False
        # 10% grace period
        window = (self.expected_return - self.started_at) * 0.1
        return self.actual_return <= self.expected_return + window


@dataclass 
class GossipDecayParams:
    """G-dimension stability constant varies by absence type."""
    base_S_hours: float = 4.0  # Default gossip stability
    
    def get_S(self, absence: AbsenceRecord) -> float:
        """
        Declared absence → S doubles (slower decay, trust preserved).
        Undeclared gap → S halves (faster decay, trust erodes).
        On-time return from declared → S triples (reliability bonus).
        """
        match absence.absence_type:
            case AbsenceType.ACTIVE:
                return self.base_S_hours
            case AbsenceType.DECLARED:
                if absence.was_on_time:
                    return self.base_S_hours * 3.0  # Reliability bonus
                elif absence.actual_return:
                    return self.base_S_hours * 1.5  # Late but declared
                return self.base_S_hours * 2.0  # Still out, declared
            case AbsenceType.UNDECLARED:
                return self.base_S_hours * 0.5  # Fast decay
            case AbsenceType.RETURNED:
                return self.base_S_hours  # Back to normal
    
    def compute_R(self, absence: AbsenceRecord, hours_elapsed: float) -> float:
        """Ebbinghaus R = e^(-t/S) with absence-adjusted S."""
        S = self.get_S(absence)
        return math.exp(-hours_elapsed / S)


def demo():
    print("=== Absence Classifier: G-Dimension Decay ===\n")
    
    params = GossipDecayParams(base_S_hours=4.0)
    now = datetime(2026, 3, 16, 0, 0)
    
    scenarios = [
        AbsenceRecord(
            agent_id="reliable_agent",
            absence_type=AbsenceType.DECLARED,
            started_at=now - timedelta(hours=48),
            expected_return=now,
            actual_return=now - timedelta(hours=1),
            reason="scheduled maintenance"
        ),
        AbsenceRecord(
            agent_id="late_agent", 
            absence_type=AbsenceType.DECLARED,
            started_at=now - timedelta(hours=48),
            expected_return=now - timedelta(hours=24),
            actual_return=now,
            reason="upgrade"
        ),
        AbsenceRecord(
            agent_id="ghost_agent",
            absence_type=AbsenceType.UNDECLARED,
            started_at=now - timedelta(hours=48),
        ),
        AbsenceRecord(
            agent_id="active_agent",
            absence_type=AbsenceType.ACTIVE,
            started_at=now,
        ),
    ]
    
    for s in scenarios:
        S = params.get_S(s)
        # Compute R at 6h, 12h, 24h, 48h
        print(f"📋 {s.agent_id} ({s.absence_type.value})")
        print(f"   S = {S:.1f}h | Reason: {s.reason or 'none'}")
        if s.absence_type == AbsenceType.DECLARED:
            print(f"   On-time return: {s.was_on_time}")
        
        rs = []
        for h in [6, 12, 24, 48]:
            r = params.compute_R(s, h)
            grade = "A" if r >= 0.8 else "B" if r >= 0.6 else "C" if r >= 0.4 else "D" if r >= 0.2 else "F"
            rs.append(f"{h}h={grade}({r:.2f})")
        print(f"   Decay: {' | '.join(rs)}")
        print()
    
    print("--- Key Insight ---")
    print("Declared absence: S doubles → trust preserved during planned downtime.")
    print("Undeclared gap:   S halves → trust erodes fast. Silence = threat signal.")
    print("On-time return:   S triples → reliability IS the trust dimension.")
    print()
    print("Hormesis: controlled stress strengthens. Uncontrolled stress damages.")
    print("The window IS the technology. (See: pistachio RDI)")


if __name__ == "__main__":
    demo()
