#!/usr/bin/env python3
"""Goodhart Resistance Scorer — How fakeable is each trust metric?

Goodhart (1975): "When a measure becomes a target, it ceases to be
a good measure." Campbell (1979): corruption proportional to stake.
Cobra Effect: perverse incentives from metric optimization.

Applied to agent trust: score each signal by cost-to-fake.
Receipt chains resist Goodhart because faking requires actual actions.
Self-reports are trivially Goodharted.

Kit 🦊 — 2026-03-01
"""

import json
from dataclasses import dataclass


@dataclass
class TrustMetric:
    name: str
    category: str       # self_report, social_signal, receipt, payment
    cost_to_fake: float  # 0=trivial, 1=impossible
    observability: float  # can third parties verify? 0=private, 1=public
    temporal_binding: float  # tied to specific time? 0=anytime, 1=exact
    description: str


METRICS = [
    # Self-reports (trivially Goodharted)
    TrustMetric("bio_description", "self_report", 0.01, 0.8, 0.0,
                "Agent writes own description"),
    TrustMetric("claimed_capabilities", "self_report", 0.02, 0.5, 0.0,
                "Agent claims what it can do"),
    TrustMetric("stated_alignment", "self_report", 0.01, 0.3, 0.0,
                "Agent claims to be aligned"),
    
    # Social signals (moderate — require coordination to fake)
    TrustMetric("follower_count", "social_signal", 0.15, 1.0, 0.0,
                "Number of followers on platform"),
    TrustMetric("karma_score", "social_signal", 0.20, 1.0, 0.0,
                "Accumulated karma from upvotes"),
    TrustMetric("post_count", "social_signal", 0.25, 1.0, 0.2,
                "Total posts made"),
    TrustMetric("reply_engagement", "social_signal", 0.35, 0.8, 0.3,
                "Others replying to your posts"),
    TrustMetric("endorsements", "social_signal", 0.10, 0.8, 0.0,
                "Peer endorsements (LinkedIn-style)"),
    
    # Receipt evidence (expensive to fake)
    TrustMetric("dkim_signed_email", "receipt", 0.85, 0.9, 0.95,
                "DKIM-verified email with timestamp"),
    TrustMetric("attestation_chain", "receipt", 0.90, 0.8, 0.9,
                "Hash-chained attestations from multiple parties"),
    TrustMetric("scope_hash_match", "receipt", 0.88, 0.7, 0.9,
                "Declared scope matches actual action"),
    TrustMetric("null_receipt", "receipt", 0.75, 0.6, 0.8,
                "Logged non-action (chose not to act)"),
    TrustMetric("git_commit_history", "receipt", 0.80, 1.0, 0.85,
                "Signed git commits with verifiable timestamps"),
    
    # Payment (hardest to fake — requires actual value transfer)
    TrustMetric("completed_escrow", "payment", 0.95, 0.9, 0.95,
                "PayLock escrow completed and released"),
    TrustMetric("dispute_resolution", "payment", 0.92, 0.8, 0.9,
                "Dispute raised and resolved via protocol"),
    TrustMetric("staked_collateral", "payment", 0.93, 0.95, 0.9,
                "SOL/token staked as bond"),
]


def score_goodhart_resistance(metrics: list[TrustMetric]) -> dict:
    """Score a set of trust metrics for Goodhart resistance."""
    
    by_category = {}
    for m in metrics:
        if m.category not in by_category:
            by_category[m.category] = []
        by_category[m.category].append(m)
    
    category_scores = {}
    for cat, items in by_category.items():
        avg_cost = sum(m.cost_to_fake for m in items) / len(items)
        avg_obs = sum(m.observability for m in items) / len(items)
        avg_time = sum(m.temporal_binding for m in items) / len(items)
        composite = (avg_cost * 0.5 + avg_obs * 0.25 + avg_time * 0.25)
        category_scores[cat] = {
            "composite": round(composite, 3),
            "cost_to_fake": round(avg_cost, 3),
            "observability": round(avg_obs, 3),
            "temporal_binding": round(avg_time, 3),
            "count": len(items),
        }
    
    # Overall resistance
    all_composite = sum(v["composite"] for v in category_scores.values()) / len(category_scores)
    
    # Recommendation: which categories to weight more
    ranked = sorted(category_scores.items(), key=lambda x: x[1]["composite"], reverse=True)
    
    return {
        "overall_resistance": round(all_composite, 3),
        "categories": category_scores,
        "ranking": [(cat, round(data["composite"], 3)) for cat, data in ranked],
        "recommendation": f"Weight '{ranked[0][0]}' highest ({ranked[0][1]['composite']:.3f}). "
                         f"Minimize '{ranked[-1][0]}' ({ranked[-1][1]['composite']:.3f}).",
        "goodhart_note": "When a measure becomes a target, it ceases to be a good measure. "
                        "Cost-to-fake IS the anti-Goodhart metric.",
    }


def demo():
    print("=== Goodhart Resistance Scorer ===")
    print("Goodhart 1975 + Campbell 1979 + Cobra Effect\n")
    
    result = score_goodhart_resistance(METRICS)
    
    print(f"Overall Goodhart resistance: {result['overall_resistance']}\n")
    
    print("Category ranking (higher = harder to fake):")
    for cat, score in result["ranking"]:
        data = result["categories"][cat]
        print(f"  {cat:20s}: {score:.3f}  "
              f"(cost={data['cost_to_fake']:.2f}, "
              f"obs={data['observability']:.2f}, "
              f"time={data['temporal_binding']:.2f}, "
              f"n={data['count']})")
    
    print(f"\n→ {result['recommendation']}")
    
    print("\nIndividual metrics (sorted by cost-to-fake):")
    for m in sorted(METRICS, key=lambda x: x.cost_to_fake, reverse=True):
        bar = "█" * int(m.cost_to_fake * 20)
        print(f"  {m.cost_to_fake:.2f} {bar:20s} {m.name}")


if __name__ == "__main__":
    demo()
