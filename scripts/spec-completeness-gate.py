#!/usr/bin/env python3
"""
spec-completeness-gate.py — Gates escrow lock on specification completeness.

Based on:
- santaclawd: "escrow solves delivery verification, none solve spec verification"
- Sorensen (IEEE 2024): 60%+ smart contract disputes trace to incomplete specs
- bro_agent: acceptance_criteria_hash locked at escrow creation

The problem: hash(artifact) == spec_hash. Correct hash, wrong behavior.
The spec was vague → dispute is about interpretation, not fraud.

Dimensions scored:
1. Acceptance criteria count (measurable outcomes)
2. Measurability (each criterion has a metric + threshold)
3. Boundary conditions (partial delivery, edge cases)
4. Timeout clause (what happens if neither party acts)
5. Dispute resolution (who decides, how)
6. Scope hash (prevents scope creep post-lock)
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Criterion:
    description: str
    metric: Optional[str] = None      # How to measure
    threshold: Optional[float] = None  # Pass/fail threshold
    boundary: Optional[str] = None     # Edge case handling


@dataclass
class Spec:
    title: str
    criteria: list[Criterion] = field(default_factory=list)
    timeout_hours: Optional[int] = None
    dispute_method: Optional[str] = None
    partial_delivery_clause: bool = False


def score_spec(spec: Spec) -> dict:
    """Score a spec on completeness dimensions."""
    scores = {}

    # 1. Criteria count (0 = F, 1-2 = C, 3+ = A)
    n = len(spec.criteria)
    scores["criteria_count"] = min(1.0, n / 3)

    # 2. Measurability (fraction with metric + threshold)
    if n > 0:
        measurable = sum(1 for c in spec.criteria if c.metric and c.threshold is not None)
        scores["measurability"] = measurable / n
    else:
        scores["measurability"] = 0.0

    # 3. Boundary conditions (fraction with boundary defined)
    if n > 0:
        bounded = sum(1 for c in spec.criteria if c.boundary)
        scores["boundaries"] = bounded / n
    else:
        scores["boundaries"] = 0.0

    # 4. Timeout clause
    scores["timeout"] = 1.0 if spec.timeout_hours is not None else 0.0

    # 5. Dispute resolution
    scores["dispute"] = 1.0 if spec.dispute_method else 0.0

    # 6. Partial delivery
    scores["partial_delivery"] = 1.0 if spec.partial_delivery_clause else 0.0

    # Weighted composite
    weights = {
        "criteria_count": 0.20,
        "measurability": 0.30,  # Most important
        "boundaries": 0.15,
        "timeout": 0.15,
        "dispute": 0.10,
        "partial_delivery": 0.10,
    }

    composite = sum(scores[k] * weights[k] for k in weights)

    # Grade
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"

    # Gate decision
    gate = "LOCK_ALLOWED" if composite >= 0.6 else "LOCK_DENIED"

    # Scope hash
    spec_content = json.dumps({
        "title": spec.title,
        "criteria": [{"desc": c.description, "metric": c.metric,
                       "threshold": c.threshold, "boundary": c.boundary}
                      for c in spec.criteria],
        "timeout": spec.timeout_hours,
        "dispute": spec.dispute_method,
    }, sort_keys=True)
    scope_hash = hashlib.sha256(spec_content.encode()).hexdigest()[:16]

    return {
        "scores": scores,
        "composite": round(composite, 3),
        "grade": grade,
        "gate": gate,
        "scope_hash": scope_hash,
        "missing": [k for k, v in scores.items() if v < 0.5],
    }


def main():
    print("=" * 70)
    print("SPEC COMPLETENESS GATE")
    print("santaclawd: 'none solve spec verification'")
    print("=" * 70)

    specs = [
        # Good spec (TC4-like)
        Spec(
            title="Research deliverable: agent economy analysis",
            criteria=[
                Criterion("Word count ≥ 5000", "word_count", 5000, "5000-10000 range"),
                Criterion("Sources ≥ 10 primary", "source_count", 10, "Wikipedia excluded"),
                Criterion("Thesis defended in thread", "thread_defense", 1.0, "Minimum 3 substantive replies"),
            ],
            timeout_hours=72,
            dispute_method="independent_scorer_brier",
            partial_delivery_clause=True,
        ),
        # Vague spec (typical marketplace)
        Spec(
            title="Build me a website",
            criteria=[
                Criterion("Website works"),
                Criterion("Looks good"),
            ],
        ),
        # Medium spec
        Spec(
            title="Data analysis report",
            criteria=[
                Criterion("Analysis of 100+ records", "record_count", 100),
                Criterion("3+ visualizations", "viz_count", 3),
            ],
            timeout_hours=48,
        ),
        # Empty spec
        Spec(title="Do the thing"),
    ]

    print(f"\n{'Spec':<45} {'Grade':<6} {'Score':<7} {'Gate':<15} {'Missing'}")
    print("-" * 95)

    for spec in specs:
        result = score_spec(spec)
        missing = ", ".join(result["missing"]) if result["missing"] else "none"
        print(f"{spec.title:<45} {result['grade']:<6} {result['composite']:<7.3f} "
              f"{result['gate']:<15} {missing}")

    print("\n--- Detailed: TC4-like spec ---")
    r = score_spec(specs[0])
    for dim, score in r["scores"].items():
        status = "✅" if score >= 0.5 else "❌"
        print(f"  {status} {dim}: {score:.2f}")
    print(f"  scope_hash: {r['scope_hash']}")

    print("\n--- Key Insight ---")
    print("Sorensen (IEEE 2024): 60%+ disputes = incomplete specs, not fraud.")
    print("Gate threshold: composite ≥ 0.6 to lock funds.")
    print("Below threshold: escrow REFUSES to lock.")
    print()
    print("scope_hash = SHA-256 of spec at lock time.")
    print("Post-lock spec changes = scope_hash mismatch = automatic dispute.")
    print("The spec IS the contract. Lock it or lose it.")


if __name__ == "__main__":
    main()
