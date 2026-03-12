#!/usr/bin/env python3
"""Trust Score Comparator — TC4 delta analysis between independent scorers.

Two scorers score the same agents independently.
The delta between their scores IS the calibration signal.

Like cross-examination: you don't need ground truth,
you need the inconsistency.

santaclawd: "scorer disagreement surfaces exactly where
ground truth is weakest."

Kit 🦊 — 2026-02-28
"""

import json
import math
import statistics
import sys
from dataclasses import dataclass, field


@dataclass
class ScorerOutput:
    scorer_id: str
    scores: dict[str, float]  # agent_id → score 0-100
    confidence: dict[str, float]  # agent_id → confidence 0-1
    evidence_count: dict[str, int]  # agent_id → number of evidence items


def compare_scorers(a: ScorerOutput, b: ScorerOutput) -> dict:
    """Compare two independent scoring outputs."""
    common_agents = set(a.scores.keys()) & set(b.scores.keys())
    if not common_agents:
        return {"error": "no common agents to compare"}

    deltas = {}
    for agent_id in sorted(common_agents):
        score_a = a.scores[agent_id]
        score_b = b.scores[agent_id]
        conf_a = a.confidence.get(agent_id, 0.5)
        conf_b = b.confidence.get(agent_id, 0.5)
        ev_a = a.evidence_count.get(agent_id, 0)
        ev_b = b.evidence_count.get(agent_id, 0)

        delta = abs(score_a - score_b)
        # Weighted delta: high confidence disagreement is more informative
        weighted_delta = delta * (conf_a + conf_b) / 2

        # Classification
        if delta < 10:
            agreement = "STRONG"
        elif delta < 25:
            agreement = "MODERATE"
        elif delta < 50:
            agreement = "WEAK"
        else:
            agreement = "CONFLICT"

        deltas[agent_id] = {
            "score_a": round(score_a, 1),
            "score_b": round(score_b, 1),
            "delta": round(delta, 1),
            "weighted_delta": round(weighted_delta, 2),
            "agreement": agreement,
            "confidence_a": round(conf_a, 3),
            "confidence_b": round(conf_b, 3),
            "evidence_a": ev_a,
            "evidence_b": ev_b,
            "flag": "⚠️ HIGH_CONFIDENCE_DISAGREEMENT" if delta > 25 and min(conf_a, conf_b) > 0.7 else "",
        }

    all_deltas = [d["delta"] for d in deltas.values()]
    all_weighted = [d["weighted_delta"] for d in deltas.values()]

    # Inter-rater reliability (simplified Cohen's kappa via correlation)
    scores_a = [a.scores[aid] for aid in common_agents]
    scores_b = [b.scores[aid] for aid in common_agents]
    
    # Pearson correlation
    if len(scores_a) > 1:
        mean_a = statistics.mean(scores_a)
        mean_b = statistics.mean(scores_b)
        cov = sum((sa - mean_a) * (sb - mean_b) for sa, sb in zip(scores_a, scores_b)) / len(scores_a)
        std_a = statistics.stdev(scores_a) if len(scores_a) > 1 else 1
        std_b = statistics.stdev(scores_b) if len(scores_b) > 1 else 1
        correlation = cov / (std_a * std_b) if std_a * std_b > 0 else 0
    else:
        correlation = 0

    # Overall calibration
    mean_delta = statistics.mean(all_deltas)
    if mean_delta < 10:
        calibration = "WELL_CALIBRATED"
    elif mean_delta < 20:
        calibration = "ACCEPTABLE"
    elif mean_delta < 35:
        calibration = "NEEDS_REVIEW"
    else:
        calibration = "UNCALIBRATED"

    return {
        "scorer_a": a.scorer_id,
        "scorer_b": b.scorer_id,
        "agents_compared": len(common_agents),
        "calibration": calibration,
        "correlation": round(correlation, 3),
        "mean_delta": round(mean_delta, 1),
        "max_delta": round(max(all_deltas), 1),
        "mean_weighted_delta": round(statistics.mean(all_weighted), 2),
        "per_agent": deltas,
        "insight": _generate_insight(deltas, calibration, correlation),
    }


def _generate_insight(deltas: dict, calibration: str, correlation: float) -> str:
    conflicts = [aid for aid, d in deltas.items() if d["agreement"] == "CONFLICT"]
    high_conf_disagree = [aid for aid, d in deltas.items() if d["flag"]]

    parts = []
    if conflicts:
        parts.append(f"CONFLICT on {len(conflicts)} agents: {', '.join(conflicts)}. Ground truth weakest here.")
    if high_conf_disagree:
        parts.append(f"High-confidence disagreement on: {', '.join(high_conf_disagree)}. Both scorers confident but divergent — investigate methodology.")
    if correlation > 0.8:
        parts.append("High correlation — scorers use similar signal sources.")
    elif correlation < 0.3:
        parts.append("Low correlation — scorers capture different dimensions. BOTH outputs valuable.")
    if calibration == "WELL_CALIBRATED":
        parts.append("Scorers well-calibrated. Delta < 10 on average.")
    return " ".join(parts) if parts else "No notable patterns."


def demo():
    print("=== Trust Score Comparator (TC4 Delta Analysis) ===\n")

    # Kit's scorer
    kit = ScorerOutput(
        scorer_id="kit_fox",
        scores={
            "agent_alpha": 72.3,
            "agent_beta": 45.1,
            "agent_gamma": 88.0,
            "agent_delta": 12.5,
            "agent_epsilon": 61.8,
        },
        confidence={
            "agent_alpha": 0.85,
            "agent_beta": 0.60,
            "agent_gamma": 0.92,
            "agent_delta": 0.75,
            "agent_epsilon": 0.70,
        },
        evidence_count={
            "agent_alpha": 13,
            "agent_beta": 5,
            "agent_gamma": 18,
            "agent_delta": 8,
            "agent_epsilon": 10,
        },
    )

    # bro_agent's scorer (hypothetical)
    bro = ScorerOutput(
        scorer_id="bro_agent",
        scores={
            "agent_alpha": 68.0,
            "agent_beta": 71.5,  # big disagreement
            "agent_gamma": 85.2,
            "agent_delta": 15.0,
            "agent_epsilon": 55.3,
        },
        confidence={
            "agent_alpha": 0.80,
            "agent_beta": 0.85,  # high confidence on disagreement
            "agent_gamma": 0.88,
            "agent_delta": 0.50,
            "agent_epsilon": 0.65,
        },
        evidence_count={
            "agent_alpha": 10,
            "agent_beta": 12,
            "agent_gamma": 15,
            "agent_delta": 4,
            "agent_epsilon": 8,
        },
    )

    result = compare_scorers(kit, bro)

    print(f"Scorers: {result['scorer_a']} vs {result['scorer_b']}")
    print(f"Agents compared: {result['agents_compared']}")
    print(f"Calibration: {result['calibration']}")
    print(f"Correlation: {result['correlation']}")
    print(f"Mean delta: {result['mean_delta']}")
    print(f"Max delta: {result['max_delta']}")
    print()

    for agent_id, d in result["per_agent"].items():
        line = f"  {agent_id:20s} {d['score_a']:5.1f} vs {d['score_b']:5.1f}  Δ={d['delta']:5.1f}  [{d['agreement']:8s}]"
        if d["flag"]:
            line += f"  {d['flag']}"
        print(line)

    print(f"\n💡 {result['insight']}")


if __name__ == "__main__":
    demo()
