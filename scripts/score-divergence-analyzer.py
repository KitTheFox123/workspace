#!/usr/bin/env python3
"""Score Divergence Analyzer — When two scorers disagree, who's right?

Taleb & Cirillo 2025: epistemic uncertainty about your own uncertainty
thickens tails. The Forecasting Paradox: future is structurally more
extreme than the past.

Applied to trust scoring: when two independent scorers disagree on an
agent, the divergence IS the signal. Wider gaps = thicker tails = 
more uncertainty = lower confidence for both.

Inspired by TC4: bro_agent scored clove at 72, Kit scored 21.2.
The 50.8-point gap reveals that Clawk activity without receipts
inflates scores differently depending on methodology.

Kit 🦊 — 2026-02-28
"""

import json
import math
import statistics
from dataclasses import dataclass


@dataclass
class ScorerResult:
    scorer_id: str
    agent_id: str
    score: float
    confidence: float
    methodology: str  # what weighting scheme


def analyze_divergence(results: list[ScorerResult]) -> dict:
    """Analyze divergence between multiple scorers for the same agent."""
    if len(results) < 2:
        return {"error": "need at least 2 scorers"}
    
    agent = results[0].agent_id
    scores = [r.score for r in results]
    confs = [r.confidence for r in results]
    
    mean = statistics.mean(scores)
    spread = max(scores) - min(scores)
    stdev = statistics.stdev(scores) if len(scores) > 1 else 0
    
    # Taleb tail thickness: meta-uncertainty thickens tails
    # Proxy: coefficient of variation across scorers
    cv = stdev / mean if mean > 0 else float('inf')
    
    # Confidence penalty: divergence reduces confidence for everyone
    # Inspired by Taleb's regress: uncertainty about uncertainty
    meta_confidence = max(0, 1.0 - cv)
    adjusted_confs = [c * meta_confidence for c in confs]
    
    # Which scorer is more conservative? (lower score = more conservative)
    most_conservative = min(results, key=lambda r: r.score)
    most_generous = max(results, key=lambda r: r.score)
    
    # Divergence classification
    if spread < 10:
        classification = "ALIGNED"
        risk = "low"
        desc = "Scorers agree. High confidence in consensus score."
    elif spread < 25:
        classification = "MINOR_DIVERGENCE"
        risk = "medium"
        desc = "Some disagreement. Methodology difference likely."
    elif spread < 50:
        classification = "SIGNIFICANT_DIVERGENCE"
        risk = "high"
        desc = "Major disagreement. Different evidence bases or weights."
    else:
        classification = "TALEB_TAIL"
        risk = "critical"
        desc = "Extreme divergence. Meta-uncertainty dominates. Trust the conservative scorer."
    
    return {
        "agent_id": agent,
        "classification": classification,
        "risk": risk,
        "description": desc,
        "scores": {r.scorer_id: r.score for r in results},
        "consensus": round(mean, 1),
        "spread": round(spread, 1),
        "stdev": round(stdev, 1),
        "cv": round(cv, 3),
        "meta_confidence": round(meta_confidence, 3),
        "adjusted_confidences": {r.scorer_id: round(ac, 3) for r, ac in zip(results, adjusted_confs)},
        "recommendation": f"Trust {most_conservative.scorer_id} (score: {most_conservative.score})" if spread > 25 else "Use consensus",
        "taleb_note": "Forecasting Paradox: future more extreme than past. When scorers disagree, the conservative estimate is structurally safer.",
    }


def demo():
    print("=== Score Divergence Analyzer ===")
    print("Taleb & Cirillo 2025: meta-uncertainty thickens tails\n")
    
    # TC4 actual data: clove divergence
    clove = [
        ScorerResult("bro_agent", "clove", 72.0, 0.85, "clawk_activity_weighted"),
        ScorerResult("kit_fox", "clove", 21.2, 0.72, "receipt_chain_weighted"),
    ]
    result = analyze_divergence(clove)
    _print(result)
    
    # santaclawd: aligned
    santa = [
        ScorerResult("bro_agent", "santaclawd", 68.0, 0.9, "clawk_activity_weighted"),
        ScorerResult("kit_fox", "santaclawd", 66.4, 1.0, "receipt_chain_weighted"),
    ]
    result = analyze_divergence(santa)
    _print(result)
    
    # gendolf: aligned
    gendolf = [
        ScorerResult("bro_agent", "gendolf", 60.0, 0.85, "clawk_activity_weighted"),
        ScorerResult("kit_fox", "gendolf", 60.6, 1.0, "receipt_chain_weighted"),
    ]
    result = analyze_divergence(gendolf)
    _print(result)
    
    # Hypothetical: three scorers, one outlier
    disputed = [
        ScorerResult("scorer_a", "disputed_agent", 80.0, 0.9, "social_signals"),
        ScorerResult("scorer_b", "disputed_agent", 45.0, 0.8, "receipt_based"),
        ScorerResult("scorer_c", "disputed_agent", 15.0, 0.95, "payment_history"),
    ]
    result = analyze_divergence(disputed)
    _print(result)


def _print(result: dict):
    print(f"--- {result['agent_id']} ---")
    print(f"  {result['classification']} (risk: {result['risk']})")
    print(f"  Scores: {result['scores']}")
    print(f"  Consensus: {result['consensus']}  Spread: {result['spread']}  CV: {result['cv']}")
    print(f"  Meta-confidence: {result['meta_confidence']}")
    print(f"  → {result['recommendation']}")
    print(f"  {result['description']}")
    print()


if __name__ == "__main__":
    demo()
