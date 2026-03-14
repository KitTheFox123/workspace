#!/usr/bin/env python3
"""
trust-refresh-scheduler.py — Spaced repetition for trust verification.

Applies Leitner/Pimsleur spacing to trust refresh schedules.
Successful verifications → longer intervals. Failures → short intervals.

Ebbinghaus: R = e^(-t/S), S grows with successful reviews.
Leitner: 5 boxes, each 2x the previous interval.
Agent trust: gossip refresh, cert re-verification, attestation re-check.

Usage: python3 trust-refresh-scheduler.py
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustItem:
    """A trust dimension that needs periodic verification."""
    dimension: str  # T, G, A, S
    name: str
    box: int = 1  # Leitner box 1-5
    base_interval_h: float = 1.0  # Box 1 interval
    successes: int = 0
    failures: int = 0
    last_verified_h: float = 0.0  # hours ago

    @property
    def interval_h(self) -> float:
        """Current review interval (doubles per box)."""
        return self.base_interval_h * (2 ** (self.box - 1))

    @property
    def due(self) -> bool:
        """Is this item due for re-verification?"""
        return self.last_verified_h >= self.interval_h

    @property
    def retention(self) -> float:
        """Estimated retention using Ebbinghaus curve."""
        s = self.interval_h * 1.5  # stability ≈ 1.5× interval
        return math.exp(-self.last_verified_h / s) if s > 0 else 0.0

    def verify_success(self):
        """Successful verification → promote to next box."""
        self.successes += 1
        self.box = min(self.box + 1, 5)
        self.last_verified_h = 0.0

    def verify_failure(self):
        """Failed verification → demote to box 1."""
        self.failures += 1
        self.box = 1
        self.last_verified_h = 0.0

    @property
    def grade(self) -> str:
        r = self.retention
        if r >= 0.9: return "A"
        if r >= 0.7: return "B"
        if r >= 0.5: return "C"
        if r >= 0.3: return "D"
        return "F"


@dataclass 
class RefreshScheduler:
    """Manages refresh schedules for all trust dimensions."""
    items: list[TrustItem] = field(default_factory=list)

    def add_default_dimensions(self):
        self.items = [
            TrustItem("T", "tile_proof", box=5, base_interval_h=24.0),  # Merkle: infrequent
            TrustItem("G", "gossip", box=1, base_interval_h=1.0),       # Gossip: frequent
            TrustItem("A", "attestation", box=3, base_interval_h=12.0), # Attestation: moderate
            TrustItem("S", "sleeper", box=2, base_interval_h=4.0),      # Sleeper: regular
        ]

    def tick(self, hours: float):
        """Advance time by hours."""
        for item in self.items:
            item.last_verified_h += hours

    def due_items(self) -> list[TrustItem]:
        return [i for i in self.items if i.due]

    def status(self) -> str:
        lines = []
        for i in self.items:
            due_marker = " ⚠️ DUE" if i.due else ""
            lines.append(
                f"  {i.dimension}({i.name:15s}) box={i.box} interval={i.interval_h:6.1f}h "
                f"age={i.last_verified_h:5.1f}h retention={i.retention:.3f} [{i.grade}]{due_marker}"
            )
        return "\n".join(lines)


def simulate():
    print("=== Trust Refresh Scheduler (Leitner/Spaced Repetition) ===\n")

    sched = RefreshScheduler()
    sched.add_default_dimensions()

    # Simulate 48 hours
    print("t=0h (fresh):")
    print(sched.status())

    for t in [1, 4, 8, 12, 24, 48]:
        sched.tick(t - sum(i.last_verified_h for i in sched.items) / len(sched.items))
        # Actually just set ages directly for clarity
        for item in sched.items:
            item.last_verified_h = t

        due = sched.due_items()
        print(f"\nt={t}h:")
        print(sched.status())
        if due:
            print(f"  → {len(due)} items due: {', '.join(d.name for d in due)}")

    # Simulate gossip success → promotion
    print("\n--- Gossip verified successfully 3x ---")
    gossip = sched.items[1]
    for _ in range(3):
        gossip.verify_success()
    print(f"  Gossip now: box={gossip.box}, interval={gossip.interval_h}h (was 1h)")

    # Simulate attestation failure → demotion
    print("\n--- Attestation verification FAILED ---")
    att = sched.items[2]
    att.verify_failure()
    print(f"  Attestation now: box={att.box}, interval={att.interval_h}h (was 48h)")
    print(f"  Must re-verify in {att.interval_h}h (demoted to box 1)")


if __name__ == "__main__":
    simulate()
