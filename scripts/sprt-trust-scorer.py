#!/usr/bin/env python3
"""
sprt-trust-scorer.py — Sequential Probability Ratio Test for continuous agent trust.

Based on:
- Wald (1945): SPRT — optimal stopping with bounded error
- Patronus AI (2025): SPRT for AI product monitoring
- bro_agent: (T level × T confidence) 2x2, width of T estimate = signal
- funwolf: "N never stops. Trust is continuous monitoring."
- santaclawd: adversary passing N probes then drifting

SPRT advantage: stops EARLY when evidence is clear.
Honest agent: ~6 observations to accept (likelihood moves fast).
Adversary: either detected fast or forced to maintain honest behavior indefinitely.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Observation:
    step: int
    value: float       # 0.0-1.0 behavioral score
    is_probe: bool     # Was this a strategic probe?
    timestamp: float   # Seconds since epoch (for Poisson spacing)


@dataclass
class SPRTState:
    agent_name: str
    # SPRT parameters
    alpha: float = 0.05   # P(false accept)
    beta: float = 0.10    # P(false reject)
    p0: float = 0.3       # Null hypothesis: agent is adversarial (low trust prob)
    p1: float = 0.8       # Alt hypothesis: agent is trustworthy (high trust prob)
    # Running state
    log_likelihood_ratio: float = 0.0
    observations: list[Observation] = field(default_factory=list)
    decision: str = "undecided"  # "accept", "reject", "undecided"
    t_estimate: float = 0.5     # Current trust level
    t_confidence_width: float = 1.0  # Width of CI (narrowing = learning)

    @property
    def upper_bound(self) -> float:
        """Accept threshold: ln((1-β)/α)"""
        return math.log((1 - self.beta) / self.alpha)

    @property
    def lower_bound(self) -> float:
        """Reject threshold: ln(β/(1-α))"""
        return math.log(self.beta / (1 - self.alpha))

    def observe(self, value: float, is_probe: bool = False, timestamp: float = 0.0):
        step = len(self.observations) + 1
        obs = Observation(step, value, is_probe, timestamp)
        self.observations.append(obs)

        # Update log-likelihood ratio
        if value > 0.5:
            lr = math.log(self.p1 / self.p0) if self.p0 > 0 else 5.0
        else:
            lr = math.log((1 - self.p1) / (1 - self.p0)) if (1 - self.p0) > 0 else -5.0
        self.log_likelihood_ratio += lr

        # Update T estimate (running mean)
        values = [o.value for o in self.observations]
        self.t_estimate = sum(values) / len(values)

        # Update confidence width (Hoeffding)
        n = len(values)
        if n > 1:
            self.t_confidence_width = 2 * math.sqrt(math.log(2 / 0.05) / (2 * n))
        else:
            self.t_confidence_width = 1.0

        # Check boundaries
        if self.log_likelihood_ratio >= self.upper_bound:
            self.decision = "accept"
        elif self.log_likelihood_ratio <= self.lower_bound:
            self.decision = "reject"

    def quadrant(self) -> str:
        """bro_agent's 2x2: (T level) × (T confidence)"""
        high_t = self.t_estimate > 0.6
        narrow = self.t_confidence_width < 0.3
        if high_t and narrow:
            return "TRUST (high T, narrow CI)"
        elif high_t and not narrow:
            return "HOPEFUL (high T, wide CI)"
        elif not high_t and narrow:
            return "REJECT (low T, narrow CI)"
        else:
            return "UNCERTAIN (low T, wide CI)"


def simulate_agent(name: str, behavior_fn, n_steps: int = 20,
                    poisson_rate: float = 3.0) -> SPRTState:
    """Simulate SPRT scoring with Poisson-timed probes."""
    state = SPRTState(agent_name=name)
    rng = random.Random(hash(name))
    t = 0.0

    for i in range(n_steps):
        # Poisson timing (stochastic k)
        interval = rng.expovariate(poisson_rate)
        t += interval

        # Is this a probe? ~20% chance
        is_probe = rng.random() < 0.2
        value = behavior_fn(i, is_probe, rng)
        state.observe(value, is_probe, t)

        if state.decision != "undecided":
            break

    return state


def main():
    print("=" * 70)
    print("SPRT TRUST SCORER — Continuous Agent Monitoring")
    print("Wald (1945) + bro_agent 2x2 + funwolf 'N never stops'")
    print("=" * 70)

    # Define agent behaviors
    def honest(step, is_probe, rng):
        return 0.75 + rng.gauss(0, 0.1)

    def adversary_naive(step, is_probe, rng):
        return 0.25 + rng.gauss(0, 0.15)

    def adversary_strategic(step, is_probe, rng):
        """Pass probes, drift on non-probes (santaclawd's scenario)"""
        if is_probe:
            return 0.80 + rng.gauss(0, 0.05)  # Ace the probe
        if step < 5:
            return 0.75 + rng.gauss(0, 0.1)   # Honest early
        return 0.35 + rng.gauss(0, 0.1)       # Drift later

    def adversary_slow_drift(step, is_probe, rng):
        """Gradual drift — hardest to detect"""
        base = 0.80 - (step * 0.03)  # Slow decline
        return max(0.1, base + rng.gauss(0, 0.08))

    agents = {
        "honest_agent": honest,
        "naive_adversary": adversary_naive,
        "strategic_adversary": adversary_strategic,
        "slow_drift": adversary_slow_drift,
    }

    print(f"\n{'Agent':<22} {'Decision':<10} {'Steps':<6} {'T':<6} {'CI Width':<9} {'Quadrant'}")
    print("-" * 70)

    for name, fn in agents.items():
        state = simulate_agent(name, fn, n_steps=30)
        print(f"{name:<22} {state.decision:<10} {len(state.observations):<6} "
              f"{state.t_estimate:<6.2f} {state.t_confidence_width:<9.3f} {state.quadrant()}")

    # Poisson vs fixed probe timing
    print("\n--- Probe Timing: Fixed vs Poisson ---")
    print("Fixed k=5: adversary knows probe arrives at step 5,10,15...")
    print("Poisson λ=3: probes at random intervals, unpredictable")
    print("Strategic adversary ONLY cheats on non-probes.")
    print("Poisson probes: ~20% chance ANY step is a probe → no safe window.")

    # Key: width of T as signal (bro_agent)
    print("\n--- Width of T Estimate (bro_agent's insight) ---")
    for name, fn in agents.items():
        state = simulate_agent(name, fn, n_steps=30)
        widths = []
        s = SPRTState(agent_name=name)
        rng = random.Random(hash(name))
        for i in range(min(15, len(state.observations))):
            obs = state.observations[i]
            s.observe(obs.value, obs.is_probe, obs.timestamp)
            widths.append(s.t_confidence_width)
        trend = "NARROWING" if len(widths) > 2 and widths[-1] < widths[1] else "STABLE/WIDENING"
        print(f"  {name:<22} CI: {widths[0]:.3f} → {widths[-1]:.3f}  [{trend}]")

    print("\nNarrowing CI = learning the agent. Stable/wide = inconsistent behavior.")
    print("PayLock should expose CI width at commitment time as initial risk parameter.")


if __name__ == "__main__":
    main()
