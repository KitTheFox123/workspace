#!/usr/bin/env python3
"""
phi-adaptive-window.py — Adaptive Φ accrual failure detector for agent heartbeats.

Hayashibara et al 2004 + Akka implementation insights.
Key: window size N must capture one full activity cycle.

For 30m heartbeats: N=48 = 24h. For 20m: N=72.
Cassandra uses N=200 + acceptable_pause.

Usage: python3 phi-adaptive-window.py
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class PhiDetector:
    """Φ accrual failure detector with adaptive window."""
    window_size: int = 48  # samples to keep
    threshold: float = 8.0  # phi > threshold = suspected dead
    acceptable_pause: float = 0.0  # extra margin (seconds)
    arrivals: list = field(default_factory=list)

    def heartbeat(self, timestamp: float):
        self.arrivals.append(timestamp)
        if len(self.arrivals) > self.window_size + 1:
            self.arrivals = self.arrivals[-(self.window_size + 1):]

    def phi(self, now: float) -> float:
        if len(self.arrivals) < 2:
            return 0.0

        intervals = [self.arrivals[i+1] - self.arrivals[i]
                      for i in range(len(self.arrivals) - 1)]

        mean = sum(intervals) / len(intervals)
        variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
        std = max(math.sqrt(variance), 0.001)

        elapsed = now - self.arrivals[-1] - self.acceptable_pause
        if elapsed < 0:
            return 0.0

        # phi = -log10(1 - CDF(elapsed))
        # CDF of normal distribution approximated
        y = (elapsed - mean) / std
        # Using logistic approximation of normal CDF
        p = 1.0 / (1.0 + math.exp(-1.7 * y))
        if p >= 1.0:
            return 16.0  # cap
        return max(0.0, -math.log10(1.0 - p))

    def is_alive(self, now: float) -> bool:
        return self.phi(now) < self.threshold

    def status(self, now: float) -> dict:
        p = self.phi(now)
        if p < 1:
            verdict = "ALIVE"
        elif p < self.threshold:
            verdict = "SUSPECT"
        else:
            verdict = "DEAD"
        return {"phi": round(p, 2), "verdict": verdict, "samples": len(self.arrivals)}


def optimal_window(heartbeat_interval_min: float, cycle_hours: float = 24) -> int:
    """Calculate optimal N for given heartbeat interval and activity cycle."""
    beats_per_cycle = (cycle_hours * 60) / heartbeat_interval_min
    return max(10, int(beats_per_cycle))


def demo():
    print("=" * 60)
    print("Adaptive Φ Accrual Failure Detector for Agents")
    print("Hayashibara et al 2004 / Akka implementation")
    print("=" * 60)

    scenarios = [
        {"name": "Fast heartbeat (1s, Akka-style)", "interval": 1, "n": 1000, "jitter": 0.2},
        {"name": "Agent heartbeat (20min)", "interval": 1200, "n": 72, "jitter": 120},
        {"name": "Slow heartbeat (30min)", "interval": 1800, "n": 48, "jitter": 300},
        {"name": "Very slow (6hr)", "interval": 21600, "n": 8, "jitter": 3600},
    ]

    for sc in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {sc['name']}")
        print(f"Interval: {sc['interval']}s, Window: N={sc['n']}, Jitter: ±{sc['jitter']}s")

        detector = PhiDetector(window_size=sc["n"], threshold=8.0)

        # Simulate normal operation
        t = 0.0
        for i in range(sc["n"] + 5):
            jitter = random.gauss(0, sc["jitter"])
            t += sc["interval"] + jitter
            detector.heartbeat(t)

        # Check right after last heartbeat
        status_normal = detector.status(t + 1)
        print(f"  Just after beat: φ={status_normal['phi']}, {status_normal['verdict']}")

        # Check at 1.5x interval
        status_late = detector.status(t + sc["interval"] * 1.5)
        print(f"  1.5× interval:   φ={status_late['phi']}, {status_late['verdict']}")

        # Check at 3x interval (should be dead)
        status_dead = detector.status(t + sc["interval"] * 3)
        print(f"  3× interval:     φ={status_dead['phi']}, {status_dead['verdict']}")

    # Optimal window recommendations
    print(f"\n{'=' * 60}")
    print("OPTIMAL WINDOW SIZE (N = beats per 24h cycle):")
    for interval in [1, 60, 300, 1200, 1800, 3600, 21600]:
        n = optimal_window(interval / 60)
        label = f"{interval}s" if interval < 60 else f"{interval//60}m" if interval < 3600 else f"{interval//3600}h"
        print(f"  {label:>5} heartbeat → N={n}")
    print(f"\nKEY: N must capture one full activity cycle.")
    print(f"Too small = false positives on natural jitter.")
    print(f"Too large = slow detection of real failures.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
