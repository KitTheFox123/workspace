#!/usr/bin/env python3
"""
decay-audit-log.py — Empirical S calibration via consumption logging.

Per riverholybot's suggestion: log (t, R) at consumption time,
then fit S empirically. Ebbinghaus measured, not assumed.

Records every trust vector consumption with timestamps,
then fits optimal S per dimension using least-squares.

Usage: python3 decay-audit-log.py
"""

import json
import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConsumptionRecord:
    """Single trust vector consumption event."""
    dimension: str  # T, G, A, S, C
    raw_score: float
    age_hours: float
    computed_R: float
    S_used: float
    consumer_accepted: bool  # did the consumer proceed with this score?
    timestamp: str = ""


@dataclass
class DecayAuditLog:
    """Collects consumption records for S calibration."""
    records: list[ConsumptionRecord] = field(default_factory=list)

    def log(self, dim: str, raw: float, age: float, S: float, accepted: bool):
        R = raw * math.exp(-age / S) if S != float("inf") else raw
        self.records.append(ConsumptionRecord(
            dimension=dim, raw_score=raw, age_hours=age,
            computed_R=R, S_used=S, consumer_accepted=accepted,
        ))

    def fit_S(self, dimension: str) -> Optional[float]:
        """Fit optimal S for a dimension using acceptance boundary.
        Find S where acceptance probability transitions from high to low.
        """
        dim_records = [r for r in self.records if r.dimension == dimension and r.age_hours > 0]
        if len(dim_records) < 10:
            return None  # not enough data

        # Binary search for S that best separates accepted from rejected
        best_S = None
        best_accuracy = 0

        for S_candidate in [0.5, 1, 2, 4, 8, 12, 24, 48, 168, 336, 720, 1440]:
            correct = 0
            for r in dim_records:
                R = r.raw_score * math.exp(-r.age_hours / S_candidate)
                predicted_accept = R >= 0.3  # threshold
                if predicted_accept == r.consumer_accepted:
                    correct += 1
            accuracy = correct / len(dim_records)
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_S = S_candidate

        return best_S

    def summary(self, dimension: str) -> dict:
        dim_records = [r for r in self.records if r.dimension == dimension]
        if not dim_records:
            return {"dimension": dimension, "n": 0}

        accepted = [r for r in dim_records if r.consumer_accepted]
        rejected = [r for r in dim_records if not r.consumer_accepted]

        fitted_S = self.fit_S(dimension)
        current_S = dim_records[0].S_used if dim_records else None

        return {
            "dimension": dimension,
            "n": len(dim_records),
            "acceptance_rate": round(len(accepted) / len(dim_records), 3),
            "avg_age_accepted": round(sum(r.age_hours for r in accepted) / max(len(accepted), 1), 1),
            "avg_age_rejected": round(sum(r.age_hours for r in rejected) / max(len(rejected), 1), 1),
            "current_S": current_S,
            "fitted_S": fitted_S,
            "S_drift": round(abs((fitted_S or current_S) - current_S) / current_S, 3) if current_S and fitted_S else None,
        }


def simulate_consumption(log: DecayAuditLog, dimension: str, true_S: float, configured_S: float, n: int = 100):
    """Simulate consumers with a 'true' acceptance boundary."""
    for _ in range(n):
        raw = random.uniform(0.7, 1.0)
        age = random.expovariate(1 / (true_S * 1.5))  # exponential age distribution
        true_R = raw * math.exp(-age / true_S)
        accepted = true_R >= 0.3 + random.gauss(0, 0.05)  # noisy threshold
        log.log(dimension, raw, age, configured_S, accepted)


def demo():
    print("=== Decay Audit Log — Empirical S Calibration ===\n")
    random.seed(42)

    log = DecayAuditLog()

    # Simulate: configured S=4h for gossip, but true acceptance boundary suggests S=6h
    simulate_consumption(log, "G", true_S=6.0, configured_S=4.0, n=200)

    # Simulate: configured S=168h for sleeper, true S ≈ 120h
    simulate_consumption(log, "S", true_S=120.0, configured_S=168.0, n=200)

    # Simulate: configured S=720h for attestation, true S ≈ 720h (well calibrated)
    simulate_consumption(log, "A", true_S=720.0, configured_S=720.0, n=200)

    print("--- Per-Dimension Calibration ---\n")
    for dim in ["G", "S", "A"]:
        s = log.summary(dim)
        print(f"  {dim}: n={s['n']}, acceptance={s['acceptance_rate']}")
        print(f"     current S={s['current_S']}h, fitted S={s['fitted_S']}h")
        if s['S_drift'] is not None:
            drift_pct = s['S_drift'] * 100
            status = "✅ well calibrated" if drift_pct < 20 else f"⚠️ {drift_pct:.0f}% drift — recalibrate"
            print(f"     drift: {status}")
        print(f"     avg age accepted={s['avg_age_accepted']}h, rejected={s['avg_age_rejected']}h")
        print()

    print("--- Recommendation ---")
    for dim in ["G", "S", "A"]:
        s = log.summary(dim)
        if s['S_drift'] and s['S_drift'] > 0.2:
            print(f"  {dim}: RECALIBRATE S from {s['current_S']}h → {s['fitted_S']}h")
        else:
            print(f"  {dim}: S={s['current_S']}h is well calibrated")


if __name__ == "__main__":
    demo()
