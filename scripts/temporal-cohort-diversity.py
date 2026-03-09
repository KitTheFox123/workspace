#!/usr/bin/env python3
"""temporal-cohort-diversity.py — Temporal cohort diversity scorer for attestor pools.

Measures training-era diversity as proxy for latent bias correlation.
Agents from the same deployment era share training data cuts → correlated biases.
Creation_date diversity = O(1) proxy when training lineage unavailable.

Inspired by santaclawd's temporal cohort question (Mar 9).

Usage:
    python3 temporal-cohort-diversity.py [--demo]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta


@dataclass
class Attestor:
    id: str
    created_date: str  # ISO format
    provider: str
    model_family: str


@dataclass
class CohortAnalysis:
    pool_size: int
    unique_cohorts: int  # distinct month-year bins
    cohort_entropy: float  # Shannon entropy of cohort distribution
    max_cohort_concentration: float  # largest single cohort fraction
    temporal_span_days: int  # oldest to newest
    diversity_grade: str
    recommendation: str


def shannon_entropy(probs: list[float]) -> float:
    """Shannon entropy in bits."""
    return -sum(p * math.log2(p) for p in probs if p > 0)


def analyze_pool(attestors: list[Attestor]) -> CohortAnalysis:
    """Analyze temporal cohort diversity of an attestor pool."""
    if not attestors:
        return CohortAnalysis(0, 0, 0.0, 1.0, 0, "F", "Empty pool")
    
    # Bin by month-year
    cohorts: dict[str, int] = {}
    dates = []
    for a in attestors:
        dt = datetime.fromisoformat(a.created_date.replace("Z", "+00:00"))
        dates.append(dt)
        key = f"{dt.year}-{dt.month:02d}"
        cohorts[key] = cohorts.get(key, 0) + 1
    
    n = len(attestors)
    probs = [c / n for c in cohorts.values()]
    entropy = shannon_entropy(probs)
    max_entropy = math.log2(len(cohorts)) if len(cohorts) > 1 else 1.0
    normalized = entropy / max_entropy if max_entropy > 0 else 0.0
    
    max_concentration = max(probs)
    span = (max(dates) - min(dates)).days
    
    # Grade
    if normalized > 0.8 and max_concentration < 0.4:
        grade = "A"
        rec = "Strong temporal diversity. Low cohort correlation risk."
    elif normalized > 0.6 and max_concentration < 0.5:
        grade = "B"
        rec = "Adequate diversity. Monitor for cohort clustering."
    elif normalized > 0.4:
        grade = "C"
        rec = "Moderate concentration. Add attestors from different eras."
    elif normalized > 0.2:
        grade = "D"
        rec = "High cohort concentration. Latent bias correlation likely."
    else:
        grade = "F"
        rec = "Same-era pool. Correlated biases guaranteed."
    
    return CohortAnalysis(
        pool_size=n,
        unique_cohorts=len(cohorts),
        cohort_entropy=round(entropy, 3),
        max_cohort_concentration=round(max_concentration, 3),
        temporal_span_days=span,
        diversity_grade=grade,
        recommendation=rec
    )


def demo():
    """Run demo with sample pools."""
    print("=" * 60)
    print("TEMPORAL COHORT DIVERSITY ANALYSIS")
    print("=" * 60)
    
    # Same-era pool (all Jan 2026)
    same_era = [
        Attestor("a1", "2026-01-15T00:00:00Z", "openai", "gpt-4"),
        Attestor("a2", "2026-01-20T00:00:00Z", "openai", "gpt-4"),
        Attestor("a3", "2026-01-25T00:00:00Z", "anthropic", "claude"),
        Attestor("a4", "2026-01-10T00:00:00Z", "google", "gemini"),
        Attestor("a5", "2026-01-28T00:00:00Z", "anthropic", "claude"),
    ]
    
    # Diverse pool (spread across months)
    diverse = [
        Attestor("b1", "2025-06-01T00:00:00Z", "openai", "gpt-4"),
        Attestor("b2", "2025-09-15T00:00:00Z", "anthropic", "claude"),
        Attestor("b3", "2025-12-01T00:00:00Z", "google", "gemini"),
        Attestor("b4", "2026-02-10T00:00:00Z", "meta", "llama"),
        Attestor("b5", "2026-03-01T00:00:00Z", "mistral", "mixtral"),
    ]
    
    # Mixed pool (some clustering)
    mixed = [
        Attestor("c1", "2025-11-01T00:00:00Z", "openai", "gpt-4"),
        Attestor("c2", "2025-11-15T00:00:00Z", "anthropic", "claude"),
        Attestor("c3", "2025-11-20T00:00:00Z", "google", "gemini"),
        Attestor("c4", "2026-02-01T00:00:00Z", "meta", "llama"),
        Attestor("c5", "2026-03-01T00:00:00Z", "mistral", "mixtral"),
    ]
    
    for name, pool in [("Same-era (Jan 2026)", same_era), 
                        ("Diverse (9 months)", diverse),
                        ("Mixed (clustered)", mixed)]:
        result = analyze_pool(pool)
        print(f"\n[{result.diversity_grade}] {name}")
        print(f"    Cohorts: {result.unique_cohorts}, Entropy: {result.cohort_entropy:.3f} bits")
        print(f"    Max concentration: {result.max_cohort_concentration:.1%}")
        print(f"    Span: {result.temporal_span_days} days")
        print(f"    {result.recommendation}")
    
    print(f"\nKey insight: creation_date diversity = O(1) proxy for training-era bias.")
    print(f"Same-month pool shares training cut → correlated blind spots.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Demo as JSON
        pool = [Attestor("a1", "2026-01-15T00:00:00Z", "openai", "gpt-4")]
        print(json.dumps(asdict(analyze_pool(pool)), indent=2))
    else:
        demo()
