#!/usr/bin/env python3
"""
ewma-jitter-detector.py — Adaptive heartbeat anomaly detection.

EWMA (Roberts 1959) + Shewhart control charts (1931) for heartbeat jitter.
Risk-tiered N window: L0=N4 (2h lag), L2=N6 (30m lag at 5m intervals).

Key insight from hash + santaclawd thread: false positive floor is the
design parameter, not N itself.

Usage: python3 ewma-jitter-detector.py
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class EWMADetector:
    alpha: float = 0.3  # smoothing factor
    sigma_threshold: float = 3.0  # Shewhart 3-sigma
    warmup: int = 4  # cold-start N
    max_window: int = 10  # stable N
    
    _history: list = field(default_factory=list)
    _count: int = 0
    _alerts: list = field(default_factory=list)
    
    def update(self, interval: float) -> dict:
        self._count += 1
        self._history.append(interval)
        
        # Keep sliding window
        window = self._history[-self.max_window:]
        n_eff = len(window)
        
        if n_eff < self.warmup:
            return {"status": "WARMUP", "n": n_eff}
        
        # Use window EXCLUDING current for baseline
        baseline = window[:-1]
        mean = sum(baseline) / len(baseline)
        variance = sum((x - mean) ** 2 for x in baseline) / len(baseline)
        sigma = math.sqrt(variance) if variance > 0 else mean * 0.1
        
        # Minimum sigma floor: 10% of mean (natural jitter)
        sigma = max(sigma, mean * 0.1)
        
        z_score = abs(interval - mean) / sigma
        
        if z_score > self.sigma_threshold:
            alert = {
                "status": "ALERT",
                "interval": interval,
                "expected": round(mean, 1),
                "z_score": round(z_score, 2),
                "sigma": round(sigma, 2),
                "n_eff": n_eff,
                "beat": self._count
            }
            self._alerts.append(alert)
            return alert
        
        return {
            "status": "OK",
            "interval": round(interval, 1),
            "mean": round(mean, 1),
            "z_score": round(z_score, 2),
            "n_eff": n_eff
        }


@dataclass
class RiskTier:
    name: str
    heartbeat_min: float  # minutes
    n_cold: int
    n_stable: int
    detection_lag_min: float  # worst case

    @property
    def detection_lag_str(self) -> str:
        if self.detection_lag_min >= 60:
            return f"{self.detection_lag_min/60:.1f}h"
        return f"{self.detection_lag_min:.0f}m"


TIERS = [
    RiskTier("L0_free", 30, 4, 10, 300),     # 5h lag
    RiskTier("L1_standard", 20, 4, 8, 160),   # 2.7h lag
    RiskTier("L2_high", 5, 6, 6, 30),          # 30m lag
    RiskTier("L3_critical", 1, 8, 8, 8),       # 8m lag
]


def simulate_tier(tier: RiskTier, n_beats: int = 20, anomaly_at: int = 15):
    """Simulate heartbeat stream with anomaly injection."""
    detector = EWMADetector(warmup=tier.n_cold, max_window=tier.n_stable)
    
    print(f"\n{'─'*50}")
    print(f"Tier: {tier.name} | Interval: {tier.heartbeat_min}m | Detection: {tier.detection_lag_str}")
    
    alerts = 0
    for i in range(1, n_beats + 1):
        if i == anomaly_at:
            # Inject anomaly: 5x normal interval (agent went silent)
            interval = tier.heartbeat_min * 5
        else:
            # Normal jitter: ±10% 
            jitter = random.gauss(0, tier.heartbeat_min * 0.1)
            interval = tier.heartbeat_min + jitter
        
        result = detector.update(interval)
        
        if result["status"] == "ALERT":
            alerts += 1
            print(f"  Beat {i}: ⚠️  ALERT z={result['z_score']} (interval={result['interval']:.0f}m vs expected={result['expected']:.0f}m)")
        elif i == anomaly_at and result["status"] != "ALERT":
            print(f"  Beat {i}: ❌ MISSED (interval={interval:.0f}m, status={result['status']})")
    
    detected = alerts > 0
    print(f"  Result: {'DETECTED ✓' if detected else 'MISSED ✗'} | Alerts: {alerts}/{n_beats}")
    return detected


def demo():
    print("=" * 60)
    print("EWMA Heartbeat Jitter Detector")
    print("Roberts 1959 + Shewhart 1931 | Risk-Tiered N Window")
    print("=" * 60)
    
    random.seed(42)
    
    results = {}
    for tier in TIERS:
        detected = simulate_tier(tier, n_beats=20, anomaly_at=15)
        results[tier.name] = detected
    
    # Summary
    print(f"\n{'='*60}")
    print("TIER SUMMARY:")
    for tier in TIERS:
        status = "✓" if results[tier.name] else "✗"
        print(f"  {tier.name:15s} | {tier.heartbeat_min:4.0f}m interval | {tier.detection_lag_str:>5s} lag | {status}")
    
    print(f"\nKEY INSIGHT:")
    print(f"  False positive floor = design parameter, not N.")
    print(f"  L0 at 5h lag is fine — L0 isn't protecting $600M bridges.")
    print(f"  L2 at 30m matches Ronin's 48min drain window.")
    print(f"{'='*60}")


if __name__ == "__main__":
    demo()
