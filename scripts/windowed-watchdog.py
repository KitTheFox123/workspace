#!/usr/bin/env python3
"""
windowed-watchdog.py — Min AND max TTL for agent heartbeats

santaclawd insight: too-frequent kicks = stuck loop churning pings.
too-infrequent = silent failure. Both are failure modes.

Windowed watchdog: beat must arrive WITHIN a time window.
Early kicks are rejected (infinite loop detection).
Late kicks trigger alarm (silent failure).

Based on Memfault embedded watchdog best practices + Pont & Ong 2002.
"""

from dataclasses import dataclass, field
import time

@dataclass 
class WindowedWatchdog:
    min_interval_s: float = 300    # 5 min minimum between beats
    max_interval_s: float = 2400   # 40 min maximum between beats
    last_kick: float = 0.0
    early_kicks: int = 0
    late_kicks: int = 0
    valid_kicks: int = 0
    total_kicks: int = 0

    def kick(self, now: float) -> dict:
        self.total_kicks += 1
        elapsed = now - self.last_kick if self.last_kick > 0 else self.min_interval_s + 1

        if elapsed < self.min_interval_s:
            self.early_kicks += 1
            return {
                "status": "REJECTED_EARLY",
                "elapsed_s": round(elapsed, 1),
                "window": f"[{self.min_interval_s}, {self.max_interval_s}]",
                "detail": "Too fast — possible stuck loop",
                "early_kicks": self.early_kicks
            }
        elif elapsed > self.max_interval_s:
            self.late_kicks += 1
            self.last_kick = now
            return {
                "status": "LATE",
                "elapsed_s": round(elapsed, 1),
                "window": f"[{self.min_interval_s}, {self.max_interval_s}]",
                "detail": "Beat arrived after window — possible silent failure period",
                "late_kicks": self.late_kicks
            }
        else:
            self.valid_kicks += 1
            self.last_kick = now
            return {
                "status": "OK",
                "elapsed_s": round(elapsed, 1),
                "valid_kicks": self.valid_kicks
            }

    def check_expired(self, now: float) -> dict:
        """Called by external timer — has the window expired?"""
        elapsed = now - self.last_kick if self.last_kick > 0 else 0
        if elapsed > self.max_interval_s:
            return {
                "status": "EXPIRED",
                "elapsed_s": round(elapsed, 1),
                "detail": "No beat received within max window"
            }
        remaining = self.max_interval_s - elapsed
        return {
            "status": "WAITING",
            "remaining_s": round(remaining, 1)
        }

    def grade(self) -> str:
        if self.total_kicks == 0: return "F"
        ratio = self.valid_kicks / self.total_kicks
        if ratio > 0.95: return "A"
        if ratio > 0.80: return "B"
        if ratio > 0.60: return "C"
        if ratio > 0.40: return "D"
        return "F"

    def diagnosis(self) -> str:
        if self.early_kicks > self.valid_kicks:
            return "STUCK_LOOP — agent beating too fast, likely infinite loop"
        if self.late_kicks > self.valid_kicks:
            return "INTERMITTENT — agent has silent periods, investigate scope contraction"
        if self.total_kicks == 0:
            return "DEAD — no beats received"
        return "HEALTHY"


def demo():
    print("=" * 60)
    print("Windowed Watchdog Timer")
    print("Min AND max TTL for agent heartbeats")
    print("=" * 60)

    # Scenario 1: healthy agent (beats every ~20 min)
    print("\n--- Scenario 1: Healthy Agent ---")
    w1 = WindowedWatchdog(min_interval_s=300, max_interval_s=2400)
    t = 0.0
    for i in range(5):
        t += 1200  # 20 min
        r = w1.kick(t)
        print(f"  Beat {i+1}: {r['status']} (elapsed {r.get('elapsed_s', 'n/a')}s)")
    print(f"  Grade: {w1.grade()} — {w1.diagnosis()}")

    # Scenario 2: stuck loop (beats every 10s)
    print("\n--- Scenario 2: Stuck Loop Agent ---")
    w2 = WindowedWatchdog(min_interval_s=300, max_interval_s=2400)
    t2 = 0.0
    w2.kick(t2)  # first kick
    for i in range(6):
        t2 += 10  # 10s — way too fast
        r = w2.kick(t2)
        print(f"  Beat {i+1}: {r['status']} — {r.get('detail', '')}")
    print(f"  Grade: {w2.grade()} — {w2.diagnosis()}")

    # Scenario 3: intermittent (long gaps)
    print("\n--- Scenario 3: Intermittent Agent ---")
    w3 = WindowedWatchdog(min_interval_s=300, max_interval_s=2400)
    t3 = 0.0
    w3.kick(t3)
    for i in range(4):
        t3 += 5000  # 83 min — way too slow
        r = w3.kick(t3)
        print(f"  Beat {i+1}: {r['status']} — {r.get('detail', '')}")
    print(f"  Grade: {w3.grade()} — {w3.diagnosis()}")

    # Scenario 4: mixed
    print("\n--- Scenario 4: Mixed (recovering agent) ---")
    w4 = WindowedWatchdog(min_interval_s=300, max_interval_s=2400)
    t4 = 0.0
    w4.kick(t4)
    t4 += 5000; w4.kick(t4)  # late
    t4 += 10; w4.kick(t4)    # early 
    t4 += 1200; w4.kick(t4)  # ok
    t4 += 1200; w4.kick(t4)  # ok
    t4 += 1200; w4.kick(t4)  # ok
    print(f"  Valid: {w4.valid_kicks}, Early: {w4.early_kicks}, Late: {w4.late_kicks}")
    print(f"  Grade: {w4.grade()} — {w4.diagnosis()}")

    print(f"\n{'='*60}")
    print("Key: windowed watchdog catches BOTH failure modes.")
    print("  Too fast = stuck loop (infinite ping)")
    print("  Too slow = silent failure (scope contraction)")
    print("  Both rejected. Only within-window beats count.")


if __name__ == "__main__":
    demo()
