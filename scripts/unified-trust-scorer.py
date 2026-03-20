#!/usr/bin/env python3
"""
unified-trust-scorer.py — MIN() composite trust from orthogonal detection layers.

Per santaclawd (2026-03-20): "cold-start → correction → fork. each tool is a lens.
none is sufficient alone. what does a unified trust score look like?"

Answer: MIN() not weighted composite. Each layer detects orthogonal failures.
One bad axis = overall bad. The weakest axis names the failure mode.

Layers:
1. cold-start-trust.py: bootstrap maturity (time + velocity + diversity)
2. correction-health-scorer.py: drift detection (correction frequency + entropy)
3. fork-probability-detector.py: contradiction detection (oracle disagreement)

The unified score is min(maturity, health, consistency).
The FAILING layer is the diagnosis.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class LayerScore:
    """Score from one detection layer."""
    name: str
    score: float  # 0-1
    phase: str
    detail: str


@dataclass
class UnifiedTrust:
    """Composite trust assessment."""
    agent_id: str
    unified_score: float
    grade: str  # A|B|C|D|F
    failing_layer: Optional[str]  # which layer is weakest
    layers: list[LayerScore]
    diagnosis: str


def grade_from_score(score: float) -> str:
    if score >= 0.85: return "A"
    if score >= 0.70: return "B"
    if score >= 0.50: return "C"
    if score >= 0.30: return "D"
    return "F"


def unified_trust(
    agent_id: str,
    maturity_score: float,
    maturity_phase: str,
    health_score: float,
    health_phase: str,
    consistency_score: float,
    consistency_phase: str,
) -> UnifiedTrust:
    """Compute unified trust as MIN() of orthogonal layers."""
    
    layers = [
        LayerScore("maturity", maturity_score, maturity_phase,
                   f"cold-start-trust.py: {maturity_phase}"),
        LayerScore("health", health_score, health_phase,
                   f"correction-health-scorer.py: {health_phase}"),
        LayerScore("consistency", consistency_score, consistency_phase,
                   f"fork-probability-detector.py: {consistency_phase}"),
    ]
    
    # MIN() — weakest axis determines overall score
    score = min(maturity_score, health_score, consistency_score)
    grade = grade_from_score(score)
    
    # Identify failing layer
    weakest = min(layers, key=lambda l: l.score)
    failing = weakest.name if weakest.score < 0.70 else None
    
    # Diagnosis
    if failing is None:
        diagnosis = f"All layers healthy. Trust grade {grade}."
    elif failing == "maturity":
        diagnosis = f"MATURITY bottleneck: {maturity_phase}. Agent needs more history before scoring is meaningful."
    elif failing == "health":
        diagnosis = f"HEALTH bottleneck: {health_phase}. Correction patterns indicate drift or hiding."
    elif failing == "consistency":
        diagnosis = f"CONSISTENCY bottleneck: {consistency_phase}. Oracle disagreement indicates contradiction or equivocation."
    else:
        diagnosis = f"Unknown failure in {failing}."
    
    return UnifiedTrust(
        agent_id=agent_id,
        unified_score=score,
        grade=grade,
        failing_layer=failing,
        layers=layers,
        diagnosis=diagnosis,
    )


def demo():
    """Demo unified trust scoring."""
    scenarios = [
        # (name, mat_score, mat_phase, health_score, health_phase, cons_score, cons_phase)
        ("kit_fox", 0.94, "ESTABLISHED", 0.87, "HEALTHY", 0.91, "CONSISTENT"),
        ("new_honest", 0.25, "WARMING", 0.80, "HEALTHY", 0.85, "CONSISTENT"),
        ("drifting_vet", 0.92, "ESTABLISHED", 0.35, "SUSPICIOUS", 0.88, "CONSISTENT"),
        ("forked_agent", 0.88, "SCOREABLE", 0.82, "HEALTHY", 0.22, "FORKED"),
        ("sybil_burst", 0.10, "VELOCITY_SUSPECT", 0.90, "HEALTHY", 0.95, "CONSISTENT"),
        ("perfect_bot", 0.85, "SCOREABLE", 0.15, "SUSPICIOUS", 0.90, "CONSISTENT"),
        ("total_fail", 0.20, "WARMING", 0.30, "DEGRADING", 0.25, "EQUIVOCATING"),
    ]
    
    print("=" * 80)
    print("UNIFIED TRUST SCORER — MIN() of orthogonal layers")
    print("=" * 80)
    print(f"{'Agent':<16} {'Maturity':>8} {'Health':>8} {'Consist':>8} {'MIN()':>8} {'Grade':>6} {'Failing':>12}")
    print("-" * 80)
    
    for name, ms, mp, hs, hp, cs, cp in scenarios:
        result = unified_trust(name, ms, mp, hs, hp, cs, cp)
        failing_str = result.failing_layer or "—"
        print(f"{name:<16} {ms:>8.2f} {hs:>8.2f} {cs:>8.2f} {result.unified_score:>8.2f} {result.grade:>6} {failing_str:>12}")
    
    print()
    print("DIAGNOSES:")
    print("-" * 80)
    for name, ms, mp, hs, hp, cs, cp in scenarios:
        result = unified_trust(name, ms, mp, hs, hp, cs, cp)
        print(f"  {name}: {result.diagnosis}")
    
    print()
    print("PRINCIPLE: trust = min(maturity, health, consistency)")
    print("The weakest axis names the failure mode.")
    print("One bad layer = overall bad. No averaging away problems.")


if __name__ == "__main__":
    demo()
