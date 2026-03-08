#!/usr/bin/env python3
"""alpha-diagnostic.py — Krippendorff alpha tentative zone diagnostic.

When alpha lands in 0.67-0.79 ("tentative zone"), the cause matters:
- Correlated bias: attestors agree with each other but are all wrong → diversity fix
- Inconsistent criteria: attestors disagree randomly → calibration fix

Uses leave-one-out analysis to distinguish the two failure modes.

Based on: Krippendorff (2019) Content Analysis 4th Ed, Marzi et al (2024).
Inspired by santaclawd's diagnostic question on Clawk.

Usage:
    python3 alpha-diagnostic.py --demo
"""

import argparse
import json
from dataclasses import dataclass, asdict
from itertools import combinations


def krippendorff_alpha(ratings: list[list[float | None]]) -> float:
    """Compute Krippendorff's alpha for interval data.
    
    ratings: list of raters, each a list of scores (None = missing).
    """
    n_items = len(ratings[0])
    n_raters = len(ratings)
    
    # Build pairable values per item
    pairs_observed = 0
    sum_sq_diff_observed = 0.0
    all_values = []
    
    for item in range(n_items):
        values = [ratings[r][item] for r in range(n_raters) if ratings[r][item] is not None]
        all_values.extend(values)
        m = len(values)
        if m < 2:
            continue
        for i in range(m):
            for j in range(i + 1, m):
                sum_sq_diff_observed += (values[i] - values[j]) ** 2
                pairs_observed += 1
    
    if pairs_observed == 0:
        return 0.0
    
    D_o = sum_sq_diff_observed / pairs_observed
    
    # Expected disagreement
    n_total = len(all_values)
    if n_total < 2:
        return 0.0
    
    sum_sq_diff_expected = 0.0
    pairs_expected = 0
    for i in range(n_total):
        for j in range(i + 1, n_total):
            sum_sq_diff_expected += (all_values[i] - all_values[j]) ** 2
            pairs_expected += 1
    
    D_e = sum_sq_diff_expected / pairs_expected if pairs_expected > 0 else 1.0
    
    if D_e == 0:
        return 1.0
    
    return 1.0 - (D_o / D_e)


@dataclass
class DiagnosticResult:
    overall_alpha: float
    zone: str  # "reliable", "tentative", "unreliable"
    leave_one_out: dict  # rater_name -> alpha_without
    diagnosis: str  # "correlated_bias", "inconsistent_criteria", "mixed", "healthy"
    problematic_raters: list[str]
    alpha_range: float  # max - min of leave-one-out
    recommendation: str


def diagnose(ratings: dict[str, list[float | None]]) -> DiagnosticResult:
    """Run leave-one-out diagnostic on attestor ratings."""
    rater_names = list(ratings.keys())
    rating_matrix = [ratings[name] for name in rater_names]
    
    overall = krippendorff_alpha(rating_matrix)
    
    # Zone classification
    if overall >= 0.80:
        zone = "reliable"
    elif overall >= 0.67:
        zone = "tentative"
    else:
        zone = "unreliable"
    
    # Leave-one-out
    loo = {}
    for i, name in enumerate(rater_names):
        reduced = [rating_matrix[j] for j in range(len(rater_names)) if j != i]
        loo[name] = round(krippendorff_alpha(reduced), 4)
    
    alpha_range = max(loo.values()) - min(loo.values())
    
    # Diagnosis
    # If dropping one rater causes big alpha jump → that rater is inconsistent
    problematic = []
    threshold = 0.05  # 5% alpha improvement = significant
    for name, alpha_without in loo.items():
        if alpha_without - overall > threshold:
            problematic.append(name)
    
    if len(problematic) > 0:
        diagnosis = "inconsistent_criteria"
        recommendation = f"Calibrate rater(s): {', '.join(problematic)}. Their removal improves alpha by {max(loo[p] - overall for p in problematic):.3f}."
    elif alpha_range < 0.02 and zone == "tentative":
        diagnosis = "correlated_bias"
        recommendation = "All raters contribute equally to disagreement. Inject attestor diversity — different providers, models, or data sources."
    elif zone == "reliable":
        diagnosis = "healthy"
        recommendation = "Alpha is reliable. No intervention needed."
    else:
        diagnosis = "mixed"
        recommendation = "No single rater is clearly problematic. Review criteria definitions and add diverse attestors."
    
    return DiagnosticResult(
        overall_alpha=round(overall, 4),
        zone=zone,
        leave_one_out=loo,
        diagnosis=diagnosis,
        problematic_raters=problematic,
        alpha_range=round(alpha_range, 4),
        recommendation=recommendation,
    )


def demo():
    """Demo with two scenarios: correlated bias vs inconsistent criteria."""
    print("=" * 60)
    print("KRIPPENDORFF ALPHA TENTATIVE ZONE DIAGNOSTIC")
    print("=" * 60)
    
    # Scenario 1: Correlated bias — all raters agree but are systematically off
    print("\n--- Scenario 1: Correlated Bias ---")
    print("All attestors from same provider, similar scoring patterns")
    correlated = {
        "attestor_A": [0.8, 0.7, 0.9, 0.6, 0.8, 0.7, 0.5, 0.9],
        "attestor_B": [0.7, 0.8, 0.8, 0.7, 0.7, 0.8, 0.6, 0.8],
        "attestor_C": [0.8, 0.7, 0.9, 0.6, 0.8, 0.6, 0.5, 0.9],
        "attestor_D": [0.7, 0.8, 0.8, 0.7, 0.7, 0.7, 0.6, 0.8],
    }
    r1 = diagnose(correlated)
    print(f"  Alpha: {r1.overall_alpha} ({r1.zone})")
    print(f"  LOO range: {r1.alpha_range}")
    print(f"  Diagnosis: {r1.diagnosis}")
    print(f"  Recommendation: {r1.recommendation}")
    
    # Scenario 2: Inconsistent criteria — one rater is off
    print("\n--- Scenario 2: Inconsistent Criteria ---")
    print("One attestor using different scoring criteria")
    inconsistent = {
        "attestor_A": [0.9, 0.8, 0.7, 0.9, 0.8, 0.9, 0.7, 0.8],
        "attestor_B": [0.9, 0.7, 0.8, 0.9, 0.8, 0.8, 0.7, 0.9],
        "attestor_C": [0.8, 0.8, 0.7, 0.8, 0.9, 0.9, 0.8, 0.8],
        "rogue_rater": [0.3, 0.9, 0.2, 0.8, 0.3, 0.4, 0.9, 0.2],
    }
    r2 = diagnose(inconsistent)
    print(f"  Alpha: {r2.overall_alpha} ({r2.zone})")
    print(f"  LOO: {r2.leave_one_out}")
    print(f"  Diagnosis: {r2.diagnosis}")
    print(f"  Problematic: {r2.problematic_raters}")
    print(f"  Recommendation: {r2.recommendation}")
    
    # Scenario 3: Healthy
    print("\n--- Scenario 3: Healthy Agreement ---")
    healthy = {
        "attestor_A": [0.9, 0.3, 0.8, 0.2, 0.7, 0.9, 0.4, 0.8],
        "attestor_B": [0.9, 0.2, 0.8, 0.3, 0.7, 0.9, 0.3, 0.8],
        "attestor_C": [0.8, 0.3, 0.9, 0.2, 0.8, 0.8, 0.4, 0.7],
    }
    r3 = diagnose(healthy)
    print(f"  Alpha: {r3.overall_alpha} ({r3.zone})")
    print(f"  Diagnosis: {r3.diagnosis}")
    print(f"  Recommendation: {r3.recommendation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Krippendorff alpha tentative zone diagnostic")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    else:
        demo()
