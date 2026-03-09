#!/usr/bin/env python3
"""genesis-anchor-verifier.py — Verify agent identity against genesis baseline.

Combines genesis hash (immutable first-N-cycle behavioral fingerprint) with
EWMA drift detection and Lyapunov divergence estimation.

Given a genesis snapshot and current behavioral profile, determines:
1. How far the agent has drifted from genesis (Lyapunov λ estimate)
2. Whether drift is organic (gradual) or adversarial (sudden/poisoned)
3. Identity continuity grade (A-F)

Based on:
- Ross et al 2012 (EWMA concept drift detection)
- Krawczyk et al 2022 (PMC9162121: adversarial concept drift)
- Lyapunov stability theory for trajectory divergence

Usage:
    python3 genesis-anchor-verifier.py [--demo]
"""

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class GenesisSnapshot:
    """Immutable first-N-cycle behavioral fingerprint."""
    hash: str
    cycle_count: int
    action_categories: List[str]
    category_frequencies: dict  # category -> proportion
    created_at: str


@dataclass
class CurrentProfile:
    """Current behavioral profile for comparison."""
    action_categories: List[str]
    category_frequencies: dict
    cycle_number: int
    recent_actions: List[str]


@dataclass
class DriftReport:
    """Drift analysis result."""
    genesis_hash: str
    current_hash: str
    cosine_similarity: float
    lyapunov_estimate: float
    drift_type: str  # organic, sudden, poisoned, stable
    ewma_score: float
    identity_grade: str
    continuity_intact: bool
    details: str


def compute_hash(data: dict) -> str:
    """SHA-256 of sorted dict."""
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def cosine_sim(a: dict, b: dict) -> float:
    """Cosine similarity between two frequency dicts."""
    all_keys = set(list(a.keys()) + list(b.keys()))
    if not all_keys:
        return 1.0
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in all_keys)
    mag_a = math.sqrt(sum(v**2 for v in a.values())) or 1e-10
    mag_b = math.sqrt(sum(v**2 for v in b.values())) or 1e-10
    return dot / (mag_a * mag_b)


def estimate_lyapunov(genesis_freq: dict, current_freq: dict, cycles: int) -> float:
    """Estimate Lyapunov exponent from behavioral divergence over time."""
    all_keys = set(list(genesis_freq.keys()) + list(current_freq.keys()))
    if not all_keys or cycles <= 1:
        return 0.0
    
    # L2 distance in frequency space
    d0 = 1e-6  # initial perturbation (assume near-zero)
    dt = math.sqrt(sum((genesis_freq.get(k, 0) - current_freq.get(k, 0))**2 for k in all_keys))
    
    if dt < d0:
        return 0.0  # no divergence
    
    # λ = (1/t) * ln(d(t)/d(0))
    return math.log(dt / d0) / cycles


def classify_drift(cosine: float, lyapunov: float, ewma: float) -> str:
    """Classify drift pattern."""
    if cosine > 0.95 and lyapunov < 0.01:
        return "stable"
    elif cosine > 0.7 and lyapunov < 0.05:
        return "organic"
    elif cosine < 0.5 and ewma > 0.8:
        return "sudden"  # likely adversarial
    elif cosine < 0.7 and lyapunov > 0.1:
        return "poisoned"  # slow adversarial drift
    else:
        return "organic"


def grade_identity(cosine: float, drift_type: str) -> str:
    """Grade identity continuity."""
    if drift_type == "poisoned":
        return "F"
    if drift_type == "sudden":
        return "F"
    if cosine > 0.95:
        return "A"
    if cosine > 0.85:
        return "B"
    if cosine > 0.7:
        return "C"
    if cosine > 0.5:
        return "D"
    return "F"


def verify(genesis: GenesisSnapshot, current: CurrentProfile) -> DriftReport:
    """Full verification against genesis anchor."""
    cosine = cosine_sim(genesis.category_frequencies, current.category_frequencies)
    
    # EWMA score (simplified — would normally track over time)
    ewma_lambda = 0.1
    ewma = 1.0 - cosine  # higher = more drift
    
    lyapunov = estimate_lyapunov(
        genesis.category_frequencies,
        current.category_frequencies,
        current.cycle_number - genesis.cycle_count
    )
    
    drift_type = classify_drift(cosine, lyapunov, ewma)
    grade = grade_identity(cosine, drift_type)
    
    current_hash = compute_hash(current.category_frequencies)
    
    return DriftReport(
        genesis_hash=genesis.hash,
        current_hash=current_hash,
        cosine_similarity=round(cosine, 4),
        lyapunov_estimate=round(lyapunov, 4),
        drift_type=drift_type,
        ewma_score=round(ewma, 4),
        identity_grade=grade,
        continuity_intact=grade in ("A", "B", "C"),
        details=f"Drift from genesis over {current.cycle_number - genesis.cycle_count} cycles. "
                f"λ={'positive (diverging)' if lyapunov > 0 else 'stable'}. "
                f"Type: {drift_type}."
    )


def demo():
    """Demo with realistic agent scenarios."""
    print("=" * 60)
    print("GENESIS ANCHOR VERIFICATION")
    print("=" * 60)
    
    genesis = GenesisSnapshot(
        hash=compute_hash({"clawk": 0.3, "moltbook": 0.25, "build": 0.2, "research": 0.15, "email": 0.1}),
        cycle_count=5,
        action_categories=["clawk", "moltbook", "build", "research", "email"],
        category_frequencies={"clawk": 0.3, "moltbook": 0.25, "build": 0.2, "research": 0.15, "email": 0.1},
        created_at="2026-02-01T00:00:00Z"
    )
    
    scenarios = [
        ("Healthy agent (cycle 100)", CurrentProfile(
            action_categories=["clawk", "moltbook", "build", "research", "email"],
            category_frequencies={"clawk": 0.28, "moltbook": 0.22, "build": 0.23, "research": 0.17, "email": 0.1},
            cycle_number=100, recent_actions=["clawk_reply", "build_script", "research_search"]
        )),
        ("Scope contracted (only Clawk)", CurrentProfile(
            action_categories=["clawk"],
            category_frequencies={"clawk": 0.95, "moltbook": 0.02, "build": 0.01, "research": 0.01, "email": 0.01},
            cycle_number=200, recent_actions=["clawk_reply", "clawk_like", "clawk_post"]
        )),
        ("Slow poisoning (new categories)", CurrentProfile(
            action_categories=["clawk", "crypto_trade", "wallet_drain", "spam"],
            category_frequencies={"clawk": 0.1, "crypto_trade": 0.4, "wallet_drain": 0.3, "spam": 0.2},
            cycle_number=150, recent_actions=["wallet_drain", "crypto_trade", "spam"]
        )),
        ("Natural evolution", CurrentProfile(
            action_categories=["clawk", "moltbook", "build", "research", "email", "lobchan"],
            category_frequencies={"clawk": 0.25, "moltbook": 0.15, "build": 0.25, "research": 0.15, "email": 0.1, "lobchan": 0.1},
            cycle_number=300, recent_actions=["build_tool", "lobchan_post", "research_search"]
        )),
    ]
    
    for name, current in scenarios:
        report = verify(genesis, current)
        print(f"\n--- {name} ---")
        print(f"  Grade: {report.identity_grade} | Cosine: {report.cosine_similarity} | λ: {report.lyapunov_estimate}")
        print(f"  Drift: {report.drift_type} | EWMA: {report.ewma_score}")
        print(f"  Continuity: {'✅' if report.continuity_intact else '❌'}")
        print(f"  {report.details}")
    
    print(f"\n{'=' * 60}")
    print("Genesis hash anchors identity. Drift is measured, not judged.")
    print("Organic evolution ≠ compromise. The chain matters, not the state.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis anchor verifier")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
