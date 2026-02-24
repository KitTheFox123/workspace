#!/usr/bin/env python3
"""
dispute-profile-generator.py — Generate default dispute resolution profiles for v0.3 spec.

Maps deliverable characteristics to optimal dispute parameters:
- Subjective deliverables → escrow + dispute window + diverse attesters
- Machine-verifiable deliverables → payment-first + on-chain anchor
- Mixed → hybrid with weighted scoring

The tc3 lesson: informal negotiation worked, but v0.3 needs sensible defaults.

Usage:
    python3 dispute-profile-generator.py              # Interactive mode
    python3 dispute-profile-generator.py classify      # Classify a deliverable
    python3 dispute-profile-generator.py profiles      # Show all default profiles
"""

import json
import sys
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class DisputeProfile:
    """Default dispute resolution configuration."""
    name: str
    description: str
    # Payment model
    payment_model: str  # "escrow" | "payment_first" | "hybrid"
    # Timing
    auto_approve_hours: int
    challenge_window_hours: int
    # Quality
    quality_floor: float  # Minimum score to auto-release (0.0-1.0)
    # Attestation
    min_attesters: int
    require_diverse: bool  # Must attesters use different models/platforms?
    # Dispute
    dispute_mechanism: str  # "oracle_pool" | "buyer_judge" | "third_party"
    max_dispute_rounds: int
    # Stake
    worker_stake_pct: float  # Percentage of bounty worker stakes
    # Reputation effects
    rep_gain_on_complete: float
    rep_loss_on_dispute_lost: float


# Default profiles based on deliverable type
PROFILES = {
    "subjective_research": DisputeProfile(
        name="Subjective Research",
        description="Research, analysis, strategy — quality is opinion. TC3 pattern.",
        payment_model="escrow",
        auto_approve_hours=48,
        challenge_window_hours=48,
        quality_floor=0.7,
        min_attesters=2,
        require_diverse=True,
        dispute_mechanism="oracle_pool",
        max_dispute_rounds=2,
        worker_stake_pct=0.0,  # No stake for knowledge work
        rep_gain_on_complete=0.05,
        rep_loss_on_dispute_lost=0.10,
    ),
    "machine_verifiable": DisputeProfile(
        name="Machine Verifiable",
        description="Code passes tests, data matches schema, tx hash exists. TC4 pattern.",
        payment_model="payment_first",
        auto_approve_hours=24,
        challenge_window_hours=24,
        quality_floor=1.0,  # Binary: works or doesn't
        min_attesters=1,
        require_diverse=False,
        dispute_mechanism="buyer_judge",
        max_dispute_rounds=1,
        worker_stake_pct=10.0,
        rep_gain_on_complete=0.03,
        rep_loss_on_dispute_lost=0.15,
    ),
    "creative": DisputeProfile(
        name="Creative Work",
        description="Design, writing, content — highly subjective, revision expected.",
        payment_model="escrow",
        auto_approve_hours=72,
        challenge_window_hours=72,
        quality_floor=0.6,  # Lower floor, more revision rounds
        min_attesters=2,
        require_diverse=True,
        dispute_mechanism="oracle_pool",
        max_dispute_rounds=3,
        worker_stake_pct=0.0,
        rep_gain_on_complete=0.04,
        rep_loss_on_dispute_lost=0.08,
    ),
    "commodity": DisputeProfile(
        name="Commodity Task",
        description="Data entry, scraping, format conversion — low ambiguity.",
        payment_model="payment_first",
        auto_approve_hours=24,
        challenge_window_hours=12,
        quality_floor=0.9,
        min_attesters=1,
        require_diverse=False,
        dispute_mechanism="buyer_judge",
        max_dispute_rounds=1,
        worker_stake_pct=5.0,
        rep_gain_on_complete=0.02,
        rep_loss_on_dispute_lost=0.05,
    ),
    "high_value": DisputeProfile(
        name="High Value Contract",
        description="Large bounties requiring maximum protection for both parties.",
        payment_model="escrow",
        auto_approve_hours=48,
        challenge_window_hours=96,
        quality_floor=0.8,
        min_attesters=3,
        require_diverse=True,
        dispute_mechanism="third_party",
        max_dispute_rounds=3,
        worker_stake_pct=10.0,
        rep_gain_on_complete=0.08,
        rep_loss_on_dispute_lost=0.20,
    ),
}


# Classification heuristics
SUBJECTIVE_SIGNALS = [
    "research", "analyze", "strategy", "recommend", "evaluate", "assess",
    "review", "opinion", "insight", "perspective", "argue", "thesis",
]
VERIFIABLE_SIGNALS = [
    "code", "test", "compile", "deploy", "hash", "schema", "api",
    "endpoint", "pass", "fail", "binary", "boolean", "exists",
]
CREATIVE_SIGNALS = [
    "design", "write", "content", "copy", "brand", "visual", "art",
    "creative", "draft", "narrative", "story", "style",
]
COMMODITY_SIGNALS = [
    "scrape", "convert", "format", "extract", "list", "collect",
    "transcribe", "tag", "label", "categorize", "sort",
]


def classify_deliverable(description: str) -> tuple[str, dict]:
    """Classify a deliverable description into a dispute profile.
    
    Returns (profile_key, scores_dict).
    """
    desc_lower = description.lower()
    
    scores = {
        "subjective_research": sum(1 for s in SUBJECTIVE_SIGNALS if s in desc_lower),
        "machine_verifiable": sum(1 for s in VERIFIABLE_SIGNALS if s in desc_lower),
        "creative": sum(1 for s in CREATIVE_SIGNALS if s in desc_lower),
        "commodity": sum(1 for s in COMMODITY_SIGNALS if s in desc_lower),
    }
    
    # High value override: check for money signals
    money_words = ["$", "usdc", "sol", "high value", "large", "significant"]
    if any(w in desc_lower for w in money_words):
        scores["high_value"] = max(scores.values()) + 1
    else:
        scores["high_value"] = 0
    
    best = max(scores, key=scores.get)
    
    # Default to subjective if no signals
    if all(v == 0 for v in scores.values()):
        best = "subjective_research"
    
    return best, scores


def dynamic_profile(base_profile: DisputeProfile, worker_rep: float) -> DisputeProfile:
    """Adjust profile based on worker reputation (0.0-1.0).
    
    Higher rep = shorter windows, lower stakes (earned trust).
    """
    import copy
    p = copy.deepcopy(base_profile)
    
    if worker_rep > 0.8:
        p.challenge_window_hours = max(12, int(p.challenge_window_hours * 0.5))
        p.worker_stake_pct = max(0, p.worker_stake_pct * 0.5)
        p.auto_approve_hours = max(12, int(p.auto_approve_hours * 0.75))
    elif worker_rep > 0.5:
        p.challenge_window_hours = int(p.challenge_window_hours * 0.75)
        p.worker_stake_pct = p.worker_stake_pct * 0.75
    
    return p


def show_profiles():
    """Display all default profiles."""
    print("=" * 60)
    print("v0.3 Default Dispute Resolution Profiles")
    print("=" * 60)
    
    for key, profile in PROFILES.items():
        print(f"\n### {profile.name} ({key})")
        print(f"  {profile.description}")
        print(f"  Payment: {profile.payment_model}")
        print(f"  Auto-approve: {profile.auto_approve_hours}h | Challenge: {profile.challenge_window_hours}h")
        print(f"  Quality floor: {profile.quality_floor}")
        print(f"  Attesters: {profile.min_attesters} (diverse: {profile.require_diverse})")
        print(f"  Dispute: {profile.dispute_mechanism} (max {profile.max_dispute_rounds} rounds)")
        print(f"  Worker stake: {profile.worker_stake_pct}%")
        print(f"  Rep: +{profile.rep_gain_on_complete} / -{profile.rep_loss_on_dispute_lost}")


def classify_interactive():
    """Interactive classification mode."""
    desc = input("Describe the deliverable: ")
    profile_key, scores = classify_deliverable(desc)
    profile = PROFILES[profile_key]
    
    print(f"\n--- Classification ---")
    print(f"Scores: {json.dumps(scores, indent=2)}")
    print(f"Best match: {profile.name} ({profile_key})")
    print(f"\n--- Recommended Profile ---")
    print(json.dumps(asdict(profile), indent=2))
    
    rep = input("\nWorker reputation (0.0-1.0, enter to skip): ").strip()
    if rep:
        adjusted = dynamic_profile(profile, float(rep))
        print(f"\n--- Adjusted for rep={rep} ---")
        print(json.dumps(asdict(adjusted), indent=2))


def demo():
    """Run demo classifications."""
    print("=" * 60)
    print("Dispute Profile Generator — Demo")
    print("=" * 60)
    
    examples = [
        "Research what the agent economy needs at scale. Deliverable: written analysis with sources.",
        "Write a Python script that passes these 5 test cases. Code must compile and tests must pass.",
        "Design a logo for our agent marketplace. Creative direction open.",
        "Scrape and format the top 100 Moltbook posts into a CSV file.",
        "Build a $500 USDC smart contract integration for our high value escrow system.",
    ]
    
    for desc in examples:
        key, scores = classify_deliverable(desc)
        profile = PROFILES[key]
        print(f"\n📋 \"{desc[:70]}...\"")
        print(f"   → {profile.name} | {profile.payment_model} | "
              f"{profile.auto_approve_hours}h approve | "
              f"{profile.min_attesters} attesters | "
              f"stake {profile.worker_stake_pct}%")
    
    # Show rep adjustment
    print(f"\n--- Rep adjustment example (subjective_research) ---")
    base = PROFILES["subjective_research"]
    for rep in [0.3, 0.6, 0.9]:
        adj = dynamic_profile(base, rep)
        print(f"  rep={rep}: challenge={adj.challenge_window_hours}h, "
              f"stake={adj.worker_stake_pct}%, auto_approve={adj.auto_approve_hours}h")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "profiles":
        show_profiles()
    elif sys.argv[1] == "classify":
        classify_interactive()
    else:
        print(__doc__)
