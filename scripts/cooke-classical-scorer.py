#!/usr/bin/env python3
"""cooke-classical-scorer.py — Cooke classical model for attestor calibration.

Implements structured expert judgment (Cooke 1991) for scoring attestors.
Seed variables with known outcomes test calibration + informativeness.
Performance-weighted combinations beat equal weights (Colson & Cooke 2018).

Usage:
    python3 cooke-classical-scorer.py [--demo]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class SeedQuestion:
    """Calibration question with known answer."""
    name: str
    true_value: float
    description: str


@dataclass
class AttestorAssessment:
    """Attestor's probabilistic assessment of a seed question."""
    p5: float   # 5th percentile
    p50: float  # 50th percentile (median)
    p95: float  # 95th percentile


@dataclass
class AttestorScore:
    """Cooke classical model scores."""
    name: str
    calibration: float      # Statistical accuracy (chi-squared test)
    informativeness: float  # Sharpness of distributions
    combined: float         # calibration × informativeness
    weight: float           # Normalized weight in combination
    grade: str


def compute_calibration(assessments: List[AttestorAssessment], 
                        seeds: List[SeedQuestion]) -> float:
    """Compute calibration score using empirical interquantile counts.
    
    For each seed, check which bin the true value falls in:
    [0, p5), [p5, p50), [p50, p95), [p95, inf)
    Compare empirical frequencies to theoretical (0.05, 0.45, 0.45, 0.05).
    """
    n = len(seeds)
    if n == 0:
        return 0.0
    
    bins = [0, 0, 0, 0]  # <p5, p5-p50, p50-p95, >p95
    theoretical = [0.05, 0.45, 0.45, 0.05]
    
    for seed, assess in zip(seeds, assessments):
        tv = seed.true_value
        if tv < assess.p5:
            bins[0] += 1
        elif tv < assess.p50:
            bins[1] += 1
        elif tv < assess.p95:
            bins[2] += 1
        else:
            bins[3] += 1
    
    # Chi-squared-like statistic (KL divergence approach from Cooke)
    # Lower divergence = better calibration
    empirical = [b / n for b in bins]
    kl = 0.0
    for e, t in zip(empirical, theoretical):
        if e > 0:
            kl += e * math.log(e / t)
    
    # Convert to p-value-like score (0-1, higher = better calibrated)
    # Using 2*n*KL as chi-squared with df=3
    chi2 = 2 * n * kl
    # Approximate p-value using chi-squared CDF with 3 df
    # Simple approximation: p ≈ exp(-chi2/2) for large chi2
    p_value = math.exp(-chi2 / 2) if chi2 < 50 else 0.0
    return min(1.0, p_value)


def compute_informativeness(assessments: List[AttestorAssessment],
                           seeds: List[SeedQuestion]) -> float:
    """Compute informativeness (sharpness) of assessments.
    
    Narrower credible intervals = more informative.
    Relative to a baseline uniform distribution.
    """
    if not assessments:
        return 0.0
    
    # Average relative width of 90% CI
    widths = []
    for seed, assess in zip(seeds, assessments):
        ci_width = assess.p95 - assess.p5
        # Normalize by true value magnitude (avoid division by zero)
        scale = max(abs(seed.true_value), 1.0)
        widths.append(ci_width / scale)
    
    avg_width = sum(widths) / len(widths)
    # Informativeness: narrower = higher score
    # Baseline width = 10 (very wide)
    info = max(0.0, 1.0 - avg_width / 10.0)
    return info


def grade_attestor(combined: float) -> str:
    """Assign letter grade based on combined score."""
    if combined >= 0.5: return "A"
    if combined >= 0.3: return "B"
    if combined >= 0.1: return "C"
    if combined >= 0.01: return "D"
    return "F"


def score_attestors(attestors: dict, seeds: List[SeedQuestion]) -> List[AttestorScore]:
    """Score all attestors using Cooke classical model."""
    scores = []
    
    for name, assessments in attestors.items():
        cal = compute_calibration(assessments, seeds)
        info = compute_informativeness(assessments, seeds)
        combined = cal * info
        scores.append(AttestorScore(
            name=name,
            calibration=round(cal, 4),
            informativeness=round(info, 4),
            combined=round(combined, 4),
            weight=0.0,  # Set after normalization
            grade=grade_attestor(combined)
        ))
    
    # Normalize weights
    total = sum(s.combined for s in scores)
    if total > 0:
        for s in scores:
            s.weight = round(s.combined / total, 4)
    
    # Sort by combined score descending
    scores.sort(key=lambda s: s.combined, reverse=True)
    return scores


def demo():
    """Demo with synthetic attestor data."""
    # 8 seed questions with known answers
    seeds = [
        SeedQuestion("benchmark_a", 0.85, "Task completion rate on standard benchmark"),
        SeedQuestion("benchmark_b", 0.72, "Response accuracy on factual questions"),
        SeedQuestion("latency_ms", 150.0, "Median response latency in ms"),
        SeedQuestion("drift_rate", 0.03, "Weekly behavioral drift rate"),
        SeedQuestion("uptime_pct", 99.2, "30-day uptime percentage"),
        SeedQuestion("error_rate", 0.08, "Error rate on known-answer questions"),
        SeedQuestion("scope_adherence", 0.91, "Scope boundary adherence rate"),
        SeedQuestion("ttl_compliance", 0.95, "TTL renewal compliance rate"),
    ]
    
    # 5 attestors with different assessment styles
    attestors = {
        "calibrated_fox": [  # Well-calibrated, informative
            AttestorAssessment(0.75, 0.84, 0.92),   # benchmark_a: true=0.85 ✓ in p50-p95
            AttestorAssessment(0.60, 0.70, 0.82),   # benchmark_b: true=0.72 ✓
            AttestorAssessment(100, 145, 220),        # latency: true=150 ✓
            AttestorAssessment(0.01, 0.03, 0.06),    # drift: true=0.03 ✓
            AttestorAssessment(98.5, 99.1, 99.7),    # uptime: true=99.2 ✓
            AttestorAssessment(0.04, 0.07, 0.12),    # error: true=0.08 ✓
            AttestorAssessment(0.85, 0.90, 0.96),    # scope: true=0.91 ✓
            AttestorAssessment(0.90, 0.94, 0.98),    # TTL: true=0.95 ✓
        ],
        "overconfident_hawk": [  # Narrow intervals, poor calibration
            AttestorAssessment(0.82, 0.84, 0.86),   # Too narrow
            AttestorAssessment(0.68, 0.70, 0.72),
            AttestorAssessment(140, 148, 155),
            AttestorAssessment(0.025, 0.030, 0.035),
            AttestorAssessment(99.0, 99.2, 99.4),
            AttestorAssessment(0.06, 0.07, 0.08),
            AttestorAssessment(0.89, 0.91, 0.93),
            AttestorAssessment(0.93, 0.95, 0.97),
        ],
        "vague_cloud": [  # Wide intervals, well-calibrated but uninformative
            AttestorAssessment(0.30, 0.80, 0.99),
            AttestorAssessment(0.20, 0.70, 0.99),
            AttestorAssessment(10, 200, 900),
            AttestorAssessment(0.001, 0.05, 0.50),
            AttestorAssessment(90.0, 98.0, 99.9),
            AttestorAssessment(0.001, 0.10, 0.80),
            AttestorAssessment(0.30, 0.85, 0.99),
            AttestorAssessment(0.30, 0.90, 0.99),
        ],
        "biased_bull": [  # Systematically optimistic
            AttestorAssessment(0.88, 0.92, 0.97),   # True=0.85, thinks higher
            AttestorAssessment(0.78, 0.82, 0.90),   # True=0.72, thinks higher
            AttestorAssessment(80, 120, 160),         # True=150, thinks faster
            AttestorAssessment(0.005, 0.01, 0.02),   # True=0.03, thinks lower
            AttestorAssessment(99.5, 99.7, 99.9),    # True=99.2, thinks higher
            AttestorAssessment(0.01, 0.03, 0.05),    # True=0.08, thinks lower
            AttestorAssessment(0.93, 0.96, 0.99),    # True=0.91, thinks higher
            AttestorAssessment(0.96, 0.98, 0.99),    # True=0.95, thinks higher
        ],
        "sybil_echo": [  # Copies biased_bull with noise (sybil detection target)
            AttestorAssessment(0.87, 0.91, 0.96),
            AttestorAssessment(0.77, 0.81, 0.89),
            AttestorAssessment(82, 122, 162),
            AttestorAssessment(0.006, 0.011, 0.021),
            AttestorAssessment(99.4, 99.6, 99.8),
            AttestorAssessment(0.012, 0.032, 0.052),
            AttestorAssessment(0.92, 0.95, 0.98),
            AttestorAssessment(0.95, 0.97, 0.99),
        ],
    }
    
    scores = score_attestors(attestors, seeds)
    
    print("=" * 65)
    print("COOKE CLASSICAL MODEL — ATTESTOR CALIBRATION SCORES")
    print("=" * 65)
    print(f"Seed questions: {len(seeds)}")
    print(f"Attestors: {len(attestors)}")
    print()
    
    print(f"{'Name':<22} {'Cal':>6} {'Info':>6} {'Comb':>6} {'Wt':>6} {'Grade':>5}")
    print("-" * 55)
    for s in scores:
        print(f"{s.name:<22} {s.calibration:>6.4f} {s.informativeness:>6.4f} "
              f"{s.combined:>6.4f} {s.weight:>6.4f} {s.grade:>5}")
    
    print()
    calibrated = sum(1 for s in scores if s.calibration > 0.05)
    print(f"Statistically calibrated (p>0.05): {calibrated}/{len(scores)} "
          f"({calibrated/len(scores)*100:.0f}%)")
    print(f"Cooke benchmark: <33% of experts pass calibration")
    print()
    
    # Sybil detection: correlation between biased_bull and sybil_echo
    bull_scores = [s for s in scores if s.name == "biased_bull"]
    echo_scores = [s for s in scores if s.name == "sybil_echo"]
    if bull_scores and echo_scores:
        b, e = bull_scores[0], echo_scores[0]
        diff = abs(b.combined - e.combined)
        print(f"⚠️  Sybil indicator: biased_bull/sybil_echo score difference = {diff:.4f}")
        if diff < 0.01:
            print("    SUSPICIOUS: Nearly identical scores suggest copied assessments")
    
    print()
    print("Key insight: Performance-weighted combination beats equal weights.")
    print("Credentials don't predict calibration. Track record does.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cooke classical model attestor scorer")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    demo()
