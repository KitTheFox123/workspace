#!/usr/bin/env python3
"""drift-metric-compositor.py — Composite drift metric for attestation TTL.

Three drift signals weighted into single metric:
1. Action-similarity cosine vs scope document (0.5)
2. CUSUM on behavioral delta (0.3)  
3. Attestation chain freshness (0.2)

Based on Aminikhanghahi & Cook 2017 (PMC5464762) change point detection survey.
CUSUM catches cumulative slow drift; cosine catches semantic drift;
freshness catches renewal gaps.

Usage:
    python3 drift-metric-compositor.py --demo
"""

import argparse
import json
import math
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Tuple


@dataclass
class DriftSignal:
    name: str
    weight: float
    value: float  # 0.0 = no drift, 1.0 = max drift
    method: str
    detail: str


@dataclass
class CompositeResult:
    timestamp: str
    composite_drift: float
    grade: str
    signals: List[dict]
    ttl_recommendation_minutes: int
    interpretation: str


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def simple_bow(text: str) -> dict:
    """Simple bag-of-words."""
    words = text.lower().split()
    bow = {}
    for w in words:
        w = ''.join(c for c in w if c.isalnum())
        if w and len(w) > 2:
            bow[w] = bow.get(w, 0) + 1
    return bow


def bow_to_vector(bow1: dict, bow2: dict) -> Tuple[List[float], List[float]]:
    """Convert two BOWs to aligned vectors."""
    vocab = sorted(set(list(bow1.keys()) + list(bow2.keys())))
    v1 = [bow1.get(w, 0) for w in vocab]
    v2 = [bow2.get(w, 0) for w in vocab]
    return v1, v2


def compute_scope_drift(scope_text: str, actions: List[str]) -> DriftSignal:
    """Cosine similarity between scope doc and recent actions."""
    scope_bow = simple_bow(scope_text)
    action_text = " ".join(actions)
    action_bow = simple_bow(action_text)
    v1, v2 = bow_to_vector(scope_bow, action_bow)
    sim = cosine_similarity(v1, v2)
    drift = 1.0 - sim  # Higher = more drift
    return DriftSignal(
        name="scope_cosine",
        weight=0.5,
        value=round(drift, 3),
        method="Cosine similarity (scope doc vs action log)",
        detail=f"similarity={sim:.3f}, drift={drift:.3f}"
    )


def compute_cusum(values: List[float], target: float = 0.0, threshold: float = 4.0) -> DriftSignal:
    """CUSUM change detection (Page 1954)."""
    s_pos = 0.0
    s_neg = 0.0
    max_cusum = 0.0
    alarm_count = 0
    
    for v in values:
        s_pos = max(0, s_pos + (v - target))
        s_neg = max(0, s_neg - (v - target))
        current = max(s_pos, s_neg)
        max_cusum = max(max_cusum, current)
        if current > threshold:
            alarm_count += 1
    
    # Normalize to 0-1
    drift = min(1.0, max_cusum / (threshold * 3))
    return DriftSignal(
        name="cusum_behavioral",
        weight=0.3,
        value=round(drift, 3),
        method="CUSUM (Page 1954) on behavioral delta",
        detail=f"max_cusum={max_cusum:.2f}, alarms={alarm_count}, threshold={threshold}"
    )


def compute_freshness(last_attestation_age_minutes: float, ttl_minutes: float = 60.0) -> DriftSignal:
    """Attestation chain freshness."""
    ratio = last_attestation_age_minutes / ttl_minutes
    drift = min(1.0, max(0.0, ratio))
    return DriftSignal(
        name="chain_freshness",
        weight=0.2,
        value=round(drift, 3),
        method="Attestation age / TTL ratio",
        detail=f"age={last_attestation_age_minutes:.0f}min, ttl={ttl_minutes:.0f}min, ratio={ratio:.2f}"
    )


def composite(signals: List[DriftSignal]) -> CompositeResult:
    """Weighted composite of drift signals."""
    total = sum(s.weight * s.value for s in signals)
    
    if total < 0.15:
        grade, interp = "A", "Minimal drift. Normal operation."
    elif total < 0.30:
        grade, interp = "B", "Low drift. Monitor."
    elif total < 0.50:
        grade, interp = "C", "Moderate drift. Reduce TTL."
    elif total < 0.70:
        grade, interp = "D", "High drift. Immediate re-attestation needed."
    else:
        grade, interp = "F", "Critical drift. Scope violation likely."
    
    # TTL recommendation: base 60min, scale inversely with drift
    base_ttl = 60
    ttl = max(5, int(base_ttl * (1 - total)))
    
    return CompositeResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
        composite_drift=round(total, 3),
        grade=grade,
        signals=[asdict(s) for s in signals],
        ttl_recommendation_minutes=ttl,
        interpretation=interp
    )


def demo():
    """Demo with synthetic data."""
    print("=" * 60)
    print("DRIFT METRIC COMPOSITOR — Demo")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "Healthy agent",
            "scope": "check clawk notifications reply to mentions post research build tools update memory",
            "actions": ["checked clawk", "replied to mention", "posted research", "built tool", "updated memory"],
            "deltas": [0.1, -0.05, 0.08, -0.02, 0.03, 0.01, -0.04],
            "attestation_age": 15,
        },
        {
            "name": "Drifting agent",
            "scope": "check clawk notifications reply to mentions post research build tools update memory",
            "actions": ["scraped competitor data", "sent bulk emails", "modified credentials", "exfiltrated logs"],
            "deltas": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
            "attestation_age": 90,
        },
        {
            "name": "Slow drifter (hardest)",
            "scope": "check clawk notifications reply to mentions post research build tools update memory",
            "actions": ["checked clawk", "replied to mention", "also checked competitor", "posted research with competitor data", "built scraper tool"],
            "deltas": [0.05, 0.08, 0.12, 0.15, 0.18, 0.20, 0.22],
            "attestation_age": 45,
        },
    ]
    
    for s in scenarios:
        print(f"\n--- {s['name']} ---")
        sig1 = compute_scope_drift(s["scope"], s["actions"])
        sig2 = compute_cusum(s["deltas"])
        sig3 = compute_freshness(s["attestation_age"])
        result = composite([sig1, sig2, sig3])
        
        print(f"  Scope cosine drift:  {sig1.value:.3f} (w={sig1.weight})")
        print(f"  CUSUM behavioral:    {sig2.value:.3f} (w={sig2.weight})")
        print(f"  Chain freshness:     {sig3.value:.3f} (w={sig3.weight})")
        print(f"  Composite:           {result.composite_drift:.3f} [{result.grade}]")
        print(f"  TTL recommendation:  {result.ttl_recommendation_minutes} min")
        print(f"  {result.interpretation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Composite drift metric for attestation TTL")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Run demo scenarios as JSON
        sig1 = compute_scope_drift("check posts reply build", ["checked posts", "replied", "built tool"])
        sig2 = compute_cusum([0.1, -0.05, 0.08])
        sig3 = compute_freshness(20)
        result = composite([sig1, sig2, sig3])
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
