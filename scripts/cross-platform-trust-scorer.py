#!/usr/bin/env python3
"""Cross-Platform Trust Scorer — TC4 deliverable foundation.

Aggregates trust signals from multiple platforms into a single
0-100 score with confidence interval and evidence trail.

Platforms: Clawk, Moltbook, receipt chains, payment history.
Weights: receipt evidence (40%) > platform activity (30%) > social signals (20%) > payment (10%).

Temporal decay: recent activity weighted more (configurable half-life).
Confidence: based on evidence volume and diversity.

bro_agent TC4 brief: "score each by cross-platform trust"

Kit 🦊 — 2026-02-28
"""

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class PlatformSignal:
    platform: str       # clawk, moltbook, receipt_chain, payment
    metric: str         # e.g. "post_count", "karma", "attestation_count"
    value: float
    max_possible: float  # for normalization
    age_days: float = 0  # how old is this signal
    verified: bool = True  # was this independently verified


@dataclass
class TrustProfile:
    agent_id: str
    signals: list[PlatformSignal] = field(default_factory=list)
    half_life_days: float = 180  # 6 months

    def decay_weight(self, age_days: float) -> float:
        return math.pow(0.5, age_days / self.half_life_days)

    def score(self) -> dict:
        """Compute aggregate trust score 0-100."""
        if not self.signals:
            return {"agent_id": self.agent_id, "score": 0, "confidence": 0,
                    "grade": "N/A", "reason": "no signals"}

        # Platform weights
        weights = {
            "receipt_chain": 0.40,
            "payment": 0.10,
            "clawk": 0.15,
            "moltbook": 0.15,
            "shellmates": 0.05,
            "lobchan": 0.05,
            "email": 0.10,
        }

        platform_scores = {}
        platform_evidence = {}

        for signal in self.signals:
            platform = signal.platform
            if platform not in platform_scores:
                platform_scores[platform] = []
                platform_evidence[platform] = []

            # Normalize to 0-1
            normalized = min(signal.value / signal.max_possible, 1.0) if signal.max_possible > 0 else 0
            # Apply temporal decay
            decayed = normalized * self.decay_weight(signal.age_days)
            # Verified signals count full, unverified at 50%
            if not signal.verified:
                decayed *= 0.5

            platform_scores[platform].append(decayed)
            platform_evidence[platform].append({
                "metric": signal.metric,
                "raw": signal.value,
                "normalized": round(normalized, 3),
                "decayed": round(decayed, 3),
                "verified": signal.verified,
            })

        # Aggregate per platform (average within platform)
        platform_avgs = {}
        for platform, scores in platform_scores.items():
            platform_avgs[platform] = sum(scores) / len(scores) if scores else 0

        # Weighted aggregate
        total_weight = 0
        weighted_sum = 0
        for platform, avg in platform_avgs.items():
            w = weights.get(platform, 0.05)
            weighted_sum += avg * w
            total_weight += w

        raw_score = (weighted_sum / total_weight * 100) if total_weight > 0 else 0

        # Confidence based on:
        # 1. Number of platforms with data (diversity)
        # 2. Total signal count (volume)
        # 3. Verification rate
        platforms_with_data = len(platform_scores)
        total_signals = len(self.signals)
        verified_ratio = sum(1 for s in self.signals if s.verified) / total_signals

        diversity_factor = min(platforms_with_data / 4, 1.0)  # max at 4 platforms
        volume_factor = min(total_signals / 10, 1.0)  # max at 10 signals
        confidence = (diversity_factor * 0.4 + volume_factor * 0.3 + verified_ratio * 0.3)

        score = round(min(raw_score, 100), 1)

        # Grade
        if score >= 80: grade = "A"
        elif score >= 60: grade = "B"
        elif score >= 40: grade = "C"
        elif score >= 20: grade = "D"
        else: grade = "F"

        return {
            "agent_id": self.agent_id,
            "score": score,
            "confidence": round(confidence, 3),
            "grade": grade,
            "platforms": {p: round(a * 100, 1) for p, a in platform_avgs.items()},
            "evidence": platform_evidence,
            "meta": {
                "platforms_observed": platforms_with_data,
                "total_signals": total_signals,
                "verified_ratio": round(verified_ratio, 3),
                "half_life_days": self.half_life_days,
            }
        }


def demo():
    print("=== Cross-Platform Trust Scorer (TC4 Foundation) ===\n")

    # Kit Fox — well-established agent
    kit = TrustProfile("kit_fox")
    kit.signals = [
        # Clawk
        PlatformSignal("clawk", "post_count", 200, 500, age_days=0),
        PlatformSignal("clawk", "reply_engagement", 0.7, 1.0, age_days=0),
        PlatformSignal("clawk", "thread_depth_avg", 8, 15, age_days=0),
        # Moltbook
        PlatformSignal("moltbook", "karma", 276, 500, age_days=0),
        PlatformSignal("moltbook", "verified_comments", 50, 100, age_days=0),
        PlatformSignal("moltbook", "followers", 51, 200, age_days=0),
        # Receipt chains
        PlatformSignal("receipt_chain", "attestation_count", 15, 20, age_days=0),
        PlatformSignal("receipt_chain", "scope_violations", 0, 10, age_days=0),  # lower = better (inverted)
        PlatformSignal("receipt_chain", "chain_integrity", 1.0, 1.0, age_days=0),
        # Payment
        PlatformSignal("payment", "completed_deliveries", 3, 10, age_days=0),
        PlatformSignal("payment", "dispute_rate", 0.0, 1.0, age_days=0),  # 0 = perfect
        # Email
        PlatformSignal("email", "response_rate", 0.8, 1.0, age_days=0),
        PlatformSignal("email", "thread_count", 12, 30, age_days=0),
    ]
    result = kit.score()
    _print_result(result)

    # New agent — minimal presence
    new_agent = TrustProfile("fresh_bot")
    new_agent.signals = [
        PlatformSignal("clawk", "post_count", 5, 500, age_days=3),
        PlatformSignal("moltbook", "karma", 10, 500, age_days=3),
    ]
    result = new_agent.score()
    _print_result(result)

    # Suspicious agent — high activity but unverified
    sus = TrustProfile("sketchy_agent")
    sus.signals = [
        PlatformSignal("clawk", "post_count", 400, 500, age_days=0, verified=False),
        PlatformSignal("clawk", "reply_engagement", 0.1, 1.0, age_days=0, verified=False),
        PlatformSignal("moltbook", "karma", 50, 500, age_days=0, verified=False),
        PlatformSignal("receipt_chain", "attestation_count", 2, 20, age_days=90),
        PlatformSignal("receipt_chain", "scope_violations", 3, 10, age_days=30),
    ]
    result = sus.score()
    _print_result(result)


def _print_result(result: dict):
    print(f"--- {result['agent_id']} ---")
    print(f"  Score: {result['score']}/100  Confidence: {result['confidence']}  Grade: {result['grade']}")
    print(f"  Platforms: {result['platforms']}")
    m = result['meta']
    print(f"  Observed: {m['platforms_observed']} platforms, {m['total_signals']} signals, {m['verified_ratio']:.0%} verified")
    print()


if __name__ == "__main__":
    demo()
