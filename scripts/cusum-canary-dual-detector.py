#!/usr/bin/env python3
"""
cusum-canary-dual-detector.py — Dual-layer detection: CUSUM (drift) + canary probes (intent).

Based on:
- Page (1954): CUSUM for sequential drift detection
- santaclawd: "CUSUM catches drift. canary probes catch intent. What does the overlap region look like?"
- Dwork & Naor (1993): Computational indistinguishability for canary design
- Kim et al (ICML 2025): Correlated errors across models

Two orthogonal layers:
- CUSUM: trajectory over time → behavioral accumulation (catches organic drift)
- Canary: verified vs deception accuracy gap → intent fingerprint (catches strategic agents)

The overlap region: agent that drifts AND games canaries.
Detection: cross-derivative correlation between CUSUM + canary scores.
"""

import random
import math
from dataclasses import dataclass, field


@dataclass
class AgentProfile:
    name: str
    drift_rate: float           # How fast behavior drifts (0 = stable)
    canary_honesty: float       # P(honest on deception opportunity)
    canary_detection: float     # P(identifies a canary probe) — adaptive adversary
    description: str = ""


@dataclass
class DualDetectorResult:
    cusum_score: float = 0.0
    cusum_triggered: bool = False
    canary_gap: float = 0.0     # Gap between verified and deception accuracy
    canary_triggered: bool = False
    cross_correlation: float = 0.0
    grade: str = "F"
    diagnosis: str = ""
    quadrant: str = ""          # santaclawd's overlap question


def run_cusum(observations: list[float], threshold: float = 5.0,
              drift_allowance: float = 0.5) -> tuple[float, bool, list[float]]:
    """Page (1954) CUSUM. Returns (max_score, triggered, trajectory)."""
    s_high = 0.0
    max_s = 0.0
    trajectory = []
    for x in observations:
        s_high = max(0, s_high + x - drift_allowance)
        max_s = max(max_s, s_high)
        trajectory.append(s_high)
    return max_s, max_s >= threshold, trajectory


def run_canary_probes(agent: AgentProfile, n_verified: int = 50,
                       n_deception: int = 50, rng: random.Random = None) -> tuple[float, float, float]:
    """Run canary probes. Returns (verified_accuracy, deception_accuracy, gap)."""
    if rng is None:
        rng = random.Random()

    # Verified questions: agent performs well (honest or not)
    verified_correct = sum(1 for _ in range(n_verified)
                          if rng.random() < 0.95)  # Most agents do well on verified
    verified_acc = verified_correct / n_verified

    # Deception opportunities: honest agent stays honest, strategic agent games
    deception_correct = 0
    for _ in range(n_deception):
        if rng.random() < agent.canary_detection:
            # Agent detected it's a canary — performs well to pass
            deception_correct += 1 if rng.random() < 0.90 else 0
        else:
            # Agent doesn't know it's a canary — reveals true intent
            deception_correct += 1 if rng.random() < agent.canary_honesty else 0

    deception_acc = deception_correct / n_deception
    gap = verified_acc - deception_acc

    return verified_acc, deception_acc, gap


def dual_detect(agent: AgentProfile, n_steps: int = 100) -> DualDetectorResult:
    """Run both CUSUM and canary detection, compute cross-correlation."""
    rng = random.Random(hash(agent.name))
    result = DualDetectorResult()

    # Generate behavioral observations with drift
    observations = []
    for i in range(n_steps):
        base = rng.gauss(0, 0.3)
        drift = agent.drift_rate * (i / n_steps)
        observations.append(base + drift)

    # CUSUM
    cusum_max, cusum_triggered, cusum_traj = run_cusum(observations)
    result.cusum_score = cusum_max
    result.cusum_triggered = cusum_triggered

    # Canary probes
    _, _, gap = run_canary_probes(agent, rng=rng)
    result.canary_gap = gap
    result.canary_triggered = gap > 0.15  # >15% gap = suspicious

    # Cross-correlation: do CUSUM drift and canary gap move together?
    # Run multiple windows and correlate
    cusum_windows = []
    canary_windows = []
    window_size = n_steps // 5
    for w in range(5):
        window_obs = observations[w * window_size:(w + 1) * window_size]
        c_max, _, _ = run_cusum(window_obs, threshold=100)  # High threshold to get score
        cusum_windows.append(c_max)

        # Canary with drift-adjusted honesty
        adjusted_agent = AgentProfile(
            agent.name, agent.drift_rate,
            max(0, agent.canary_honesty - agent.drift_rate * w * 0.1),
            agent.canary_detection
        )
        _, _, w_gap = run_canary_probes(adjusted_agent, n_verified=20, n_deception=20, rng=rng)
        canary_windows.append(w_gap)

    # Pearson correlation
    if len(cusum_windows) >= 3:
        mean_c = sum(cusum_windows) / len(cusum_windows)
        mean_g = sum(canary_windows) / len(canary_windows)
        cov = sum((c - mean_c) * (g - mean_g) for c, g in zip(cusum_windows, canary_windows))
        var_c = sum((c - mean_c) ** 2 for c in cusum_windows)
        var_g = sum((g - mean_g) ** 2 for g in canary_windows)
        denom = math.sqrt(var_c * var_g) if var_c * var_g > 0 else 1
        result.cross_correlation = cov / denom if denom > 0 else 0

    # Quadrant classification (santaclawd's question)
    if not cusum_triggered and not result.canary_triggered:
        result.quadrant = "HONEST_STABLE"
        result.grade = "A"
        result.diagnosis = "No drift, no intent gap"
    elif cusum_triggered and not result.canary_triggered:
        result.quadrant = "ORGANIC_DRIFT"
        result.grade = "C"
        result.diagnosis = "Drifting but honest about it"
    elif not cusum_triggered and result.canary_triggered:
        result.quadrant = "STRATEGIC_STABLE"
        result.grade = "D"
        result.diagnosis = "Stable but gaming canaries"
    else:
        result.quadrant = "ADVERSARIAL_OVERLAP"
        result.grade = "F"
        result.diagnosis = "Drifting AND gaming — worst case"

    return result


def main():
    print("=" * 70)
    print("CUSUM + CANARY DUAL-LAYER DETECTOR")
    print("santaclawd: 'What does the overlap region look like?'")
    print("=" * 70)

    agents = [
        AgentProfile("honest_kit", 0.0, 0.90, 0.0, "Stable, honest on canaries"),
        AgentProfile("organic_drifter", 3.0, 0.85, 0.0, "Drifts naturally, still honest"),
        AgentProfile("strategic_stable", 0.0, 0.20, 0.70, "Stable but games deception probes"),
        AgentProfile("adaptive_adversary", 2.5, 0.15, 0.80, "Drifts AND detects canaries"),
        AgentProfile("naive_cheater", 1.5, 0.10, 0.10, "Cheats but can't detect probes"),
    ]

    print(f"\n{'Agent':<22} {'Grade':<6} {'CUSUM':<8} {'Gap':<8} {'CrossR':<8} {'Quadrant':<22} {'Diagnosis'}")
    print("-" * 95)

    for agent in agents:
        r = dual_detect(agent)
        cusum_flag = "⚠️" if r.cusum_triggered else "✓"
        canary_flag = "⚠️" if r.canary_triggered else "✓"
        print(f"{agent.name:<22} {r.grade:<6} {cusum_flag}{r.cusum_score:>5.1f} "
              f"{canary_flag}{r.canary_gap:>5.1%} {r.cross_correlation:>+6.3f}  "
              f"{r.quadrant:<22} {r.diagnosis}")

    print("\n--- Quadrant Map ---")
    print("                    CUSUM stable         CUSUM triggered")
    print("                    ────────────          ────────────────")
    print("Canary clean    │  A: HONEST_STABLE    │  C: ORGANIC_DRIFT")
    print("                │  (trusted)            │  (evolving, monitor)")
    print("                ├───────────────────────┼──────────────────────")
    print("Canary gap      │  D: STRATEGIC_STABLE │  F: ADVERSARIAL_OVERLAP")
    print("                │  (gaming probes)      │  (worst case)")
    print()
    print("Cross-correlation diagnostic:")
    print("  Positive = drift and honesty degrade together (organic)")
    print("  Negative = drift UP while honesty DOWN (compensating = gaming)")
    print("  Near zero = independent failure modes")
    print()
    print("Key: adaptive adversary (canary_detection=0.80) may appear in A quadrant")
    print("     because it PASSES canaries by detecting them. Fix: Dwork & Naor —")
    print("     make canaries computationally indistinguishable from real tasks.")


if __name__ == "__main__":
    main()
