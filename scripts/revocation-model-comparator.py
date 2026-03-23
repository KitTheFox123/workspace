#!/usr/bin/env python3
"""
revocation-model-comparator.py — Compare OCSP vs CRL vs Stapling revocation models for ATF.

Let's Encrypt killed OCSP in Aug 2025 after 10 years. Reasons:
  - Privacy: OCSP responder sees every certificate check (site + IP)
  - Complexity: running OCSP infrastructure is expensive
  - Failure modes: OCSP soft-fail means revocation is advisory, not enforced

CRLs won because: bulk download, no per-visit leak, browsers already supported them.

For ATF, three revocation models:
  1. ORACLE_QUERY (OCSP-like): ask oracle per interaction → privacy leak + latency
  2. BULK_SNAPSHOT (CRL-like): periodic trust list download → private, stale
  3. RECEIPT_STAPLED (OCSP-stapling done right): trust status inline in receipt → private, fresh

Usage:
    python3 revocation-model-comparator.py
"""

import json
from dataclasses import dataclass, field


@dataclass
class RevocationModel:
    name: str
    privacy_leak_per_interaction: bool
    latency_ms: float  # added per interaction
    freshness_seconds: float  # max staleness
    infrastructure_cost: str  # LOW/MEDIUM/HIGH
    failure_mode: str  # HARD_FAIL / SOFT_FAIL
    requires_online_oracle: bool
    counterparty_verifiable: bool  # ATF Axiom 1


MODELS = {
    "ORACLE_QUERY": RevocationModel(
        name="ORACLE_QUERY (OCSP-like)",
        privacy_leak_per_interaction=True,
        latency_ms=150.0,
        freshness_seconds=0,  # real-time
        infrastructure_cost="HIGH",
        failure_mode="SOFT_FAIL",  # browsers soft-fail OCSP
        requires_online_oracle=True,
        counterparty_verifiable=True,
    ),
    "BULK_SNAPSHOT": RevocationModel(
        name="BULK_SNAPSHOT (CRL-like)",
        privacy_leak_per_interaction=False,
        latency_ms=0,
        freshness_seconds=3600,  # 1hr typical CRL validity
        infrastructure_cost="LOW",
        failure_mode="HARD_FAIL",
        requires_online_oracle=False,
        counterparty_verifiable=True,
    ),
    "RECEIPT_STAPLED": RevocationModel(
        name="RECEIPT_STAPLED (ATF HOT_SWAP)",
        privacy_leak_per_interaction=False,
        latency_ms=0,
        freshness_seconds=0,  # stapled at receipt time
        infrastructure_cost="LOW",
        failure_mode="HARD_FAIL",
        requires_online_oracle=False,
        counterparty_verifiable=True,
    ),
}


@dataclass
class InteractionScenario:
    name: str
    interactions_per_day: int
    agents_in_network: int
    revocation_events_per_day: int
    privacy_sensitive: bool


def evaluate(model: RevocationModel, scenario: InteractionScenario) -> dict:
    """Score a revocation model against a scenario."""

    # Privacy score: 0 (leaks everything) to 1 (no leaks)
    if model.privacy_leak_per_interaction:
        privacy_score = 0.0
        privacy_leaks = scenario.interactions_per_day
    else:
        privacy_score = 1.0
        privacy_leaks = 0

    # Latency impact (ms added per day)
    total_latency_ms = model.latency_ms * scenario.interactions_per_day

    # Staleness risk: probability of acting on stale revocation
    if model.freshness_seconds == 0:
        staleness_risk = 0.0
    else:
        # Probability an interaction happens before revocation propagates
        avg_interaction_gap = 86400 / max(scenario.interactions_per_day, 1)
        staleness_risk = min(
            model.freshness_seconds / max(avg_interaction_gap, 1), 1.0
        )

    # Infrastructure cost score
    cost_map = {"LOW": 0.9, "MEDIUM": 0.5, "HIGH": 0.2}
    cost_score = cost_map.get(model.infrastructure_cost, 0.5)

    # Enforcement score
    enforcement = 1.0 if model.failure_mode == "HARD_FAIL" else 0.3

    # Axiom 1 compliance
    axiom1 = 1.0 if model.counterparty_verifiable else 0.0

    # Composite score (weighted)
    composite = (
        privacy_score * 0.30
        + (1 - staleness_risk) * 0.25
        + cost_score * 0.15
        + enforcement * 0.15
        + axiom1 * 0.15
    )

    grade = (
        "A" if composite >= 0.85
        else "B" if composite >= 0.70
        else "C" if composite >= 0.55
        else "D" if composite >= 0.40
        else "F"
    )

    return {
        "model": model.name,
        "scenario": scenario.name,
        "privacy_score": round(privacy_score, 2),
        "privacy_leaks_per_day": privacy_leaks,
        "total_latency_ms": round(total_latency_ms, 1),
        "staleness_risk": round(staleness_risk, 4),
        "cost_score": cost_score,
        "enforcement": model.failure_mode,
        "axiom1_compliant": model.counterparty_verifiable,
        "composite_score": round(composite, 3),
        "grade": grade,
    }


def demo():
    print("=" * 65)
    print("Revocation Model Comparator — OCSP vs CRL vs Stapling for ATF")
    print("Let's Encrypt killed OCSP Aug 2025. Here's why stapling wins.")
    print("=" * 65)

    scenarios = [
        InteractionScenario(
            name="Small agent network",
            interactions_per_day=50,
            agents_in_network=10,
            revocation_events_per_day=0,
            privacy_sensitive=True,
        ),
        InteractionScenario(
            name="Production marketplace",
            interactions_per_day=10000,
            agents_in_network=500,
            revocation_events_per_day=3,
            privacy_sensitive=True,
        ),
        InteractionScenario(
            name="High-frequency trading agents",
            interactions_per_day=100000,
            agents_in_network=50,
            revocation_events_per_day=1,
            privacy_sensitive=True,
        ),
    ]

    for scenario in scenarios:
        print(f"\n--- {scenario.name} ({scenario.interactions_per_day} interactions/day) ---")
        results = []
        for model in MODELS.values():
            result = evaluate(model, scenario)
            results.append(result)
            print(
                f"  {result['grade']} | {model.name:<35} | "
                f"privacy={result['privacy_score']:.1f} "
                f"stale={result['staleness_risk']:.3f} "
                f"latency={result['total_latency_ms']:.0f}ms "
                f"| composite={result['composite_score']:.3f}"
            )

        winner = max(results, key=lambda r: r["composite_score"])
        print(f"  → Winner: {winner['model']} (Grade {winner['grade']})")

    print("\n" + "=" * 65)
    print("Key findings:")
    print("  - ORACLE_QUERY always loses on privacy (leaks per interaction)")
    print("  - BULK_SNAPSHOT is private but stale (CRL validity window)")
    print("  - RECEIPT_STAPLED wins: private, fresh, low cost, hard-fail")
    print("  - Let's Encrypt proved this over 10 years of production")
    print("  - ATF HOT_SWAP = stapled revocation done right")
    print("=" * 65)


if __name__ == "__main__":
    demo()
