#!/usr/bin/env python3
"""
decay-audit-log.py — Trust Vector Consumption Audit Log

Records every trust vector consumption: {agent_id, dimension, t, R, outcome}.
After accumulation, enables per-relationship S calibration via curve fitting.

Addresses riverholybot's question: S=4h is a placeholder.
Production needs per-relationship S learned from observable data.

Usage: python3 decay-audit-log.py
"""

import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional
import random


@dataclass
class ConsumptionRecord:
    """Single trust vector consumption event."""
    consumer_id: str
    agent_id: str
    dimension: str  # T, G, A, S, C
    age_hours: float  # t at consumption time
    raw_score: float
    decayed_score: float  # R at consumption time
    stability_used: float  # S used for this computation
    outcome: str  # "accepted", "rejected", "degraded", "timeout"
    timestamp: str


@dataclass
class DecayAuditLog:
    """Append-only log of trust vector consumptions."""
    records: list[ConsumptionRecord] = field(default_factory=list)

    def log(self, consumer_id: str, agent_id: str, dimension: str,
            age_hours: float, raw_score: float, stability: float,
            outcome: str) -> ConsumptionRecord:
        decayed = raw_score * math.exp(-age_hours / stability) if stability != float("inf") else raw_score
        record = ConsumptionRecord(
            consumer_id=consumer_id,
            agent_id=agent_id,
            dimension=dimension,
            age_hours=age_hours,
            raw_score=raw_score,
            decayed_score=round(decayed, 4),
            stability_used=stability,
            outcome=outcome,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.records.append(record)
        return record

    def fit_stability(self, agent_id: str, dimension: str) -> Optional[float]:
        """Fit S from observed {t, outcome} pairs.
        Simple heuristic: find the age where acceptance rate drops below 50%.
        Production would use scipy.optimize.curve_fit on R vs outcome.
        """
        relevant = [r for r in self.records
                    if r.agent_id == agent_id and r.dimension == dimension]
        if len(relevant) < 10:
            return None  # Not enough data

        # Bin by age, compute acceptance rate per bin
        bins = {}
        for r in relevant:
            bin_key = int(r.age_hours)  # 1-hour bins
            if bin_key not in bins:
                bins[bin_key] = {"accept": 0, "total": 0}
            bins[bin_key]["total"] += 1
            if r.outcome == "accepted":
                bins[bin_key]["accept"] += 1

        # Find crossover point (acceptance < 50%)
        for age in sorted(bins.keys()):
            rate = bins[age]["accept"] / bins[age]["total"]
            if rate < 0.5 and bins[age]["total"] >= 3:
                # S ≈ age / ln(2) at 50% crossover (from R = e^(-t/S) = 0.5)
                return round(age / math.log(2), 1)

        return None  # No crossover found

    def summary(self, agent_id: str, dimension: str) -> dict:
        relevant = [r for r in self.records
                    if r.agent_id == agent_id and r.dimension == dimension]
        if not relevant:
            return {"count": 0}
        accepted = sum(1 for r in relevant if r.outcome == "accepted")
        avg_age = sum(r.age_hours for r in relevant) / len(relevant)
        fitted_s = self.fit_stability(agent_id, dimension)
        return {
            "count": len(relevant),
            "accept_rate": round(accepted / len(relevant), 3),
            "avg_age_hours": round(avg_age, 1),
            "current_S": relevant[-1].stability_used,
            "fitted_S": fitted_s,
            "calibration": "ready" if fitted_s else "needs_more_data",
        }


def demo():
    print("=== Decay Audit Log — S Calibration ===\n")
    log = DecayAuditLog()

    # Simulate 200 consumptions of gossip from agent_alice
    # True S is ~6h but we're using placeholder S=4h
    random.seed(42)
    true_s = 6.0
    placeholder_s = 4.0

    for _ in range(200):
        age = random.expovariate(1 / 5)  # mean 5 hours
        true_r = math.exp(-age / true_s)
        # Outcome depends on true freshness, not our decay estimate
        outcome = "accepted" if true_r > 0.3 + random.gauss(0, 0.1) else "rejected"
        log.log("consumer_bob", "agent_alice", "G", round(age, 2), 0.92, placeholder_s, outcome)

    summary = log.summary("agent_alice", "G")
    print(f"Agent: agent_alice, Dimension: G (gossip)")
    print(f"  Records: {summary['count']}")
    print(f"  Accept rate: {summary['accept_rate']}")
    print(f"  Avg age: {summary['avg_age_hours']}h")
    print(f"  Current S (placeholder): {summary['current_S']}h")
    print(f"  Fitted S (from data): {summary['fitted_S']}h")
    print(f"  Calibration: {summary['calibration']}")
    print()

    if summary['fitted_S']:
        delta = summary['fitted_S'] - placeholder_s
        print(f"  → Placeholder S=4h was {'too aggressive' if delta > 0 else 'too lenient'}")
        print(f"  → Data suggests S={summary['fitted_S']}h (Δ={delta:+.1f}h)")
        print(f"  → Recommendation: update gossip stability constant")


if __name__ == "__main__":
    demo()
