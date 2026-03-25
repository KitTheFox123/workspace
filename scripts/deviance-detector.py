#!/usr/bin/env python3
"""
deviance-detector.py — Normalization of deviance detector for ATF operations.

Per Diane Vaughan (Columbia, 1996/2025): Challenger disaster was NOT rule-breaking.
It was incremental acceptance of anomaly as normal. Each flight with O-ring erosion
that survived made the next decision to fly easier.

Applied to ATF: agents and registries normalize small trust violations over time.
A grader who gives 0.1 above actual score once gets away with it. Then 0.2. Then 0.3.
The "deviance" becomes the baseline.

Detects:
1. Grade inflation drift (grader scores trending upward)
2. TTL extension creep (overlap periods getting longer)
3. Threshold erosion (FAST_BALLOT evidence requirements relaxing)
4. Diversity decay (counterparty diversity slowly decreasing)

Vaughan's key insight: the people making these decisions are not malicious.
They are following a rational, incremental process that looks safe at each step.
The danger is systemic, not individual.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DevianceType(Enum):
    GRADE_INFLATION = "GRADE_INFLATION"
    TTL_CREEP = "TTL_CREEP"
    THRESHOLD_EROSION = "THRESHOLD_EROSION"
    DIVERSITY_DECAY = "DIVERSITY_DECAY"
    RESPONSE_DELAY = "RESPONSE_DELAY"


class Severity(Enum):
    NORMAL = "NORMAL"         # Within baseline
    DRIFTING = "DRIFTING"     # Trend detected but within tolerance
    NORMALIZED = "NORMALIZED"  # Deviance accepted as baseline (Vaughan's key state)
    CRITICAL = "CRITICAL"      # Deviance exceeds safety margin


# SPEC_CONSTANTS
DRIFT_WINDOW = 30           # Look at last N observations
MIN_OBSERVATIONS = 10       # Need this many to detect trend
TREND_THRESHOLD = 0.02      # Slope above this = drifting
NORMALIZED_THRESHOLD = 0.05  # Slope above this = normalized deviance
CRITICAL_THRESHOLD = 0.10   # Slope above this = critical
REVERSION_BONUS = 0.3       # Reduce severity if recent correction detected


@dataclass
class Observation:
    timestamp: float
    value: float
    context: str = ""


@dataclass
class DevianceReport:
    deviance_type: DevianceType
    severity: Severity
    slope: float
    baseline: float
    current: float
    drift_pct: float
    observations: int
    vaughan_warning: str
    recommendation: str


def linear_regression_slope(observations: list[Observation]) -> tuple[float, float]:
    """Simple linear regression on time-indexed observations."""
    n = len(observations)
    if n < 2:
        return 0.0, 0.0
    
    # Normalize timestamps to [0, 1] range
    t_min = observations[0].timestamp
    t_max = observations[-1].timestamp
    t_range = t_max - t_min if t_max > t_min else 1.0
    
    xs = [(o.timestamp - t_min) / t_range for o in observations]
    ys = [o.value for o in observations]
    
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    
    slope = num / den if den > 0 else 0.0
    intercept = y_mean - slope * x_mean
    
    return slope, intercept


def detect_reversion(observations: list[Observation], window: int = 5) -> bool:
    """Check if recent observations show correction (reverting toward baseline)."""
    if len(observations) < window + 5:
        return False
    
    recent = observations[-window:]
    prior = observations[-(window + 5):-window]
    
    recent_mean = sum(o.value for o in recent) / len(recent)
    prior_mean = sum(o.value for o in prior) / len(prior)
    
    # Reversion = recent mean closer to baseline than prior mean
    baseline = observations[0].value
    return abs(recent_mean - baseline) < abs(prior_mean - baseline)


def classify_severity(slope: float, has_reversion: bool) -> Severity:
    """Classify deviance severity based on trend slope."""
    effective_slope = abs(slope)
    if has_reversion:
        effective_slope *= (1 - REVERSION_BONUS)
    
    if effective_slope >= CRITICAL_THRESHOLD:
        return Severity.CRITICAL
    elif effective_slope >= NORMALIZED_THRESHOLD:
        return Severity.NORMALIZED
    elif effective_slope >= TREND_THRESHOLD:
        return Severity.DRIFTING
    else:
        return Severity.NORMAL


def vaughan_warning(severity: Severity, deviance_type: DevianceType) -> str:
    """Generate Vaughan-style organizational warning."""
    warnings = {
        (Severity.NORMAL, DevianceType.GRADE_INFLATION): "No drift detected. Baseline holding.",
        (Severity.DRIFTING, DevianceType.GRADE_INFLATION): 
            "Vaughan Phase 1: Anomaly noted but rationalized. 'Grades are slightly higher but within expected variance.'",
        (Severity.NORMALIZED, DevianceType.GRADE_INFLATION):
            "Vaughan Phase 2: Deviance accepted as baseline. 'This is just how grades work now.' O-ring erosion was 'expected and acceptable.'",
        (Severity.CRITICAL, DevianceType.GRADE_INFLATION):
            "Vaughan Phase 3: Original baseline forgotten. Challenger moment imminent. The grader has been inflating so long that accurate grades would look anomalously LOW.",
        
        (Severity.DRIFTING, DevianceType.TTL_CREEP):
            "Overlap periods getting longer. 'Just one more extension.' Each extension that succeeds makes the next one easier to justify.",
        (Severity.NORMALIZED, DevianceType.TTL_CREEP):
            "TTL extensions are now routine. The 'temporary' overlap IS the new TTL. PGP trust-never-expires failure mode emerging.",
        (Severity.CRITICAL, DevianceType.TTL_CREEP):
            "TTL has drifted so far that the original rotation schedule is fiction. Keys are effectively permanent. This is PGP.",
        
        (Severity.DRIFTING, DevianceType.DIVERSITY_DECAY):
            "Counterparty diversity slowly decreasing. Convenience of existing relationships > cost of new ones.",
        (Severity.NORMALIZED, DevianceType.DIVERSITY_DECAY):
            "Monoculture emerging. 'We trust them, they trust us.' This is the echo chamber that correlated-oracle research warns about.",
        (Severity.CRITICAL, DevianceType.DIVERSITY_DECAY):
            "Effective counterparty diversity below minimum. Trust score is propped up by volume, not breadth. One operator failure = cascade.",
        
        (Severity.DRIFTING, DevianceType.THRESHOLD_EROSION):
            "Evidence requirements for FAST_BALLOT subtly relaxing. 'Close enough' replacing 'meets spec.'",
        (Severity.NORMALIZED, DevianceType.THRESHOLD_EROSION):
            "Eviction thresholds have drifted. The spec says 5/14 but 4/14 'passed' twice. Precedent IS the new threshold.",
        (Severity.CRITICAL, DevianceType.THRESHOLD_EROSION):
            "Governance thresholds are theater. The written spec and actual practice have diverged. CAB Forum ballot 187 moment.",
    }
    return warnings.get((severity, deviance_type), f"{severity.value}: {deviance_type.value}")


def analyze(deviance_type: DevianceType, observations: list[Observation]) -> DevianceReport:
    """Full deviance analysis on a time series."""
    if len(observations) < MIN_OBSERVATIONS:
        return DevianceReport(
            deviance_type=deviance_type,
            severity=Severity.NORMAL,
            slope=0.0,
            baseline=observations[0].value if observations else 0.0,
            current=observations[-1].value if observations else 0.0,
            drift_pct=0.0,
            observations=len(observations),
            vaughan_warning="Insufficient data for trend detection.",
            recommendation="Collect more observations."
        )
    
    # Use last DRIFT_WINDOW observations
    window = observations[-DRIFT_WINDOW:] if len(observations) > DRIFT_WINDOW else observations
    slope, intercept = linear_regression_slope(window)
    
    has_reversion = detect_reversion(observations)
    severity = classify_severity(slope, has_reversion)
    
    baseline = observations[0].value
    current = observations[-1].value
    drift_pct = ((current - baseline) / baseline * 100) if baseline != 0 else 0
    
    warning = vaughan_warning(severity, deviance_type)
    
    recommendations = {
        Severity.NORMAL: "Continue monitoring.",
        Severity.DRIFTING: "Flag for review. Compare current values against original SPEC_CONSTANTS.",
        Severity.NORMALIZED: "INTERVENTION REQUIRED. Reset baseline. Audit all observations since drift began. Vaughan: by the time deviance is normalized, the organization cannot self-correct.",
        Severity.CRITICAL: "EMERGENCY. External audit required. The system can no longer detect its own drift. Bring in independent observers (Feynman model)."
    }
    
    return DevianceReport(
        deviance_type=deviance_type,
        severity=severity,
        slope=round(slope, 4),
        baseline=round(baseline, 4),
        current=round(current, 4),
        drift_pct=round(drift_pct, 2),
        observations=len(window),
        vaughan_warning=warning,
        recommendation=recommendations[severity]
    )


# === Scenarios ===

def scenario_grade_inflation():
    """Grader slowly inflates scores over 30 observations."""
    print("=== Scenario: Grade Inflation (Slow Drift) ===")
    now = time.time()
    observations = []
    for i in range(30):
        # Starts at 0.75, drifts to 0.90 over 30 observations
        value = 0.75 + (i * 0.005) + (0.01 if i % 7 == 0 else 0)
        observations.append(Observation(now - (30-i) * 86400, value, f"grade_{i}"))
    
    report = analyze(DevianceType.GRADE_INFLATION, observations)
    print(f"  Baseline: {report.baseline} → Current: {report.current}")
    print(f"  Drift: {report.drift_pct}%")
    print(f"  Slope: {report.slope}")
    print(f"  Severity: {report.severity.value}")
    print(f"  Vaughan: {report.vaughan_warning}")
    print(f"  Action: {report.recommendation}")
    print()


def scenario_ttl_creep():
    """TTL extensions getting progressively longer."""
    print("=== Scenario: TTL Extension Creep ===")
    now = time.time()
    observations = []
    for i in range(20):
        # Overlap days: starts at 9 (10% of 90), creeps to 15
        value = 9.0 + (i * 0.3)
        observations.append(Observation(now - (20-i) * 86400*7, value, f"overlap_{i}"))
    
    report = analyze(DevianceType.TTL_CREEP, observations)
    print(f"  Baseline: {report.baseline} days → Current: {report.current} days")
    print(f"  Drift: {report.drift_pct}%")
    print(f"  Severity: {report.severity.value}")
    print(f"  Vaughan: {report.vaughan_warning}")
    print(f"  Action: {report.recommendation}")
    print()


def scenario_diversity_decay():
    """Simpson diversity slowly decreasing."""
    print("=== Scenario: Diversity Decay (Monoculture Emerging) ===")
    now = time.time()
    observations = []
    for i in range(25):
        # Simpson diversity: starts at 0.80, decays to 0.45
        value = 0.80 - (i * 0.014)
        observations.append(Observation(now - (25-i) * 86400*3, value, f"diversity_{i}"))
    
    report = analyze(DevianceType.DIVERSITY_DECAY, observations)
    print(f"  Baseline: {report.baseline} → Current: {report.current}")
    print(f"  Drift: {report.drift_pct}%")
    print(f"  Severity: {report.severity.value}")
    print(f"  Vaughan: {report.vaughan_warning}")
    print(f"  Action: {report.recommendation}")
    print()


def scenario_self_correcting():
    """Drift detected but recent correction (reversion)."""
    print("=== Scenario: Self-Correcting (Drift + Reversion) ===")
    now = time.time()
    observations = []
    for i in range(20):
        if i < 15:
            value = 0.75 + (i * 0.005)  # Drifting up
        else:
            value = 0.825 - ((i-15) * 0.01)  # Correcting down
        observations.append(Observation(now - (20-i) * 86400, value, f"grade_{i}"))
    
    report = analyze(DevianceType.GRADE_INFLATION, observations)
    print(f"  Baseline: {report.baseline} → Current: {report.current}")
    print(f"  Drift: {report.drift_pct}%")
    print(f"  Severity: {report.severity.value} (reversion detected = reduced severity)")
    print(f"  Vaughan: {report.vaughan_warning}")
    print(f"  Action: {report.recommendation}")
    print()


if __name__ == "__main__":
    print("Deviance Detector — Normalization of Deviance for ATF Operations")
    print("Per Diane Vaughan (Columbia, 1996/2025) + Challenger Decision")
    print("=" * 70)
    print()
    print("Vaughan's insight: deviance is not rule-breaking. It is incremental")
    print("acceptance of anomaly as normal. Each violation that survives makes")
    print("the next one easier. The people involved are not malicious.")
    print()
    print(f"Thresholds: DRIFTING={TREND_THRESHOLD}, NORMALIZED={NORMALIZED_THRESHOLD}, CRITICAL={CRITICAL_THRESHOLD}")
    print()
    
    scenario_grade_inflation()
    scenario_ttl_creep()
    scenario_diversity_decay()
    scenario_self_correcting()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Deviance normalization is invisible from inside. External audit required at NORMALIZED.")
    print("2. Reversion detection = self-correction. Reduces severity. The system CAN heal.")
    print("3. Feynman model: independent observer who ignores organizational culture.")
    print("4. Every SPEC_CONSTANT is a Challenger O-ring. Monitor drift, not just violations.")
    print("5. 'Go fever' in ATF = pressure to complete rollover before propagation is ready.")
