#!/usr/bin/env python3
"""cooke-classical-scorer.py — Cooke Classical Model attestor scoring.

Weight attestors by calibration on seed variables (known outcomes),
not by reputation, stake, or confidence. Based on Cooke 1991.

Key finding: 227/320 experts fail calibration at 5%. Expert mutual
rankings negatively correlated with actual performance.

Usage:
    python3 cooke-classical-scorer.py [--demo]
"""

import json
import math
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict


@dataclass
class SeedOutcome:
    """Known outcome for calibration."""
    variable: str
    true_value: float
    description: str


@dataclass 
class AttestorAssessment:
    """Attestor's probabilistic assessment on seed variable."""
    attestor_id: str
    variable: str
    p05: float  # 5th percentile
    p50: float  # 50th percentile  
    p95: float  # 95th percentile


def statistical_accuracy(assessments: List[AttestorAssessment], 
                         outcomes: List[SeedOutcome]) -> float:
    """Calibration p-value via chi-squared on interquantile bins."""
    outcome_map = {o.variable: o.true_value for o in outcomes}
    bins = [0, 0, 0, 0]  # <p05, p05-p50, p50-p95, >p95
    n = 0
    for a in assessments:
        if a.variable not in outcome_map:
            continue
        tv = outcome_map[a.variable]
        if tv < a.p05:
            bins[0] += 1
        elif tv < a.p50:
            bins[1] += 1
        elif tv < a.p95:
            bins[2] += 1
        else:
            bins[3] += 1
        n += 1
    
    if n == 0:
        return 0.0
    
    # Expected: 5%, 45%, 45%, 5%
    expected = [0.05 * n, 0.45 * n, 0.45 * n, 0.05 * n]
    chi2 = sum((o - e) ** 2 / max(e, 0.01) for o, e in zip(bins, expected))
    
    # Approximate p-value (chi2 with 3 df)
    # Using simple approximation
    if chi2 < 0.35:
        return 0.95
    elif chi2 < 1.21:
        return 0.75
    elif chi2 < 2.37:
        return 0.50
    elif chi2 < 6.25:
        return 0.10
    elif chi2 < 7.81:
        return 0.05
    else:
        return max(0.001, 0.05 * math.exp(-(chi2 - 7.81) / 3))


def informativeness(assessments: List[AttestorAssessment]) -> float:
    """Shannon relative information (tighter = more informative)."""
    if not assessments:
        return 0.0
    
    widths = []
    for a in assessments:
        width = a.p95 - a.p05
        if width > 0:
            widths.append(width)
    
    if not widths:
        return 0.0
    
    avg_width = sum(widths) / len(widths)
    # Normalize: narrower = more informative
    return max(0.0, min(1.0, 1.0 / (1.0 + avg_width)))


def combined_score(stat_acc: float, info: float) -> float:
    """Product of statistical accuracy and informativeness."""
    return stat_acc * info


def grade(score: float) -> str:
    if score >= 0.3: return "A"
    if score >= 0.15: return "B"
    if score >= 0.05: return "C"
    if score >= 0.01: return "D"
    return "F"


def demo():
    """Demo with 5 attestors, 8 seed variables."""
    random.seed(42)
    
    # Seed variables with known outcomes
    seeds = [
        SeedOutcome("uptime_pct", 0.94, "Agent uptime last 30 days"),
        SeedOutcome("scope_violations", 3, "Scope violations detected"),
        SeedOutcome("response_latency_ms", 450, "P95 response latency"),
        SeedOutcome("drift_score", 0.12, "Behavioral drift metric"),
        SeedOutcome("false_positive_rate", 0.08, "Monitor false positive rate"),
        SeedOutcome("attestation_freshness_hr", 2.5, "Avg attestation age"),
        SeedOutcome("capability_count", 12, "Active capabilities"),
        SeedOutcome("trust_score", 0.73, "Relying party trust score"),
    ]
    
    attestors = {
        "calibrated_alice": {  # Good calibration, tight intervals
            "uptime_pct": (0.90, 0.93, 0.97),
            "scope_violations": (1, 3, 6),
            "response_latency_ms": (200, 400, 800),
            "drift_score": (0.05, 0.10, 0.20),
            "false_positive_rate": (0.03, 0.07, 0.15),
            "attestation_freshness_hr": (1.0, 2.0, 4.0),
            "capability_count": (8, 11, 15),
            "trust_score": (0.60, 0.72, 0.85),
        },
        "overconfident_bob": {  # Tight intervals, often wrong
            "uptime_pct": (0.96, 0.98, 0.99),
            "scope_violations": (0, 1, 2),
            "response_latency_ms": (100, 200, 300),
            "drift_score": (0.01, 0.03, 0.05),
            "false_positive_rate": (0.01, 0.02, 0.04),
            "attestation_freshness_hr": (0.5, 1.0, 1.5),
            "capability_count": (5, 7, 9),
            "trust_score": (0.80, 0.90, 0.95),
        },
        "rubber_stamp": {  # Wide intervals, always "captures" truth
            "uptime_pct": (0.50, 0.75, 1.00),
            "scope_violations": (0, 5, 20),
            "response_latency_ms": (50, 500, 5000),
            "drift_score": (0.00, 0.25, 0.50),
            "false_positive_rate": (0.00, 0.10, 0.50),
            "attestation_freshness_hr": (0.1, 5.0, 24.0),
            "capability_count": (1, 10, 50),
            "trust_score": (0.10, 0.50, 0.95),
        },
        "stale_charlie": {  # Good once, now drifted
            "uptime_pct": (0.85, 0.90, 0.95),
            "scope_violations": (5, 8, 12),
            "response_latency_ms": (500, 700, 1000),
            "drift_score": (0.20, 0.30, 0.50),
            "false_positive_rate": (0.10, 0.15, 0.25),
            "attestation_freshness_hr": (5.0, 8.0, 12.0),
            "capability_count": (15, 20, 30),
            "trust_score": (0.40, 0.55, 0.65),
        },
        "sybil_echo": {  # Copies overconfident_bob with noise
            "uptime_pct": (0.95, 0.97, 0.99),
            "scope_violations": (0, 1, 3),
            "response_latency_ms": (100, 250, 350),
            "drift_score": (0.01, 0.04, 0.06),
            "false_positive_rate": (0.01, 0.03, 0.05),
            "attestation_freshness_hr": (0.5, 1.2, 1.8),
            "capability_count": (5, 8, 10),
            "trust_score": (0.78, 0.88, 0.94),
        },
    }
    
    print("=" * 60)
    print("COOKE CLASSICAL MODEL — ATTESTOR SCORING")
    print("=" * 60)
    print(f"\nSeed variables: {len(seeds)}")
    print(f"Attestors: {len(attestors)}")
    print()
    
    results = []
    for name, assessments_raw in attestors.items():
        assmts = [
            AttestorAssessment(name, var, p05, p50, p95)
            for var, (p05, p50, p95) in assessments_raw.items()
        ]
        sa = statistical_accuracy(assmts, seeds)
        info = informativeness(assmts)
        cs = combined_score(sa, info)
        g = grade(cs)
        results.append((name, sa, info, cs, g))
        
    # Sort by combined score
    results.sort(key=lambda x: -x[3])
    
    # Performance-weighted combination
    total_cs = sum(r[3] for r in results)
    
    for name, sa, info, cs, g in results:
        pw = cs / total_cs if total_cs > 0 else 0
        print(f"[{g}] {name}")
        print(f"    Statistical accuracy: {sa:.3f}")
        print(f"    Informativeness:      {info:.3f}")
        print(f"    Combined score:       {cs:.4f}")
        print(f"    Performance weight:   {pw:.1%}")
        print()
    
    print("-" * 60)
    print("KEY FINDINGS (Cooke 1991 data):")
    print("- 227/320 experts fail calibration at 5% threshold")
    print("- Expert mutual rankings NEGATIVELY correlated with performance")
    print("- Reputation/stake/confidence ≠ calibration quality")
    print("- Seed variable validation is the ONLY reliable weighting")
    print()
    
    # Check for sybil correlation
    bob_idx = next(i for i, r in enumerate(results) if r[0] == "overconfident_bob")
    echo_idx = next(i for i, r in enumerate(results) if r[0] == "sybil_echo")
    print(f"⚠️  Sybil detection: bob score={results[bob_idx][3]:.4f}, "
          f"echo score={results[echo_idx][3]:.4f}")
    print(f"   Correlated poor performers get correlated LOW weights.")
    print(f"   Equal weighting would give sybils 2/{len(attestors)} = "
          f"{2/len(attestors):.0%} influence.")
    print(f"   Performance weighting gives them: "
          f"{(results[bob_idx][3] + results[echo_idx][3]) / total_cs:.1%}")


if __name__ == "__main__":
    import sys
    demo()
