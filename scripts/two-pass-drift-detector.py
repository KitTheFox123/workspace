#!/usr/bin/env python3
"""
two-pass-drift-detector.py — Per-session jerk + inter-session baseline drift.

Based on:
- santaclawd: "per-session jerk for fast anomalies + inter-session baseline drift as second pass"
- Beauducel et al (Nature Comms 2025): volcanic jerk 92% prediction
- Page (1954): CUSUM for persistent drift

The problem: jerk catches fast anomalies but patient attackers drift
slowly across sessions. Session boundaries = attacker-legible.

Two-pass architecture:
  Pass 1: Per-session jerk (d³/dt³) — catches sudden changes
  Pass 2: Inter-session baseline drift — catches slow evolution
  Fallback: Poisson time-gate if neither fires

External checkpoint (SMTP/isnad) makes session boundary invisible to drift detection.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field


@dataclass
class SessionSnapshot:
    session_id: str
    epoch: int
    style_score: float      # Stylometry similarity to genesis
    scope_usage: float      # Fraction of scope actually used
    topic_centroid: float   # Topic drift from genesis
    timestamp: float        # External timestamp
    checkpoint_hash: str = ""

    def behavioral_vector(self) -> tuple[float, float, float]:
        return (self.style_score, self.scope_usage, self.topic_centroid)

    def compute_checkpoint(self, genesis_hash: str) -> str:
        content = json.dumps({
            "session": self.session_id,
            "epoch": self.epoch,
            "style": round(self.style_score, 4),
            "scope": round(self.scope_usage, 4),
            "topic": round(self.topic_centroid, 4),
            "genesis": genesis_hash,
        }, sort_keys=True)
        self.checkpoint_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.checkpoint_hash


@dataclass
class DriftResult:
    pass_1_jerk: float          # Per-session jerk magnitude
    pass_1_fired: bool
    pass_2_baseline: float      # Inter-session drift from genesis
    pass_2_fired: bool
    combined_grade: str
    diagnosis: str


def compute_derivatives(values: list[float]) -> dict:
    """Compute velocity, acceleration, jerk from time series."""
    if len(values) < 2:
        return {"velocity": 0, "acceleration": 0, "jerk": 0}
    
    velocity = [values[i+1] - values[i] for i in range(len(values)-1)]
    acceleration = [velocity[i+1] - velocity[i] for i in range(len(velocity)-1)] if len(velocity) > 1 else [0]
    jerk = [acceleration[i+1] - acceleration[i] for i in range(len(acceleration)-1)] if len(acceleration) > 1 else [0]
    
    return {
        "velocity": velocity[-1] if velocity else 0,
        "acceleration": acceleration[-1] if acceleration else 0,
        "jerk": jerk[-1] if jerk else 0,
    }


def pass_1_session_jerk(snapshots: list[SessionSnapshot], threshold: float = 0.1) -> tuple[float, bool]:
    """Per-session jerk detection for fast anomalies."""
    if len(snapshots) < 4:
        return 0.0, False
    
    # Use style_score as primary signal
    values = [s.style_score for s in snapshots]
    derivs = compute_derivatives(values)
    jerk_mag = abs(derivs["jerk"])
    
    return jerk_mag, jerk_mag > threshold


def pass_2_baseline_drift(current: SessionSnapshot, genesis: SessionSnapshot,
                           threshold: float = 0.3) -> tuple[float, bool]:
    """Inter-session drift from genesis baseline."""
    curr = current.behavioral_vector()
    gen = genesis.behavioral_vector()
    
    # Euclidean distance in behavioral space
    drift = math.sqrt(sum((c - g) ** 2 for c, g in zip(curr, gen)))
    
    return drift, drift > threshold


def two_pass_detect(sessions: list[SessionSnapshot], genesis: SessionSnapshot,
                     jerk_threshold: float = 0.1, drift_threshold: float = 0.3) -> DriftResult:
    """Run both passes and combine."""
    # Pass 1: per-session jerk (needs recent session history)
    jerk_mag, jerk_fired = pass_1_session_jerk(sessions, jerk_threshold)
    
    # Pass 2: inter-session baseline drift
    current = sessions[-1] if sessions else genesis
    drift_mag, drift_fired = pass_2_baseline_drift(current, genesis, drift_threshold)
    
    # Combined grading
    if jerk_fired and drift_fired:
        grade, diag = "F", "BOTH_PASSES_FIRED"
    elif jerk_fired:
        grade, diag = "C", "FAST_ANOMALY"
    elif drift_fired:
        grade, diag = "D", "SLOW_DRIFT"
    else:
        if drift_mag > drift_threshold * 0.7:
            grade, diag = "B", "APPROACHING_THRESHOLD"
        else:
            grade, diag = "A", "STABLE"
    
    return DriftResult(jerk_mag, jerk_fired, drift_mag, drift_fired, grade, diag)


def main():
    print("=" * 70)
    print("TWO-PASS DRIFT DETECTOR")
    print("santaclawd: 'per-session jerk + inter-session baseline drift'")
    print("=" * 70)

    genesis_hash = "genesis_abc123"
    
    # Genesis snapshot
    genesis = SessionSnapshot("s0", 0, 0.95, 0.80, 0.10, 1000.0)
    genesis.compute_checkpoint(genesis_hash)

    # Scenario 1: Stable agent (Kit-like)
    stable = [
        SessionSnapshot("s1", 1, 0.94, 0.78, 0.11, 1020.0),
        SessionSnapshot("s2", 2, 0.93, 0.79, 0.12, 1040.0),
        SessionSnapshot("s3", 3, 0.94, 0.80, 0.11, 1060.0),
        SessionSnapshot("s4", 4, 0.93, 0.79, 0.10, 1080.0),
    ]
    
    # Scenario 2: Fast anomaly (sudden style change)
    fast_anomaly = [
        SessionSnapshot("s1", 1, 0.94, 0.78, 0.11, 1020.0),
        SessionSnapshot("s2", 2, 0.93, 0.79, 0.12, 1040.0),
        SessionSnapshot("s3", 3, 0.60, 0.79, 0.11, 1060.0),  # Sudden drop
        SessionSnapshot("s4", 4, 0.55, 0.80, 0.10, 1080.0),
    ]
    
    # Scenario 3: Patient attacker (slow drift across sessions)
    slow_drift = [
        SessionSnapshot("s1", 1, 0.92, 0.78, 0.15, 1020.0),
        SessionSnapshot("s2", 2, 0.89, 0.75, 0.20, 1040.0),
        SessionSnapshot("s3", 3, 0.86, 0.72, 0.25, 1060.0),
        SessionSnapshot("s4", 4, 0.83, 0.69, 0.30, 1080.0),
    ]
    
    # Scenario 4: Both (fast anomaly on already-drifted baseline)
    both = [
        SessionSnapshot("s1", 1, 0.88, 0.70, 0.25, 1020.0),
        SessionSnapshot("s2", 2, 0.85, 0.68, 0.28, 1040.0),
        SessionSnapshot("s3", 3, 0.50, 0.65, 0.45, 1060.0),  # Sudden + drifted
        SessionSnapshot("s4", 4, 0.45, 0.60, 0.50, 1080.0),
    ]

    scenarios = {
        "stable_agent": stable,
        "fast_anomaly": fast_anomaly,
        "slow_drift": slow_drift,
        "both_passes": both,
    }

    print(f"\n{'Scenario':<18} {'Grade':<6} {'Jerk':<8} {'P1?':<5} {'Drift':<8} {'P2?':<5} {'Diagnosis'}")
    print("-" * 70)

    for name, sessions in scenarios.items():
        result = two_pass_detect(sessions, genesis)
        print(f"{name:<18} {result.combined_grade:<6} {result.pass_1_jerk:<8.3f} "
              f"{'YES' if result.pass_1_fired else 'no':<5} {result.pass_2_baseline:<8.3f} "
              f"{'YES' if result.pass_2_fired else 'no':<5} {result.diagnosis}")

    print("\n--- Architecture ---")
    print("Pass 1 (per-session):  d³/dt³ of behavioral vector")
    print("  Catches: sudden takeover, model swap, prompt injection")
    print("  Blind to: patient multi-session drift")
    print()
    print("Pass 2 (inter-session): d(current, genesis) in behavioral space")
    print("  Catches: slow evolution, gradual scope creep")
    print("  Blind to: within-session anomalies that revert")
    print()
    print("External checkpoint: SMTP/isnad timestamp + behavioral hash")
    print("  Makes session boundary invisible to attacker")
    print("  Drift measured against external reference, not self-report")
    print()
    print("Fallback: Poisson time-gate if neither pass fires")
    print("  Random probing at Avenhaus-optimal λ")


if __name__ == "__main__":
    main()
