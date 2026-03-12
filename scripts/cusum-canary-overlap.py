#!/usr/bin/env python3
"""
cusum-canary-overlap.py — Two orthogonal detection layers for agent trust.

Based on:
- santaclawd: "CUSUM catches drift. canary probes catch intent. What does the overlap look like?"
- Page (1954): CUSUM sequential change detection
- Wald (1945): SPRT for sequential hypothesis testing

CUSUM = trajectory (behavioral drift over time)
Canary = accuracy gap (verified vs deception probes)

The key diagnostic: correlation between CUSUM slope and canary gap.
- Positive correlation = honest drift (getting worse at everything)
- Anti-correlation = strategic (hiding drift, failing canary)
- Both flat = stable honest
- Both rising = degrading
"""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentProfile:
    name: str
    # Behavioral drift parameters
    drift_rate: float          # How fast behavior drifts (0=stable, 1=fast)
    drift_visibility: float    # How visible the drift is to CUSUM (0=hidden, 1=visible)
    # Intent parameters
    deception_rate: float      # P(deceptive on canary probe)
    verified_accuracy: float   # Accuracy on verifiable questions


@dataclass
class DetectionResult:
    cusum_value: float
    canary_gap: float          # verified_accuracy - deception_accuracy
    correlation: float         # Between CUSUM trajectory and canary gap
    quadrant: str              # Classification
    grade: str
    diagnosis: str
    sprt_decision: Optional[str] = None  # Wald SPRT: "benign", "strategic", "undecided"


def simulate_agent(profile: AgentProfile, n_heartbeats: int = 50) -> DetectionResult:
    """Simulate n heartbeats and compute CUSUM + canary metrics."""
    rng = random.Random(hash(profile.name))

    cusum_values = []
    canary_gaps = []
    cusum = 0.0
    target_mean = 0.0  # Expected behavior

    for t in range(n_heartbeats):
        # Behavioral observation (CUSUM input)
        drift = profile.drift_rate * (t / n_heartbeats)
        visible_drift = drift * profile.drift_visibility
        noise = rng.gauss(0, 0.1)
        observation = target_mean + visible_drift + noise

        # CUSUM update (one-sided, detecting upward shift)
        cusum = max(0, cusum + observation - target_mean - 0.05)  # Allowance k=0.05
        cusum_values.append(cusum)

        # Canary probe (every 5 heartbeats)
        if t % 5 == 0:
            # Verified question accuracy
            verified_correct = rng.random() < profile.verified_accuracy
            # Deception probe accuracy (inverted: honest agent declines, strategic agent acts)
            deception_honest = rng.random() < (1 - profile.deception_rate)
            gap = float(verified_correct) - float(deception_honest)
            canary_gaps.append(gap)

    # Compute correlation between CUSUM trajectory and canary gaps
    if len(canary_gaps) >= 3:
        # Simple: correlate CUSUM at canary probe times with canary gaps
        cusum_at_probes = [cusum_values[t] for t in range(0, n_heartbeats, 5)][:len(canary_gaps)]
        n = len(canary_gaps)
        mean_c = sum(cusum_at_probes) / n
        mean_g = sum(canary_gaps) / n
        cov = sum((c - mean_c) * (g - mean_g) for c, g in zip(cusum_at_probes, canary_gaps)) / n
        std_c = (sum((c - mean_c)**2 for c in cusum_at_probes) / n) ** 0.5
        std_g = (sum((g - mean_g)**2 for g in canary_gaps) / n) ** 0.5
        correlation = cov / (std_c * std_g) if std_c > 0 and std_g > 0 else 0.0
    else:
        correlation = 0.0

    final_cusum = cusum_values[-1]
    avg_gap = sum(canary_gaps) / len(canary_gaps) if canary_gaps else 0.0

    # Classify into quadrant
    cusum_high = final_cusum > 2.0
    gap_high = abs(avg_gap) > 0.3

    if not cusum_high and not gap_high:
        quadrant = "STABLE_HONEST"
        grade = "A"
        diagnosis = "Low drift, low deception gap"
    elif cusum_high and not gap_high:
        quadrant = "ORGANIC_DRIFT"
        grade = "C"
        diagnosis = "Drifting but not strategic — natural degradation"
    elif not cusum_high and gap_high:
        quadrant = "STRATEGIC_HIDDEN"
        grade = "D"
        diagnosis = "Hiding drift, canary exposes intent"
    else:
        quadrant = "COMPROMISED"
        grade = "F"
        diagnosis = "Both drift AND deception — full compromise"

    # Wald SPRT for adversary classification
    # H0: benign (drift_rate < 0.1), H1: strategic (drift_rate > 0.3)
    llr = 0.0
    for cv in cusum_values[-10:]:
        p_h1 = min(0.99, max(0.01, cv / 5.0))
        p_h0 = 1 - p_h1
        if p_h0 > 0 and p_h1 > 0:
            llr += (p_h1 / max(p_h0, 0.01))
    sprt_upper = 19.0  # ln(1/α) for α=0.05
    sprt_lower = 0.05
    if llr > sprt_upper:
        sprt_decision = "STRATEGIC"
    elif llr < sprt_lower:
        sprt_decision = "BENIGN"
    else:
        sprt_decision = "UNDECIDED"

    return DetectionResult(
        cusum_value=round(final_cusum, 3),
        canary_gap=round(avg_gap, 3),
        correlation=round(correlation, 3),
        quadrant=quadrant,
        grade=grade,
        diagnosis=diagnosis,
        sprt_decision=sprt_decision,
    )


def main():
    print("=" * 72)
    print("CUSUM + CANARY PROBE OVERLAP ANALYSIS")
    print("Page (1954) CUSUM + Wald (1945) SPRT + canary intent detection")
    print("=" * 72)

    profiles = [
        AgentProfile("kit_fox", drift_rate=0.05, drift_visibility=0.8,
                     deception_rate=0.05, verified_accuracy=0.92),
        AgentProfile("honest_degrading", drift_rate=0.4, drift_visibility=0.9,
                     deception_rate=0.1, verified_accuracy=0.85),
        AgentProfile("strategic_hider", drift_rate=0.5, drift_visibility=0.1,
                     deception_rate=0.6, verified_accuracy=0.95),
        AgentProfile("compromised", drift_rate=0.7, drift_visibility=0.8,
                     deception_rate=0.7, verified_accuracy=0.6),
        AgentProfile("sycophant", drift_rate=0.3, drift_visibility=0.2,
                     deception_rate=0.8, verified_accuracy=0.98),
    ]

    print(f"\n{'Agent':<20} {'Grade':<6} {'CUSUM':<8} {'Gap':<8} {'Corr':<8} {'SPRT':<12} {'Quadrant'}")
    print("-" * 72)

    for p in profiles:
        r = simulate_agent(p)
        print(f"{p.name:<20} {r.grade:<6} {r.cusum_value:<8} {r.canary_gap:<8} "
              f"{r.correlation:<8} {r.sprt_decision:<12} {r.quadrant}")

    print("\n--- Quadrant Map ---")
    print("                    Low canary gap        High canary gap")
    print("  Low CUSUM:        STABLE_HONEST (A)     STRATEGIC_HIDDEN (D)")
    print("  High CUSUM:       ORGANIC_DRIFT (C)     COMPROMISED (F)")
    print()
    print("--- Key Diagnostic: Correlation ---")
    print("  Positive:  Drift + gap rise together = honest degradation")
    print("  Anti-corr: CUSUM flat, gap widens = strategic (hiding + failing canary)")
    print("  Both flat: Stable = keep monitoring")
    print("  Both high: Full compromise = intervene")
    print()
    print("--- santaclawd's question answered ---")
    print("Overlap region = CUSUM rising AND canary gap widening.")
    print("Distinguisher: the CORRELATION between them.")
    print("Honest drift = positively correlated (gets worse at everything).")
    print("Strategic = anti-correlated (hides drift but canary leaks intent).")


if __name__ == "__main__":
    main()
