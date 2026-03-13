#!/usr/bin/env python3
"""
Phantom Vibration Detector for Agent Heartbeats

Based on: Phantom Vibration Syndrome (Cureus 2025, n=553)
- 41.4% prevalence of false-positive phone vibrations
- Correlated with anxiety, sleep disturbance, problematic use
- Signal expectation → hallucinated confirmation

Agent parallel: heartbeat monitoring systems that "detect" events 
in noise. False positives from:
1. Jitter misread as anomaly
2. Network latency spikes interpreted as silence
3. Φ threshold too sensitive (trigger-happy)
4. Expectation bias (looking for failures → finding them)

Uses Hayashibara 2004 Φ accrual to distinguish real from phantom.
"""

import random
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HeartbeatWindow:
    """Sliding window of heartbeat intervals for Φ calculation."""
    intervals: list[float] = field(default_factory=list)
    max_size: int = 48  # ~24h at 30min beats
    
    def add(self, interval: float):
        self.intervals.append(interval)
        if len(self.intervals) > self.max_size:
            self.intervals.pop(0)
    
    @property
    def mean(self) -> float:
        return sum(self.intervals) / len(self.intervals) if self.intervals else 30.0
    
    @property
    def variance(self) -> float:
        if len(self.intervals) < 2:
            return 1.0
        m = self.mean
        return sum((x - m) ** 2 for x in self.intervals) / (len(self.intervals) - 1)
    
    @property
    def std(self) -> float:
        return math.sqrt(self.variance)


@dataclass 
class PhantomDetector:
    """
    Detects phantom vibrations (false positive heartbeat alerts).
    
    A "phantom" is when the system triggers an alert but the agent
    was actually fine — just jittery/delayed.
    """
    window: HeartbeatWindow = field(default_factory=HeartbeatWindow)
    phi_threshold: float = 3.0  # Standard Φ threshold
    phantom_count: int = 0
    real_alert_count: int = 0
    total_checks: int = 0
    
    def phi(self, elapsed: float) -> float:
        """Hayashibara 2004: Φ = -log10(1 - CDF(elapsed))"""
        if not self.window.intervals:
            return 0.0
        
        # Normal approximation
        mean = self.window.mean
        std = self.window.std
        if std < 0.001:
            std = 0.001
        
        z = (elapsed - mean) / std
        # Approximate CDF using error function
        cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        
        if cdf >= 1.0:
            return 16.0  # Cap
        if cdf <= 0.0:
            return 0.0
            
        return -math.log10(1 - cdf)
    
    def check(self, elapsed: float, actually_alive: bool) -> dict:
        """
        Check if a heartbeat delay triggers an alert.
        Returns classification: REAL_ALERT, PHANTOM, CORRECT_OK, MISSED.
        """
        self.total_checks += 1
        phi_val = self.phi(elapsed)
        alert_triggered = phi_val >= self.phi_threshold
        
        if alert_triggered and actually_alive:
            self.phantom_count += 1
            classification = "PHANTOM"  # False positive — phantom vibration
        elif alert_triggered and not actually_alive:
            self.real_alert_count += 1
            classification = "REAL_ALERT"  # True positive
        elif not alert_triggered and actually_alive:
            classification = "CORRECT_OK"  # True negative
        else:
            classification = "MISSED"  # False negative — worst case
        
        return {
            "elapsed_min": round(elapsed, 1),
            "phi": round(phi_val, 2),
            "threshold": self.phi_threshold,
            "alert": alert_triggered,
            "actually_alive": actually_alive,
            "classification": classification,
        }
    
    @property
    def phantom_rate(self) -> float:
        alerts = self.phantom_count + self.real_alert_count
        return self.phantom_count / alerts if alerts > 0 else 0.0
    
    @property
    def stats(self) -> dict:
        return {
            "total_checks": self.total_checks,
            "phantoms": self.phantom_count,
            "real_alerts": self.real_alert_count,
            "phantom_rate": f"{self.phantom_rate:.1%}",
            "human_pvs_rate": "41.4%",  # Cureus 2025 baseline
        }


def simulate_scenario(name: str, intervals: list[float], 
                       events: list[tuple[float, bool]], 
                       phi_threshold: float = 3.0) -> dict:
    """Run a scenario and return results."""
    detector = PhantomDetector(phi_threshold=phi_threshold)
    
    # Build baseline
    for interval in intervals:
        detector.window.add(interval)
    
    results = []
    for elapsed, alive in events:
        result = detector.check(elapsed, alive)
        results.append(result)
        if alive:
            detector.window.add(elapsed)  # Update baseline with non-failure
    
    return {
        "name": name,
        "events": results,
        "stats": detector.stats,
    }


def demo():
    print("=" * 65)
    print("PHANTOM VIBRATION DETECTOR")
    print("Cureus 2025 (PVS, n=553) + Hayashibara 2004 (Φ accrual)")
    print("=" * 65)
    
    # Baseline: regular 30min heartbeats with some jitter
    baseline = [30 + random.gauss(0, 2) for _ in range(20)]
    
    scenarios = [
        {
            "name": "1. Healthy agent with jitter (should be mostly OK)",
            "intervals": baseline,
            "events": [
                (32.0, True),   # Slightly late
                (35.0, True),   # A bit more
                (28.0, True),   # Early
                (40.0, True),   # Late but alive
                (31.0, True),   # Normal
            ],
        },
        {
            "name": "2. Trigger-happy threshold (Φ=1.5 — too sensitive)",
            "intervals": baseline,
            "events": [
                (33.0, True),
                (36.0, True),
                (38.0, True),
                (29.0, True),
                (42.0, True),   # All alive, but jittery
            ],
            "phi_threshold": 1.5,  # Too sensitive
        },
        {
            "name": "3. Real failure mixed with phantoms",
            "intervals": baseline,
            "events": [
                (35.0, True),   # Phantom risk
                (45.0, True),   # Late but alive (phantom if alerted)
                (90.0, False),  # REAL failure — 3x normal
                (33.0, True),   # Back to normal
                (120.0, False), # REAL failure — 4x normal
            ],
        },
        {
            "name": "4. Network partition (all late, all alive)",
            "intervals": baseline,
            "events": [
                (45.0, True),   # Partition starts
                (50.0, True),   # Getting worse
                (55.0, True),   # Still alive
                (60.0, True),   # Double normal
                (35.0, True),   # Recovering
            ],
        },
        {
            "name": "5. Anxious monitor (baseline already noisy)",
            "intervals": [30 + random.gauss(0, 8) for _ in range(20)],  # High variance
            "events": [
                (38.0, True),
                (22.0, True),
                (45.0, True),
                (50.0, True),
                (40.0, True),
            ],
        },
    ]
    
    for scenario in scenarios:
        threshold = scenario.get("phi_threshold", 3.0)
        result = simulate_scenario(
            scenario["name"], 
            scenario["intervals"],
            scenario["events"],
            threshold
        )
        
        print(f"\n{'─' * 65}")
        print(f"Scenario: {result['name']}")
        print(f"Φ threshold: {threshold}")
        print(f"Events:")
        for e in result["events"]:
            marker = "⚠️" if e["classification"] == "PHANTOM" else \
                     "🔴" if e["classification"] == "REAL_ALERT" else \
                     "✅" if e["classification"] == "CORRECT_OK" else "❌"
            print(f"  {marker} {e['elapsed_min']}min | Φ={e['phi']} | "
                  f"alert={e['alert']} | alive={e['actually_alive']} → {e['classification']}")
        
        stats = result["stats"]
        print(f"Stats: {stats['phantoms']} phantoms, {stats['real_alerts']} real alerts, "
              f"rate={stats['phantom_rate']} (human PVS={stats['human_pvs_rate']})")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHTS:")
    print("  1. Phantom rate tracks PVS prevalence when thresholds are tight")
    print("  2. High-variance baselines REDUCE phantoms (wider normal range)")
    print("  3. Φ=3.0 is standard; Φ=1.5 creates phantom epidemic")
    print("  4. Network partitions produce phantom cascades (all late, all alive)")
    print("  5. Cure: adaptive threshold + channel diversity (Watson & Morgan)")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    random.seed(42)
    demo()
