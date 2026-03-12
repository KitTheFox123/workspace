#!/usr/bin/env python3
"""
uncertainty-type-classifier.py — Classify uncertainty TYPE, not magnitude.

Kirchhof et al (ICLR 2025): 8 definitions of epistemic uncertainty contradict.
"Bimodal" is maximal epistemic by disagreement def, minimal by model-count def.
Stop asking "how uncertain" — ask "what KIND of uncertain."

Types:
- CONSENSUS: narrow distribution, low variance → trust or distrust with confidence
- IGNORANCE: flat/uniform → need more data, any direction
- CONFLICT: bimodal/multimodal → attestors fundamentally disagree (Zadeh paradox territory)
- NOISE: high variance, unimodal → aleatory, more data won't help

Actions differ:
- CONSENSUS → act on it
- IGNORANCE → gather more evidence
- CONFLICT → resolve disagreement (different from gathering)
- NOISE → accept irreducible uncertainty

Usage:
    uv run --with numpy python3 uncertainty-type-classifier.py
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class AttestationSet:
    """A set of trust scores from different attestors for one agent."""
    agent: str
    scores: List[float]  # trust scores [0,1] from different attestors
    attestor_names: List[str]


def bimodality_coefficient(scores: np.ndarray) -> float:
    """Sarle's bimodality coefficient. >0.555 suggests bimodality."""
    n = len(scores)
    if n < 3:
        return 0.0
    skew = float(np.mean(((scores - np.mean(scores)) / np.std(scores)) ** 3))
    kurt = float(np.mean(((scores - np.mean(scores)) / np.std(scores)) ** 4))
    bc = (skew ** 2 + 1) / (kurt + 3 * ((n - 1) ** 2) / ((n - 2) * (n - 3)))
    return min(bc, 1.0)


def classify_uncertainty(attestations: AttestationSet) -> dict:
    """Classify the TYPE of uncertainty in attestation scores."""
    scores = np.array(attestations.scores)
    n = len(scores)

    if n < 2:
        return {"type": "INSUFFICIENT", "grade": "F", "action": "gather more attestors"}

    mean = float(np.mean(scores))
    std = float(np.std(scores))
    spread = float(np.max(scores) - np.min(scores))
    bc = bimodality_coefficient(scores)

    # Classification
    if std < 0.08 and spread < 0.2:
        utype = "CONSENSUS"
        grade = "A"
        action = "act on consensus"
        confidence = "high"
    elif bc > 0.5 and spread > 0.4:
        utype = "CONFLICT"
        grade = "D"
        action = "resolve disagreement between attestors (Zadeh territory)"
        confidence = "low — attestors fundamentally disagree"
    elif std > 0.25 and bc < 0.4:
        utype = "NOISE"
        grade = "C"
        action = "accept irreducible variance, use p-box bounds"
        confidence = "bounded — more data won't converge"
    elif std > 0.15:
        utype = "IGNORANCE"
        grade = "B"
        action = "gather more evidence from diverse sources"
        confidence = "medium — data may resolve"
    else:
        utype = "CONSENSUS"
        grade = "A"
        action = "act on consensus"
        confidence = "moderate"

    # Kirchhof paradox check
    kirchhof_paradox = False
    if utype == "CONFLICT":
        # Two strong opposing views = maximal epistemic by disagreement def,
        # minimal by model-count def (only 2 models left)
        kirchhof_paradox = True

    return {
        "agent": attestations.agent,
        "type": utype,
        "grade": grade,
        "action": action,
        "confidence": confidence,
        "mean_score": round(mean, 3),
        "std": round(std, 3),
        "spread": round(spread, 3),
        "bimodality": round(bc, 3),
        "n_attestors": n,
        "kirchhof_paradox": kirchhof_paradox,
    }


def demo():
    print("=" * 60)
    print("UNCERTAINTY TYPE CLASSIFIER")
    print("Kirchhof et al (ICLR 2025): what KIND, not how much")
    print("=" * 60)

    scenarios = [
        AttestationSet("kit_fox", [0.85, 0.82, 0.88, 0.84, 0.86],
                       ["bro_agent", "gendolf", "gerundium", "braindiff", "temporal"]),
        AttestationSet("contested_agent", [0.91, 0.12, 0.88, 0.15, 0.93, 0.18],
                       ["llm_1", "rule_based", "llm_2", "behavioral", "llm_3", "temporal"]),
        AttestationSet("unknown_agent", [0.55, 0.62, 0.48, 0.71, 0.39],
                       ["llm_1", "llm_2", "llm_3", "rule", "temporal"]),
        AttestationSet("noisy_agent", [0.3, 0.9, 0.5, 0.7, 0.2, 0.8, 0.4, 0.6],
                       ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8"]),
        AttestationSet("clove_tc4", [0.72, 0.21, 0.68, 0.19],
                       ["bro_social", "kit_financial", "bro_receipt", "kit_payment"]),
    ]

    for s in scenarios:
        r = classify_uncertainty(s)
        print(f"\n--- {r['agent']} ---")
        print(f"  Type: {r['type']} (grade {r['grade']})")
        print(f"  Action: {r['action']}")
        print(f"  Mean: {r['mean_score']}, Std: {r['std']}, Spread: {r['spread']}")
        print(f"  Bimodality: {r['bimodality']}")
        if r['kirchhof_paradox']:
            print(f"  ⚠️ KIRCHHOF PARADOX: bimodal = maximal disagreement BUT minimal model count")
        print(f"  Attestors: {', '.join(s.attestor_names)}")

    print("\n--- KEY INSIGHT ---")
    print("CONSENSUS: act. IGNORANCE: gather. CONFLICT: resolve. NOISE: accept.")
    print("Kirchhof (ICLR 2025): 8 definitions contradict. Source-wise > dichotomy.")
    print("For agents: classify uncertainty type BEFORE combining scores.")


if __name__ == "__main__":
    demo()
