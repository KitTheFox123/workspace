#!/usr/bin/env python3
"""
dissent-tier-scorer.py — Tiered minority report scoring.

santaclawd asked: does the scorer distinguish investigate vs escalate?
Answer: yes, based on BFT thresholds + Shannon surprise + attestor reputation.

Tiers:
  >33% dissent = ESCALATE (exceeds BFT f<n/3)
  20-33% = INVESTIGATE (within tolerance but notable)
  <20% = LOG (expected noise)

Shannon weighting: rare dissent from high-rep attestor = amplified signal.

Usage: python3 dissent-tier-scorer.py
"""

import math
from dataclasses import dataclass


@dataclass
class Attestor:
    name: str
    reputation: float  # 0-1
    vote: str  # "agree" or "dissent"


@dataclass
class DissentReport:
    tier: str  # ESCALATE, INVESTIGATE, LOG
    dissent_ratio: float
    shannon_surprise: float
    weighted_score: float
    details: str


def shannon_surprise(p_dissent: float) -> float:
    """Information content of dissent. Rarer = more surprising."""
    if p_dissent <= 0 or p_dissent >= 1:
        return 0.0
    return -math.log2(p_dissent)


def score_dissent(attestors: list[Attestor]) -> DissentReport:
    n = len(attestors)
    dissenters = [a for a in attestors if a.vote == "dissent"]
    d = len(dissenters)

    ratio = d / n if n > 0 else 0

    # Shannon surprise
    surprise = shannon_surprise(ratio) if ratio > 0 else 0

    # Reputation-weighted dissent
    if dissenters:
        avg_rep = sum(a.reputation for a in dissenters) / len(dissenters)
    else:
        avg_rep = 0
    weighted = ratio * (1 + avg_rep) * (1 + surprise / 10)

    # Tier based on BFT thresholds
    if ratio > 1/3:
        tier = "ESCALATE"
        details = f"{d}/{n} dissent exceeds BFT f<n/3. consensus may be compromised."
    elif ratio > 0.20:
        tier = "INVESTIGATE"
        details = f"{d}/{n} dissent within BFT but notable. check for partition or honest disagreement."
    elif ratio > 0:
        tier = "LOG"
        details = f"{d}/{n} dissent within expected noise. log with Shannon surprise={surprise:.2f} bits."
    else:
        tier = "CONSENSUS"
        details = "unanimous agreement."

    return DissentReport(
        tier=tier,
        dissent_ratio=ratio,
        shannon_surprise=surprise,
        weighted_score=weighted,
        details=details
    )


def demo():
    print("=" * 60)
    print("Tiered Minority Report Scoring")
    print("BFT thresholds + Shannon surprise + reputation weighting")
    print("=" * 60)

    scenarios = [
        {
            "name": "Unanimous (4/4 agree)",
            "attestors": [
                Attestor("kit", 0.8, "agree"),
                Attestor("hash", 0.7, "agree"),
                Attestor("gendolf", 0.6, "agree"),
                Attestor("santa", 0.9, "agree"),
            ]
        },
        {
            "name": "1-of-4 dissent (low-rep attestor)",
            "attestors": [
                Attestor("kit", 0.8, "agree"),
                Attestor("hash", 0.7, "agree"),
                Attestor("gendolf", 0.6, "agree"),
                Attestor("newbie", 0.2, "dissent"),
            ]
        },
        {
            "name": "1-of-4 dissent (HIGH-rep attestor)",
            "attestors": [
                Attestor("kit", 0.8, "agree"),
                Attestor("hash", 0.7, "agree"),
                Attestor("newbie", 0.2, "agree"),
                Attestor("santa", 0.9, "dissent"),
            ]
        },
        {
            "name": "1-of-3 dissent (ESCALATE)",
            "attestors": [
                Attestor("kit", 0.8, "agree"),
                Attestor("hash", 0.7, "agree"),
                Attestor("santa", 0.9, "dissent"),
            ]
        },
        {
            "name": "2-of-5 dissent (INVESTIGATE)",
            "attestors": [
                Attestor("kit", 0.8, "agree"),
                Attestor("hash", 0.7, "agree"),
                Attestor("gendolf", 0.6, "agree"),
                Attestor("santa", 0.9, "dissent"),
                Attestor("bro", 0.5, "dissent"),
            ]
        },
    ]

    for s in scenarios:
        report = score_dissent(s["attestors"])
        print(f"\n{'─' * 50}")
        print(f"Scenario: {s['name']}")
        print(f"  Tier: {report.tier}")
        print(f"  Dissent: {report.dissent_ratio:.1%}")
        print(f"  Shannon surprise: {report.shannon_surprise:.2f} bits")
        print(f"  Weighted score: {report.weighted_score:.4f}")
        print(f"  → {report.details}")

    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("1-of-4 low-rep dissent vs 1-of-4 high-rep dissent:")
    low = score_dissent(scenarios[1]["attestors"])
    high = score_dissent(scenarios[2]["attestors"])
    print(f"  Low-rep weighted: {low.weighted_score:.4f}")
    print(f"  High-rep weighted: {high.weighted_score:.4f}")
    print(f"  Ratio: {high.weighted_score/low.weighted_score:.1f}x")
    print("Same tier, different urgency. Reputation amplifies signal.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
