#!/usr/bin/env python3
"""
windowed-watchdog.py — Min AND max TTL for agent heartbeats

santaclawd insight: "too frequent = stuck loop churning pings.
too infrequent = silent failure."

Memfault best practices: windowed watchdog only accepts kicks within
a time window. Too early = suspicious. Too late = failure.

Agent mapping:
  - Too fast: stuck heartbeat loop, no real work between beats
  - Too slow: agent down or degraded
  - Window hit: healthy operation

Three failure modes embedded engineers track:
  1. Deadlock → circular scope dependency
  2. Sensor wedge → stuck API call
  3. Priority inversion → heartbeat crowds out real work
"""

import time
from dataclasses import dataclass, field

@dataclass
class WindowedWatchdog:
    """Windowed watchdog: kicks only accepted within [min_interval, max_interval]"""
    name: str
    min_interval_s: float   # too-fast threshold
    max_interval_s: float   # too-slow threshold
    last_kick: float = 0.0
    kicks_total: int = 0
    too_fast: int = 0
    too_slow: int = 0
    in_window: int = 0

    def kick(self, now: float) -> dict:
        self.kicks_total += 1
        if self.last_kick == 0:
            self.last_kick = now
            return {"status": "INIT", "channel": self.name}

        elapsed = now - self.last_kick
        self.last_kick = now

        if elapsed < self.min_interval_s:
            self.too_fast += 1
            return {
                "status": "TOO_FAST",
                "channel": self.name,
                "elapsed_s": round(elapsed, 1),
                "min_s": self.min_interval_s,
                "diagnosis": "stuck_loop",
                "detail": "Kick too early — spinning without real work?"
            }
        elif elapsed > self.max_interval_s:
            self.too_slow += 1
            return {
                "status": "TOO_SLOW",
                "channel": self.name,
                "elapsed_s": round(elapsed, 1),
                "max_s": self.max_interval_s,
                "diagnosis": "silent_failure",
                "detail": "Kick too late — degraded or wedged?"
            }
        else:
            self.in_window += 1
            return {
                "status": "OK",
                "channel": self.name,
                "elapsed_s": round(elapsed, 1)
            }

    def grade(self) -> str:
        total = self.too_fast + self.too_slow + self.in_window
        if total == 0: return "A"
        fault_rate = (self.too_fast + self.too_slow) / total
        if fault_rate < 0.05: return "A"
        if fault_rate < 0.15: return "B"
        if fault_rate < 0.30: return "C"
        if fault_rate < 0.50: return "D"
        return "F"

    def diagnosis(self) -> str:
        if self.too_fast > self.too_slow:
            return "STUCK_LOOP: agent kicking too fast, likely spinning without progress"
        elif self.too_slow > self.too_fast:
            return "SILENT_FAILURE: agent kicking too slow, likely degraded or wedged"
        elif self.too_fast > 0:
            return "MIXED: both fast and slow anomalies detected"
        return "HEALTHY: all kicks within window"


def demo():
    print("=" * 60)
    print("Windowed Watchdog — Min AND Max TTL")
    print("santaclawd: too frequent = stuck loop. too slow = silent failure.")
    print("=" * 60)

    # Scenario 1: healthy agent (20-min heartbeat, window 15-25 min)
    print("\n--- Scenario 1: Healthy Agent ---")
    w1 = WindowedWatchdog("heartbeat", min_interval_s=900, max_interval_s=1500)
    t = 0.0
    w1.kick(t)  # init
    for i in range(5):
        t += 1200  # 20 min intervals
        r = w1.kick(t)
        print(f"  Beat {i+1}: {r['status']} ({r.get('elapsed_s', 0)}s)")
    print(f"  Grade: {w1.grade()} — {w1.diagnosis()}")

    # Scenario 2: stuck loop (kicking every 2 min)
    print("\n--- Scenario 2: Stuck Loop (too fast) ---")
    w2 = WindowedWatchdog("heartbeat", min_interval_s=900, max_interval_s=1500)
    t = 0.0
    w2.kick(t)
    for i in range(5):
        t += 120  # 2 min intervals — way too fast
        r = w2.kick(t)
        print(f"  Beat {i+1}: {r['status']} — {r.get('diagnosis', '')} ({r.get('elapsed_s', 0)}s)")
    print(f"  Grade: {w2.grade()} — {w2.diagnosis()}")

    # Scenario 3: degraded agent (kicking every 45 min)
    print("\n--- Scenario 3: Degraded Agent (too slow) ---")
    w3 = WindowedWatchdog("heartbeat", min_interval_s=900, max_interval_s=1500)
    t = 0.0
    w3.kick(t)
    for i in range(5):
        t += 2700  # 45 min intervals
        r = w3.kick(t)
        print(f"  Beat {i+1}: {r['status']} — {r.get('diagnosis', '')} ({r.get('elapsed_s', 0)}s)")
    print(f"  Grade: {w3.grade()} — {w3.diagnosis()}")

    # Scenario 4: mixed (priority inversion — some fast, some slow)
    print("\n--- Scenario 4: Priority Inversion (mixed) ---")
    w4 = WindowedWatchdog("heartbeat", min_interval_s=900, max_interval_s=1500)
    t = 0.0
    w4.kick(t)
    intervals = [60, 2700, 1200, 90, 1200]  # fast, slow, ok, fast, ok
    for i, interval in enumerate(intervals):
        t += interval
        r = w4.kick(t)
        print(f"  Beat {i+1}: {r['status']} ({r.get('elapsed_s', 0)}s)")
    print(f"  Grade: {w4.grade()} — {w4.diagnosis()}")

    print(f"\n{'='*60}")
    print("Window = [min_TTL, max_TTL]")
    print("  Too fast: stuck loop, no real work")
    print("  Too slow: silent failure, wedge")
    print("  In window: healthy")
    print("  Mixed: priority inversion")
    print("\nEmbedded systems solved this 40 years ago. (Memfault 2020)")


if __name__ == "__main__":
    demo()
