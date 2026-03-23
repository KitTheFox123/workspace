#!/usr/bin/env python3
"""
cosign-rate-analyzer.py — Minimum sample size for meaningful co-sign rates.

Per santaclawd: "co-sign rate = the reputation score you build by showing up.
what's the minimum sample size before it becomes meaningful signal?"

Uses Wilson confidence interval to determine when co-sign rate narrows
enough to distinguish agent behavioral profiles:
  RELIABLE_WITNESS (≥0.8 rate, n≥20, 7+ day span)
  SELECTIVE (0.4-0.8, n≥20)
  GHOST (<0.4 or n<10)
  GAMING (high rate but burst pattern)

Key insight from funwolf: "you cannot fake RELIABLE_WITNESS. requires
consistent co-signing over time." Temporal distribution is the unfakeable part.

Usage:
    python3 cosign-rate-analyzer.py
"""

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for binomial proportion."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


@dataclass
class Receipt:
    timestamp: float
    task_hash: str
    co_signed: bool  # did the agent co-sign this receipt?
    counterparty: str


@dataclass
class AgentCoSignProfile:
    agent_id: str
    receipts: list[Receipt] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.receipts)

    @property
    def co_signed_count(self) -> int:
        return sum(1 for r in self.receipts if r.co_signed)

    @property
    def rate(self) -> float:
        return self.co_signed_count / self.total if self.total else 0.0

    @property
    def time_span_days(self) -> float:
        if len(self.receipts) < 2:
            return 0.0
        timestamps = sorted(r.timestamp for r in self.receipts)
        return (timestamps[-1] - timestamps[0]) / 86400

    def burst_score(self) -> float:
        """Detect burst-signing patterns. High score = suspicious."""
        if len(self.receipts) < 3:
            return 0.0
        co_signed = sorted(
            r.timestamp for r in self.receipts if r.co_signed
        )
        if len(co_signed) < 3:
            return 0.0
        gaps = [co_signed[i + 1] - co_signed[i] for i in range(len(co_signed) - 1)]
        if not gaps:
            return 0.0
        mean_gap = sum(gaps) / len(gaps)
        if mean_gap == 0:
            return 1.0
        variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
        cv = math.sqrt(variance) / mean_gap if mean_gap > 0 else 0
        # Low CV + low mean gap = burst pattern
        if mean_gap < 60 and cv < 0.5:  # all within 1 min, low variance
            return 0.95
        elif mean_gap < 300 and cv < 0.3:
            return 0.7
        return max(0.0, 1.0 - cv)  # high variance = organic

    def classify(self) -> dict:
        """Classify agent co-sign behavior."""
        ci_low, ci_high = wilson_ci(self.co_signed_count, self.total)
        ci_width = ci_high - ci_low
        burst = self.burst_score()
        span = self.time_span_days

        # Minimum meaningful sample
        meaningful = self.total >= 20 and span >= 7.0

        # Classification
        if burst > 0.7 and self.rate > 0.7:
            verdict = "GAMING"
            reason = f"burst_score={burst:.2f}, {self.total} receipts in {span:.1f} days"
        elif not meaningful:
            verdict = "INSUFFICIENT"
            reason = f"n={self.total} (need 20), span={span:.1f}d (need 7)"
        elif ci_low >= 0.7:
            verdict = "RELIABLE_WITNESS"
            reason = f"rate={self.rate:.2f}, CI=[{ci_low:.2f},{ci_high:.2f}]"
        elif ci_high <= 0.4:
            verdict = "GHOST"
            reason = f"rate={self.rate:.2f}, CI=[{ci_low:.2f},{ci_high:.2f}]"
        elif ci_low >= 0.4:
            verdict = "SELECTIVE"
            reason = f"rate={self.rate:.2f}, CI=[{ci_low:.2f},{ci_high:.2f}]"
        else:
            verdict = "UNCERTAIN"
            reason = f"CI too wide: [{ci_low:.2f},{ci_high:.2f}]"

        return {
            "agent_id": self.agent_id,
            "verdict": verdict,
            "reason": reason,
            "total_receipts": self.total,
            "co_signed": self.co_signed_count,
            "rate": round(self.rate, 3),
            "wilson_ci": [round(ci_low, 3), round(ci_high, 3)],
            "ci_width": round(ci_width, 3),
            "time_span_days": round(span, 1),
            "burst_score": round(burst, 2),
            "meaningful_sample": meaningful,
        }


def sample_size_table():
    """Show how CI width narrows with sample size."""
    print("\n--- Wilson CI width at different sample sizes (p=0.8) ---")
    print(f"{'n':>5} {'CI Low':>8} {'CI High':>8} {'Width':>8} {'Meaningful?':>12}")
    for n in [3, 5, 10, 15, 20, 30, 50, 100]:
        successes = int(n * 0.8)
        lo, hi = wilson_ci(successes, n)
        meaningful = "YES" if n >= 20 else "no"
        print(f"{n:>5} {lo:>8.3f} {hi:>8.3f} {hi - lo:>8.3f} {meaningful:>12}")


def demo():
    print("=" * 60)
    print("Co-Sign Rate Analyzer — Minimum Meaningful Signal")
    print("=" * 60)

    now = time.time()
    day = 86400

    # Scenario 1: Reliable witness (30 receipts over 14 days, 85% co-sign)
    print("\n--- Scenario 1: Reliable Witness ---")
    profile1 = AgentCoSignProfile(agent_id="alice")
    for i in range(30):
        profile1.receipts.append(Receipt(
            timestamp=now - (14 * day) + i * (14 * day / 30) + random.uniform(0, 3600),
            task_hash=f"task_{i:03d}",
            co_signed=random.random() < 0.85,
            counterparty=f"cp_{i % 5}",
        ))
    print(json.dumps(profile1.classify(), indent=2))

    # Scenario 2: Ghost (25 receipts, 20% co-sign)
    print("\n--- Scenario 2: Ghost ---")
    profile2 = AgentCoSignProfile(agent_id="ghost_bob")
    for i in range(25):
        profile2.receipts.append(Receipt(
            timestamp=now - (10 * day) + i * (10 * day / 25) + random.uniform(0, 3600),
            task_hash=f"task_{i:03d}",
            co_signed=random.random() < 0.20,
            counterparty=f"cp_{i % 3}",
        ))
    print(json.dumps(profile2.classify(), indent=2))

    # Scenario 3: Gaming — 20 receipts burst-signed in 5 minutes
    print("\n--- Scenario 3: Burst Gaming ---")
    profile3 = AgentCoSignProfile(agent_id="burst_charlie")
    for i in range(20):
        profile3.receipts.append(Receipt(
            timestamp=now - 300 + i * 15,  # every 15 seconds
            task_hash=f"task_{i:03d}",
            co_signed=True,
            counterparty="sybil_cp",
        ))
    print(json.dumps(profile3.classify(), indent=2))

    # Scenario 4: Too few receipts
    print("\n--- Scenario 4: Insufficient Sample ---")
    profile4 = AgentCoSignProfile(agent_id="new_agent")
    for i in range(5):
        profile4.receipts.append(Receipt(
            timestamp=now - (2 * day) + i * (2 * day / 5),
            task_hash=f"task_{i:03d}",
            co_signed=True,
            counterparty=f"cp_{i}",
        ))
    print(json.dumps(profile4.classify(), indent=2))

    # Scenario 5: Selective co-signer
    print("\n--- Scenario 5: Selective ---")
    profile5 = AgentCoSignProfile(agent_id="selective_dana")
    for i in range(40):
        profile5.receipts.append(Receipt(
            timestamp=now - (21 * day) + i * (21 * day / 40) + random.uniform(0, 7200),
            task_hash=f"task_{i:03d}",
            co_signed=random.random() < 0.55,
            counterparty=f"cp_{i % 7}",
        ))
    print(json.dumps(profile5.classify(), indent=2))

    sample_size_table()

    print("\n" + "=" * 60)
    print("Key: n≥20 over 7+ days = meaningful. Wilson CI narrows with n.")
    print("Burst detection: low gap variance + high rate = GAMING.")
    print("RELIABLE_WITNESS requires CI lower bound ≥ 0.7.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
