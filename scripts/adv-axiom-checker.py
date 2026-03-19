#!/usr/bin/env python3
"""adv-axiom-checker.py — ADV v0.2 axiom verification suite.

Per santaclawd: "trust = min(continuity, stake, reachability) but without
predicates you have notation, not a spec."

Maps each axiom to its implementation + predicate:
- continuity: soul-hash-canonicalizer.py → manifest_hash comparison
- stake: attestation-density-scorer.py → trajectory window + decay
- reachability: replay-guard.py → liveness via sequence monotonicity

This checker runs all three and produces a composite trust verdict.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Literal


@dataclass
class AgentProfile:
    agent_id: str
    manifest_hash_current: str
    manifest_hash_previous: str
    days_since_manifest_change: int
    # Stake
    receipts_last_90d: int
    unique_counterparties: int
    chain_grade_ratio: float  # % of chain-grade receipts
    interaction_gap_cv: float  # coefficient of variation of gaps
    # Reachability
    last_sequence_id: int
    last_receipt_age_hours: float
    gaps_detected: int
    equivocations_detected: int


def check_continuity(profile: AgentProfile) -> dict:
    """Axiom 1: Continuity — manifest_hash comparison rule."""
    hash_match = profile.manifest_hash_current == profile.manifest_hash_previous

    if hash_match:
        score = 1.0
        status = "STABLE"
        note = "manifest unchanged"
    elif profile.days_since_manifest_change <= 7:
        score = 0.5
        status = "RECENT_CHANGE"
        note = f"manifest changed {profile.days_since_manifest_change}d ago — monitoring"
    else:
        score = 0.8
        status = "EVOLVED"
        note = f"manifest changed {profile.days_since_manifest_change}d ago — stabilized"

    return {"axiom": "continuity", "score": score, "status": status, "note": note}


def check_stake(profile: AgentProfile) -> dict:
    """Axiom 2: Stake — trajectory window + decay function."""
    # Density: receipts per day over 90d window
    density = profile.receipts_last_90d / 90

    # Diversity: unique counterparties
    diversity = min(1.0, profile.unique_counterparties / 20)

    # Quality: chain-grade ratio
    quality = profile.chain_grade_ratio

    # Consistency: low CV = regular interaction pattern
    consistency = max(0, 1.0 - profile.interaction_gap_cv)

    # Weighted composite
    score = (density * 0.2 + diversity * 0.3 + quality * 0.3 + consistency * 0.2)
    score = min(1.0, score)

    if score >= 0.7:
        status = "HIGH_STAKE"
    elif score >= 0.4:
        status = "MODERATE_STAKE"
    else:
        status = "LOW_STAKE"

    return {
        "axiom": "stake",
        "score": round(score, 3),
        "status": status,
        "components": {
            "density": round(density, 2),
            "diversity": round(diversity, 2),
            "quality": round(quality, 2),
            "consistency": round(consistency, 2),
        },
    }


def check_reachability(profile: AgentProfile) -> dict:
    """Axiom 3: Reachability — liveness_interval + ghost_threshold."""
    GHOST_THRESHOLD_HOURS = 168  # 7 days

    if profile.equivocations_detected > 0:
        score = 0.0
        status = "EQUIVOCATION_DETECTED"
        note = f"{profile.equivocations_detected} equivocations — trust revoked"
    elif profile.last_receipt_age_hours > GHOST_THRESHOLD_HOURS:
        score = 0.1
        status = "GHOST"
        note = f"last receipt {profile.last_receipt_age_hours:.0f}h ago — ghost threshold exceeded"
    elif profile.gaps_detected > 3:
        score = 0.5
        status = "UNRELIABLE"
        note = f"{profile.gaps_detected} sequence gaps — possible message loss"
    elif profile.last_receipt_age_hours > 24:
        score = 0.7
        status = "STALE"
        note = f"last receipt {profile.last_receipt_age_hours:.0f}h ago"
    else:
        score = 1.0
        status = "LIVE"
        note = f"last receipt {profile.last_receipt_age_hours:.1f}h ago, sequence clean"

    return {"axiom": "reachability", "score": score, "status": status, "note": note}


def composite_trust(profile: AgentProfile) -> dict:
    """trust = min(continuity, stake, reachability) — per santaclawd."""
    c = check_continuity(profile)
    s = check_stake(profile)
    r = check_reachability(profile)

    # min() is the right operator: weakest link determines trust
    trust = min(c["score"], s["score"], r["score"])

    if trust >= 0.7:
        verdict = "TRUSTED"
    elif trust >= 0.4:
        verdict = "PROVISIONAL"
    elif trust > 0:
        verdict = "UNTRUSTED"
    else:
        verdict = "REVOKED"

    return {
        "agent_id": profile.agent_id,
        "trust_score": round(trust, 3),
        "verdict": verdict,
        "axioms": {
            "continuity": c,
            "stake": s,
            "reachability": r,
        },
        "bottleneck": min(
            [c, s, r], key=lambda x: x["score"]
        )["axiom"],
    }


def demo():
    profiles = [
        AgentProfile(
            "kit_fox", "a1b2c3", "a1b2c3", 0,
            180, 25, 0.85, 0.3,
            450, 2.5, 0, 0,
        ),
        AgentProfile(
            "new_agent", "d4e5f6", "x0y0z0", 3,
            15, 4, 0.40, 1.2,
            12, 8.0, 0, 0,
        ),
        AgentProfile(
            "ghost_agent", "g7h8i9", "g7h8i9", 60,
            50, 12, 0.70, 0.5,
            50, 200.0, 1, 0,
        ),
        AgentProfile(
            "equivocator", "j0k1l2", "j0k1l2", 0,
            100, 18, 0.90, 0.2,
            100, 1.0, 0, 2,
        ),
    ]

    print("=" * 65)
    print("ADV v0.2 Axiom Checker")
    print("trust = min(continuity, stake, reachability)")
    print("Per santaclawd: predicates, not notation.")
    print("=" * 65)

    for p in profiles:
        result = composite_trust(p)
        icon = {"TRUSTED": "🟢", "PROVISIONAL": "🟡", "UNTRUSTED": "🟠", "REVOKED": "🔴"}[result["verdict"]]

        print(f"\n  {icon} {result['agent_id']}: {result['verdict']} ({result['trust_score']})")
        print(f"     bottleneck: {result['bottleneck']}")
        for name, ax in result["axioms"].items():
            print(f"     {name}: {ax['score']} — {ax['status']}")
            if "note" in ax:
                print(f"       └─ {ax['note']}")

    print(f"\n{'=' * 65}")
    print("IMPLEMENTATIONS:")
    print("  continuity  → soul-hash-canonicalizer.py (manifest_hash)")
    print("  stake       → attestation-density-scorer.py (density+decay)")
    print("  reachability → replay-guard.py (sequence monotonicity)")
    print("\nAll three MUST be present for ADV v0.2 compliance.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
