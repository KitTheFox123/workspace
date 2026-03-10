#!/usr/bin/env python3
"""
nyquist-watchdog.py — Nyquist-aware windowed watchdog for agent monitoring

Nyquist theorem: sample at ≥2x the highest frequency you want to detect.
Windowed watchdog: both min AND max TTL matter.
- Too frequent = stuck loop (PIC CLRWDT window violation)
- Too infrequent = silent failure (missed drift)

Combines Pont & Ong 2002 (observable state), Sharpe 2025 (vigilance decrement),
and Nyquist-Shannon (sampling theorem) into a unified monitoring framework.
"""

from dataclasses import dataclass, field
import math

@dataclass
class NyquistWatchdog:
    """Windowed watchdog with Nyquist-aware interval calculation"""
    min_interval_s: float   # floor — too frequent = stuck loop
    max_interval_s: float   # ceiling — too infrequent = missed drift
    beats: list = field(default_factory=list)
    violations: list = field(default_factory=list)

    @classmethod
    def from_drift_period(cls, fastest_drift_s: float, margin: float = 1.5):
        """Calculate window from fastest drift you want to detect"""
        # Nyquist: sample at 2x. With margin for safety.
        nyquist_interval = fastest_drift_s / 2.0
        max_interval = nyquist_interval / margin  # conservative
        min_interval = max_interval / 10.0  # floor = 10% of max
        return cls(min_interval_s=min_interval, max_interval_s=max_interval)

    def beat(self, timestamp: float, payload_hash: str = "") -> dict:
        """Record a heartbeat and check window"""
        result = {"timestamp": timestamp, "status": "OK", "violations": []}

        if self.beats:
            interval = timestamp - self.beats[-1]["timestamp"]

            if interval < self.min_interval_s:
                v = {
                    "type": "TOO_FREQUENT",
                    "interval_s": round(interval, 1),
                    "min_s": self.min_interval_s,
                    "severity": "WARNING"
                }
                result["violations"].append(v)
                self.violations.append(v)
                result["status"] = "WINDOW_VIOLATION"

            elif interval > self.max_interval_s:
                overdue_factor = interval / self.max_interval_s
                v = {
                    "type": "TOO_INFREQUENT",
                    "interval_s": round(interval, 1),
                    "max_s": self.max_interval_s,
                    "overdue_factor": round(overdue_factor, 1),
                    "severity": "HIGH" if overdue_factor > 3 else "MEDIUM"
                }
                result["violations"].append(v)
                self.violations.append(v)
                result["status"] = "WINDOW_VIOLATION"

            # Check for identical payload (stuck loop)
            if payload_hash and self.beats[-1].get("payload_hash") == payload_hash:
                v = {
                    "type": "STALE_PAYLOAD",
                    "severity": "HIGH",
                    "detail": "Same payload hash as last beat — stuck loop?"
                }
                result["violations"].append(v)
                self.violations.append(v)
                result["status"] = "STALE"

        self.beats.append({"timestamp": timestamp, "payload_hash": payload_hash})
        return result

    def nyquist_frequency(self) -> float:
        """Max drift frequency detectable at current sampling rate"""
        if len(self.beats) < 2:
            return 0
        intervals = [self.beats[i+1]["timestamp"] - self.beats[i]["timestamp"]
                     for i in range(len(self.beats)-1)]
        avg_interval = sum(intervals) / len(intervals)
        return 1.0 / (2.0 * avg_interval)  # Hz

    def max_detectable_drift_s(self) -> float:
        """Longest drift period detectable"""
        freq = self.nyquist_frequency()
        return 1.0 / freq if freq > 0 else float('inf')

    def grade(self) -> str:
        total = len(self.beats)
        if total == 0: return "F"
        violation_rate = len(self.violations) / total
        if violation_rate == 0: return "A"
        if violation_rate < 0.1: return "B"
        if violation_rate < 0.2: return "C"
        if violation_rate < 0.4: return "D"
        return "F"


def demo():
    print("=" * 60)
    print("Nyquist Watchdog — Sampling Theorem for Agent Monitoring")
    print("=" * 60)

    # Scenario 1: well-behaved agent (20-min heartbeats, detecting 1-hour drift)
    print("\n--- Scenario 1: Well-Behaved Agent ---")
    w1 = NyquistWatchdog.from_drift_period(fastest_drift_s=3600)  # 1 hour drift
    print(f"  Window: [{w1.min_interval_s:.0f}s, {w1.max_interval_s:.0f}s]")
    t = 0
    for i in range(6):
        t += 1200  # 20 min intervals
        r = w1.beat(t, payload_hash=f"hash_{i}")
        print(f"  Beat {i+1}: {r['status']}")
    print(f"  Max detectable drift: {w1.max_detectable_drift_s():.0f}s ({w1.max_detectable_drift_s()/60:.0f}min)")
    print(f"  Grade: {w1.grade()}")

    # Scenario 2: stuck loop (rapid-fire beats)
    print("\n--- Scenario 2: Stuck Loop ---")
    w2 = NyquistWatchdog.from_drift_period(fastest_drift_s=3600)
    t2 = 0
    for i in range(6):
        t2 += 30  # every 30s — way too fast
        r = w2.beat(t2, payload_hash="same_hash")  # same payload!
        violations = [v['type'] for v in r.get('violations', [])]
        print(f"  Beat {i+1}: {r['status']} {violations}")
    print(f"  Grade: {w2.grade()}")

    # Scenario 3: silent failure (long gaps)
    print("\n--- Scenario 3: Silent Failure ---")
    w3 = NyquistWatchdog.from_drift_period(fastest_drift_s=3600)
    t3 = 0
    w3.beat(t3, "hash_0")
    t3 += 7200  # 2 hour gap
    r3 = w3.beat(t3, "hash_1")
    violations = [f"{v['type']} ({v.get('overdue_factor', '')}x)" for v in r3.get('violations', [])]
    print(f"  Beat after 2h gap: {r3['status']} {violations}")
    t3 += 10800  # 3 hour gap
    r4 = w3.beat(t3, "hash_2")
    violations = [f"{v['type']} ({v.get('overdue_factor', '')}x)" for v in r4.get('violations', [])]
    print(f"  Beat after 3h gap: {r4['status']} {violations}")
    print(f"  Grade: {w3.grade()}")

    # Summary
    print(f"\n{'='*60}")
    print("Nyquist for monitoring:")
    print("  Want to detect 1h drift? → sample every ≤30min")
    print("  Want to detect 10min drift? → sample every ≤5min")
    print("  Too frequent = stuck loop. Too rare = aliasing.")
    print("\nWindow + payload hash + Nyquist = complete watchdog.")


if __name__ == "__main__":
    demo()
