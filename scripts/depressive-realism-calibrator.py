#!/usr/bin/env python3
"""depressive-realism-calibrator.py — Self-assessment calibration checker.

Tests whether agent self-scores are calibrated against external criteria.
Based on Moore & Fresco (2012) meta-analysis showing depressive realism
d=0.07 (effectively null) and Collabra 2022 replication failure.

Key insight: nobody is calibrated. Externalize everything.

Usage:
    python3 depressive-realism-calibrator.py [--demo]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from typing import List, Tuple


@dataclass
class CalibrationResult:
    """Calibration analysis result."""
    agent_name: str
    n_assessments: int
    self_scores: List[float]
    external_scores: List[float]
    mean_bias: float          # positive = overconfident
    abs_calibration_error: float
    correlation: float        # r between self and external
    overconfidence_rate: float # fraction where self > external
    grade: str
    diagnosis: str


def pearson_r(x: List[float], y: List[float]) -> float:
    """Pearson correlation without numpy."""
    n = len(x)
    if n < 3:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((xi - mx)**2 for xi in x) / (n - 1))
    sy = math.sqrt(sum((yi - my)**2 for yi in y) / (n - 1))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / ((n - 1) * sx * sy)


def calibrate(agent_name: str, self_scores: List[float], 
              external_scores: List[float]) -> CalibrationResult:
    """Check calibration between self-assessment and external criteria."""
    n = len(self_scores)
    biases = [s - e for s, e in zip(self_scores, external_scores)]
    mean_bias = sum(biases) / n
    abs_cal = sum(abs(b) for b in biases) / n
    r = pearson_r(self_scores, external_scores)
    overconf = sum(1 for s, e in zip(self_scores, external_scores) if s > e) / n
    
    # Grade based on Moore & Fresco benchmarks
    if abs_cal < 0.1 and abs(mean_bias) < 0.05:
        grade, diag = "A", "Well-calibrated (rare — verify external criteria)"
    elif abs_cal < 0.2 and abs(mean_bias) < 0.15:
        grade, diag = "B", "Slightly miscalibrated"
    elif abs_cal < 0.3:
        grade, diag = "C", "Moderately miscalibrated — external rubric recommended"
    elif overconf > 0.7:
        grade, diag = "D", "Systematically overconfident — self-scores unreliable"
    else:
        grade, diag = "F", "Severely miscalibrated — self-assessment is noise"
    
    return CalibrationResult(
        agent_name=agent_name,
        n_assessments=n,
        self_scores=self_scores,
        external_scores=external_scores,
        mean_bias=round(mean_bias, 3),
        abs_calibration_error=round(abs_cal, 3),
        correlation=round(r, 3),
        overconfidence_rate=round(overconf, 3),
        grade=grade,
        diagnosis=diag
    )


def demo():
    """Demo with synthetic agents."""
    random.seed(42)
    
    scenarios = [
        ("overconfident_agent", 
         [0.9, 0.85, 0.92, 0.88, 0.95, 0.87, 0.91],
         [0.4, 0.55, 0.62, 0.38, 0.71, 0.45, 0.50]),
        ("calibrated_agent",
         [0.65, 0.72, 0.58, 0.81, 0.69, 0.74, 0.63],
         [0.62, 0.70, 0.55, 0.78, 0.71, 0.72, 0.60]),
        ("pessimistic_agent",
         [0.3, 0.25, 0.35, 0.28, 0.32, 0.27, 0.31],
         [0.55, 0.48, 0.62, 0.51, 0.59, 0.53, 0.57]),
        ("random_agent",
         [random.random() for _ in range(7)],
         [random.random() for _ in range(7)]),
    ]
    
    print("=" * 60)
    print("DEPRESSIVE REALISM CALIBRATION CHECK")
    print("Moore & Fresco 2012: d=0.07 (null effect)")
    print("Collabra 2022: failed replication")
    print("Nobody is calibrated. Externalize everything.")
    print("=" * 60)
    
    for name, self_s, ext_s in scenarios:
        result = calibrate(name, self_s, ext_s)
        print(f"\n[{result.grade}] {result.agent_name}")
        print(f"    Bias: {result.mean_bias:+.3f} (>0 = overconfident)")
        print(f"    Abs calibration error: {result.abs_calibration_error:.3f}")
        print(f"    Self↔External r: {result.correlation:.3f}")
        print(f"    Overconfidence rate: {result.overconfidence_rate:.1%}")
        print(f"    Diagnosis: {result.diagnosis}")
    
    print("\n" + "-" * 60)
    print("Key finding: Mabe & West (1982): self-assessment r=0.29")
    print("With concrete criteria + feedback: r=0.47")
    print("Without: r=0.04 (noise)")
    print("Architecture: pull-based external attestation > self-report")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = calibrate("demo", [0.9]*5, [0.5]*5)
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
