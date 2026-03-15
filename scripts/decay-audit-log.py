#!/usr/bin/env python3
"""
decay-audit-log.py — 衰减审计日志 (Decay Audit Log)

Every time a trust vector is computed, log (t, R_computed, observed_outcome).
After enough events, fit S per relationship. Global S → per-relationship S → learned S.

The audit log IS the calibration dataset.

Per riverholybot (Moltbook) + santaclawd (Clawk): S=4h is a prior, not a truth.

Usage: python3 decay-audit-log.py
"""

import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional
import random


@dataclass
class DecayEvent:
    """Single observation: what we predicted vs what happened."""
    dimension: str  # T, G, A, S, C
    agent_id: str
    relationship_id: str  # agent pair
    age_hours: float  # t since last verification
    stability_used: float  # S constant used for prediction
    r_predicted: float  # e^(-t/S)
    outcome: float  # actual observed trustworthiness (0 or 1 for binary, 0-1 for graded)
    timestamp: str

    @property
    def prediction_error(self) -> float:
        return abs(self.r_predicted - self.outcome)

    @property
    def squared_error(self) -> float:
        return (self.r_predicted - self.outcome) ** 2


@dataclass
class DecayAuditLog:
    """Append-only log of decay predictions vs observations."""
    events: list[DecayEvent] = field(default_factory=list)

    def record(self, dimension: str, agent_id: str, relationship_id: str,
               age_hours: float, stability: float, outcome: float):
        r_predicted = math.exp(-age_hours / stability) if stability > 0 else 0.0
        event = DecayEvent(
            dimension=dimension,
            agent_id=agent_id,
            relationship_id=relationship_id,
            age_hours=age_hours,
            stability_used=stability,
            r_predicted=r_predicted,
            outcome=outcome,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.events.append(event)
        return event

    def mse(self, dimension: str = None, relationship_id: str = None) -> float:
        """Mean squared error for a dimension or relationship."""
        filtered = self.events
        if dimension:
            filtered = [e for e in filtered if e.dimension == dimension]
        if relationship_id:
            filtered = [e for e in filtered if e.relationship_id == relationship_id]
        if not filtered:
            return 0.0
        return sum(e.squared_error for e in filtered) / len(filtered)

    def fit_stability(self, dimension: str, relationship_id: str = None,
                      candidates: list[float] = None) -> tuple[float, float]:
        """Fit optimal S by grid search over candidates. Returns (best_S, best_MSE)."""
        if candidates is None:
            candidates = [0.5, 1, 2, 4, 8, 12, 24, 48, 168, 336, 720]

        filtered = [e for e in self.events if e.dimension == dimension]
        if relationship_id:
            filtered = [e for e in filtered if e.relationship_id == relationship_id]

        if len(filtered) < 5:
            return (None, None)  # Not enough data

        best_s, best_mse = None, float("inf")
        for s in candidates:
            mse = 0.0
            for e in filtered:
                r = math.exp(-e.age_hours / s)
                mse += (r - e.outcome) ** 2
            mse /= len(filtered)
            if mse < best_mse:
                best_s, best_mse = s, mse
        return (best_s, best_mse)

    def summary(self) -> dict:
        dims = set(e.dimension for e in self.events)
        return {
            "total_events": len(self.events),
            "dimensions": {
                d: {
                    "count": len([e for e in self.events if e.dimension == d]),
                    "mse": round(self.mse(dimension=d), 4),
                    "fit_S": self.fit_stability(d),
                }
                for d in sorted(dims)
            },
        }


def demo():
    print("=== Decay Audit Log (衰减审计日志) ===\n")
    log = DecayAuditLog()
    random.seed(42)

    # Simulate gossip observations: true S ≈ 6h (not our prior of 4h)
    print("--- Simulating 50 gossip observations (true S ≈ 6h, prior S = 4h) ---")
    for _ in range(50):
        age = random.uniform(0.5, 24)
        true_r = math.exp(-age / 6.0)  # True S = 6h
        outcome = 1.0 if random.random() < true_r else 0.0  # Binary observed
        log.record("G", "agent_alice", "alice→bob", age, stability=4.0, outcome=outcome)

    # Simulate attestation observations: true S ≈ 500h
    print("--- Simulating 30 attestation observations (true S ≈ 500h, prior S = 720h) ---")
    for _ in range(30):
        age = random.uniform(1, 720)
        true_r = math.exp(-age / 500.0)
        outcome = 1.0 if random.random() < true_r else 0.0
        log.record("A", "agent_alice", "alice→carol", age, stability=720.0, outcome=outcome)

    # Results
    summary = log.summary()
    print(f"\nTotal events: {summary['total_events']}")
    for dim, data in summary["dimensions"].items():
        fit_s, fit_mse = data["fit_S"]
        print(f"\n  {dim}:")
        print(f"    Events: {data['count']}")
        print(f"    MSE with current S: {data['mse']:.4f}")
        if fit_s:
            print(f"    Best fit S: {fit_s}h (MSE: {fit_mse:.4f})")
            improvement = (data['mse'] - fit_mse) / data['mse'] * 100 if data['mse'] > 0 else 0
            print(f"    Improvement: {improvement:.1f}% MSE reduction")

    # Show the calibration gap
    print("\n--- Calibration Gap ---")
    print(f"  Gossip: prior S=4h, fitted S={summary['dimensions']['G']['fit_S'][0]}h (true=6h)")
    print(f"  Attestation: prior S=720h, fitted S={summary['dimensions']['A']['fit_S'][0]}h (true=500h)")
    print(f"  → Priors are WRONG. Ship the audit log, calibrate from data.")


if __name__ == "__main__":
    demo()
