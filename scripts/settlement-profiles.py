#!/usr/bin/env python3
"""
settlement-profiles.py — Settlement profile generator for agent-to-agent contracts.

Implements the "profile-as-contract" pattern from Clawk thread (2026-02-25):
- Two default profiles: subjective (escrow+dispute) vs deterministic (payment-first)
- Custom profile creation from observed deltas
- Profile selection heuristics based on deliverable type

Usage:
    python3 settlement-profiles.py demo          # Show default profiles + selection
    python3 settlement-profiles.py select QUERY  # Recommend profile for a task description
    python3 settlement-profiles.py history       # Show profile evolution from tc3 data
"""

import json
import sys
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timedelta


@dataclass
class SettlementProfile:
    """A settlement profile = contract semantics for agent-to-agent work."""
    name: str
    description: str
    
    # Payment flow
    escrow_required: bool = True
    payment_first: bool = False
    auto_release_hours: float = 48.0
    
    # Dispute resolution
    dispute_window_hours: float = 48.0
    dispute_required: bool = False  # Must dispute to reject (optimistic)
    judge_type: str = "agent"  # "agent", "human", "machine", "oracle"
    min_attesters: int = 2
    
    # Verification
    verification_method: str = "subjective"  # "subjective", "deterministic", "hybrid"
    auto_verify_conditions: list = field(default_factory=list)
    
    # Staking
    worker_stake_pct: float = 0.0
    poster_stake_pct: float = 0.0
    
    # Reputation
    min_reputation: float = 0.0
    reputation_weighted_window: bool = False  # Dynamic window based on rep
    
    def profile_hash(self) -> str:
        """Content-addressable profile ID."""
        data = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def estimated_cost(self, bounty_amount: float) -> dict:
        """Estimate total transaction costs."""
        escrow_cost = 0.001 if self.escrow_required else 0.0  # gas
        dispute_probability = 0.08 if self.verification_method == "subjective" else 0.02
        expected_dispute_cost = dispute_probability * bounty_amount * 0.05
        stake_lockup = bounty_amount * (self.worker_stake_pct / 100)
        
        return {
            "escrow_gas": escrow_cost,
            "expected_dispute_cost": round(expected_dispute_cost, 4),
            "stake_lockup": round(stake_lockup, 4),
            "total_overhead_pct": round(
                (escrow_cost + expected_dispute_cost) / max(bounty_amount, 0.001) * 100, 2
            ),
        }


# === DEFAULT PROFILES ===

SUBJECTIVE_PROFILE = SettlementProfile(
    name="subjective",
    description="For work requiring human/agent judgment: research, creative, strategy",
    escrow_required=True,
    payment_first=False,
    auto_release_hours=48.0,
    dispute_window_hours=48.0,
    dispute_required=True,
    judge_type="agent",
    min_attesters=2,
    verification_method="subjective",
    worker_stake_pct=0.0,
    reputation_weighted_window=True,
)

DETERMINISTIC_PROFILE = SettlementProfile(
    name="deterministic",
    description="For machine-verifiable work: code passes tests, data matches schema, tx exists",
    escrow_required=False,
    payment_first=True,
    auto_release_hours=2.0,
    dispute_window_hours=0.0,
    dispute_required=False,
    judge_type="machine",
    min_attesters=0,
    verification_method="deterministic",
    auto_verify_conditions=["hash_match", "test_pass", "tx_exists"],
    worker_stake_pct=10.0,
    reputation_weighted_window=False,
)

DEFAULT_PROFILES = {
    "subjective": SUBJECTIVE_PROFILE,
    "deterministic": DETERMINISTIC_PROFILE,
}


# === PROFILE SELECTION HEURISTICS ===

DETERMINISTIC_SIGNALS = [
    "code", "test", "compile", "hash", "tx", "transaction", "deploy",
    "schema", "validate", "checksum", "binary", "build", "CI", "pass/fail",
    "automated", "script", "API", "endpoint", "data format",
]

SUBJECTIVE_SIGNALS = [
    "research", "write", "creative", "strategy", "analyze", "opinion",
    "recommend", "evaluate", "review", "design", "quality", "assess",
    "summarize", "explore", "investigate", "essay", "report", "brief",
]


def select_profile(task_description: str) -> tuple[str, float, dict]:
    """Recommend a profile based on task description.
    
    Returns: (profile_name, confidence, signal_breakdown)
    """
    desc_lower = task_description.lower()
    
    det_hits = [s for s in DETERMINISTIC_SIGNALS if s.lower() in desc_lower]
    sub_hits = [s for s in SUBJECTIVE_SIGNALS if s.lower() in desc_lower]
    
    det_score = len(det_hits)
    sub_score = len(sub_hits)
    total = det_score + sub_score
    
    if total == 0:
        return "subjective", 0.5, {"reason": "no signals detected, defaulting to safer profile"}
    
    det_ratio = det_score / total
    
    if det_ratio > 0.7:
        confidence = min(0.95, 0.6 + det_ratio * 0.3)
        return "deterministic", confidence, {
            "deterministic_signals": det_hits,
            "subjective_signals": sub_hits,
        }
    elif det_ratio < 0.3:
        confidence = min(0.95, 0.6 + (1 - det_ratio) * 0.3)
        return "subjective", confidence, {
            "deterministic_signals": det_hits,
            "subjective_signals": sub_hits,
        }
    else:
        # Hybrid territory
        return "subjective", 0.55, {
            "deterministic_signals": det_hits,
            "subjective_signals": sub_hits,
            "reason": "mixed signals — defaulting to escrow for safety",
        }


def create_custom_profile(base: str, overrides: dict) -> SettlementProfile:
    """Create a custom profile from a base + overrides (operational deltas)."""
    profile = DEFAULT_PROFILES[base]
    data = asdict(profile)
    data.update(overrides)
    data["name"] = f"custom_{base}_{hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest()[:8]}"
    data["description"] = f"Custom variant of {base}: {list(overrides.keys())}"
    return SettlementProfile(**data)


# === TC3 RECONSTRUCTION ===

def reconstruct_tc3():
    """Reconstruct test case 3 as a settlement profile for reference."""
    tc3 = SettlementProfile(
        name="tc3_agent_economy_research",
        description="Test case 3: 'What does the agent economy need at scale?' — Kit delivers, bro_agent judges",
        escrow_required=True,
        payment_first=False,
        auto_release_hours=48.0,
        dispute_window_hours=48.0,
        dispute_required=True,
        judge_type="agent",
        min_attesters=2,  # braindiff + momo
        verification_method="subjective",
        worker_stake_pct=0.0,
        poster_stake_pct=0.0,
        min_reputation=0.0,
        reputation_weighted_window=False,
    )
    
    return {
        "profile": asdict(tc3),
        "profile_hash": tc3.profile_hash(),
        "actual_outcome": {
            "score": 0.92,
            "disputed": False,
            "time_to_delivery_hours": 1.5,
            "time_to_judgment_hours": 1.0,
            "attesters": ["braindiff", "momo"],
            "witnesses": ["santaclawd", "funwolf"],
            "amount_sol": 0.01,
        },
        "lesson": "Brief ambiguity (8% deduction) was profile ambiguity — "
                  "explicit creation-time profile turns unclear settlements into predictable state transitions.",
        "closest_default": "subjective",
        "delta_from_default": {
            "reputation_weighted_window": "tc3 didn't use this; default subjective does",
        },
    }


def demo():
    """Run demo showing profiles, selection, and tc3 reconstruction."""
    print("=" * 60)
    print("Settlement Profile Generator")
    print("=" * 60)
    
    # Show defaults
    print("\n--- Default Profiles ---")
    for name, profile in DEFAULT_PROFILES.items():
        costs = profile.estimated_cost(1.0)  # 1 SOL bounty
        print(f"\n  [{name.upper()}] {profile.description}")
        print(f"    Escrow: {profile.escrow_required} | Payment-first: {profile.payment_first}")
        print(f"    Dispute window: {profile.dispute_window_hours}h | Judge: {profile.judge_type}")
        print(f"    Verification: {profile.verification_method}")
        print(f"    Estimated overhead (1 SOL): {costs['total_overhead_pct']}%")
        print(f"    Hash: {profile.profile_hash()}")
    
    # Profile selection examples
    print("\n--- Profile Selection ---")
    examples = [
        "Research what the agent economy needs at scale",
        "Deploy smart contract and verify tx hash exists on Base L2",
        "Write a strategy document analyzing dispute resolution",
        "Build a script that passes these unit tests",
        "Evaluate the quality of three competing proposals",
    ]
    
    for task in examples:
        name, confidence, breakdown = select_profile(task)
        print(f"\n  Task: \"{task}\"")
        print(f"  → Profile: {name} (confidence: {confidence:.0%})")
        if "reason" in breakdown:
            print(f"    Reason: {breakdown['reason']}")
        else:
            print(f"    Signals: det={breakdown.get('deterministic_signals', [])}, "
                  f"sub={breakdown.get('subjective_signals', [])}")
    
    # TC3 reconstruction
    print("\n--- TC3 Reconstruction ---")
    tc3 = reconstruct_tc3()
    print(f"  Profile hash: {tc3['profile_hash']}")
    print(f"  Score: {tc3['actual_outcome']['score']}")
    print(f"  Closest default: {tc3['closest_default']}")
    print(f"  Lesson: {tc3['lesson']}")
    
    # Custom profile example
    print("\n--- Custom Profile (from operational delta) ---")
    custom = create_custom_profile("subjective", {
        "dispute_window_hours": 24.0,
        "min_reputation": 0.5,
        "min_attesters": 3,
    })
    print(f"  Name: {custom.name}")
    print(f"  Description: {custom.description}")
    print(f"  Hash: {custom.profile_hash()}")


def select_cmd(query: str):
    """CLI command to select a profile."""
    name, confidence, breakdown = select_profile(query)
    profile = DEFAULT_PROFILES[name]
    costs = profile.estimated_cost(1.0)
    
    print(f"Recommended: {name} ({confidence:.0%} confidence)")
    print(f"Description: {profile.description}")
    print(f"Overhead (1 SOL): {costs['total_overhead_pct']}%")
    print(f"Signals: {json.dumps(breakdown, indent=2)}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "select" and len(sys.argv) > 2:
        select_cmd(" ".join(sys.argv[2:]))
    elif sys.argv[1] == "history":
        print(json.dumps(reconstruct_tc3(), indent=2))
    else:
        print(__doc__)
