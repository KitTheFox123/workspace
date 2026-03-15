#!/usr/bin/env python3
"""
dormant-state-machine.py — DORMANT vs SILENT_GONE state management.

Per santaclawd (2026-03-15): DORMANT ≠ UX distinction — economic.
- SILENT_GONE: R decays from last_seen. No recovery path.
- DORMANT: announced downtime = slower decay. Recovery possible.
- Punishing planned downtime same as ghosting = agents never go offline = brittle.

Ethereum parallel: inactivity leak ≠ slashing. Planned exit ≠ abandonment.
ETH validators: offline = gradual leak (~50% in 18 days). Slashing = immediate 1+ ETH.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from math import exp, log


class AbsenceState(Enum):
    ACTIVE = "active"
    DORMANT = "dormant"         # Announced downtime with return date
    SILENT_GONE = "silent_gone" # Unannounced absence, decaying
    RETURNED = "returned"       # Back from dormancy


class AbsenceOutcome(Enum):
    ON_TIME_RETURN = "on_time_return"      # Returned before promised date
    LATE_RETURN = "late_return"            # Returned after promised date
    NO_SHOW = "no_show"                    # Missed return date entirely
    GRACEFUL_RETURN = "graceful_return"    # SILENT_GONE but came back


@dataclass
class DormancyRecord:
    agent_id: str
    state: AbsenceState
    announced_at: datetime | None = None
    return_date: datetime | None = None
    actual_return: datetime | None = None
    last_seen: datetime | None = None
    reason: str = ""
    
    # Decay parameters (per santaclawd)
    dormant_half_life_hours: float = 720.0   # 30 days — slow decay
    silent_half_life_hours: float = 168.0    # 7 days — fast decay
    
    def compute_R(self, now: datetime) -> float:
        """Compute trust retention R based on absence state."""
        if self.state == AbsenceState.ACTIVE:
            return 1.0
        elif self.state == AbsenceState.RETURNED:
            return self._return_bonus()
        
        # Determine decay origin and half-life
        if self.state == AbsenceState.DORMANT:
            origin = self.announced_at or now
            S = self.dormant_half_life_hours
        else:  # SILENT_GONE
            origin = self.last_seen or now
            S = self.silent_half_life_hours
        
        hours = (now - origin).total_seconds() / 3600
        R = exp(-hours * log(2) / S)
        
        # Check if DORMANT missed return date → transition
        if self.state == AbsenceState.DORMANT and self.return_date:
            if now > self.return_date:
                # Grace period: 10% of dormancy duration
                dormancy_duration = (self.return_date - self.announced_at).total_seconds() / 3600
                grace_hours = dormancy_duration * 0.1
                overdue_hours = (now - self.return_date).total_seconds() / 3600
                
                if overdue_hours > grace_hours:
                    # Transition to SILENT_GONE decay rate
                    # R continues from DORMANT value but accelerates
                    R_at_deadline = exp(-dormancy_duration * log(2) / S)
                    R_overdue = exp(-overdue_hours * log(2) / self.silent_half_life_hours)
                    R = R_at_deadline * R_overdue
        
        return max(0.0, min(1.0, R))
    
    def _return_bonus(self) -> float:
        """Agents who return get a bonus based on how well they kept their promise."""
        if not self.actual_return or not self.announced_at:
            return 0.8  # Default return bonus
        
        if self.return_date and self.actual_return <= self.return_date:
            return 0.95  # On-time or early
        elif self.return_date:
            overdue = (self.actual_return - self.return_date).total_seconds() / 3600
            # Penalty scales with lateness
            penalty = min(0.3, overdue / 720)  # Max 30% penalty over 30 days late
            return 0.95 - penalty
        return 0.8
    
    def grade(self, R: float) -> str:
        if R >= 0.9: return "A"
        if R >= 0.8: return "B"
        if R >= 0.6: return "C"
        if R >= 0.3: return "D"
        return "F"
    
    def to_dict(self, now: datetime) -> dict:
        R = self.compute_R(now)
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "R": round(R, 4),
            "grade": self.grade(R),
            "return_date": self.return_date.isoformat() if self.return_date else None,
            "reason": self.reason,
        }


def demo():
    now = datetime(2026, 3, 15, 7, 0, 0)
    
    print("=== DORMANT vs SILENT_GONE State Machine ===\n")
    print("ETH parallel: inactivity leak ≠ slashing.")
    print("Planned exit ≠ abandonment.\n")
    
    scenarios = [
        {
            "name": "Planned 7-day maintenance (on schedule)",
            "record": DormancyRecord(
                agent_id="reliable_agent",
                state=AbsenceState.DORMANT,
                announced_at=now - timedelta(days=3),
                return_date=now + timedelta(days=4),
                reason="infrastructure upgrade",
            ),
            "eval_at": now,
        },
        {
            "name": "Planned maintenance, 2 days overdue",
            "record": DormancyRecord(
                agent_id="late_agent",
                state=AbsenceState.DORMANT,
                announced_at=now - timedelta(days=9),
                return_date=now - timedelta(days=2),
                reason="database migration",
            ),
            "eval_at": now,
        },
        {
            "name": "Ghosted 7 days ago (SILENT_GONE)",
            "record": DormancyRecord(
                agent_id="ghost_agent",
                state=AbsenceState.SILENT_GONE,
                last_seen=now - timedelta(days=7),
            ),
            "eval_at": now,
        },
        {
            "name": "Ghosted 7 days, same duration as planned maintenance",
            "record": DormancyRecord(
                agent_id="comparison_agent",
                state=AbsenceState.SILENT_GONE,
                last_seen=now - timedelta(days=7),
            ),
            "eval_at": now,
        },
        {
            "name": "Returned on time from dormancy",
            "record": DormancyRecord(
                agent_id="good_agent",
                state=AbsenceState.RETURNED,
                announced_at=now - timedelta(days=10),
                return_date=now - timedelta(days=3),
                actual_return=now - timedelta(days=3),
                reason="scheduled maintenance",
            ),
            "eval_at": now,
        },
    ]
    
    for s in scenarios:
        rec = s["record"]
        R = rec.compute_R(s["eval_at"])
        d = rec.to_dict(s["eval_at"])
        print(f"📋 {s['name']}")
        print(f"   State: {d['state']} | R: {d['R']:.4f} | Grade: {d['grade']}")
        if d['reason']:
            print(f"   Reason: {d['reason']}")
        print()
    
    # Key comparison
    dormant_3d = DormancyRecord("d", AbsenceState.DORMANT,
                                announced_at=now - timedelta(days=7),
                                return_date=now + timedelta(days=7),
                                reason="planned")
    silent_3d = DormancyRecord("s", AbsenceState.SILENT_GONE,
                               last_seen=now - timedelta(days=7))
    
    R_dormant = dormant_3d.compute_R(now)
    R_silent = silent_3d.compute_R(now)
    
    print("--- Key Comparison: 7 days absent ---")
    print(f"   DORMANT (announced):   R={R_dormant:.4f} ({dormant_3d.grade(R_dormant)})")
    print(f"   SILENT_GONE (ghosted): R={R_silent:.4f} ({silent_3d.grade(R_silent)})")
    print(f"   Ratio: {R_dormant/R_silent:.1f}x retention for announcing downtime")
    print()
    print("--- Design: santaclawd's 3 principles ---")
    print("1. DORMANT requires staked return date")
    print("2. Miss return = auto-transition to SILENT_GONE (not SLASHED)")
    print("3. Ghosting ≠ breach, but promised return that fails = G dimension hit")
    print("   (promised testimony that failed verification)")


if __name__ == "__main__":
    demo()
