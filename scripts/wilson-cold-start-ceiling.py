#!/usr/bin/env python3
"""
wilson-cold-start-ceiling.py — Wilson CI trust ceilings for ATF cold-start.

Per santaclawd: "what trust ceiling does Wilson assign at n=5, n=15, n=29?"

Wilson score interval (Wilson 1927) gives confidence bounds for proportions
with small samples. Key property: works from n=1 (unlike KS which needs ~30).

ATF SPEC_CONSTANT proposal:
  - COLD_START_THRESHOLD = 30 (KS becomes valid)
  - COLD_START_METHOD = "wilson_ci"
  - WILSON_Z = 1.96 (95% confidence)
  - Trust ceiling = Wilson lower bound (conservative)

Natural gradient creates incentive:
  n=1  perfect → ceiling 0.21 (can't do much)
  n=5  perfect → ceiling 0.57 (limited scope)
  n=15 perfect → ceiling 0.80 (moderate trust)
  n=30 perfect → ceiling 0.89 (full trust with KS)
  n=50 perfect → ceiling 0.93 (diminishing returns)

Usage:
    python3 wilson-cold-start-ceiling.py
"""

import math
import json
from dataclasses import dataclass


# ATF SPEC_CONSTANTS for cold-start trust
SPEC_CONSTANTS = {
    "COLD_START_THRESHOLD": 30,       # KS-test minimum sample
    "COLD_START_METHOD": "wilson_ci",  # Method below threshold
    "WILSON_Z": 1.96,                 # 95% confidence
    "TRUST_CEILING_PROVISIONAL": 0.60, # Max trust at n<10
    "TRUST_CEILING_EMERGING": 0.80,    # Max trust at n<20
    "TRUST_CEILING_ESTABLISHED": 0.90, # Max trust at n<30
    "MIN_CEREMONY_WITNESSES": 3,       # BFT minimum
    "CEREMONY_QUORUM_RATIO": 0.67,     # For larger witness sets
}


def wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score lower bound — conservative trust estimate."""
    if total == 0:
        return 0.0
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return max(0.0, center - spread)


def wilson_upper_bound(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score upper bound."""
    if total == 0:
        return 1.0
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return min(1.0, center + spread)


@dataclass
class ColdStartAssessment:
    agent_id: str
    total_receipts: int
    successful_receipts: int
    success_rate: float
    wilson_lower: float
    wilson_upper: float
    trust_ceiling: float
    trust_phase: str  # BOOTSTRAP, PROVISIONAL, EMERGING, ESTABLISHED, MATURE
    ks_eligible: bool
    scope_recommendation: str

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "total_receipts": self.total_receipts,
            "successful_receipts": self.successful_receipts,
            "success_rate": round(self.success_rate, 3),
            "wilson_lower": round(self.wilson_lower, 3),
            "wilson_upper": round(self.wilson_upper, 3),
            "trust_ceiling": round(self.trust_ceiling, 3),
            "trust_phase": self.trust_phase,
            "ks_eligible": self.ks_eligible,
            "scope_recommendation": self.scope_recommendation,
        }


def assess_cold_start(
    agent_id: str,
    total_receipts: int,
    successful_receipts: int,
) -> ColdStartAssessment:
    """Assess trust ceiling for an agent in cold-start phase."""
    z = SPEC_CONSTANTS["WILSON_Z"]
    threshold = SPEC_CONSTANTS["COLD_START_THRESHOLD"]

    if total_receipts == 0:
        return ColdStartAssessment(
            agent_id=agent_id,
            total_receipts=0,
            successful_receipts=0,
            success_rate=0.0,
            wilson_lower=0.0,
            wilson_upper=1.0,
            trust_ceiling=0.0,
            trust_phase="BOOTSTRAP",
            ks_eligible=False,
            scope_recommendation="GENESIS_ONLY: no receipts, no trust",
        )

    success_rate = successful_receipts / total_receipts
    wl = wilson_lower_bound(successful_receipts, total_receipts, z)
    wu = wilson_upper_bound(successful_receipts, total_receipts, z)
    ks_eligible = total_receipts >= threshold

    # Trust ceiling: Wilson lower bound, capped by phase
    if total_receipts < 10:
        phase = "PROVISIONAL"
        ceiling = min(wl, SPEC_CONSTANTS["TRUST_CEILING_PROVISIONAL"])
        scope = f"LIMITED: max {ceiling:.2f} trust, small-scope tasks only"
    elif total_receipts < 20:
        phase = "EMERGING"
        ceiling = min(wl, SPEC_CONSTANTS["TRUST_CEILING_EMERGING"])
        scope = f"MODERATE: max {ceiling:.2f} trust, standard tasks"
    elif total_receipts < threshold:
        phase = "ESTABLISHED"
        ceiling = min(wl, SPEC_CONSTANTS["TRUST_CEILING_ESTABLISHED"])
        scope = f"ESTABLISHED: max {ceiling:.2f} trust, approaching KS eligibility"
    else:
        phase = "MATURE"
        ceiling = wl  # No phase cap, Wilson lower bound is the ceiling
        scope = f"MATURE: KS-eligible, full trust range, ceiling={ceiling:.2f}"

    return ColdStartAssessment(
        agent_id=agent_id,
        total_receipts=total_receipts,
        successful_receipts=successful_receipts,
        success_rate=success_rate,
        wilson_lower=wl,
        wilson_upper=wu,
        trust_ceiling=ceiling,
        trust_phase=phase,
        ks_eligible=ks_eligible,
        scope_recommendation=scope,
    )


def demo():
    print("=" * 60)
    print("Wilson CI Cold-Start Trust Ceiling — ATF SPEC_CONSTANTS")
    print("=" * 60)

    # Show the natural gradient
    print("\n--- Natural trust gradient (100% success rate) ---")
    print(f"{'n':>4} {'Wilson LB':>10} {'Phase':>14} {'Ceiling':>8}")
    print("-" * 40)
    for n in [1, 2, 3, 5, 8, 10, 15, 20, 25, 29, 30, 40, 50]:
        a = assess_cold_start("test", n, n)
        print(f"{n:>4} {a.wilson_lower:>10.3f} {a.trust_phase:>14} {a.trust_ceiling:>8.3f}")

    # Show the gradient with imperfect performance
    print("\n--- Trust gradient (80% success rate) ---")
    print(f"{'n':>4} {'s':>3} {'Wilson LB':>10} {'Phase':>14} {'Ceiling':>8}")
    print("-" * 45)
    for n in [5, 10, 15, 20, 29, 30, 50]:
        s = int(n * 0.8)
        a = assess_cold_start("test", n, s)
        print(f"{n:>4} {s:>3} {a.wilson_lower:>10.3f} {a.trust_phase:>14} {a.trust_ceiling:>8.3f}")

    # Scenario assessments
    print("\n--- Agent Assessments ---")
    scenarios = [
        ("new_agent", 0, 0),
        ("kit_fox_early", 5, 5),
        ("kit_fox_growing", 15, 14),
        ("sybil_bot", 5, 2),
        ("established_agent", 29, 27),
        ("mature_agent", 50, 48),
        ("flaky_agent", 30, 20),
    ]

    for agent_id, total, success in scenarios:
        a = assess_cold_start(agent_id, total, success)
        print(f"\n  {json.dumps(a.to_dict(), indent=4)}")

    # SPEC_CONSTANTS proposal
    print("\n" + "=" * 60)
    print("ATF SPEC_CONSTANTS proposal:")
    print(json.dumps(SPEC_CONSTANTS, indent=2))
    print("\nKey insight: Wilson CI creates NATURAL incentive gradient.")
    print("n=5 caps at 0.57 even with 100% success.")
    print("No artificial penalty needed — the math IS the penalty.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
