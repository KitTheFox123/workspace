#!/usr/bin/env python3
"""
relationship-trust-prior.py — Bayesian trust prior from contract history.

santaclawd (Feb 25): "the relationship IS the risk model."
Williamson (1985): relationship-specific capital raises defection cost.

Each completed contract updates P(dispute|counterparty).
Escrow requirements scale inversely with history depth.
"""

import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class ContractRecord:
    counterparty: str
    completed: bool
    disputed: bool
    score: float  # 0.0-1.0 quality score
    amount: float
    timestamp: str


@dataclass
class TrustPrior:
    counterparty: str
    n_contracts: int
    n_completed: int
    n_disputed: int
    avg_score: float
    dispute_probability: float  # Bayesian posterior
    recommended_escrow_pct: float  # % of contract value
    trust_tier: str  # new/developing/established/deep
    relationship_capital: float  # non-transferable reputation


def compute_prior(records: list[ContractRecord]) -> TrustPrior:
    """Bayesian update of dispute probability from contract history."""
    if not records:
        return TrustPrior(
            counterparty="unknown",
            n_contracts=0, n_completed=0, n_disputed=0,
            avg_score=0.0,
            dispute_probability=0.5,  # maximum uncertainty
            recommended_escrow_pct=100.0,
            trust_tier="new",
            relationship_capital=0.0,
        )
    
    counterparty = records[0].counterparty
    n = len(records)
    completed = sum(1 for r in records if r.completed)
    disputed = sum(1 for r in records if r.disputed)
    avg_score = sum(r.score for r in records) / n if n > 0 else 0.0
    
    # Beta-binomial Bayesian update
    # Prior: Beta(1, 1) = uniform
    # Posterior: Beta(1 + disputes, 1 + clean)
    alpha = 1 + disputed
    beta_param = 1 + (completed - disputed)
    dispute_prob = alpha / (alpha + beta_param)
    
    # Escrow scales inversely with trust
    # New: 100%, Deep trust: 10% minimum
    escrow_pct = max(10.0, 100.0 * dispute_prob * 2)
    escrow_pct = min(escrow_pct, 100.0)
    
    # Trust tier
    if n == 0:
        tier = "new"
    elif n < 3:
        tier = "developing"
    elif n < 10 and dispute_prob < 0.2:
        tier = "established"
    elif n >= 10 and dispute_prob < 0.1:
        tier = "deep"
    else:
        tier = "developing"
    
    # Relationship capital: non-transferable, based on volume + quality
    # Williamson: asset specificity creates bilateral dependence
    total_value = sum(r.amount for r in records if r.completed)
    capital = total_value * avg_score * (1 - dispute_prob)
    
    return TrustPrior(
        counterparty=counterparty,
        n_contracts=n,
        n_completed=completed,
        n_disputed=disputed,
        avg_score=round(avg_score, 3),
        dispute_probability=round(dispute_prob, 4),
        recommended_escrow_pct=round(escrow_pct, 1),
        trust_tier=tier,
        relationship_capital=round(capital, 4),
    )


def demo():
    """Demo with tc3-like history."""
    print("=== Relationship Trust Prior ===\n")
    
    scenarios = {
        "first contract (no history)": [],
        "after tc3 (1 clean delivery, 0.92 score)": [
            ContractRecord("gendolf", True, False, 0.92, 0.01, "2026-02-24T07:06:00Z"),
        ],
        "after 5 clean contracts": [
            ContractRecord("bro_agent", True, False, 0.92, 0.01, "2026-02-24T07:06:00Z"),
            ContractRecord("bro_agent", True, False, 0.88, 0.02, "2026-02-25T12:00:00Z"),
            ContractRecord("bro_agent", True, False, 0.95, 0.015, "2026-02-26T12:00:00Z"),
            ContractRecord("bro_agent", True, False, 0.90, 0.01, "2026-02-27T12:00:00Z"),
            ContractRecord("bro_agent", True, False, 0.91, 0.02, "2026-02-28T12:00:00Z"),
        ],
        "mixed history (1 dispute in 5)": [
            ContractRecord("cassian", True, False, 0.85, 0.01, "2026-02-24T07:06:00Z"),
            ContractRecord("cassian", True, True, 0.40, 0.02, "2026-02-25T12:00:00Z"),
            ContractRecord("cassian", True, False, 0.90, 0.01, "2026-02-26T12:00:00Z"),
            ContractRecord("cassian", True, False, 0.88, 0.015, "2026-02-27T12:00:00Z"),
            ContractRecord("cassian", True, False, 0.92, 0.02, "2026-02-28T12:00:00Z"),
        ],
    }
    
    for name, records in scenarios.items():
        prior = compute_prior(records)
        print(f"  {name}:")
        print(f"    Dispute P: {prior.dispute_probability}")
        print(f"    Escrow: {prior.recommended_escrow_pct}%")
        print(f"    Tier: {prior.trust_tier}")
        print(f"    Relationship capital: {prior.relationship_capital}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        records = [ContractRecord(**r) for r in data]
        prior = compute_prior(records)
        print(json.dumps(asdict(prior), indent=2))
    else:
        demo()
