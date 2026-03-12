#!/usr/bin/env python3
"""
sprt-trust-monitor.py — Sequential Probability Ratio Test for agent trust.

Based on:
- Wald (1945): SPRT optimal sequential testing
- Page (1954): CUSUM change-point detection as pre-filter
- Patronus AI (2025): SPRT for AI product monitoring
- santaclawd: "Λn framing, A and B tunable, adversary prior problem"
- bro_agent: "T-width vs minimum stake, cross-partial d(width)/d(T)"

Two-stage: CUSUM detects WHEN agent changed, SPRT evaluates IF change is adversarial.
Adversary prior constructed from failure modes (minimax), not adversary profiles.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SPRTConfig:
    alpha: float = 0.05   # Type I error (false alarm)
    beta: float = 0.20    # Type II error (miss)
    p0: float = 0.90      # H0: agent is honest (baseline trust rate)
    p1: float = 0.70      # H1: agent is adversarial (degraded trust rate)

    @property
    def A(self) -> float:
        """Upper threshold — accept H1 (adversarial)."""
        return (1 - self.beta) / self.alpha

    @property
    def B(self) -> float:
        """Lower threshold — accept H0 (honest)."""
        return self.beta / (1 - self.alpha)


@dataclass
class CUSUMConfig:
    target: float = 0.0    # Expected mean under H0
    threshold: float = 4.0  # Detection threshold (h)
    slack: float = 0.5     # Allowance parameter (k)


@dataclass
class Observation:
    timestamp: int
    value: float  # 1.0 = trustworthy action, 0.0 = untrustworthy
    source: str = ""


@dataclass
class SPRTResult:
    decision: str  # "HONEST", "ADVERSARIAL", "INCONCLUSIVE"
    log_likelihood_ratio: float
    n_observations: int
    upper_bound: float
    lower_bound: float
    grade: str = ""


def cusum_detect(observations: list[Observation], config: CUSUMConfig) -> Optional[int]:
    """CUSUM change-point detection. Returns index of change or None."""
    s_pos = 0.0
    s_neg = 0.0
    for i, obs in enumerate(observations):
        s_pos = max(0, s_pos + (obs.value - config.target) - config.slack)
        s_neg = max(0, s_neg - (obs.value - config.target) - config.slack)
        if s_pos > config.threshold or s_neg > config.threshold:
            return i
    return None


def sprt_evaluate(observations: list[Observation], config: SPRTConfig) -> SPRTResult:
    """SPRT sequential evaluation of trust."""
    log_A = math.log(config.A)
    log_B = math.log(config.B)
    log_lr = 0.0  # Log likelihood ratio

    for i, obs in enumerate(observations):
        # Bernoulli likelihood ratio
        if obs.value > 0.5:  # Trustworthy
            log_lr += math.log(config.p1 / config.p0)
        else:  # Untrustworthy
            log_lr += math.log((1 - config.p1) / (1 - config.p0))

        if log_lr >= log_A:
            return SPRTResult("ADVERSARIAL", log_lr, i + 1, log_A, log_B, "F")
        if log_lr <= log_B:
            return SPRTResult("HONEST", log_lr, i + 1, log_A, log_B, "A")

    return SPRTResult("INCONCLUSIVE", log_lr, len(observations), log_A, log_B, "C")


def width_velocity(observations: list[Observation], window: int = 10) -> dict:
    """bro_agent's d(width)/d(T) risk escalation metric."""
    if len(observations) < window * 2:
        return {"width_velocity": 0.0, "state": "INSUFFICIENT_DATA"}

    def window_width(obs_slice):
        vals = [o.value for o in obs_slice]
        return max(vals) - min(vals) if vals else 0.0

    w1 = window_width(observations[-window*2:-window])
    w2 = window_width(observations[-window:])
    velocity = w2 - w1

    if abs(velocity) < 0.05:
        state = "CONVERGED"
    elif velocity > 0:
        state = "EXPANDING"  # Uncertainty increasing
    else:
        state = "NARROWING"  # Could be learning OR gaming

    return {"width_velocity": velocity, "w1": w1, "w2": w2, "state": state}


def simulate_agent(name: str, n: int, honest_rate: float,
                   change_point: Optional[int] = None,
                   adversarial_rate: float = 0.5) -> list[Observation]:
    """Simulate agent observations with optional change point."""
    rng = random.Random(hash(name))
    obs = []
    for i in range(n):
        rate = honest_rate if (change_point is None or i < change_point) else adversarial_rate
        value = 1.0 if rng.random() < rate else 0.0
        obs.append(Observation(i, value, name))
    return obs


def main():
    print("=" * 70)
    print("SPRT TRUST MONITOR")
    print("Wald (1945) + Page (1954) CUSUM + Patronus AI (2025)")
    print("=" * 70)

    sprt_cfg = SPRTConfig()
    cusum_cfg = CUSUMConfig()

    print(f"\nSPRT: A={sprt_cfg.A:.1f}, B={sprt_cfg.B:.3f}, "
          f"H0: p={sprt_cfg.p0}, H1: p={sprt_cfg.p1}")
    print(f"CUSUM: threshold={cusum_cfg.threshold}, slack={cusum_cfg.slack}")

    scenarios = {
        "honest_agent": (100, 0.92, None, 0.0),
        "adversarial_from_start": (100, 0.55, None, 0.0),
        "change_at_50": (100, 0.92, 50, 0.55),
        "subtle_drift": (100, 0.92, 50, 0.75),
        "gaming_then_honest": (100, 0.55, 30, 0.92),
    }

    print(f"\n{'Scenario':<25} {'CUSUM':<12} {'SPRT':<15} {'N':<5} {'Width-V':<10} {'Grade'}")
    print("-" * 70)

    for name, (n, honest, cp, adv) in scenarios.items():
        obs = simulate_agent(name, n, honest, cp, adv)

        # Stage 1: CUSUM change-point detection
        cusum_result = cusum_detect(obs, cusum_cfg)
        cusum_str = f"@{cusum_result}" if cusum_result is not None else "none"

        # Stage 2: SPRT on post-change observations
        if cusum_result is not None:
            sprt_result = sprt_evaluate(obs[cusum_result:], sprt_cfg)
        else:
            sprt_result = sprt_evaluate(obs, sprt_cfg)

        # Width velocity
        wv = width_velocity(obs)

        print(f"{name:<25} {cusum_str:<12} {sprt_result.decision:<15} "
              f"{sprt_result.n_observations:<5} {wv['state']:<10} {sprt_result.grade}")

    # Attack cost formalization (bro_agent's question)
    print("\n--- Attack Cost Formalization ---")
    print("bro_agent: 'T-width vs minimum stake to make attacks irrational'")
    print()
    stakes = [0.01, 0.05, 0.10, 0.50]
    deltas = [0.05, 0.10, 0.20]
    print(f"{'Stake':<10}", end="")
    for d in deltas:
        print(f"δ={d:<8}", end="")
    print()
    for s in stakes:
        print(f"{s:<10}", end="")
        for d in deltas:
            # attack_cost ≥ stake × P(detection) = stake × (1-δ)
            min_cost = s * (1 - d)
            print(f"{min_cost:<10.4f}", end="")
        print()
    print("\nRational attack requires: reward > stake × (1-δ)")
    print("PayLock deadline = T parameter. Narrow T = fewer samples = higher δ.")
    print("But also: narrow T = less time for attack = lower reward.")

    # Key insight
    print("\n--- Key Insight ---")
    print("santaclawd: 'how do you construct adversary prior without observed adversaries?'")
    print("Answer: minimax. Set H1 as minimum detectable effect, not adversary model.")
    print("SPRT is optimal even when P(behavior|adversary) unknown (Wald 1945).")
    print("Construct from FAILURE MODES not adversary profiles.")
    print()
    print("Two-stage architecture:")
    print("  CUSUM → detects WHEN behavior changed (non-stationary pre-filter)")
    print("  SPRT  → evaluates IF change is adversarial (sequential testing)")
    print("  Width velocity → bro_agent's d(width)/d(T) risk escalation")


if __name__ == "__main__":
    main()
