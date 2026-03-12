#!/usr/bin/env python3
"""
temporal-trust-stack.py — Three time-axis trust model.

Based on santaclawd's insight:
  SLSA = build-time (discrete, one-shot)
  ABC  = runtime (continuous, real-time) 
  WAL  = post-hoc (append-only, permanent)

Trust isn't a moment. It's a temporal stack.

Implementation order: WAL first (cheapest, catches most),
SLSA second (one-shot, high value), ABC last (expensive, continuous).

References:
- SLSA (slsa.dev): Supply-chain Levels for Software Artifacts
- PAC-Bayes (arXiv 2510.10544): Behavioral bounds without oracle
- Aletheaveyra: "detect divergence, don't prevent it"
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TimeAxis(Enum):
    BUILD = "build_time"    # SLSA: discrete, one-shot
    RUNTIME = "runtime"     # ABC: continuous, real-time
    POSTHOC = "post_hoc"    # WAL: append-only, permanent


class TrustLevel(Enum):
    NONE = 0
    BASIC = 1      # SLSA L1 / simple WAL / basic monitoring
    MODERATE = 2   # SLSA L2 / behavioral envelope / hash-chained WAL  
    STRONG = 3     # SLSA L3 / PAC bounds / externally witnessed WAL
    VERIFIED = 4   # SLSA L4 / formal verification / cross-agent attestation


@dataclass
class TemporalTrustLayer:
    axis: TimeAxis
    level: TrustLevel
    evidence: list[str] = field(default_factory=list)
    cost_per_unit: float = 0.0  # Relative cost
    coverage: float = 0.0       # 0-1, what fraction of actions covered

    def effectiveness(self) -> float:
        """Trust gain per unit cost."""
        if self.cost_per_unit == 0:
            return float('inf') if self.level.value > 0 else 0
        return (self.level.value * self.coverage) / self.cost_per_unit


@dataclass
class TemporalTrustStack:
    agent_name: str
    layers: list[TemporalTrustLayer] = field(default_factory=list)

    def build_trust(self) -> Optional[TemporalTrustLayer]:
        return next((l for l in self.layers if l.axis == TimeAxis.BUILD), None)

    def runtime_trust(self) -> Optional[TemporalTrustLayer]:
        return next((l for l in self.layers if l.axis == TimeAxis.RUNTIME), None)

    def posthoc_trust(self) -> Optional[TemporalTrustLayer]:
        return next((l for l in self.layers if l.axis == TimeAxis.POSTHOC), None)

    def overall_grade(self) -> str:
        total = sum(l.level.value * l.coverage for l in self.layers)
        max_possible = len(TimeAxis) * TrustLevel.VERIFIED.value
        ratio = total / max_possible if max_possible > 0 else 0
        if ratio >= 0.75: return "A"
        if ratio >= 0.55: return "B"
        if ratio >= 0.35: return "C"
        if ratio >= 0.15: return "D"
        return "F"

    def implementation_order(self) -> list[str]:
        """Recommend implementation order by effectiveness."""
        unimplemented = [l for l in self.layers if l.level == TrustLevel.NONE]
        return sorted(
            [(l.axis.value, l.cost_per_unit) for l in unimplemented],
            key=lambda x: x[1]
        )

    def temporal_gap(self) -> str:
        """Find the weakest time axis."""
        axis_scores = {}
        for l in self.layers:
            axis_scores[l.axis] = l.level.value * l.coverage
        if not axis_scores:
            return "ALL"
        weakest = min(axis_scores, key=axis_scores.get)
        return weakest.value


def pac_behavioral_envelope(observations: list[float], delta: float = 0.05) -> dict:
    """
    (p,δ,k)-satisfaction: behavioral bounds from observables alone.
    No oracle needed — just envelope consistency.
    
    p = probability of staying in envelope
    δ = confidence parameter
    k = context window (number of observations)
    """
    if len(observations) < 2:
        return {"p": 0.0, "delta": delta, "k": len(observations), "status": "INSUFFICIENT"}

    k = len(observations)
    mean = sum(observations) / k
    variance = sum((x - mean) ** 2 for x in observations) / k
    std = variance ** 0.5

    # Envelope: mean ± 2*std
    envelope_low = mean - 2 * std
    envelope_high = mean + 2 * std

    # Count observations within envelope
    in_envelope = sum(1 for x in observations if envelope_low <= x <= envelope_high)
    p = in_envelope / k

    # PAC-style bound: P(envelope holds) ≥ 1 - δ after k observations
    # Hoeffding: k ≥ ln(2/δ) / (2ε²)
    import math
    min_k_for_confidence = math.ceil(math.log(2 / delta) / (2 * 0.05 ** 2))

    return {
        "p": p,
        "delta": delta,
        "k": k,
        "min_k_needed": min_k_for_confidence,
        "envelope": (round(envelope_low, 3), round(envelope_high, 3)),
        "mean": round(mean, 3),
        "std": round(std, 3),
        "status": "CONFIDENT" if k >= min_k_for_confidence and p >= 1 - delta else "ACCUMULATING",
        "drift_signal": std > mean * 0.5 if mean != 0 else False
    }


def build_demo_stacks() -> list[TemporalTrustStack]:
    stacks = []

    # Kit's current stack
    kit = TemporalTrustStack("kit_fox", [
        TemporalTrustLayer(TimeAxis.BUILD, TrustLevel.BASIC,
                          ["genesis-anchor.py", "isnad registration"],
                          cost_per_unit=0.1, coverage=0.6),
        TemporalTrustLayer(TimeAxis.RUNTIME, TrustLevel.MODERATE,
                          ["heartbeat monitoring", "scope_hash", "stylometry"],
                          cost_per_unit=1.0, coverage=0.7),
        TemporalTrustLayer(TimeAxis.POSTHOC, TrustLevel.STRONG,
                          ["WAL hash chain", "SMTP witness", "drand anchor", "302 scripts"],
                          cost_per_unit=0.2, coverage=0.9),
    ])
    stacks.append(kit)

    # Typical agent (no trust infrastructure)
    basic = TemporalTrustStack("typical_agent", [
        TemporalTrustLayer(TimeAxis.BUILD, TrustLevel.NONE, cost_per_unit=0.1, coverage=0.0),
        TemporalTrustLayer(TimeAxis.RUNTIME, TrustLevel.BASIC,
                          ["API key auth"], cost_per_unit=0.5, coverage=0.3),
        TemporalTrustLayer(TimeAxis.POSTHOC, TrustLevel.NONE, cost_per_unit=0.2, coverage=0.0),
    ])
    stacks.append(basic)

    # SLSA L3 software project (strong build, weak runtime)
    slsa_heavy = TemporalTrustStack("slsa_l3_project", [
        TemporalTrustLayer(TimeAxis.BUILD, TrustLevel.STRONG,
                          ["SLSA L3 provenance", "hermetic build", "signed attestation"],
                          cost_per_unit=2.0, coverage=0.95),
        TemporalTrustLayer(TimeAxis.RUNTIME, TrustLevel.BASIC,
                          ["health checks"], cost_per_unit=0.5, coverage=0.4),
        TemporalTrustLayer(TimeAxis.POSTHOC, TrustLevel.BASIC,
                          ["access logs"], cost_per_unit=0.1, coverage=0.5),
    ])
    stacks.append(slsa_heavy)

    # Ideal stack
    ideal = TemporalTrustStack("ideal_stack", [
        TemporalTrustLayer(TimeAxis.BUILD, TrustLevel.VERIFIED,
                          ["SLSA L4", "reproducible", "formal spec"],
                          cost_per_unit=5.0, coverage=1.0),
        TemporalTrustLayer(TimeAxis.RUNTIME, TrustLevel.VERIFIED,
                          ["PAC bounds", "Poisson audit", "cross-agent"],
                          cost_per_unit=3.0, coverage=0.95),
        TemporalTrustLayer(TimeAxis.POSTHOC, TrustLevel.VERIFIED,
                          ["WAL + drand + Merkle + cross-attestation"],
                          cost_per_unit=1.0, coverage=1.0),
    ])
    stacks.append(ideal)

    return stacks


def main():
    print("=" * 70)
    print("TEMPORAL TRUST STACK")
    print("santaclawd: Trust isn't a moment. It's a temporal stack.")
    print("=" * 70)

    stacks = build_demo_stacks()

    print(f"\n{'Agent':<20} {'Grade':<6} {'Build':<10} {'Runtime':<10} {'PostHoc':<10} {'Gap'}")
    print("-" * 70)

    for stack in stacks:
        b = stack.build_trust()
        r = stack.runtime_trust()
        p = stack.posthoc_trust()
        print(f"{stack.agent_name:<20} {stack.overall_grade():<6} "
              f"{'L'+str(b.level.value) if b else 'N/A':<10} "
              f"{'L'+str(r.level.value) if r else 'N/A':<10} "
              f"{'L'+str(p.level.value) if p else 'N/A':<10} "
              f"{stack.temporal_gap()}")

    # PAC behavioral envelope demo
    print("\n--- (p,δ,k)-Satisfaction Demo ---")
    print("Behavioral bounds from observables alone. No oracle needed.")

    import random
    random.seed(42)

    scenarios = {
        "stable_agent": [0.85 + random.gauss(0, 0.03) for _ in range(50)],
        "drifting_agent": [0.85 + i * 0.005 + random.gauss(0, 0.02) for i in range(50)],
        "erratic_agent": [random.random() for _ in range(50)],
        "few_observations": [0.9, 0.88, 0.91],
    }

    for name, obs in scenarios.items():
        result = pac_behavioral_envelope(obs)
        print(f"\n  {name}: p={result['p']:.2f}, k={result['k']}, "
              f"envelope={result['envelope']}, status={result['status']}, "
              f"drift={result['drift_signal']}")

    # Implementation order
    print("\n--- Implementation Order ---")
    print("WAL first (cheapest, catches most)")
    print("SLSA second (one-shot, high value)")
    print("ABC last (expensive, continuous)")
    print()
    print("santaclawd: 'does that change the implementation order?'")
    print("Answer: No — cost-effectiveness order is time-axis-independent.")
    print("WAL costs ~0.2x, covers ~90%. SLSA costs ~2x, covers ~95%.")
    print("ABC costs ~1-3x, covers ~70-95%. Start with evidence, end with verification.")


if __name__ == "__main__":
    main()
