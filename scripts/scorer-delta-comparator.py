#!/usr/bin/env python3
"""Scorer Delta Comparator — Two independent scorers, delta = confidence.

santaclawd insight: "two scorers agree = confident. diverge = flag for review.
no ground truth needed, just independence. the gap IS the signal."

Surowiecki (Wisdom of Crowds 2004): independent estimates aggregated
beat individual experts. Independence is load-bearing.

Used for TC4: if bro_agent and Kit both score same agents,
the delta between scores IS the uncertainty measure.

Kit 🦊 — 2026-02-28
"""

import json
import math
import statistics
from dataclasses import dataclass


@dataclass
class AgentScore:
    agent_id: str
    score: float       # 0-100
    confidence: float  # 0-1
    evidence_count: int


def compare_scorers(scorer_a: dict[str, AgentScore],
                    scorer_b: dict[str, AgentScore],
                    name_a: str = "scorer_a",
                    name_b: str = "scorer_b") -> dict:
    """Compare two independent scorers on the same agent set."""
    common = set(scorer_a.keys()) & set(scorer_b.keys())
    if not common:
        return {"error": "no common agents to compare"}

    deltas = []
    agent_results = []

    for agent_id in sorted(common):
        a = scorer_a[agent_id]
        b = scorer_b[agent_id]
        delta = abs(a.score - b.score)
        avg = (a.score + b.score) / 2
        # Confidence: inverse of delta, weighted by evidence
        evidence_weight = min((a.evidence_count + b.evidence_count) / 20, 1.0)
        agreement_conf = max(0, 1.0 - delta / 100)
        combined_conf = agreement_conf * 0.6 + evidence_weight * 0.4

        deltas.append(delta)
        agent_results.append({
            "agent_id": agent_id,
            f"{name_a}_score": a.score,
            f"{name_b}_score": b.score,
            "consensus_score": round(avg, 1),
            "delta": round(delta, 1),
            "combined_confidence": round(combined_conf, 3),
            "flag": "🟢" if delta < 10 else "🟡" if delta < 25 else "🔴",
            "recommendation": (
                "AGREE" if delta < 10 else
                "REVIEW" if delta < 25 else
                "DISPUTE"
            ),
        })

    avg_delta = statistics.mean(deltas)
    max_delta = max(deltas)
    stdev_delta = statistics.stdev(deltas) if len(deltas) > 1 else 0

    # Correlation check (are scorers independent?)
    a_scores = [scorer_a[aid].score for aid in common]
    b_scores = [scorer_b[aid].score for aid in common]
    if len(common) > 2:
        # Pearson correlation
        mean_a = statistics.mean(a_scores)
        mean_b = statistics.mean(b_scores)
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(a_scores, b_scores)) / len(common)
        std_a = statistics.stdev(a_scores) or 1
        std_b = statistics.stdev(b_scores) or 1
        correlation = cov / (std_a * std_b)
    else:
        correlation = None

    # Independence check
    if correlation is not None and correlation > 0.95:
        independence = "⚠️ SUSPICIOUS — scorers may not be independent (r={:.3f})".format(correlation)
    elif correlation is not None and correlation > 0.8:
        independence = "OK — moderate correlation (r={:.3f})".format(correlation)
    else:
        independence = "✅ GOOD — scorers appear independent"

    return {
        "summary": {
            "agents_compared": len(common),
            "avg_delta": round(avg_delta, 1),
            "max_delta": round(max_delta, 1),
            "stdev_delta": round(stdev_delta, 1),
            "correlation": round(correlation, 3) if correlation else None,
            "independence": independence,
            "agreements": sum(1 for d in deltas if d < 10),
            "reviews": sum(1 for d in deltas if 10 <= d < 25),
            "disputes": sum(1 for d in deltas if d >= 25),
        },
        "agents": agent_results,
    }


def demo():
    print("=== Scorer Delta Comparator (TC4) ===\n")

    # Simulate Kit's scores
    kit_scores = {
        "agent_alpha": AgentScore("agent_alpha", 72.5, 0.85, 12),
        "agent_beta": AgentScore("agent_beta", 45.0, 0.70, 8),
        "agent_gamma": AgentScore("agent_gamma", 88.0, 0.92, 15),
        "agent_delta": AgentScore("agent_delta", 15.0, 0.60, 5),
        "agent_epsilon": AgentScore("agent_epsilon", 60.0, 0.75, 10),
    }

    # Simulate bro_agent's scores (independent methodology)
    bro_scores = {
        "agent_alpha": AgentScore("agent_alpha", 68.0, 0.80, 10),
        "agent_beta": AgentScore("agent_beta", 52.0, 0.65, 7),
        "agent_gamma": AgentScore("agent_gamma", 85.0, 0.88, 13),
        "agent_delta": AgentScore("agent_delta", 40.0, 0.55, 4),  # Big disagreement!
        "agent_epsilon": AgentScore("agent_epsilon", 58.0, 0.70, 9),
    }

    result = compare_scorers(kit_scores, bro_scores, "kit", "bro_agent")

    s = result["summary"]
    print(f"Agents compared: {s['agents_compared']}")
    print(f"Avg delta: {s['avg_delta']} | Max: {s['max_delta']} | StDev: {s['stdev_delta']}")
    print(f"Correlation: {s['correlation']}")
    print(f"Independence: {s['independence']}")
    print(f"Results: {s['agreements']} agree, {s['reviews']} review, {s['disputes']} dispute\n")

    for a in result["agents"]:
        print(f"  {a['flag']} {a['agent_id']:20s} kit={a['kit_score']:5.1f}  bro={a['bro_agent_score']:5.1f}  "
              f"Δ={a['delta']:5.1f}  consensus={a['consensus_score']:5.1f}  → {a['recommendation']}")

    print(f"\n💡 Key: delta IS the uncertainty. No ground truth needed.")
    print(f"   Disputes (Δ≥25) need manual review or third scorer.")
    print(f"   Correlated scorers = expensive groupthink (Surowiecki).")


if __name__ == "__main__":
    demo()
