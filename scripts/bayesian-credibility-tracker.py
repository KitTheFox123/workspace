#!/usr/bin/env python3
"""bayesian-credibility-tracker.py — Bayesian credibility accumulation for attestors.

Implements Mayerson (1964) / Bühlmann (1967) credibility with email-thread-inspired
data accumulation. Each interaction = data point. Z accumulates over time.

Key formula: Estimate = Z × individual_data + (1-Z) × population_prior
Where Z = n / (n + k), k = within_variance / between_variance

Usage:
    python3 bayesian-credibility-tracker.py [--demo]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict, field
from typing import List, Dict
from datetime import datetime, timezone


@dataclass
class Interaction:
    """Single attestation interaction (= claim in insurance terms)."""
    timestamp: str
    claim: str        # What was attested
    outcome: float    # 0.0 = wrong, 1.0 = correct
    channel: str      # email, clawk, direct — funwolf insight: channel IS the log


@dataclass 
class AttestorRecord:
    """Attestor's accumulated credibility record."""
    name: str
    interactions: List[Interaction] = field(default_factory=list)
    
    @property
    def n(self) -> int:
        return len(self.interactions)
    
    @property
    def individual_rate(self) -> float:
        if not self.interactions:
            return 0.0
        return sum(i.outcome for i in self.interactions) / len(self.interactions)
    
    @property
    def within_variance(self) -> float:
        """Variance of this attestor's outcomes."""
        if self.n < 2:
            return 1.0  # Maximum uncertainty
        mean = self.individual_rate
        return sum((i.outcome - mean) ** 2 for i in self.interactions) / (self.n - 1)


def compute_credibility(record: AttestorRecord, 
                       population_rate: float = 0.5,
                       k: float = 10.0) -> dict:
    """Compute Bühlmann credibility Z and blended estimate.
    
    Z = n / (n + k)
    Estimate = Z × individual + (1-Z) × population
    
    k = within_variance / between_variance (structural parameter)
    Default k=10 means you need 10 interactions for Z=0.5
    """
    n = record.n
    z = n / (n + k)
    individual = record.individual_rate
    estimate = z * individual + (1 - z) * population_rate
    
    # Confidence interval width narrows with Z
    ci_width = 2 * (1 - z)  # Wide when Z low, narrow when Z high
    
    # Grade based on Z
    if z >= 0.8: grade = "A"
    elif z >= 0.6: grade = "B"
    elif z >= 0.4: grade = "C"
    elif z >= 0.2: grade = "D"
    else: grade = "F"
    
    return {
        "name": record.name,
        "n": n,
        "Z": round(z, 4),
        "individual_rate": round(individual, 4),
        "population_prior": population_rate,
        "blended_estimate": round(estimate, 4),
        "ci_width": round(ci_width, 4),
        "grade": grade,
        "interpretation": (
            f"{'Population prior dominates' if z < 0.3 else 'Balanced blend' if z < 0.7 else 'Track record dominates'}"
            f" (Z={z:.2f}, need {max(0, round(k * 0.8 - n))} more for Grade A)"
        )
    }


def demo():
    """Demo with synthetic attestor data showing Z accumulation."""
    population_rate = 0.70  # Population average accuracy
    k = 10.0  # Structural parameter
    
    # Simulate 5 attestors with different histories
    attestors = {
        "veteran_reliable": AttestorRecord("veteran_reliable", [
            Interaction(f"2026-03-{d:02d}T{h:02d}:00:00Z", f"scope_check_{i}", 
                       0.95 if i % 20 != 0 else 0.0, "email")
            for i, (d, h) in enumerate([(1+i//3, (i*8)%24) for i in range(50)])
        ]),
        "veteran_unreliable": AttestorRecord("veteran_unreliable", [
            Interaction(f"2026-03-{d:02d}T{h:02d}:00:00Z", f"scope_check_{i}",
                       0.4 if i % 3 == 0 else 0.6, "clawk")
            for i, (d, h) in enumerate([(1+i//3, (i*8)%24) for i in range(40)])
        ]),
        "newcomer_good": AttestorRecord("newcomer_good", [
            Interaction(f"2026-03-09T{h:02d}:00:00Z", f"scope_check_{i}",
                       0.9, "email")
            for i, h in enumerate(range(5))
        ]),
        "newcomer_unknown": AttestorRecord("newcomer_unknown", [
            Interaction("2026-03-09T12:00:00Z", "scope_check_0", 1.0, "direct"),
            Interaction("2026-03-09T13:00:00Z", "scope_check_1", 1.0, "direct"),
        ]),
        "cold_start": AttestorRecord("cold_start", []),
    }
    
    print("=" * 70)
    print("BAYESIAN CREDIBILITY TRACKER — Mayerson 1964 / Bühlmann 1967")
    print(f"Population prior: {population_rate:.2f} | k={k} (Z=0.5 at n={int(k)})")
    print("=" * 70)
    print()
    
    print(f"{'Name':<22} {'n':>4} {'Z':>6} {'Indiv':>6} {'Blend':>6} {'CI±':>6} {'Grade':>5}")
    print("-" * 58)
    
    for name, record in attestors.items():
        result = compute_credibility(record, population_rate, k)
        print(f"{result['name']:<22} {result['n']:>4} {result['Z']:>6.3f} "
              f"{result['individual_rate']:>6.3f} {result['blended_estimate']:>6.3f} "
              f"{result['ci_width']:>6.3f} {result['grade']:>5}")
    
    print()
    print("Key insights:")
    print("  • cold_start: Z=0.000, uses population prior entirely (Grade F)")
    print("  • newcomer_unknown: n=2, Z=0.167, mostly prior (Grade F)")
    print("  • newcomer_good: n=5, Z=0.333, blending toward individual (Grade D)")
    print("  • veteran_unreliable: n=40, Z=0.800, track record dominates (Grade A)")
    print("  • veteran_reliable: n=50, Z=0.833, track record dominates (Grade A)")
    print()
    print("Z accumulation by channel (funwolf insight):")
    
    # Show channel breakdown
    for name, record in attestors.items():
        if record.n > 0:
            channels = {}
            for i in record.interactions:
                channels[i.channel] = channels.get(i.channel, 0) + 1
            ch_str = ", ".join(f"{c}={n}" for c, n in channels.items())
            print(f"  {name}: {ch_str}")
    
    print()
    print("Mayerson 1964: 'In 1950 the actuary stood nearly alone in his use")
    print("of statistical techniques to modify prior knowledge.'")
    print("SMTP is the accidental actuary. Each email = one more data point toward Z=1.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bayesian credibility tracker")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
