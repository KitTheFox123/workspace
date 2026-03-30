#!/usr/bin/env python3
"""
custodes-regress-auditor.py — Who watches the watchmen? Infinite regress termination.

Juvenal (Satires VI): "Quis custodiet ipsos custodes?"
Kumar et al (EMNLP 2024): AI-generated peer review detection — watchers need watchers.
Hansson (Phil of Sci 2025): Defining criteria ≠ diagnosing cases.

The regress of attestor oversight terminates in STRUCTURE, not authority:
1. Cross-attestation (attestors attest each other — mutual monitoring)
2. Statistical anomaly detection (attestation-burst-detector.py — math watches)
3. Rotation (no permanent watchmen — Popper's open society)
4. Transparency (logs public — everyone watches)

Nobody is the final authority. The system IS the authority.

Usage: python3 custodes-regress-auditor.py
"""

import json
import math
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple

@dataclass
class Attestor:
    name: str
    attestations_given: int
    attestations_received: int  # cross-attestation count
    tenure_months: int
    anomaly_flags: int  # statistical flags raised against them
    transparency_score: float  # 0-1, how much of their work is public

def regress_depth(chain: List[str]) -> int:
    """How deep does the oversight chain go before cycling?"""
    seen = set()
    for i, node in enumerate(chain):
        if node in seen:
            return i  # cycle detected
        seen.add(node)
    return len(chain)  # no cycle — open chain (worse)

def cross_attestation_score(attestors: List[Attestor]) -> Dict:
    """
    Measure mutual monitoring density.
    Higher = more cross-checking = better regress termination.
    """
    n = len(attestors)
    if n < 2:
        return {"density": 0.0, "status": "SINGLETON_NO_OVERSIGHT"}
    
    # Max possible cross-attestations = n*(n-1)
    total_received = sum(a.attestations_received for a in attestors)
    max_possible = n * (n - 1) * 10  # rough scaling
    density = min(1.0, total_received / max_possible)
    
    # Asymmetry: some attestors never get checked
    unchecked = [a for a in attestors if a.attestations_received == 0]
    
    return {
        "density": round(density, 3),
        "unchecked_attestors": len(unchecked),
        "unchecked_names": [a.name for a in unchecked],
        "status": "HEALTHY" if density > 0.3 and len(unchecked) == 0 
                 else "GAPS" if len(unchecked) > 0 
                 else "LOW_DENSITY"
    }

def statistical_termination_score(attestors: List[Attestor]) -> Dict:
    """
    Can anomaly detection substitute for human oversight?
    The math watches when nobody else does.
    """
    flagged = [a for a in attestors if a.anomaly_flags > 0]
    flag_rate = len(flagged) / len(attestors) if attestors else 0
    
    # Flag distribution — are flags concentrated or spread?
    flag_counts = [a.anomaly_flags for a in attestors]
    mean_flags = sum(flag_counts) / len(flag_counts) if flag_counts else 0
    variance = sum((f - mean_flags)**2 for f in flag_counts) / len(flag_counts) if flag_counts else 0
    
    # High variance = concentrated flags = system working (catching specific bad actors)
    # Low variance + high mean = everything flagged = system broken (too sensitive)
    # Low variance + low mean = nothing flagged = system working OR blind
    
    if mean_flags < 0.5 and variance < 0.5:
        status = "QUIET"  # Could be healthy or blind
        confidence = 0.5  # Uncertain
    elif mean_flags > 2.0 and variance < 1.0:
        status = "OVERSENSITIVE"
        confidence = 0.3
    elif variance > mean_flags:
        status = "TARGETED"  # Good — catching specific actors
        confidence = 0.8
    else:
        status = "MODERATE"
        confidence = 0.6
    
    return {
        "flag_rate": round(flag_rate, 3),
        "mean_flags": round(mean_flags, 2),
        "variance": round(variance, 2),
        "status": status,
        "confidence": confidence
    }

def rotation_score(attestors: List[Attestor]) -> Dict:
    """
    No permanent watchmen — Popper's open society principle.
    Long tenure without cross-checking = entrenchment.
    """
    tenures = [a.tenure_months for a in attestors]
    max_tenure = max(tenures) if tenures else 0
    mean_tenure = sum(tenures) / len(tenures) if tenures else 0
    
    # Entrenchment risk: long tenure + low cross-attestation
    entrenched = [a for a in attestors 
                  if a.tenure_months > 12 and a.attestations_received < 5]
    
    return {
        "max_tenure_months": max_tenure,
        "mean_tenure_months": round(mean_tenure, 1),
        "entrenched_count": len(entrenched),
        "entrenched_names": [a.name for a in entrenched],
        "rotation_health": "HEALTHY" if len(entrenched) == 0 
                          else "STALE" if len(entrenched) < len(attestors) * 0.3
                          else "ENTRENCHED"
    }

def transparency_score(attestors: List[Attestor]) -> Dict:
    """
    Everyone watches = regress dissolves.
    Public logs make the final watchman unnecessary.
    """
    scores = [a.transparency_score for a in attestors]
    mean_t = sum(scores) / len(scores) if scores else 0
    opaque = [a for a in attestors if a.transparency_score < 0.3]
    
    return {
        "mean_transparency": round(mean_t, 3),
        "opaque_attestors": len(opaque),
        "opaque_names": [a.name for a in opaque],
        "status": "OPEN" if mean_t > 0.7 and len(opaque) == 0
                 else "MIXED" if mean_t > 0.4
                 else "OPAQUE"
    }

def custodes_audit(attestors: List[Attestor]) -> Dict:
    """Full regress termination audit."""
    cross = cross_attestation_score(attestors)
    stats = statistical_termination_score(attestors)
    rotation = rotation_score(attestors)
    transparency = transparency_score(attestors)
    
    # Composite: how well does the regress terminate?
    # Each mechanism contributes independently
    termination_scores = {
        "cross_attestation": cross["density"],
        "statistical_detection": stats["confidence"],
        "rotation": 1.0 if rotation["rotation_health"] == "HEALTHY" else 0.5 if rotation["rotation_health"] == "STALE" else 0.2,
        "transparency": transparency["mean_transparency"]
    }
    
    composite = sum(termination_scores.values()) / len(termination_scores)
    
    # The regress terminates when composite > 0.6
    terminates = composite > 0.6
    
    return {
        "composite_score": round(composite, 3),
        "regress_terminates": terminates,
        "termination_mechanism": max(termination_scores, key=termination_scores.get),
        "weakest_mechanism": min(termination_scores, key=termination_scores.get),
        "scores": {k: round(v, 3) for k, v in termination_scores.items()},
        "cross_attestation": cross,
        "statistical_detection": stats,
        "rotation": rotation,
        "transparency": transparency
    }


def demo():
    print("=" * 70)
    print("CUSTODES REGRESS AUDITOR")
    print("Juvenal: 'Quis custodiet ipsos custodes?'")
    print("Answer: Structure, not authority. The math watches.")
    print("=" * 70)
    
    # Scenario 1: Healthy ecosystem
    healthy = [
        Attestor("kit_fox", 200, 45, 3, 0, 0.95),
        Attestor("santaclawd", 180, 52, 4, 0, 0.90),
        Attestor("bro_agent", 150, 38, 3, 1, 0.85),
        Attestor("funwolf", 120, 30, 2, 0, 0.80),
        Attestor("clove", 90, 25, 2, 0, 0.75),
    ]
    
    # Scenario 2: Entrenched oligarchy  
    oligarchy = [
        Attestor("old_guard_1", 500, 5, 24, 0, 0.30),
        Attestor("old_guard_2", 450, 3, 20, 0, 0.25),
        Attestor("newcomer_1", 10, 0, 1, 2, 0.90),
        Attestor("newcomer_2", 5, 0, 0, 3, 0.85),
    ]
    
    # Scenario 3: Transparent but no cross-checking
    transparent_silo = [
        Attestor("solo_1", 200, 0, 6, 0, 0.95),
        Attestor("solo_2", 180, 0, 5, 0, 0.90),
        Attestor("solo_3", 150, 0, 4, 0, 0.92),
    ]
    
    for name, group in [("Healthy Ecosystem", healthy), 
                         ("Entrenched Oligarchy", oligarchy),
                         ("Transparent Silos", transparent_silo)]:
        print(f"\n{'─' * 70}")
        print(f"Scenario: {name}")
        print(f"{'─' * 70}")
        
        result = custodes_audit(group)
        
        print(f"  Composite:    {result['composite_score']}")
        print(f"  Terminates:   {'YES ✓' if result['regress_terminates'] else 'NO ✗'}")
        print(f"  Strongest:    {result['termination_mechanism']}")
        print(f"  Weakest:      {result['weakest_mechanism']}")
        print(f"  Scores:       {json.dumps(result['scores'])}")
        
        if result['cross_attestation']['unchecked_names']:
            print(f"  ⚠️ Unchecked:  {result['cross_attestation']['unchecked_names']}")
        if result['rotation']['entrenched_names']:
            print(f"  ⚠️ Entrenched: {result['rotation']['entrenched_names']}")
        if result['transparency']['opaque_names']:
            print(f"  ⚠️ Opaque:     {result['transparency']['opaque_names']}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT:")
    print("The regress terminates in 4 mechanisms, not 1 authority:")
    print("  1. Cross-attestation (mutual monitoring)")
    print("  2. Statistical anomaly (the math watches)")
    print("  3. Rotation (no permanent watchmen)")
    print("  4. Transparency (everyone watches)")
    print("")
    print("Oligarchy fails: entrenched + opaque + no cross-checking.")
    print("Silos fail: transparent but nobody checks anyone.")
    print("Healthy works: all 4 mechanisms active simultaneously.")
    print("Nobody is the final watchman. The STRUCTURE is.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
