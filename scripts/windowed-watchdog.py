#!/usr/bin/env python3
"""
windowed-watchdog.py — Bidirectional anomaly detection for heartbeats

Pont & Ong 2002: windowed watchdog only accepts kicks within a time window.
Too early = stuck loop / panic. Too late = silent failure.

Both directions are anomalous:
  - Too fast: task thrashing, stuck loop, panic mode
  - Too slow: silent failure, scope contraction, agent down
  - Window: normal operation band

santaclawd: "min TTL AND max TTL. too frequent = stuck loop churning pings."
"""

import statistics
from dataclasses import dataclass, field

@dataclass
class WindowedWatchdog:
    """Bidirectional heartbeat anomaly detector"""
    min_interval_s: float   # too fast below this
    max_interval_s: float   # too slow above this
    intervals: list = field(default_factory=list)
    violations: list = field(default_factory=list)
    last_beat_time: float = 0.0

    def kick(self, now: float) -> dict:
        if self.last_beat_time > 0:
            interval = now - self.last_beat_time
            self.intervals.append(interval)

            if interval < self.min_interval_s:
                violation = {
                    "type": "TOO_FAST",
                    "interval_s": round(interval, 1),
                    "expected_min": self.min_interval_s,
                    "severity": "HIGH" if interval < self.min_interval_s * 0.5 else "MEDIUM",
                    "diagnosis": "stuck_loop" if interval < self.min_interval_s * 0.3 else "panic_mode"
                }
                self.violations.append(violation)
                self.last_beat_time = now
                return violation
            elif interval > self.max_interval_s:
                violation = {
                    "type": "TOO_SLOW",
                    "interval_s": round(interval, 1),
                    "expected_max": self.max_interval_s,
                    "severity": "HIGH" if interval > self.max_interval_s * 2 else "MEDIUM",
                    "diagnosis": "silent_failure" if interval > self.max_interval_s * 3 else "degraded"
                }
                self.violations.append(violation)
                self.last_beat_time = now
                return violation
            else:
                self.last_beat_time = now
                return {"type": "OK", "interval_s": round(interval, 1)}
        self.last_beat_time = now
        return {"type": "FIRST_BEAT"}

    def stats(self) -> dict:
        if not self.intervals:
            return {"beats": 0}
        return {
            "beats": len(self.intervals) + 1,
            "mean_interval": round(statistics.mean(self.intervals), 1),
            "stdev": round(statistics.stdev(self.intervals), 1) if len(self.intervals) > 1 else 0,
            "min": round(min(self.intervals), 1),
            "max": round(max(self.intervals), 1),
            "violations": len(self.violations),
            "too_fast": sum(1 for v in self.violations if v["type"] == "TOO_FAST"),
            "too_slow": sum(1 for v in self.violations if v["type"] == "TOO_SLOW"),
        }

    def grade(self) -> str:
        if not self.intervals:
            return "N/A"
        violation_rate = len(self.violations) / len(self.intervals)
        if violation_rate < 0.05: return "A"
        if violation_rate < 0.10: return "B"
        if violation_rate < 0.20: return "C"
        if violation_rate < 0.40: return "D"
        return "F"


def demo():
    print("=" * 60)
    print("Windowed Watchdog — Bidirectional Anomaly Detection")
    print("Pont & Ong 2002: too fast AND too slow are anomalous")
    print("=" * 60)

    # Scenario 1: healthy agent (20-min heartbeat, window 15-25 min)
    print("\n--- Scenario 1: Healthy Agent ---")
    w1 = WindowedWatchdog(min_interval_s=900, max_interval_s=1500)
    t = 0
    for _ in range(10):
        w1.kick(t)
        t += 1200  # 20 min, within window
    s1 = w1.stats()
    print(f"  Beats: {s1['beats']}, Violations: {s1['violations']}")
    print(f"  Mean interval: {s1['mean_interval']}s, Grade: {w1.grade()}")

    # Scenario 2: panic mode (rapid-fire beats)
    print("\n--- Scenario 2: Panic Mode (too fast) ---")
    w2 = WindowedWatchdog(min_interval_s=900, max_interval_s=1500)
    t = 0
    w2.kick(t)
    for _ in range(10):
        t += 120  # 2 min — way too fast
        result = w2.kick(t)
    s2 = w2.stats()
    print(f"  Beats: {s2['beats']}, Too fast: {s2['too_fast']}")
    print(f"  Mean interval: {s2['mean_interval']}s, Grade: {w2.grade()}")
    print(f"  Diagnosis: {result.get('diagnosis', 'n/a')}")

    # Scenario 3: degraded agent (slow beats)
    print("\n--- Scenario 3: Degraded Agent (too slow) ---")
    w3 = WindowedWatchdog(min_interval_s=900, max_interval_s=1500)
    t = 0
    w3.kick(t)
    for _ in range(10):
        t += 3600  # 60 min — too slow
        result = w3.kick(t)
    s3 = w3.stats()
    print(f"  Beats: {s3['beats']}, Too slow: {s3['too_slow']}")
    print(f"  Mean interval: {s3['mean_interval']}s, Grade: {w3.grade()}")
    print(f"  Diagnosis: {result.get('diagnosis', 'n/a')}")

    # Scenario 4: mixed (healthy then panic then silent)
    print("\n--- Scenario 4: Mixed Pattern ---")
    w4 = WindowedWatchdog(min_interval_s=900, max_interval_s=1500)
    t = 0
    # Healthy phase
    for _ in range(5):
        w4.kick(t); t += 1200
    # Panic phase
    for _ in range(3):
        w4.kick(t); t += 60
    # Silent phase
    w4.kick(t); t += 5400
    w4.kick(t)
    s4 = w4.stats()
    print(f"  Beats: {s4['beats']}, Too fast: {s4['too_fast']}, Too slow: {s4['too_slow']}")
    print(f"  Grade: {w4.grade()}")

    print(f"\n{'='*60}")
    print("Key: both directions are anomalous.")
    print("  Too fast = stuck loop / panic / thrashing")
    print("  Too slow = silent failure / scope contraction")
    print("  Window = normal operation band")
    print("Agent heartbeat needs min AND max TTL.")


if __name__ == "__main__":
    demo()
