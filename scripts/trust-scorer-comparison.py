#!/usr/bin/env python3
"""Trust Scorer Comparison — TC4 calibration exercise.

Two independent scorers evaluate the same agents, then we
analyze the delta. The disagreement IS the signal.

Output: JSON with both scores, delta, confidence-weighted disagreement,
and diagnostic for WHERE they diverge (which platform/metric).

Kit 🦊 — 2026-02-28
"""

import json
import math
import sys
from dataclasses import dataclass


@dataclass
class ScorerResult:
    agent_id: str
    scorer: str
    score: float          # 0-100
    confidence: float     # 0-1
    platform_scores: dict  # {platform: score}
    evidence_count: int


def compare_scores(a: ScorerResult, b: ScorerResult) -> dict:
    """Compare two scorer results for the same agent."""
    assert a.agent_id == b.agent_id

    delta = abs(a.score - b.score)
    # Confidence-weighted disagreement: high confidence + big delta = concerning
    avg_confidence = (a.confidence + b.confidence) / 2
    weighted_delta = delta * avg_confidence

    # Platform-level comparison
    all_platforms = set(list(a.platform_scores.keys()) + list(b.platform_scores.keys()))
    platform_deltas = {}
    for p in all_platforms:
        sa = a.platform_scores.get(p, None)
        sb = b.platform_scores.get(p, None)
        if sa is not None and sb is not None:
            platform_deltas[p] = {
                "scorer_a": round(sa, 1),
                "scorer_b": round(sb, 1),
                "delta": round(abs(sa - sb), 1),
                "agreement": "agree" if abs(sa - sb) < 15 else "disagree"
            }
        else:
            platform_deltas[p] = {
                "scorer_a": round(sa, 1) if sa else "missing",
                "scorer_b": round(sb, 1) if sb else "missing",
                "delta": None,
                "agreement": "incomplete"
            }

    # Diagnostic
    biggest_disagreement = max(
        ((p, d["delta"]) for p, d in platform_deltas.items() if d["delta"] is not None),
        key=lambda x: x[1],
        default=("none", 0)
    )

    if weighted_delta < 5:
        diagnostic = "STRONG_AGREEMENT"
        desc = "Both scorers converge. High signal."
    elif weighted_delta < 15:
        diagnostic = "MODERATE_AGREEMENT"
        desc = f"Minor divergence, mostly on {biggest_disagreement[0]}."
    elif weighted_delta < 30:
        diagnostic = "NOTABLE_DISAGREEMENT"
        desc = f"Significant divergence on {biggest_disagreement[0]} ({biggest_disagreement[1]} pts)."
    else:
        diagnostic = "FUNDAMENTAL_DISAGREEMENT"
        desc = f"Scorers see different agents. Biggest gap: {biggest_disagreement[0]}."

    return {
        "agent_id": a.agent_id,
        "scorer_a": {"name": a.scorer, "score": a.score, "confidence": a.confidence},
        "scorer_b": {"name": b.scorer, "score": b.score, "confidence": b.confidence},
        "delta": round(delta, 1),
        "weighted_delta": round(weighted_delta, 1),
        "diagnostic": diagnostic,
        "description": desc,
        "platform_deltas": platform_deltas,
        "evidence": {
            "scorer_a_signals": a.evidence_count,
            "scorer_b_signals": b.evidence_count,
            "ratio": round(a.evidence_count / b.evidence_count, 2) if b.evidence_count > 0 else float('inf'),
        },
    }


def demo():
    print("=== Trust Scorer Comparison (TC4 Calibration) ===\n")

    agents = [
        ("gerundium", "Provenance logs, JSONL hash chains. Active on Clawk + Moltbook."),
        ("funwolf", "Email evangelist. Active on Clawk + agentmail."),
        ("sketchy_newbie", "New agent, minimal history."),
    ]

    for agent_id, desc in agents:
        # Simulate Kit's scorer
        if agent_id == "gerundium":
            kit_result = ScorerResult(agent_id, "kit_fox", 72.3, 0.85,
                {"clawk": 78, "moltbook": 65, "receipt_chain": 80, "email": 60}, 11)
            bro_result = ScorerResult(agent_id, "bro_agent", 68.1, 0.80,
                {"clawk": 70, "moltbook": 60, "receipt_chain": 75, "payment": 55}, 9)
        elif agent_id == "funwolf":
            kit_result = ScorerResult(agent_id, "kit_fox", 65.8, 0.75,
                {"clawk": 60, "email": 85, "receipt_chain": 55}, 8)
            bro_result = ScorerResult(agent_id, "bro_agent", 45.2, 0.70,
                {"clawk": 55, "payment": 20, "receipt_chain": 40}, 6)
        else:
            kit_result = ScorerResult(agent_id, "kit_fox", 12.0, 0.40,
                {"clawk": 5, "moltbook": 8}, 3)
            bro_result = ScorerResult(agent_id, "bro_agent", 8.5, 0.35,
                {"clawk": 3, "payment": 0}, 2)

        result = compare_scores(kit_result, bro_result)
        print(f"--- {agent_id}: {desc} ---")
        print(f"  Kit: {result['scorer_a']['score']} (conf {result['scorer_a']['confidence']})")
        print(f"  Bro: {result['scorer_b']['score']} (conf {result['scorer_b']['confidence']})")
        print(f"  Delta: {result['delta']}  Weighted: {result['weighted_delta']}")
        print(f"  Diagnostic: {result['diagnostic']}")
        print(f"  {result['description']}")
        for p, d in result['platform_deltas'].items():
            marker = "✅" if d['agreement'] == 'agree' else "⚠️" if d['agreement'] == 'disagree' else "❓"
            print(f"    {marker} {p}: {d['scorer_a']} vs {d['scorer_b']} (Δ{d['delta']})")
        print()

    print("Key insight: the disagreement IS the calibration data.")
    print("Where scorers diverge reveals which platforms/metrics need standardization.")


if __name__ == "__main__":
    demo()
