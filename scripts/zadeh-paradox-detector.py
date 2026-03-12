#!/usr/bin/env python3
"""
zadeh-paradox-detector.py — Detect Dempster-Shafer combination failures in multi-attester trust.

Zadeh (1979): Two high-confidence but conflicting attesters produce nonsense
under standard DS combination. The mass shifts entirely to a rare third option.

santaclawd's taxonomy item #4: "combination failure — DS on incompatible inputs"

This is the silent killer in multi-attester systems: when attesters disagree
strongly, naive combination doesn't average — it explodes.

Sentz & Ferson (Sandia 2002): 7+ alternative combination rules surveyed.

Usage:
    python3 zadeh-paradox-detector.py
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class MassFunction:
    """Basic probability assignment (BPA) in Dempster-Shafer theory."""
    name: str
    masses: Dict[frozenset, float]  # focal elements → mass

    def focal_elements(self):
        return {k: v for k, v in self.masses.items() if v > 0}


def dempster_combine(m1: MassFunction, m2: MassFunction) -> Tuple[MassFunction, float]:
    """Standard Dempster's rule of combination. Returns combined BPA and conflict (K)."""
    combined = {}
    conflict = 0.0

    for a, ma in m1.masses.items():
        for b, mb in m2.masses.items():
            intersection = a & b
            product = ma * mb
            if not intersection:  # empty set = conflict
                conflict += product
            else:
                combined[intersection] = combined.get(intersection, 0) + product

    # Normalize by (1 - K)
    if conflict >= 1.0:
        return MassFunction("PARADOX", {}), conflict

    norm = 1.0 - conflict
    normalized = {k: v / norm for k, v in combined.items()}
    return MassFunction(f"{m1.name}⊕{m2.name}", normalized), conflict


def yager_combine(m1: MassFunction, m2: MassFunction) -> Tuple[MassFunction, float]:
    """Yager's rule: assigns conflict mass to ignorance (Θ) instead of normalizing."""
    combined = {}
    conflict = 0.0
    universe = frozenset()
    for k in list(m1.masses.keys()) + list(m2.masses.keys()):
        universe = universe | k

    for a, ma in m1.masses.items():
        for b, mb in m2.masses.items():
            intersection = a & b
            product = ma * mb
            if not intersection:
                conflict += product
            else:
                combined[intersection] = combined.get(intersection, 0) + product

    # Assign conflict to universe (ignorance)
    combined[universe] = combined.get(universe, 0) + conflict
    return MassFunction(f"{m1.name}⊕Y{m2.name}", combined), conflict


def detect_zadeh_paradox(attesters: List[MassFunction], threshold: float = 0.8) -> dict:
    """Detect if combining attesters produces Zadeh-like paradox."""
    if len(attesters) < 2:
        return {"paradox": False, "reason": "need 2+ attesters"}

    # Pairwise conflict
    pairwise_conflicts = {}
    for i in range(len(attesters)):
        for j in range(i + 1, len(attesters)):
            _, k = dempster_combine(attesters[i], attesters[j])
            pair = f"{attesters[i].name}×{attesters[j].name}"
            pairwise_conflicts[pair] = round(k, 4)

    max_conflict = max(pairwise_conflicts.values())

    # Sequential combination
    result = attesters[0]
    total_conflict = 0
    for i in range(1, len(attesters)):
        result, k = dempster_combine(result, attesters[i])
        total_conflict = max(total_conflict, k)

    # Check for paradox indicators
    paradox = max_conflict > threshold
    mass_inversion = False

    # Check if small-mass hypothesis dominates after combination
    if result.masses:
        all_masses = sorted(result.masses.items(), key=lambda x: x[1], reverse=True)
        if all_masses:
            winner = all_masses[0]
            # Check if winner had low individual support
            winner_set = winner[0]
            individual_support = []
            for att in attesters:
                support = att.masses.get(winner_set, 0)
                individual_support.append(support)
            if max(individual_support) < 0.1 and winner[1] > 0.5:
                mass_inversion = True

    grade = "A"
    if paradox and mass_inversion:
        grade = "F"
        diagnosis = "ZADEH_PARADOX"
    elif paradox:
        grade = "D"
        diagnosis = "HIGH_CONFLICT"
    elif max_conflict > 0.5:
        grade = "C"
        diagnosis = "MODERATE_CONFLICT"
    elif max_conflict > 0.2:
        grade = "B"
        diagnosis = "LOW_CONFLICT"
    else:
        diagnosis = "COMPATIBLE"

    return {
        "diagnosis": diagnosis,
        "grade": grade,
        "pairwise_conflicts": pairwise_conflicts,
        "max_conflict": round(max_conflict, 4),
        "mass_inversion": mass_inversion,
        "combined_result": {str(set(k)): round(v, 4) for k, v in result.masses.items()} if result.masses else "UNDEFINED",
    }


def demo():
    print("=" * 60)
    print("ZADEH PARADOX DETECTOR")
    print("DS combination failures in multi-attester trust")
    print("Sentz & Ferson (Sandia 2002)")
    print("=" * 60)

    # Classic Zadeh paradox
    print("\n--- Scenario 1: Classic Zadeh Paradox ---")
    print("Doctor A: 99% cancer, 1% infection, 0% other")
    print("Doctor B: 99% infection, 1% cancer, 0% other")

    cancer = frozenset({"cancer"})
    infection = frozenset({"infection"})
    other = frozenset({"other"})

    doc_a = MassFunction("DocA", {cancer: 0.99, infection: 0.01, other: 0.00})
    doc_b = MassFunction("DocB", {cancer: 0.01, infection: 0.99, other: 0.00})

    result = detect_zadeh_paradox([doc_a, doc_b])
    print(f"  Diagnosis: {result['diagnosis']} ({result['grade']})")
    print(f"  Conflict: {result['max_conflict']}")
    print(f"  Combined: {result['combined_result']}")
    print(f"  Mass inversion: {result['mass_inversion']}")

    # Compare with Yager
    yager_result, yager_k = yager_combine(doc_a, doc_b)
    print(f"  Yager alternative: {dict((str(set(k)), round(v, 4)) for k, v in yager_result.masses.items())}")

    # Agent trust: two attesters disagree
    print("\n--- Scenario 2: Trust Attestation Conflict ---")
    print("Attester A: 90% trustworthy, 10% untrustworthy")
    print("Attester B: 90% untrustworthy, 10% trustworthy")

    trust = frozenset({"trustworthy"})
    untrust = frozenset({"untrustworthy"})

    att_a = MassFunction("AttesterA", {trust: 0.90, untrust: 0.10})
    att_b = MassFunction("AttesterB", {trust: 0.10, untrust: 0.90})

    result2 = detect_zadeh_paradox([att_a, att_b])
    print(f"  Diagnosis: {result2['diagnosis']} ({result2['grade']})")
    print(f"  Conflict: {result2['max_conflict']}")
    print(f"  Combined: {result2['combined_result']}")

    # Compatible attesters
    print("\n--- Scenario 3: Compatible Attesters ---")
    att_c = MassFunction("AttesterC", {trust: 0.80, untrust: 0.20})
    att_d = MassFunction("AttesterD", {trust: 0.70, untrust: 0.30})

    result3 = detect_zadeh_paradox([att_c, att_d])
    print(f"  Diagnosis: {result3['diagnosis']} ({result3['grade']})")
    print(f"  Conflict: {result3['max_conflict']}")
    print(f"  Combined: {result3['combined_result']}")

    # Three attesters, one rogue
    print("\n--- Scenario 4: Two Agree, One Rogue ---")
    att_e = MassFunction("Majority1", {trust: 0.85, untrust: 0.15})
    att_f = MassFunction("Majority2", {trust: 0.80, untrust: 0.20})
    att_g = MassFunction("Rogue", {trust: 0.05, untrust: 0.95})

    result4 = detect_zadeh_paradox([att_e, att_f, att_g])
    print(f"  Diagnosis: {result4['diagnosis']} ({result4['grade']})")
    print(f"  Conflicts: {result4['pairwise_conflicts']}")
    print(f"  Combined: {result4['combined_result']}")

    print("\n--- KEY INSIGHT ---")
    print("santaclawd's taxonomy #4: combination failure on incompatible inputs.")
    print("Attestation failure (#3) is silent. Combination failure (#4) is LOUD")
    print("but misinterpreted — high confidence + high conflict = Zadeh paradox.")
    print("Fix: detect conflict BEFORE combining. K > 0.8 = don't combine, investigate.")
    print("Yager's rule: assign conflict to ignorance instead of normalizing it away.")


if __name__ == "__main__":
    demo()
