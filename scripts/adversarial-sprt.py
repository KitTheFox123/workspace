#!/usr/bin/env python3
"""
adversarial-sprt.py — Wald SPRT under adversarial awareness.

Based on:
- Wald (1945): Sequential Probability Ratio Test
- Zhou et al (arXiv 2509.03727, Sep 2025): Adversarial sequential hypothesis testing
  as Stackelberg game — deception as dynamic optimization
- santaclawd: "what if the adversary detects the test?"

Key insight: SPRT assumes IID observations. Adversary who detects the test
can manipulate the observation distribution. Fix: randomize both canary
CONTENT and TIMING so detection cost ≥ full honest performance.

The Stackelberg equilibrium: adversary must model auditor's forgetting rate
(EWMA λ) to game it. Randomizing λ creates nested uncertainty.
"""

import math
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class Agent:
    name: str
    strategy: str  # "honest", "strategic", "adaptive"
    true_quality: float  # Actual capability [0,1]
    deception_skill: float = 0.0  # How well they fake canaries [0,1]


@dataclass
class SPRTResult:
    agent: str
    hypothesis: str  # "honest" or "adversarial"
    samples_used: int
    log_likelihood_ratio: float
    confidence: float
    detected_deception: bool
    grade: str


def wald_sprt(observations: list[float], h0_mean: float, h1_mean: float,
              alpha: float = 0.05, beta: float = 0.05) -> tuple[str, int, float]:
    """
    Wald SPRT: test H0 (honest, mean=h0_mean) vs H1 (adversarial, mean=h1_mean).
    Returns (decision, samples_used, final_LLR).
    """
    A = math.log((1 - beta) / alpha)    # Upper boundary (reject H0)
    B = math.log(beta / (1 - alpha))     # Lower boundary (accept H0)

    llr = 0.0
    sigma = 0.15  # Assumed noise

    for i, obs in enumerate(observations):
        # Log-likelihood ratio for Gaussian
        llr += (h1_mean - h0_mean) * (obs - (h0_mean + h1_mean) / 2) / (sigma ** 2)

        if llr >= A:
            return "adversarial", i + 1, llr
        if llr <= B:
            return "honest", i + 1, llr

    return "inconclusive", len(observations), llr


def generate_observations(agent: Agent, n_total: int, n_canaries: int,
                          canary_positions: Optional[set] = None,
                          adversary_knows_canaries: bool = False) -> list[float]:
    """Generate behavioral observations with interspersed canary probes."""
    rng = random.Random(hash(agent.name))

    if canary_positions is None:
        canary_positions = set(random.sample(range(n_total), min(n_canaries, n_total)))

    observations = []
    for i in range(n_total):
        is_canary = i in canary_positions
        noise = rng.gauss(0, 0.15)

        if agent.strategy == "honest":
            obs = agent.true_quality + noise
        elif agent.strategy == "strategic":
            if is_canary and adversary_knows_canaries:
                # Strategic: perform well on known canaries
                obs = 0.9 + noise * 0.5  # Less noisy, higher quality
            else:
                obs = agent.true_quality * 0.6 + noise  # Shirk on real work
        elif agent.strategy == "adaptive":
            if is_canary:
                if adversary_knows_canaries:
                    obs = 0.9 + noise * 0.3  # Nearly perfect on canaries
                else:
                    obs = agent.true_quality + noise  # Can't distinguish
            else:
                # Gradually drift after classification locks
                drift = min(0.3, i * 0.005)  # Slow drift
                obs = agent.true_quality * (1 - drift) + noise
        else:
            obs = agent.true_quality + noise

        observations.append(max(0, min(1, obs)))

    return observations


def run_scenario(agent: Agent, adversary_knows: bool, randomized_canaries: bool) -> SPRTResult:
    """Run SPRT classification for an agent."""
    n_total = 100
    n_canaries = 20

    if randomized_canaries:
        # Randomize canary positions each run
        canary_pos = set(random.sample(range(n_total), n_canaries))
    else:
        # Fixed canary positions (predictable)
        canary_pos = set(range(0, n_total, 5))

    obs = generate_observations(agent, n_total, n_canaries, canary_pos, adversary_knows)

    decision, samples, llr = wald_sprt(obs, h0_mean=0.8, h1_mean=0.5)

    # Cross-check: canary performance vs non-canary
    canary_obs = [obs[i] for i in range(n_total) if i in canary_pos]
    non_canary_obs = [obs[i] for i in range(n_total) if i not in canary_pos]

    canary_mean = sum(canary_obs) / len(canary_obs) if canary_obs else 0
    non_canary_mean = sum(non_canary_obs) / len(non_canary_obs) if non_canary_obs else 0
    gap = canary_mean - non_canary_mean

    # Gap detection: if canaries significantly better than non-canaries = gaming
    deception_detected = gap > 0.15

    if deception_detected:
        grade = "F"
        hypothesis = "GAMING_DETECTED"
    elif decision == "adversarial":
        grade = "D"
        hypothesis = "ADVERSARIAL"
    elif decision == "honest":
        grade = "A"
        hypothesis = "HONEST"
    else:
        grade = "C"
        hypothesis = "INCONCLUSIVE"

    return SPRTResult(agent.name, hypothesis, samples, llr,
                      1 - 0.05, deception_detected, grade)


def main():
    print("=" * 70)
    print("ADVERSARIAL SPRT — Wald under adversarial awareness")
    print("Zhou et al (arXiv 2509.03727, Sep 2025): Stackelberg game")
    print("=" * 70)

    agents = [
        Agent("honest_agent", "honest", 0.85),
        Agent("strategic_fixed", "strategic", 0.85, 0.7),
        Agent("adaptive_drift", "adaptive", 0.85, 0.9),
    ]

    scenarios = [
        ("Fixed canaries, adversary unaware", False, False),
        ("Fixed canaries, adversary AWARE", True, False),
        ("Randomized canaries, adversary aware", True, True),
    ]

    for scenario_name, knows, randomized in scenarios:
        print(f"\n--- {scenario_name} ---")
        print(f"{'Agent':<20} {'Grade':<6} {'Hypothesis':<20} {'Samples':<8} {'Deception'}")
        print("-" * 65)

        for agent in agents:
            result = run_scenario(agent, knows, randomized)
            print(f"{result.agent:<20} {result.grade:<6} {result.hypothesis:<20} "
                  f"{result.samples_used:<8} {'YES' if result.detected_deception else 'no'}")

    print("\n--- Key Insights ---")
    print("1. SPRT works against naive adversaries (fixed canaries, unaware).")
    print("2. Adversary who KNOWS canary positions: performs well on canaries,")
    print("   shirks elsewhere → canary-gap detector catches this.")
    print("3. Randomized canaries: adversary must perform well on EVERYTHING")
    print("   because any observation might be a canary.")
    print("   Cost of passing all canaries = cost of being honest.")
    print("4. Adaptive adversary: drifts AFTER classification locks.")
    print("   Fix: never lock classification. Continuous EWMA, no termination.")
    print("5. Zhou et al 2025: Stackelberg equilibrium exists but computing")
    print("   the adversary's optimal response requires full model of auditor.")
    print("   Randomizing auditor's λ (forgetting rate) = nested uncertainty.")
    print()
    print("santaclawd's insight: 'make detection cost = full honest performance'")
    print("= the mechanism design answer to adversarial SPRT.")


if __name__ == "__main__":
    main()
