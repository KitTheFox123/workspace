#!/usr/bin/env python3
"""adaptive-sampling-mmd.py — Dynamic attestation sampling rate based on anomaly state.

Implements santaclawd's suggestion: attestation-ttl-optimizer should use dynamic
sampling, not static intervals. Shorter intervals during anomaly windows.

Three modes:
  - Normal: baseline interval (e.g., 30min)
  - Alert: 2x shorter (CUSUM anomaly detected)
  - Critical: 4x shorter (Schmitt trigger zone change)

Based on CT MMD model — detection-latency SLA that adapts to risk.

Usage:
    python3 adaptive-sampling-mmd.py [--demo] [--baseline MINUTES]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import List


class AnomalyState(Enum):
    NORMAL = "normal"
    ALERT = "alert"       # CUSUM alarm
    CRITICAL = "critical"  # Schmitt trigger zone change


@dataclass
class SamplingConfig:
    baseline_interval_min: float  # Normal interval in minutes
    alert_multiplier: float = 0.5    # 2x faster
    critical_multiplier: float = 0.25  # 4x faster
    cooldown_cycles: int = 5  # Cycles at lower state before de-escalation


@dataclass  
class SamplingState:
    current_state: str
    current_interval_min: float
    cycles_in_state: int
    cusum_value: float
    cusum_threshold: float
    schmitt_zone: str
    total_samples: int
    total_anomalies: int


class AdaptiveSampler:
    """MMD-inspired adaptive sampling rate controller."""
    
    def __init__(self, config: SamplingConfig):
        self.config = config
        self.state = AnomalyState.NORMAL
        self.cycles_in_state = 0
        self.cusum_value = 0.0
        self.cusum_threshold = 4.0  # h=4σ
        self.schmitt_zone = "trusted"
        self.total_samples = 0
        self.total_anomalies = 0
        self.history: List[dict] = []
    
    @property
    def current_interval(self) -> float:
        if self.state == AnomalyState.CRITICAL:
            return self.config.baseline_interval_min * self.config.critical_multiplier
        elif self.state == AnomalyState.ALERT:
            return self.config.baseline_interval_min * self.config.alert_multiplier
        return self.config.baseline_interval_min
    
    def update(self, drift_score: float, zone_change: bool = False) -> dict:
        """Process new observation, update state and interval."""
        self.total_samples += 1
        old_state = self.state
        
        # CUSUM update
        self.cusum_value = max(0, self.cusum_value + drift_score - 0.5)
        cusum_alarm = self.cusum_value > self.cusum_threshold
        
        if cusum_alarm:
            self.total_anomalies += 1
        
        # State transitions
        if zone_change:
            self.state = AnomalyState.CRITICAL
            self.cycles_in_state = 0
        elif cusum_alarm and self.state == AnomalyState.NORMAL:
            self.state = AnomalyState.ALERT
            self.cycles_in_state = 0
        elif cusum_alarm and self.state == AnomalyState.ALERT:
            self.state = AnomalyState.CRITICAL
            self.cycles_in_state = 0
        elif not cusum_alarm:
            self.cycles_in_state += 1
            if self.cycles_in_state >= self.config.cooldown_cycles:
                if self.state == AnomalyState.CRITICAL:
                    self.state = AnomalyState.ALERT
                    self.cycles_in_state = 0
                elif self.state == AnomalyState.ALERT:
                    self.state = AnomalyState.NORMAL
                    self.cycles_in_state = 0
        
        if zone_change:
            self.schmitt_zone = "quarantine" if self.schmitt_zone == "trusted" else "trusted"
        
        record = {
            "sample": self.total_samples,
            "drift_score": round(drift_score, 3),
            "cusum": round(self.cusum_value, 3),
            "state": self.state.value,
            "interval_min": round(self.current_interval, 1),
            "zone": self.schmitt_zone,
            "transition": old_state.value != self.state.value
        }
        self.history.append(record)
        return record
    
    def get_state(self) -> SamplingState:
        return SamplingState(
            current_state=self.state.value,
            current_interval_min=round(self.current_interval, 1),
            cycles_in_state=self.cycles_in_state,
            cusum_value=round(self.cusum_value, 3),
            cusum_threshold=self.cusum_threshold,
            schmitt_zone=self.schmitt_zone,
            total_samples=self.total_samples,
            total_anomalies=self.total_anomalies
        )
    
    def grade(self) -> str:
        """Grade the sampling strategy's responsiveness."""
        if self.total_samples == 0:
            return "N/A"
        anomaly_rate = self.total_anomalies / self.total_samples
        transitions = sum(1 for r in self.history if r["transition"])
        
        if anomaly_rate < 0.1 and transitions < 3:
            return "A"
        elif anomaly_rate < 0.2:
            return "B"
        elif anomaly_rate < 0.4:
            return "C"
        else:
            return "F"


def demo():
    """Demo: normal → alert → critical → cooldown."""
    config = SamplingConfig(baseline_interval_min=30)
    sampler = AdaptiveSampler(config)
    
    # Scenario: 10 normal, 5 drifting, zone change, 10 cooldown
    scenario = (
        [0.1] * 10 +   # Normal operation
        [0.8] * 5 +    # Drift begins (CUSUM accumulates)
        [0.9] * 3 +    # Continued drift
        [0.1] * 15     # Recovery
    )
    zone_changes = {18: True}  # Zone change at sample 18
    
    print("=" * 70)
    print("ADAPTIVE SAMPLING MMD — Dynamic Attestation Intervals")
    print("=" * 70)
    print(f"Baseline: {config.baseline_interval_min}min | "
          f"Alert: {config.baseline_interval_min * config.alert_multiplier}min | "
          f"Critical: {config.baseline_interval_min * config.critical_multiplier}min")
    print()
    print(f"{'#':>3} {'Drift':>6} {'CUSUM':>7} {'State':>10} {'Interval':>10} {'Zone':>12}")
    print("-" * 70)
    
    for i, drift in enumerate(scenario):
        zc = zone_changes.get(i + 1, False)
        result = sampler.update(drift, zone_change=zc)
        marker = " <<<" if result["transition"] else ""
        print(f"{result['sample']:>3} {drift:>6.2f} {result['cusum']:>7.3f} "
              f"{result['state']:>10} {result['interval_min']:>8.1f}min "
              f"{result['zone']:>12}{marker}")
    
    state = sampler.get_state()
    print()
    print(f"Grade: {sampler.grade()}")
    print(f"Total samples: {state.total_samples}")
    print(f"Total anomalies: {state.total_anomalies}")
    print(f"Final state: {state.current_state} ({state.current_interval_min}min)")
    
    # Compare: static vs adaptive total samples in same time window
    total_time = sum(config.baseline_interval_min for _ in scenario)  # Static
    adaptive_time = sum(r["interval_min"] for r in sampler.history)
    static_samples = len(scenario)
    print(f"\nStatic: {static_samples} samples at {config.baseline_interval_min}min = {total_time}min")
    print(f"Adaptive: {static_samples} samples in {adaptive_time:.0f}min total "
          f"({adaptive_time/static_samples:.1f}min avg)")
    print(f"Sampling density increase during anomaly: "
          f"{config.baseline_interval_min / (config.baseline_interval_min * config.critical_multiplier):.0f}x")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adaptive sampling MMD for attestation")
    parser.add_argument("--demo", action="store_true", help="Run demo scenario")
    parser.add_argument("--baseline", type=float, default=30, help="Baseline interval (minutes)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        config = SamplingConfig(baseline_interval_min=args.baseline)
        sampler = AdaptiveSampler(config)
        # Quick demo data
        for d in [0.1]*5 + [0.8]*5 + [0.1]*5:
            sampler.update(d)
        print(json.dumps(asdict(sampler.get_state()), indent=2))
    else:
        demo()
