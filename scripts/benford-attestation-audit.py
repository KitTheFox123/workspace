#!/usr/bin/env python3
"""benford-attestation-audit.py — Apply Benford's Law to attestation timing gaps.

Natural processes produce gap distributions that follow predictable patterns.
Fabricated attestation histories have suspiciously uniform or regular timing.

Pinkham (1961): Scale invariance → Benford's Law for multiplicative processes.
Nigrini (2012): Digital analysis for fraud detection (court-admissible).
"""

import math
import json
from collections import Counter
from dataclasses import dataclass


@dataclass
class AuditResult:
    agent_id: str
    n_attestations: int
    chi_squared: float
    p_value_approx: str
    leading_digit_dist: dict
    verdict: str
    note: str


# Benford's expected frequencies for leading digits 1-9
BENFORD = {d: math.log10(1 + 1/d) for d in range(1, 10)}


def leading_digit(n: float) -> int:
    """Extract leading digit of a positive number."""
    if n <= 0:
        return 0
    s = f"{n:.10e}"
    for c in s:
        if c.isdigit() and c != '0':
            return int(c)
    return 1


def chi_squared_benford(observed: dict, n: int) -> float:
    """Chi-squared statistic against Benford's distribution."""
    chi2 = 0.0
    for d in range(1, 10):
        expected = BENFORD[d] * n
        obs = observed.get(d, 0)
        if expected > 0:
            chi2 += (obs - expected) ** 2 / expected
    return chi2


def audit_timing_gaps(agent_id: str, gap_seconds: list[float]) -> AuditResult:
    """Audit attestation timing gaps against Benford's Law."""
    # Filter positive gaps
    gaps = [g for g in gap_seconds if g > 0]
    n = len(gaps)

    if n < 20:
        return AuditResult(
            agent_id=agent_id, n_attestations=n,
            chi_squared=0, p_value_approx="N/A",
            leading_digit_dist={}, verdict="INSUFFICIENT",
            note=f"Need ≥20 gaps, got {n}"
        )

    # Extract leading digits
    digits = [leading_digit(g) for g in gaps]
    digit_counts = Counter(digits)
    digit_dist = {d: digit_counts.get(d, 0) / n for d in range(1, 10)}

    chi2 = chi_squared_benford(digit_counts, n)

    # Chi-squared critical values (df=8): 15.51 (p=0.05), 20.09 (p=0.01)
    if chi2 < 15.51:
        p_approx = ">0.05"
        verdict = "NATURAL"
        note = "Timing gaps follow Benford's Law. Consistent with organic behavior."
    elif chi2 < 20.09:
        p_approx = "0.01-0.05"
        verdict = "REVIEW"
        note = "Marginal deviation. Could be legitimate pattern or mild fabrication."
    else:
        p_approx = "<0.01"
        verdict = "SUSPICIOUS"
        note = "Significant deviation from Benford's. Timing gaps may be fabricated."

    return AuditResult(
        agent_id=agent_id, n_attestations=n,
        chi_squared=round(chi2, 2), p_value_approx=p_approx,
        leading_digit_dist={d: round(v, 3) for d, v in digit_dist.items()},
        verdict=verdict, note=note
    )


def generate_test_scenarios():
    """Generate test agents with different attestation patterns."""
    import random
    random.seed(42)

    scenarios = {}

    # Natural: log-normal gaps (real agent, variable activity)
    natural_gaps = [random.lognormvariate(8, 1.5) for _ in range(100)]
    scenarios["organic_agent"] = {
        "gaps": natural_gaps,
        "desc": "Log-normal gaps (variable activity, natural behavior)"
    }

    # Sybil: uniform gaps (automated attestation mill)
    uniform_gaps = [3600 + random.uniform(-60, 60) for _ in range(100)]
    scenarios["sybil_mill"] = {
        "gaps": uniform_gaps,
        "desc": "Nearly uniform 1-hour gaps (automated attestation)"
    }

    # Fabricated: round numbers (human-generated fake timestamps)
    round_gaps = [random.choice([300, 600, 900, 1800, 3600, 7200]) * (1 + random.uniform(-0.01, 0.01))
                  for _ in range(100)]
    scenarios["fabricated_history"] = {
        "gaps": round_gaps,
        "desc": "Round-number gaps (manually created fake history)"
    }

    # Bursty: mix of rapid + dormant (real but irregular agent)
    bursty_gaps = []
    for _ in range(50):
        bursty_gaps.append(random.lognormvariate(3, 1))  # burst phase
    for _ in range(50):
        bursty_gaps.append(random.lognormvariate(10, 1))  # dormant phase
    random.shuffle(bursty_gaps)
    scenarios["bursty_agent"] = {
        "gaps": bursty_gaps,
        "desc": "Mix of burst + dormant phases (real, irregular)"
    }

    return scenarios


def main():
    scenarios = generate_test_scenarios()

    print("=" * 65)
    print("Benford's Law Attestation Timing Audit")
    print("=" * 65)
    print(f"\nBenford expected: {', '.join(f'{d}:{BENFORD[d]:.3f}' for d in range(1, 10))}")

    for agent_id, data in scenarios.items():
        result = audit_timing_gaps(agent_id, data["gaps"])
        print(f"\n{'─' * 55}")
        print(f"Agent: {agent_id}")
        print(f"  Desc: {data['desc']}")
        print(f"  N: {result.n_attestations}")
        print(f"  χ²: {result.chi_squared} (p {result.p_value_approx})")
        print(f"  Verdict: {result.verdict}")
        print(f"  Note: {result.note}")
        top3 = sorted(result.leading_digit_dist.items(), key=lambda x: -x[1])[:3]
        print(f"  Top digits: {', '.join(f'{d}:{v:.3f}' for d, v in top3)}")

    print(f"\n{'=' * 65}")
    print("KEY: Natural processes → Benford distribution (more 1s, fewer 9s)")
    print("     Fabricated/uniform → flat or peaked distribution")
    print("     Sybil mills → nearly identical gaps → concentrated digits")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
