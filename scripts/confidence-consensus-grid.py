#!/usr/bin/env python3
"""confidence-consensus-grid.py — Hill (2024) confidence × consensus diagnostic grid.

Maps attestor pool state to 4 quadrants:
- High confidence + High consensus = VALIDATED (trust)
- High confidence + Low consensus = GENUINE DISAGREEMENT (useful signal)  
- Low confidence + High consensus = CASCADE (Kuran 1999 availability cascade)
- Low confidence + Low consensus = NOISE (insufficient data)

Uses Brier scores for confidence, inter-attestor agreement for consensus.

Usage:
    python3 confidence-consensus-grid.py [--demo]
"""

import argparse
import json
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class AttestorScore:
    name: str
    brier: float  # 0 = perfect, 1 = worst
    assessment: float  # 0-1 assessment of target


@dataclass 
class GridDiagnosis:
    quadrant: str
    confidence_level: str  # HIGH/LOW
    consensus_level: str   # HIGH/LOW
    avg_brier: float
    agreement_score: float  # 0-1
    diagnosis: str
    action: str
    grade: str


def compute_agreement(scores: list[float]) -> float:
    """Agreement = 1 - normalized variance."""
    if len(scores) < 2:
        return 1.0
    var = statistics.variance(scores)
    return max(0, 1 - 4 * var)  # Scale: var=0.25 (max for [0,1]) → 0


def diagnose(attestors: list[AttestorScore], 
             brier_threshold: float = 0.15,
             agreement_threshold: float = 0.7) -> GridDiagnosis:
    """Diagnose attestor pool state using Hill grid."""
    avg_brier = statistics.mean(a.brier for a in attestors)
    assessments = [a.assessment for a in attestors]
    agreement = compute_agreement(assessments)
    
    high_conf = avg_brier < brier_threshold
    high_cons = agreement > agreement_threshold
    
    if high_conf and high_cons:
        return GridDiagnosis(
            quadrant="VALIDATED",
            confidence_level="HIGH", consensus_level="HIGH",
            avg_brier=round(avg_brier, 3),
            agreement_score=round(agreement, 3),
            diagnosis="Calibrated attestors agree. Trust the signal.",
            action="Accept attestation at face value.",
            grade="A"
        )
    elif high_conf and not high_cons:
        return GridDiagnosis(
            quadrant="GENUINE_DISAGREEMENT",
            confidence_level="HIGH", consensus_level="LOW",
            avg_brier=round(avg_brier, 3),
            agreement_score=round(agreement, 3),
            diagnosis="Calibrated attestors disagree. Useful signal — different perspectives.",
            action="Investigate divergence. Massimi perspectival objectivity applies.",
            grade="B"
        )
    elif not high_conf and high_cons:
        return GridDiagnosis(
            quadrant="CASCADE",
            confidence_level="LOW", consensus_level="HIGH",
            avg_brier=round(avg_brier, 3),
            agreement_score=round(agreement, 3),
            diagnosis="Uncalibrated attestors agree. Kuran 1999 availability cascade risk.",
            action="Do NOT trust. High agreement with low calibration = correlated errors.",
            grade="D"
        )
    else:
        return GridDiagnosis(
            quadrant="NOISE",
            confidence_level="LOW", consensus_level="LOW",
            avg_brier=round(avg_brier, 3),
            agreement_score=round(agreement, 3),
            diagnosis="Uncalibrated attestors disagree. No signal.",
            action="Insufficient data. Recruit better attestors or wait.",
            grade="F"
        )


def demo():
    """Run 4 demo scenarios."""
    scenarios = {
        "validated": [
            AttestorScore("alice", 0.05, 0.85),
            AttestorScore("bob", 0.08, 0.82),
            AttestorScore("carol", 0.06, 0.88),
        ],
        "genuine_disagreement": [
            AttestorScore("alice", 0.05, 0.90),
            AttestorScore("bob", 0.08, 0.30),
            AttestorScore("carol", 0.06, 0.75),
        ],
        "cascade": [
            AttestorScore("sybil_1", 0.40, 0.90),
            AttestorScore("sybil_2", 0.35, 0.88),
            AttestorScore("sybil_3", 0.42, 0.91),
        ],
        "noise": [
            AttestorScore("random_1", 0.45, 0.20),
            AttestorScore("random_2", 0.50, 0.70),
            AttestorScore("random_3", 0.38, 0.45),
        ],
    }
    
    print("=" * 60)
    print("CONFIDENCE × CONSENSUS DIAGNOSTIC GRID")
    print("Hill (2024) + Kuran (1999) + Massimi (2020)")
    print("=" * 60)
    
    for name, attestors in scenarios.items():
        result = diagnose(attestors)
        print(f"\n[{result.grade}] {name.upper()} → {result.quadrant}")
        print(f"    Brier: {result.avg_brier} | Agreement: {result.agreement_score}")
        print(f"    Diagnosis: {result.diagnosis}")
        print(f"    Action: {result.action}")
    
    print("\n" + "-" * 60)
    print("Key insight: high consensus + low calibration is the DANGEROUS")
    print("quadrant. It looks like agreement but it's a cascade.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Demo as JSON
        scenarios = {
            "validated": [AttestorScore("a", 0.05, 0.85), AttestorScore("b", 0.08, 0.82), AttestorScore("c", 0.06, 0.88)],
            "cascade": [AttestorScore("s1", 0.40, 0.90), AttestorScore("s2", 0.35, 0.88), AttestorScore("s3", 0.42, 0.91)],
        }
        results = {k: asdict(diagnose(v)) for k, v in scenarios.items()}
        print(json.dumps(results, indent=2))
    else:
        demo()
