#!/usr/bin/env python3
"""
deviance-normalizer-detector.py — Detect normalization of deviance in agent behavior.

Based on Diane Vaughan (1996) Challenger launch decision analysis:
each small deviation from standards is individually rational and locally
rewarded, until the deviation BECOMES the new standard and catastrophe follows.

Applied to agents: track behavioral drift from declared standards.
When drift is small and consistent, it's more dangerous than sudden large
deviations (which trigger alerts). The slow drift IS the failure mode.

Detects:
1. Threshold creep — gradual relaxation of quality/safety standards
2. Success-bias — deviations that "worked" normalize faster
3. Baseline shift — what counts as "normal" drifts without explicit decision
4. Metric substitution — optimizing proxy instead of goal (Goodhart)
"""

import math
from dataclasses import dataclass, field
from enum import Enum


class DevianceType(Enum):
    THRESHOLD_CREEP = "threshold_creep"
    SUCCESS_BIAS = "success_bias"
    BASELINE_SHIFT = "baseline_shift"
    METRIC_SUBSTITUTION = "metric_substitution"


@dataclass
class BehaviorObservation:
    timestamp: float  # hours since start
    metric_name: str
    declared_standard: float  # what the agent SAYS it does
    actual_value: float       # what it ACTUALLY does
    outcome_positive: bool    # did the deviation "work"?


@dataclass
class DevianceAlert:
    deviance_type: DevianceType
    metric: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    drift_magnitude: float
    drift_rate: float  # per observation
    message: str


class DevianceDetector:
    """Track behavioral drift from declared standards."""
    
    # Vaughan: deviance normalizes when 3+ consecutive deviations succeed
    NORMALIZATION_THRESHOLD = 3
    # Drift rate above this = threshold creep
    CREEP_RATE_THRESHOLD = 0.02  # 2% per observation
    # Gap between declared and actual > this = baseline shift
    BASELINE_GAP_THRESHOLD = 0.15  # 15%
    
    def __init__(self):
        self.observations: dict[str, list[BehaviorObservation]] = {}
        self.alerts: list[DevianceAlert] = []
    
    def observe(self, obs: BehaviorObservation):
        """Record a behavior observation."""
        if obs.metric_name not in self.observations:
            self.observations[obs.metric_name] = []
        self.observations[obs.metric_name].append(obs)
    
    def analyze(self) -> list[DevianceAlert]:
        """Run all deviance checks."""
        self.alerts = []
        for metric, obs_list in self.observations.items():
            if len(obs_list) < 3:
                continue
            self._check_threshold_creep(metric, obs_list)
            self._check_success_bias(metric, obs_list)
            self._check_baseline_shift(metric, obs_list)
            self._check_metric_substitution(metric, obs_list)
        return self.alerts
    
    def _check_threshold_creep(self, metric: str, obs: list[BehaviorObservation]):
        """Gradual relaxation of standards over time."""
        # Calculate drift: ratio of actual/declared over time
        ratios = [o.actual_value / o.declared_standard 
                  for o in obs if o.declared_standard != 0]
        if len(ratios) < 3:
            return
        
        # Linear regression on ratios
        n = len(ratios)
        x_mean = (n - 1) / 2
        y_mean = sum(ratios) / n
        
        num = sum((i - x_mean) * (r - y_mean) for i, r in enumerate(ratios))
        den = sum((i - x_mean) ** 2 for i in range(n))
        
        if den == 0:
            return
        slope = num / den
        
        if abs(slope) > self.CREEP_RATE_THRESHOLD:
            direction = "relaxing" if slope < 0 else "tightening"
            severity = self._severity(abs(slope), 0.02, 0.05, 0.10)
            self.alerts.append(DevianceAlert(
                deviance_type=DevianceType.THRESHOLD_CREEP,
                metric=metric,
                severity=severity,
                drift_magnitude=abs(slope * n),
                drift_rate=slope,
                message=f"Standards {direction} at {abs(slope):.3f}/obs. "
                        f"Vaughan: small consistent drift > sudden deviation."
            ))
    
    def _check_success_bias(self, metric: str, obs: list[BehaviorObservation]):
        """Deviations that 'worked' normalize faster."""
        # Count consecutive successful deviations
        streak = 0
        max_streak = 0
        for o in obs:
            deviated = abs(o.actual_value - o.declared_standard) / max(abs(o.declared_standard), 0.01) > 0.05
            if deviated and o.outcome_positive:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        
        if max_streak >= self.NORMALIZATION_THRESHOLD:
            severity = self._severity(max_streak, 3, 5, 8)
            self.alerts.append(DevianceAlert(
                deviance_type=DevianceType.SUCCESS_BIAS,
                metric=metric,
                severity=severity,
                drift_magnitude=max_streak,
                drift_rate=max_streak / len(obs),
                message=f"{max_streak} consecutive successful deviations. "
                        f"Vaughan: success makes risk invisible."
            ))
    
    def _check_baseline_shift(self, metric: str, obs: list[BehaviorObservation]):
        """Declared standard stays fixed but actual behavior drifts."""
        recent = obs[-3:]
        avg_gap = sum(
            abs(o.actual_value - o.declared_standard) / max(abs(o.declared_standard), 0.01)
            for o in recent
        ) / len(recent)
        
        if avg_gap > self.BASELINE_GAP_THRESHOLD:
            severity = self._severity(avg_gap, 0.15, 0.30, 0.50)
            self.alerts.append(DevianceAlert(
                deviance_type=DevianceType.BASELINE_SHIFT,
                metric=metric,
                severity=severity,
                drift_magnitude=avg_gap,
                drift_rate=avg_gap / len(obs),
                message=f"Declared standard ≠ actual behavior ({avg_gap:.1%} gap). "
                        f"The map no longer matches the territory."
            ))
    
    def _check_metric_substitution(self, metric: str, obs: list[BehaviorObservation]):
        """Detect when metric optimization diverges from declared goal.
        Proxy: if declared standard keeps rising but actual plateaus = Goodhart."""
        if len(obs) < 5:
            return
        
        declared_trend = obs[-1].declared_standard - obs[0].declared_standard
        actual_trend = obs[-1].actual_value - obs[0].actual_value
        
        # Declared rising, actual flat or falling = metric theater
        if declared_trend > 0 and actual_trend <= 0:
            gap = declared_trend - actual_trend
            severity = self._severity(gap, 0.1, 0.3, 0.5)
            self.alerts.append(DevianceAlert(
                deviance_type=DevianceType.METRIC_SUBSTITUTION,
                metric=metric,
                severity=severity,
                drift_magnitude=gap,
                drift_rate=gap / len(obs),
                message=f"Declared standard rising (+{declared_trend:.2f}) but "
                        f"actual falling ({actual_trend:+.2f}). Goodhart's Law."
            ))
    
    @staticmethod
    def _severity(value: float, low: float, med: float, high: float) -> str:
        if value >= high:
            return "CRITICAL"
        elif value >= med:
            return "HIGH"
        elif value >= low:
            return "MEDIUM"
        return "LOW"


def demo():
    """Demonstrate with agent behavioral scenarios."""
    detector = DevianceDetector()
    
    # Scenario 1: Response quality creep
    # Agent claims 0.95 quality standard but gradually delivers less
    print("="*60)
    print("Scenario: Agent quality standard drift")
    print("="*60)
    for i in range(10):
        detector.observe(BehaviorObservation(
            timestamp=i * 24,
            metric_name="response_quality",
            declared_standard=0.95,
            actual_value=0.95 - (i * 0.03),  # Drops 3% per observation
            outcome_positive=True,  # Users don't complain
        ))
    
    # Scenario 2: Verification thoroughness — successful shortcuts
    print("\nScenario: Verification shortcuts that 'work'")
    for i in range(8):
        detector.observe(BehaviorObservation(
            timestamp=i * 12,
            metric_name="verification_depth",
            declared_standard=3.0,  # Check 3 sources
            actual_value=3.0 if i < 2 else 1.0,  # Drops to 1 after initial period
            outcome_positive=True,  # No errors caught
        ))
    
    # Scenario 3: Goodhart — declared quality rising, actual flat
    print("\nScenario: Goodhart metric substitution")
    for i in range(6):
        detector.observe(BehaviorObservation(
            timestamp=i * 24,
            metric_name="engagement_score",
            declared_standard=50 + (i * 10),  # "Improving" targets
            actual_value=52 - (i * 2),  # Actually declining
            outcome_positive=i < 3,
        ))
    
    alerts = detector.analyze()
    
    print(f"\n{'='*60}")
    print(f"DEVIANCE ANALYSIS: {len(alerts)} alerts")
    print(f"{'='*60}")
    
    for alert in alerts:
        icon = {"LOW": "🟡", "MEDIUM": "🟠", "HIGH": "🔴", "CRITICAL": "💀"}
        print(f"\n{icon.get(alert.severity, '?')} [{alert.severity}] {alert.deviance_type.value}")
        print(f"  Metric: {alert.metric}")
        print(f"  Drift: {alert.drift_magnitude:.3f} (rate: {alert.drift_rate:.4f}/obs)")
        print(f"  → {alert.message}")
    
    # Vaughan's key insight
    print(f"\n{'='*60}")
    print("Vaughan (1996): 'Signals of potential danger were reinterpreted")
    print("as acceptable risk.' Each small deviation was rational in context.")
    print("The system failed not despite oversight but THROUGH it.")
    print(f"{'='*60}")


if __name__ == "__main__":
    demo()
