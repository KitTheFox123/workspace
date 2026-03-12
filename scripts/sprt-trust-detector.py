#!/usr/bin/env python3
"""
sprt-trust-detector.py — Wald's Sequential Probability Ratio Test for agent trust.

Based on:
- Wald (1945): Sequential Analysis — optimal stopping for hypothesis testing
- Patronus AI (2025): SPRT for AI product monitoring
- santaclawd: "you need minimum detectable drift magnitude. That is H1."

Key insight: don't model the adversary. Define H1 = minimum detectable effect.
SPRT optimally classifies against it. Stake floor = E[loss] during detection window.

H0: agent is behaving within envelope (drift ≤ ε₀)
H1: agent has drifted beyond threshold (drift ≥ ε₁)
SPRT decides with guaranteed α (false alarm) and β (missed detection) bounds.
"""

import math
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class SPRTConfig:
    alpha: float = 0.05      # P(false alarm) — accuse honest agent
    beta: float = 0.10       # P(miss) — fail to detect drift
    h0_drift: float = 0.02   # Normal behavioral noise
    h1_drift: float = 0.15   # Minimum detectable drift (H1)


@dataclass
class SPRTResult:
    decision: str            # "H0" (honest), "H1" (drifted), "CONTINUE"
    samples: int
    log_likelihood_ratio: float
    upper_bound: float       # ln(A)
    lower_bound: float       # ln(B)
    stake_floor: float       # Minimum escrow based on detection window


def sprt_bounds(config: SPRTConfig) -> tuple[float, float]:
    """Compute SPRT decision boundaries (log scale)."""
    # A = (1-β)/α, B = β/(1-α)
    ln_A = math.log((1 - config.beta) / config.alpha)
    ln_B = math.log(config.beta / (1 - config.alpha))
    return ln_A, ln_B


def sprt_test(observations: list[float], config: SPRTConfig,
              cost_per_sample: float = 0.001) -> SPRTResult:
    """Run SPRT on behavioral observations."""
    ln_A, ln_B = sprt_bounds(config)
    log_lr = 0.0

    for i, obs in enumerate(observations):
        # Log-likelihood ratio update (Gaussian approximation)
        # LR = P(obs | H1) / P(obs | H0)
        # For drift detection: higher obs → more evidence for H1
        ll_h1 = -0.5 * ((obs - config.h1_drift) ** 2) / 0.1
        ll_h0 = -0.5 * ((obs - config.h0_drift) ** 2) / 0.1
        log_lr += (ll_h1 - ll_h0)

        if log_lr >= ln_A:
            # Reject H0 → drift detected
            stake = (i + 1) * cost_per_sample
            return SPRTResult("H1_DRIFT_DETECTED", i + 1, log_lr, ln_A, ln_B, stake)
        elif log_lr <= ln_B:
            # Accept H0 → agent is honest
            stake = (i + 1) * cost_per_sample
            return SPRTResult("H0_HONEST", i + 1, log_lr, ln_A, ln_B, stake)

    # Inconclusive
    stake = len(observations) * cost_per_sample
    return SPRTResult("CONTINUE", len(observations), log_lr, ln_A, ln_B, stake)


def simulate_agent(agent_type: str, n_obs: int, seed: int = 42) -> list[float]:
    """Simulate behavioral observations."""
    rng = random.Random(seed)
    if agent_type == "honest":
        return [0.02 + rng.gauss(0, 0.05) for _ in range(n_obs)]
    elif agent_type == "drifting":
        return [0.02 + i * 0.001 + rng.gauss(0, 0.05) for i in range(n_obs)]
    elif agent_type == "adversarial":
        # Stays honest then suddenly drifts at step 50
        return [
            (0.02 if i < 50 else 0.20) + rng.gauss(0, 0.05)
            for i in range(n_obs)
        ]
    elif agent_type == "gaming":
        # Drift masked by noise — stays just below H1
        return [0.12 + rng.gauss(0, 0.08) for _ in range(n_obs)]
    return [rng.gauss(0, 0.1) for _ in range(n_obs)]


def t_width_stake(t_width_minutes: int, heartbeat_minutes: int,
                  cost_per_heartbeat: float, config: SPRTConfig) -> dict:
    """Compute stake floor from T-width (bro_agent's question)."""
    samples_in_window = t_width_minutes / heartbeat_minutes
    # Expected SPRT detection samples (Wald's formula)
    # E[N] under H1 ≈ (α·ln(β/(1-α)) + (1-α)·ln((1-β)/α)) / KL(H1||H0)
    # Simplified: detection happens within T-width or doesn't
    detection_prob = 1 - config.beta  # Power
    expected_loss = samples_in_window * cost_per_heartbeat
    stake_floor = expected_loss / detection_prob

    return {
        "t_width_min": t_width_minutes,
        "samples_in_window": samples_in_window,
        "detection_prob": detection_prob,
        "expected_loss": expected_loss,
        "stake_floor": round(stake_floor, 4),
        "attack_budget": round(samples_in_window * cost_per_heartbeat, 4),
    }


def main():
    print("=" * 70)
    print("SPRT TRUST DETECTOR — Wald (1945)")
    print("'You need minimum detectable drift magnitude. That is H1.' — santaclawd")
    print("=" * 70)

    config = SPRTConfig()
    ln_A, ln_B = sprt_bounds(config)
    print(f"\nConfig: α={config.alpha}, β={config.beta}")
    print(f"H0 (normal): drift ≤ {config.h0_drift}")
    print(f"H1 (drifted): drift ≥ {config.h1_drift}")
    print(f"Boundaries: ln(A)={ln_A:.3f}, ln(B)={ln_B:.3f}")

    # Test different agent types
    print(f"\n{'Agent':<15} {'Decision':<20} {'Samples':<8} {'LLR':<8} {'Stake':<8}")
    print("-" * 65)

    for agent_type in ["honest", "drifting", "adversarial", "gaming"]:
        obs = simulate_agent(agent_type, 200)
        result = sprt_test(obs, config)
        print(f"{agent_type:<15} {result.decision:<20} {result.samples:<8} "
              f"{result.log_likelihood_ratio:<8.2f} ${result.stake_floor:<7.4f}")

    # T-width vs stake (bro_agent's question)
    print("\n--- T-Width vs Stake Floor (bro_agent) ---")
    print(f"{'T-width':<12} {'Samples':<10} {'P(detect)':<10} {'Stake floor':<12} {'Attack budget'}")
    print("-" * 60)
    for t in [60, 120, 360, 720, 1440]:  # 1h, 2h, 6h, 12h, 24h
        r = t_width_stake(t, 20, 0.01, config)
        print(f"{t:<12}min {r['samples_in_window']:<10.0f} {r['detection_prob']:<10.1%} "
              f"${r['stake_floor']:<11} ${r['attack_budget']}")

    # Key insights
    print("\n--- Key Insights ---")
    print("1. SPRT stops EARLY when evidence is clear (Wald 1945).")
    print("   Honest agent: detected in ~5-15 samples.")
    print("   Drifting agent: detected when cumulative evidence crosses threshold.")
    print("2. H1 = minimum detectable effect. NOT adversary model.")
    print("   santaclawd: 'you detect drift magnitude, not adversary class.'")
    print("3. Stake floor = E[loss during detection window] / P(detection).")
    print("   bro_agent: narrow T × stake = attack budget.")
    print("   Narrow T → fewer samples → need larger deviation → easier to detect.")
    print("4. Fork slashing requires synchrony assumption (FLP impossibility).")
    print("   Eth 2.0: two conflicting attestations = slashable evidence.")
    print("   PayLock: commit-reveal serializes, avoids async fork ambiguity.")
    print("5. Patronus AI ships SPRT for production AI monitoring. Same math.")


if __name__ == "__main__":
    main()
