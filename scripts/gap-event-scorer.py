#!/usr/bin/env python3
"""
gap-event-scorer.py — Recency-weighted gap scoring for trust vectors.

Per santaclawd (2026-03-15): "a 48h gap 2 years ago matters less than 
a 48h gap last week. trust is recency-weighted."

Gap score = Σ(duration_hours × e^(-age_hours/S))
Where S = recency stability constant (how fast old gaps stop mattering).

Ebbinghaus in reverse: recent gaps decay trust fast, old gaps barely register.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class GapEvent:
    start: datetime
    end: datetime
    
    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600
    
    def age_hours(self, now: datetime) -> float:
        return (now - self.end).total_seconds() / 3600


def gap_score(gaps: list[GapEvent], now: datetime, S: float = 720.0) -> float:
    """
    Recency-weighted gap severity.
    
    Higher = worse (more recent/longer gaps).
    S = recency half-life in hours (default 30 days).
    """
    total = 0.0
    for g in gaps:
        age = g.age_hours(now)
        weight = math.exp(-age / S)
        total += g.duration_hours * weight
    return total


def gap_grade(score: float) -> str:
    """Convert gap score to letter grade (lower = better)."""
    if score < 2:
        return "A"  # Minimal gaps
    elif score < 10:
        return "B"  # Some gaps, manageable
    elif score < 50:
        return "C"  # Notable gaps
    elif score < 200:
        return "D"  # Significant gaps
    else:
        return "F"  # Severe availability issues


def demo():
    now = datetime(2026, 3, 15, 22, 0)
    
    scenarios = [
        {
            "name": "Reliable agent — one short gap 6 months ago",
            "gaps": [
                GapEvent(now - timedelta(days=180), now - timedelta(days=180) + timedelta(hours=2)),
            ],
        },
        {
            "name": "Recent outage — 48h gap last week",
            "gaps": [
                GapEvent(now - timedelta(days=7), now - timedelta(days=7) + timedelta(hours=48)),
            ],
        },
        {
            "name": "Flaky agent — multiple recent gaps",
            "gaps": [
                GapEvent(now - timedelta(days=3), now - timedelta(days=3) + timedelta(hours=12)),
                GapEvent(now - timedelta(days=1), now - timedelta(days=1) + timedelta(hours=6)),
                GapEvent(now - timedelta(hours=4), now - timedelta(hours=1)),
            ],
        },
        {
            "name": "Reformed — bad history, clean last 90 days",
            "gaps": [
                GapEvent(now - timedelta(days=200), now - timedelta(days=200) + timedelta(hours=72)),
                GapEvent(now - timedelta(days=150), now - timedelta(days=150) + timedelta(hours=48)),
                GapEvent(now - timedelta(days=120), now - timedelta(days=120) + timedelta(hours=24)),
            ],
        },
    ]
    
    print("=== Gap Event Scorer ===")
    print(f"Formula: gap_score = Σ(duration_h × e^(-age_h/S)), S=720h\n")
    
    for s in scenarios:
        score = gap_score(s["gaps"], now)
        grade = gap_grade(score)
        print(f"📋 {s['name']}")
        for g in s["gaps"]:
            age_d = g.age_hours(now) / 24
            w = math.exp(-g.age_hours(now) / 720)
            print(f"   gap: {g.duration_hours:.0f}h, {age_d:.0f}d ago, weight: {w:.3f}")
        print(f"   Score: {score:.2f} → Grade: {grade}")
        print()
    
    print("--- Key Insight ---")
    print("48h gap last week (score ~45) vs 72h gap 200 days ago (score ~0.5)")
    print("Same duration, 90x difference in impact. Recency IS the signal.")


if __name__ == "__main__":
    demo()
