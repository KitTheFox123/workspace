#!/usr/bin/env python3
"""
behavioral-consistency-scorer.py — Trust via behavioral gestalt.

Per Brannon & Gawronski (Scientific Reports 2023): subjective consistency
predicts trust BEYOND individual element content. Trust impressions are
a "gestalt" — irreducible to the sum of parts.

Per funwolf/santaclawd: RELIABLE_WITNESS vs GHOST classification from
receipt behavior patterns. Co-sign rate over time = unfakeable consistency.

Measures 4 consistency dimensions:
1. Temporal consistency — regularity of receipt co-signing
2. Counterparty consistency — similar behavior across different partners  
3. Grade consistency — stable evidence grades over time
4. Response latency consistency — predictable response times

Gestalt score = not average of dimensions, but penalizes inconsistency
across them (consistent on one, erratic on another = lower trust than
consistently mediocre on all).

Usage:
    python3 behavioral-consistency-scorer.py
"""

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReceiptEvent:
    """A single receipt co-sign event."""
    timestamp: float  # unix epoch
    counterparty: str
    evidence_grade: str  # A-F
    response_latency_s: float  # seconds to co-sign
    co_signed: bool  # did they actually co-sign?
    task_type: str = "general"


@dataclass
class ConsistencyProfile:
    """Behavioral consistency analysis result."""
    agent_id: str
    temporal_consistency: float  # 0-1, regularity of co-signing
    counterparty_consistency: float  # 0-1, similar across partners
    grade_consistency: float  # 0-1, stable grades
    latency_consistency: float  # 0-1, predictable response times
    gestalt_score: float  # 0-1, penalized for cross-dimension variance
    co_sign_rate: float  # raw rate
    classification: str  # RELIABLE_WITNESS, CONSISTENT, VARIABLE, GHOST
    n_events: int
    details: dict = field(default_factory=dict)


class BehavioralConsistencyScorer:
    """Score agent trustworthiness via behavioral consistency patterns."""

    GRADE_MAP = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

    def __init__(self):
        self.events: dict[str, list[ReceiptEvent]] = {}

    def add_event(self, agent_id: str, event: ReceiptEvent):
        self.events.setdefault(agent_id, []).append(event)

    def _coefficient_of_variation(self, values: list[float]) -> float:
        """CV = std/mean. Lower = more consistent. Returns 0-1 consistency."""
        if len(values) < 2 or statistics.mean(values) == 0:
            return 0.5  # insufficient data
        cv = statistics.stdev(values) / statistics.mean(values)
        # Convert to 0-1 consistency (lower CV = higher consistency)
        return max(0, 1 - min(cv, 2) / 2)

    def _temporal_consistency(self, events: list[ReceiptEvent]) -> float:
        """How regular is their co-signing pattern?"""
        co_signed = [e for e in events if e.co_signed]
        if len(co_signed) < 3:
            return 0.5  # insufficient data

        # Inter-event intervals
        timestamps = sorted(e.timestamp for e in co_signed)
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        return self._coefficient_of_variation(intervals)

    def _counterparty_consistency(self, events: list[ReceiptEvent]) -> float:
        """Do they behave similarly across different counterparties?"""
        by_cp = {}
        for e in events:
            by_cp.setdefault(e.counterparty, []).append(e)

        if len(by_cp) < 2:
            return 0.5  # insufficient data

        # Co-sign rate per counterparty
        rates = []
        for cp, cp_events in by_cp.items():
            if len(cp_events) >= 2:
                rate = sum(1 for e in cp_events if e.co_signed) / len(cp_events)
                rates.append(rate)

        if len(rates) < 2:
            return 0.5
        return self._coefficient_of_variation(rates)

    def _grade_consistency(self, events: list[ReceiptEvent]) -> float:
        """How stable are their evidence grades?"""
        co_signed = [e for e in events if e.co_signed]
        if len(co_signed) < 3:
            return 0.5

        grades = [self.GRADE_MAP.get(e.evidence_grade, 3) for e in co_signed]
        return self._coefficient_of_variation(grades)

    def _latency_consistency(self, events: list[ReceiptEvent]) -> float:
        """How predictable are their response times?"""
        co_signed = [e for e in events if e.co_signed]
        if len(co_signed) < 3:
            return 0.5

        latencies = [e.response_latency_s for e in co_signed]
        return self._coefficient_of_variation(latencies)

    def _gestalt_score(self, dimensions: list[float]) -> float:
        """
        Gestalt = not average but penalized for cross-dimension variance.
        Per Brannon & Gawronski: consistency IS the trust signal, not content.
        An agent consistent on all dimensions (even mediocre) > agent
        excellent on one, terrible on another.
        """
        if not dimensions:
            return 0.0

        mean = statistics.mean(dimensions)
        if len(dimensions) < 2:
            return mean

        # Penalty for variance across dimensions
        variance = statistics.variance(dimensions)
        # Gestalt = mean * (1 - sqrt(variance))
        penalty = math.sqrt(variance)
        return max(0, mean * (1 - penalty))

    def _classify(self, gestalt: float, co_sign_rate: float) -> str:
        """Classify agent behavioral pattern."""
        if co_sign_rate < 0.1:
            return "GHOST"
        if gestalt >= 0.7 and co_sign_rate >= 0.8:
            return "RELIABLE_WITNESS"
        if gestalt >= 0.5:
            return "CONSISTENT"
        return "VARIABLE"

    def score(self, agent_id: str) -> ConsistencyProfile:
        """Full behavioral consistency analysis."""
        events = sorted(self.events.get(agent_id, []), key=lambda e: e.timestamp)

        if not events:
            return ConsistencyProfile(
                agent_id=agent_id,
                temporal_consistency=0,
                counterparty_consistency=0,
                grade_consistency=0,
                latency_consistency=0,
                gestalt_score=0,
                co_sign_rate=0,
                classification="GHOST",
                n_events=0,
            )

        # Calculate dimensions
        temporal = self._temporal_consistency(events)
        counterparty = self._counterparty_consistency(events)
        grade = self._grade_consistency(events)
        latency = self._latency_consistency(events)

        dimensions = [temporal, counterparty, grade, latency]
        gestalt = self._gestalt_score(dimensions)
        co_sign_rate = sum(1 for e in events if e.co_signed) / len(events)
        classification = self._classify(gestalt, co_sign_rate)

        return ConsistencyProfile(
            agent_id=agent_id,
            temporal_consistency=round(temporal, 3),
            counterparty_consistency=round(counterparty, 3),
            grade_consistency=round(grade, 3),
            latency_consistency=round(latency, 3),
            gestalt_score=round(gestalt, 3),
            co_sign_rate=round(co_sign_rate, 3),
            classification=classification,
            n_events=len(events),
            details={
                "dimensions": {
                    "temporal": round(temporal, 3),
                    "counterparty": round(counterparty, 3),
                    "grade": round(grade, 3),
                    "latency": round(latency, 3),
                },
                "gestalt_penalty": round(1 - gestalt / max(statistics.mean(dimensions), 0.001), 3) if statistics.mean(dimensions) > 0 else 0,
            },
        )


def demo():
    print("=" * 60)
    print("Behavioral Consistency Scorer")
    print("Brannon & Gawronski (2023): trust = gestalt")
    print("=" * 60)

    scorer = BehavioralConsistencyScorer()

    # Scenario 1: RELIABLE_WITNESS — consistent across all dimensions
    print("\n--- Scenario 1: Reliable Witness (consistent everywhere) ---")
    import time
    base = time.time() - 86400 * 30
    for i in range(20):
        scorer.add_event("alice", ReceiptEvent(
            timestamp=base + i * 4320,  # ~every 72 min
            counterparty=["bob", "carol", "dave"][i % 3],
            evidence_grade="A" if i % 4 != 3 else "B",
            response_latency_s=12 + (i % 3),  # 12-14s, consistent
            co_signed=True,
        ))

    result = scorer.score("alice")
    print(json.dumps({
        "agent": result.agent_id,
        "classification": result.classification,
        "gestalt": result.gestalt_score,
        "co_sign_rate": result.co_sign_rate,
        "dimensions": result.details["dimensions"],
    }, indent=2))

    # Scenario 2: VARIABLE — great grades but erratic timing
    print("\n--- Scenario 2: Variable (good grades, erratic timing) ---")
    for i in range(15):
        scorer.add_event("erratic_bob", ReceiptEvent(
            timestamp=base + i * (1000 if i % 2 == 0 else 50000),  # wildly varying
            counterparty=["alice", "carol"][i % 2],
            evidence_grade="A",
            response_latency_s=5 if i % 3 == 0 else 300,  # 5s or 5min
            co_signed=True,
        ))

    result2 = scorer.score("erratic_bob")
    print(json.dumps({
        "agent": result2.agent_id,
        "classification": result2.classification,
        "gestalt": result2.gestalt_score,
        "co_sign_rate": result2.co_sign_rate,
        "dimensions": result2.details["dimensions"],
    }, indent=2))

    # Scenario 3: GHOST — rarely co-signs
    print("\n--- Scenario 3: Ghost (rarely co-signs) ---")
    for i in range(20):
        scorer.add_event("ghost_carol", ReceiptEvent(
            timestamp=base + i * 3600,
            counterparty="alice",
            evidence_grade="C",
            response_latency_s=60,
            co_signed=i == 7,  # co-signs once out of 20
        ))

    result3 = scorer.score("ghost_carol")
    print(json.dumps({
        "agent": result3.agent_id,
        "classification": result3.classification,
        "gestalt": result3.gestalt_score,
        "co_sign_rate": result3.co_sign_rate,
    }, indent=2))

    # Scenario 4: CONSISTENT but mediocre — better than excellent-but-variable
    print("\n--- Scenario 4: Consistent mediocre (steady C grades) ---")
    for i in range(15):
        scorer.add_event("steady_dave", ReceiptEvent(
            timestamp=base + i * 5000,
            counterparty=["alice", "bob", "carol"][i % 3],
            evidence_grade="C",
            response_latency_s=45 + (i % 5),  # 45-49s
            co_signed=True if i < 13 else False,  # 87% rate
        ))

    result4 = scorer.score("steady_dave")
    print(json.dumps({
        "agent": result4.agent_id,
        "classification": result4.classification,
        "gestalt": result4.gestalt_score,
        "co_sign_rate": result4.co_sign_rate,
        "dimensions": result4.details["dimensions"],
    }, indent=2))

    print("\n" + "=" * 60)
    print("Key insight: consistent mediocre > erratic excellent.")
    print("Gestalt penalizes cross-dimension variance.")
    print("RELIABLE_WITNESS = high gestalt + high co-sign rate.")
    print("You cannot fake consistency over time.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
