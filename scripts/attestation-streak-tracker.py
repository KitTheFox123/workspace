#!/usr/bin/env python3
"""
attestation-streak-tracker.py — Compounding re-attestation history as first-class credential.

Per santaclawd (2026-03-15): "An agent that passes box 5 (32h) for 6 months
has earned a different trust floor than one that just cleared box 1.
The HISTORY of the schedule is the credential."

Leitner spaced repetition + streak compounding.
Streak history = the credential, not just current interval.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from math import exp, log


class StreakGrade(Enum):
    S = "S"  # 6+ months at box 5 — institutional grade
    A = "A"  # 3+ months at box 4-5
    B = "B"  # 1+ month at box 3+
    C = "C"  # Active but short history
    D = "D"  # Recently failed, rebuilding
    F = "F"  # No history or freshly slashed


@dataclass
class AttestationEvent:
    timestamp: datetime
    box: int  # Leitner box 1-5
    passed: bool
    dimension: str  # T, G, A, S, C


@dataclass
class StreakRecord:
    agent_id: str
    dimension: str
    current_box: int = 1
    consecutive_passes: int = 0
    total_passes: int = 0
    total_failures: int = 0
    longest_streak: int = 0
    time_at_box5: timedelta = field(default_factory=timedelta)
    box5_entry: datetime | None = None
    history: list[AttestationEvent] = field(default_factory=list)
    slashed: bool = False
    slash_count: int = 0

    def record(self, passed: bool, timestamp: datetime):
        event = AttestationEvent(
            timestamp=timestamp,
            box=self.current_box,
            passed=passed,
            dimension=self.dimension,
        )
        self.history.append(event)

        if passed:
            self.total_passes += 1
            self.consecutive_passes += 1
            self.longest_streak = max(self.longest_streak, self.consecutive_passes)

            # Promote: move to next box (max 5)
            if self.current_box < 5:
                self.current_box += 1
            if self.current_box == 5 and self.box5_entry is None:
                self.box5_entry = timestamp
        else:
            self.total_failures += 1
            self.consecutive_passes = 0

            # Track box 5 time before demotion
            if self.current_box == 5 and self.box5_entry:
                self.time_at_box5 += timestamp - self.box5_entry
                self.box5_entry = None

            # Demote to box 1 (Leitner rule)
            self.current_box = 1

    def slash(self, timestamp: datetime):
        """Slash = restart with penalty. Scar stays forever."""
        if self.current_box == 5 and self.box5_entry:
            self.time_at_box5 += timestamp - self.box5_entry
            self.box5_entry = None
        self.slashed = True
        self.slash_count += 1
        self.current_box = 1
        self.consecutive_passes = 0
        # History preserved — scar is visible

    def _current_box5_time(self, now: datetime | None = None) -> timedelta:
        """Include ongoing box 5 time if currently at box 5."""
        total = self.time_at_box5
        if self.current_box == 5 and self.box5_entry and now:
            total += now - self.box5_entry
        elif self.current_box == 5 and self.box5_entry and self.history:
            total += self.history[-1].timestamp - self.box5_entry
        return total

    @property
    def trust_floor(self) -> float:
        """Compounding trust floor based on streak history.
        
        Long consistent history = higher floor that R can't drop below.
        Fresh agent = floor of 0.
        """
        if self.total_passes == 0:
            return 0.0

        # Streak ratio
        total = self.total_passes + self.total_failures
        pass_rate = self.total_passes / total if total > 0 else 0

        # Box 5 tenure bonus (months) — include ongoing time
        box5_months = self._current_box5_time().total_seconds() / (30 * 24 * 3600)

        # Compounding: floor grows with consistent high-box performance
        # f = pass_rate * (1 - e^(-box5_months/3))
        floor = pass_rate * (1 - exp(-box5_months / 3))

        # Slash penalty: each slash halves the floor
        if self.slash_count > 0:
            floor *= (0.5 ** self.slash_count)

        return min(floor, 0.95)  # Cap at 0.95 — no agent is unquestionable

    @property
    def grade(self) -> StreakGrade:
        box5_months = self._current_box5_time().total_seconds() / (30 * 24 * 3600)
        if self.slash_count > 0 and self.consecutive_passes < 10:
            return StreakGrade.D
        if box5_months >= 6 and self.current_box >= 4:
            return StreakGrade.S
        if box5_months >= 3 and self.current_box >= 4:
            return StreakGrade.A
        if self.total_passes >= 30 and self.current_box >= 3:
            return StreakGrade.B
        if self.total_passes >= 5:
            return StreakGrade.C
        if self.total_passes > 0:
            return StreakGrade.D
        return StreakGrade.F

    def to_receipt_field(self) -> dict:
        """First-class field for trust receipt."""
        return {
            "attestation_streak": {
                "current_box": self.current_box,
                "consecutive_passes": self.consecutive_passes,
                "longest_streak": self.longest_streak,
                "total_pass_fail": f"{self.total_passes}/{self.total_failures}",
                "box5_days": round(self._current_box5_time().total_seconds() / 86400, 1),
                "trust_floor": round(self.trust_floor, 3),
                "grade": self.grade.value,
                "slash_count": self.slash_count,
                "history_length": len(self.history),
            }
        }


def demo():
    print("=== Attestation Streak Tracker ===\n")
    now = datetime(2026, 3, 15, 18, 0)

    # Scenario 1: Veteran agent — 6 months at box 5
    veteran = StreakRecord(agent_id="veteran_agent", dimension="G")
    t = now - timedelta(days=210)
    for i in range(200):
        veteran.record(passed=True, timestamp=t)
        t += timedelta(hours=veteran.current_box * 8)
    print(f"🏆 Veteran (200 passes, 0 failures)")
    print(f"   {json.dumps(veteran.to_receipt_field(), indent=2)}\n")

    # Scenario 2: Rebuilding after slash
    rebuilding = StreakRecord(agent_id="rebuilding_agent", dimension="G")
    t = now - timedelta(days=90)
    for i in range(50):
        rebuilding.record(passed=True, timestamp=t)
        t += timedelta(hours=8)
    rebuilding.slash(timestamp=t)
    t += timedelta(hours=1)
    for i in range(15):
        rebuilding.record(passed=True, timestamp=t)
        t += timedelta(hours=4)
    print(f"🔨 Rebuilding (50 passes → slashed → 15 passes)")
    print(f"   {json.dumps(rebuilding.to_receipt_field(), indent=2)}\n")

    # Scenario 3: Fresh agent
    fresh = StreakRecord(agent_id="fresh_agent", dimension="G")
    t = now - timedelta(days=2)
    for i in range(8):
        fresh.record(passed=True, timestamp=t)
        t += timedelta(hours=6)
    print(f"🆕 Fresh (8 passes, 2 days)")
    print(f"   {json.dumps(fresh.to_receipt_field(), indent=2)}\n")

    # Scenario 4: Unreliable — mixed record
    unreliable = StreakRecord(agent_id="unreliable_agent", dimension="G")
    t = now - timedelta(days=60)
    import random
    random.seed(42)
    for i in range(80):
        unreliable.record(passed=random.random() > 0.3, timestamp=t)
        t += timedelta(hours=12)
    print(f"⚠️ Unreliable (mixed 70/30 over 60 days)")
    print(f"   {json.dumps(unreliable.to_receipt_field(), indent=2)}\n")

    print("--- Key Insight ---")
    print("The HISTORY of the schedule is the credential.")
    print("Compounding streak = trust floor that R can't drop below.")
    print("Slash halves the floor but doesn't erase the history.")
    print("Scar + rebuild = different agent than no-history.")


if __name__ == "__main__":
    demo()
