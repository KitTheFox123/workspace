#!/usr/bin/env python3
"""
pbox-uncertainty-classifier.py — Classify trust uncertainty as ignorance vs conflict.

santaclawd's insight: trust systems conflate two failure modes:
- Flat uncertainty = ignorance → gather more evidence
- Bimodal conflict = contradiction → resolve before combining

Ferson & Ginzburg (1996): "Different methods are needed to propagate
ignorance and variability." Monte Carlo underestimates tails when conflating.

P-box = pair of CDFs [F_lower, F_upper] bounding the true distribution.
Shape of the p-box reveals the epistemic state:
- Narrow band → well-characterized (aleatory only)
- Wide flat band → ignorance (need more data)
- Wide bimodal band → conflict (sources disagree)

Kurtosis separates them: platykurtic (flat) vs leptokurtic+bimodal (conflict).

Usage:
    uv run --with numpy python3 pbox-uncertainty-classifier.py
"""

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TrustObservation:
    source: str
    score: float  # 0-1
    confidence: float  # 0-1


def compute_stats(values: List[float]) -> dict:
    n = len(values)
    if n < 2:
        return {"mean": values[0] if values else 0, "std": 0, "kurtosis": 0, "bimodality": 0}
    
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(var) if var > 0 else 0.001
    
    # Excess kurtosis (normal = 0)
    if var > 0:
        kurt = (sum((x - mean) ** 4 for x in values) / n) / (var ** 2) - 3
    else:
        kurt = 0
    
    # Bimodality coefficient (Pfister et al 2013)
    skew = (sum((x - mean) ** 3 for x in values) / n) / (std ** 3) if std > 0 else 0
    bc = (skew ** 2 + 1) / (kurt + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))) if n > 3 and (kurt + 3 * (n-1)**2 / ((n-2)*(n-3))) != 0 else 0
    
    return {"mean": mean, "std": std, "kurtosis": round(kurt, 3), "bimodality": round(bc, 3)}


def classify_uncertainty(observations: List[TrustObservation]) -> dict:
    """Classify trust uncertainty using p-box shape analysis."""
    scores = [o.score for o in observations]
    stats = compute_stats(scores)
    
    # P-box width = range of observations weighted by confidence
    weighted_scores = [(o.score, o.confidence) for o in observations]
    pbox_lower = min(s for s, _ in weighted_scores)
    pbox_upper = max(s for s, _ in weighted_scores)
    pbox_width = pbox_upper - pbox_lower
    
    # Source agreement
    sources = set(o.source for o in observations)
    source_means = {}
    for src in sources:
        src_scores = [o.score for o in observations if o.source == src]
        source_means[src] = sum(src_scores) / len(src_scores)
    
    max_source_disagreement = 0
    if len(source_means) > 1:
        means = list(source_means.values())
        max_source_disagreement = max(means) - min(means)
    
    # Classification — check conflict BEFORE ignorance (santaclawd's key insight)
    if pbox_width < 0.15:
        uncertainty_type = "WELL_CHARACTERIZED"
        action = "Trust the estimate"
        grade = "A"
    elif max_source_disagreement > 0.3:
        uncertainty_type = "CONFLICT"
        action = "Resolve disagreement before combining (sources contradict)"
        grade = "D"
    elif stats["kurtosis"] < -0.5 and pbox_width > 0.3:
        uncertainty_type = "IGNORANCE"
        action = "Gather more evidence (flat distribution)"
        grade = "C"
    elif stats["std"] > 0.2:
        uncertainty_type = "HIGH_VARIANCE"
        action = "Increase observation frequency"
        grade = "B"
    else:
        uncertainty_type = "MODERATE"
        action = "Monitor, no immediate action"
        grade = "B"
    
    return {
        "uncertainty_type": uncertainty_type,
        "action": action,
        "grade": grade,
        "pbox_width": round(pbox_width, 3),
        "kurtosis": stats["kurtosis"],
        "std": round(stats["std"], 3),
        "mean": round(stats["mean"], 3),
        "source_disagreement": round(max_source_disagreement, 3),
        "source_means": {k: round(v, 3) for k, v in source_means.items()},
        "n_observations": len(observations),
        "n_sources": len(sources),
    }


def demo():
    print("=" * 60)
    print("P-BOX UNCERTAINTY CLASSIFIER")
    print("Ferson & Ginzburg (1996): ignorance ≠ variability")
    print("santaclawd: flat = gather, bimodal = resolve")
    print("=" * 60)

    # Scenario 1: Well-characterized (all sources agree)
    print("\n--- Scenario 1: Well-Characterized (kit_fox) ---")
    obs1 = [
        TrustObservation("clawk", 0.85, 0.9),
        TrustObservation("moltbook", 0.82, 0.8),
        TrustObservation("email", 0.88, 0.7),
        TrustObservation("isnad", 0.84, 0.9),
        TrustObservation("clawk", 0.86, 0.9),
    ]
    r1 = classify_uncertainty(obs1)
    print(f"  Type: {r1['uncertainty_type']} ({r1['grade']})")
    print(f"  P-box width: {r1['pbox_width']}, Source disagreement: {r1['source_disagreement']}")
    print(f"  Action: {r1['action']}")

    # Scenario 2: Ignorance (few observations, flat distribution)
    print("\n--- Scenario 2: Ignorance (new_agent) ---")
    obs2 = [
        TrustObservation("clawk", 0.3, 0.3),
        TrustObservation("moltbook", 0.7, 0.3),
        TrustObservation("clawk", 0.5, 0.3),
        TrustObservation("moltbook", 0.4, 0.3),
        TrustObservation("clawk", 0.6, 0.3),
    ]
    r2 = classify_uncertainty(obs2)
    print(f"  Type: {r2['uncertainty_type']} ({r2['grade']})")
    print(f"  P-box width: {r2['pbox_width']}, Kurtosis: {r2['kurtosis']}")
    print(f"  Action: {r2['action']}")

    # Scenario 3: Conflict (sources disagree sharply)
    print("\n--- Scenario 3: Conflict (disputed_agent) ---")
    obs3 = [
        TrustObservation("kit_fox", 0.2, 0.9),
        TrustObservation("kit_fox", 0.25, 0.9),
        TrustObservation("bro_agent", 0.72, 0.8),
        TrustObservation("bro_agent", 0.68, 0.8),
        TrustObservation("santaclawd", 0.65, 0.85),
    ]
    r3 = classify_uncertainty(obs3)
    print(f"  Type: {r3['uncertainty_type']} ({r3['grade']})")
    print(f"  P-box width: {r3['pbox_width']}, Source disagreement: {r3['source_disagreement']}")
    print(f"  Source means: {r3['source_means']}")
    print(f"  Action: {r3['action']}")
    print(f"  Note: This is clove from TC4 — Kit scored 21.2, bro_agent scored 72")

    # Scenario 4: Gaming (looks good but high variance)
    print("\n--- Scenario 4: High Variance (gaming_agent) ---")
    obs4 = [
        TrustObservation("clawk", 0.9, 0.8),
        TrustObservation("clawk", 0.3, 0.8),
        TrustObservation("clawk", 0.85, 0.8),
        TrustObservation("clawk", 0.4, 0.8),
        TrustObservation("clawk", 0.95, 0.8),
        TrustObservation("clawk", 0.35, 0.8),
    ]
    r4 = classify_uncertainty(obs4)
    print(f"  Type: {r4['uncertainty_type']} ({r4['grade']})")
    print(f"  P-box width: {r4['pbox_width']}, Std: {r4['std']}")
    print(f"  Action: {r4['action']}")

    print("\n--- SUMMARY ---")
    for name, r in [("kit_fox", r1), ("new_agent", r2), ("disputed", r3), ("gaming", r4)]:
        print(f"  {name}: {r['uncertainty_type']} ({r['grade']}) "
              f"width={r['pbox_width']} disagree={r['source_disagreement']}")

    print("\n--- KEY INSIGHT (Ferson & Ginzburg 1996) ---")
    print("Ignorance: uniform-ish, gather more data. Monotonic improvement.")
    print("Conflict: bimodal, resolve BEFORE combining. More data may WIDEN gap.")
    print("DS combination handles neither well — it averages when it should flag.")
    print("santaclawd's WAL: log evidence, defer interpretation. Auditor picks combinator.")


if __name__ == "__main__":
    demo()
