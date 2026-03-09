#!/usr/bin/env python3
"""perspectival-convergence.py — Massimi 2019 convergence detector.

Detects when multiple attestors converge on same conclusion via DIFFERENT
inference paths (robust) vs same path (correlated). Based on Massimi's
"agreeing-whilst-perspectivally-disagreeing" framework.

Key insight: agreement via different perspectives = robustness.
Agreement via same perspective = correlation disguised as corroboration.
"""

import json
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Dict
from datetime import datetime, timezone


@dataclass
class Attestation:
    attestor: str
    conclusion: str  # What they concluded
    inference_path: str  # How they got there (method/perspective)
    data_source: str  # What data they used
    confidence: float  # 0-1
    brier_history: float  # Historical Brier score (lower=better)


def path_similarity(a: str, b: str) -> float:
    """Jaccard similarity on tokenized paths."""
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def analyze_convergence(attestations: List[Attestation]) -> dict:
    """Analyze whether attestations show perspectival convergence or correlation."""
    if len(attestations) < 2:
        return {"error": "Need ≥2 attestations"}

    # Group by conclusion
    conclusions: Dict[str, List[Attestation]] = {}
    for a in attestations:
        conclusions.setdefault(a.conclusion, []).append(a)

    results = []
    for conclusion, group in conclusions.items():
        if len(group) < 2:
            continue

        # Check path diversity
        path_sims = []
        data_sims = []
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                path_sims.append(path_similarity(
                    group[i].inference_path, group[j].inference_path))
                data_sims.append(path_similarity(
                    group[i].data_source, group[j].data_source))

        avg_path_sim = sum(path_sims) / len(path_sims) if path_sims else 1.0
        avg_data_sim = sum(data_sims) / len(data_sims) if data_sims else 1.0

        # Brier-weighted confidence
        brier_weights = [1 / (0.01 + a.brier_history) for a in group]
        total_w = sum(brier_weights)
        weighted_conf = sum(
            a.confidence * w for a, w in zip(group, brier_weights)) / total_w

        # Classify
        if avg_path_sim < 0.3 and avg_data_sim < 0.3:
            convergence_type = "ROBUST_PERSPECTIVAL"
            grade = "A"
        elif avg_path_sim < 0.3:
            convergence_type = "METHOD_DIVERSE"
            grade = "B"
        elif avg_data_sim < 0.3:
            convergence_type = "DATA_DIVERSE"
            grade = "B"
        elif avg_path_sim > 0.7 and avg_data_sim > 0.7:
            convergence_type = "CORRELATED"
            grade = "F"
        else:
            convergence_type = "PARTIAL"
            grade = "C"

        results.append({
            "conclusion": conclusion,
            "attestor_count": len(group),
            "avg_path_similarity": round(avg_path_sim, 3),
            "avg_data_similarity": round(avg_data_sim, 3),
            "brier_weighted_confidence": round(weighted_conf, 3),
            "convergence_type": convergence_type,
            "grade": grade,
        })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "convergence_analysis": results,
        "recommendation": "Perspectival diversity > agreement count. "
                         "Same-path agreement is correlation, not corroboration.",
    }


def demo():
    """Demo with Massimi-inspired scenarios."""
    print("=" * 60)
    print("PERSPECTIVAL CONVERGENCE ANALYSIS")
    print("(Massimi 2019: agreeing-whilst-perspectivally-disagreeing)")
    print("=" * 60)

    # Scenario 1: Robust — like Thomson + electrochemistry + Planck on charge
    robust = [
        Attestation("attestor_A", "agent_trusted", "behavioral CUSUM drift analysis",
                    "action logs temporal", 0.85, 0.08),
        Attestation("attestor_B", "agent_trusted", "scope-commit hash verification",
                    "signed manifests cryptographic", 0.90, 0.05),
        Attestation("attestor_C", "agent_trusted", "relying party outcome Brier scoring",
                    "task completion rates user feedback", 0.80, 0.12),
    ]
    r1 = analyze_convergence(robust)
    print("\n[Scenario 1: Robust perspectival convergence]")
    for r in r1["convergence_analysis"]:
        print(f"  Conclusion: {r['conclusion']}")
        print(f"  Path similarity: {r['avg_path_similarity']} (low=diverse)")
        print(f"  Data similarity: {r['avg_data_similarity']} (low=diverse)")
        print(f"  Type: {r['convergence_type']} — Grade {r['grade']}")

    # Scenario 2: Correlated — same method, same data
    correlated = [
        Attestation("attestor_X", "agent_trusted", "behavioral CUSUM drift analysis",
                    "action logs temporal patterns", 0.85, 0.15),
        Attestation("attestor_Y", "agent_trusted", "behavioral CUSUM drift analysis",
                    "action logs temporal patterns", 0.88, 0.20),
        Attestation("attestor_Z", "agent_trusted", "behavioral CUSUM drift analysis",
                    "action logs temporal patterns", 0.82, 0.18),
    ]
    r2 = analyze_convergence(correlated)
    print("\n[Scenario 2: Correlated (same perspective)]")
    for r in r2["convergence_analysis"]:
        print(f"  Conclusion: {r['conclusion']}")
        print(f"  Path similarity: {r['avg_path_similarity']} (high=correlated)")
        print(f"  Data similarity: {r['avg_data_similarity']} (high=correlated)")
        print(f"  Type: {r['convergence_type']} — Grade {r['grade']}")

    # Scenario 3: Disagreement
    disagreement = [
        Attestation("attestor_A", "agent_trusted", "behavioral CUSUM drift",
                    "action logs", 0.85, 0.08),
        Attestation("attestor_B", "agent_suspicious", "scope-commit hash verification",
                    "signed manifests", 0.75, 0.05),
    ]
    r3 = analyze_convergence(disagreement)
    print("\n[Scenario 3: Perspectival disagreement]")
    if r3.get("convergence_analysis"):
        for r in r3["convergence_analysis"]:
            print(f"  Conclusion: {r['conclusion']}")
            print(f"  Attestors: {r['attestor_count']} (singleton — no convergence)")
    else:
        print("  No convergence — different conclusions (genuine disagreement)")
        print("  This IS informative — not a failure state")

    print(f"\n{r1['recommendation']}")


if __name__ == "__main__":
    import sys
    if "--json" in sys.argv:
        # Quick demo as JSON
        demo_attestations = [
            Attestation("A", "trusted", "CUSUM behavioral", "action logs", 0.85, 0.08),
            Attestation("B", "trusted", "scope hash crypto", "manifests", 0.90, 0.05),
        ]
        print(json.dumps(analyze_convergence(demo_attestations), indent=2))
    else:
        demo()
