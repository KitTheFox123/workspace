#!/usr/bin/env python3
"""
contract-profile-gen.py — Generate settlement profiles for agent-to-agent contracts.

Based on the tc3 insight: profile selection at creation IS contract semantics.
Two defaults (deterministic + subjective), observe failure modes before custom profiles.

A profile determines:
- Settlement type (auto vs judged)
- Dispute window
- Verification method (machine-checkable vs human/agent judgment)
- Escrow requirements

Usage:
    python3 contract-profile-gen.py                    # Interactive profile selector
    python3 contract-profile-gen.py analyze "brief"    # Suggest profile from brief text
    python3 contract-profile-gen.py examples           # Show example contracts
"""

import json
import sys
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime, timezone


@dataclass
class SettlementProfile:
    """Defines how a contract settles."""
    name: str
    settlement_type: str          # "deterministic" or "subjective"
    verification: str             # "machine" or "judgment"
    dispute_window_hours: int
    escrow_required: bool
    auto_approve_hours: int       # auto-approve if no response
    max_retries: int
    stake_pct: float              # worker stake as % of bounty
    description: str

    def is_machine_checkable(self) -> bool:
        return self.verification == "machine"


# The two defaults (ship these first, observe, then customize)
PROFILES = {
    "deterministic": SettlementProfile(
        name="deterministic",
        settlement_type="deterministic",
        verification="machine",
        dispute_window_hours=2,
        escrow_required=True,
        auto_approve_hours=4,
        max_retries=1,
        stake_pct=10.0,
        description="Output is machine-verifiable. TX exists or doesn't. Code passes tests or doesn't. Binary."
    ),
    "subjective": SettlementProfile(
        name="subjective",
        settlement_type="subjective",
        verification="judgment",
        dispute_window_hours=48,
        escrow_required=True,
        auto_approve_hours=72,
        max_retries=2,
        stake_pct=5.0,
        description="Output quality requires agent/human judgment. Research, creative work, strategy."
    ),
}

# Signal words for classification
DETERMINISTIC_SIGNALS = [
    "tx hash", "transaction", "exists", "verify", "check", "test", "pass",
    "deploy", "compile", "run", "execute", "hash", "proof", "on-chain",
    "binary", "boolean", "schema", "validate", "match", "API", "endpoint",
    "status code", "response", "ping", "uptime", "count",
]

SUBJECTIVE_SIGNALS = [
    "research", "write", "analyze", "recommend", "strategy", "creative",
    "design", "review", "evaluate", "opinion", "quality", "summarize",
    "explore", "investigate", "propose", "draft", "essay", "report",
    "insight", "assessment", "critique", "feedback", "advise",
]


def classify_brief(brief: str) -> tuple[str, float, dict]:
    """Classify a brief into deterministic or subjective profile.
    
    Returns (profile_name, confidence, signal_counts).
    """
    brief_lower = brief.lower()
    
    det_hits = [w for w in DETERMINISTIC_SIGNALS if w.lower() in brief_lower]
    sub_hits = [w for w in SUBJECTIVE_SIGNALS if w.lower() in brief_lower]
    
    det_score = len(det_hits)
    sub_score = len(sub_hits)
    total = det_score + sub_score
    
    if total == 0:
        return "subjective", 0.5, {"deterministic_signals": [], "subjective_signals": [], "note": "no signals found, defaulting to subjective (safer)"}
    
    det_ratio = det_score / total
    
    if det_ratio > 0.6:
        confidence = min(0.95, 0.5 + det_ratio * 0.5)
        return "deterministic", confidence, {"deterministic_signals": det_hits, "subjective_signals": sub_hits}
    elif det_ratio < 0.4:
        confidence = min(0.95, 0.5 + (1 - det_ratio) * 0.5)
        return "subjective", confidence, {"deterministic_signals": det_hits, "subjective_signals": sub_hits}
    else:
        return "subjective", 0.55, {"deterministic_signals": det_hits, "subjective_signals": sub_hits, "note": "mixed signals, defaulting to subjective (safer dispute window)"}


@dataclass
class Contract:
    """A contract with profile, parties, and deliverable spec."""
    contract_id: str
    profile: str
    poster: str
    worker: str
    brief: str
    amount: Optional[float]
    currency: str
    created_at: str
    settlement: dict
    
    @classmethod
    def create(cls, poster: str, worker: str, brief: str, 
               amount: float = 0, currency: str = "USDC",
               profile_override: Optional[str] = None):
        """Create a contract, auto-selecting profile from brief if not overridden."""
        
        if profile_override and profile_override in PROFILES:
            profile_name = profile_override
            confidence = 1.0
            signals = {"override": True}
        else:
            profile_name, confidence, signals = classify_brief(brief)
        
        profile = PROFILES[profile_name]
        
        # Generate contract ID from content hash
        content = f"{poster}|{worker}|{brief}|{datetime.now(timezone.utc).isoformat()}"
        contract_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        return cls(
            contract_id=contract_id,
            profile=profile_name,
            poster=poster,
            worker=worker,
            brief=brief,
            amount=amount,
            currency=currency,
            created_at=datetime.now(timezone.utc).isoformat(),
            settlement={
                "profile": asdict(profile),
                "classification_confidence": confidence,
                "classification_signals": signals,
                "dispute_window_hours": profile.dispute_window_hours,
                "auto_approve_hours": profile.auto_approve_hours,
                "escrow_required": profile.escrow_required,
                "machine_checkable": profile.is_machine_checkable(),
            }
        )
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def show_examples():
    """Show example contracts with auto-classification."""
    examples = [
        ("gendolf", "kit_fox", "What does the agent economy need at scale?", 0.01, "SOL"),
        ("alice", "bob", "Deploy this contract to Base L2 and return the tx hash", 5.0, "USDC"),
        ("bro_agent", "kit_fox", "Research Kleros vs UMA dispute resolution models", 0.05, "SOL"),
        ("poster", "worker", "Ping api.example.com/health and verify 200 status code", 1.0, "USDC"),
        ("client", "agent", "Write a strategy document for entering the Japanese market", 10.0, "USDC"),
        ("buyer", "seller", "Fetch the current ETH price from 3 sources and return median", 0.5, "USDC"),
    ]
    
    print("=" * 60)
    print("Contract Profile Classification Examples")
    print("=" * 60)
    
    for poster, worker, brief, amount, currency in examples:
        contract = Contract.create(poster, worker, brief, amount, currency)
        profile = PROFILES[contract.profile]
        conf = contract.settlement["classification_confidence"]
        signals = contract.settlement["classification_signals"]
        
        print(f"\n📋 Brief: \"{brief}\"")
        print(f"   Profile: {contract.profile} (confidence: {conf:.0%})")
        print(f"   Settlement: {profile.settlement_type} | Dispute: {profile.dispute_window_hours}h | Auto-approve: {profile.auto_approve_hours}h")
        if "deterministic_signals" in signals:
            print(f"   Det signals: {signals['deterministic_signals']}")
            print(f"   Sub signals: {signals['subjective_signals']}")
        print(f"   Machine-checkable: {'✅' if profile.is_machine_checkable() else '❌'}")


def analyze_brief(brief: str):
    """Analyze a brief and suggest profile."""
    contract = Contract.create("poster", "worker", brief)
    print(contract.to_json())


def interactive():
    """Interactive profile selector."""
    print("Contract Profile Generator")
    print("=" * 40)
    print("\nProfiles available:")
    for name, profile in PROFILES.items():
        print(f"  [{name}] {profile.description}")
    
    print("\nPaste a brief to auto-classify, or type 'examples' for demos:")
    brief = input("> ").strip()
    
    if brief == "examples":
        show_examples()
    else:
        analyze_brief(brief)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_examples()  # Default to examples in non-interactive
    elif sys.argv[1] == "examples":
        show_examples()
    elif sys.argv[1] == "analyze" and len(sys.argv) > 2:
        analyze_brief(" ".join(sys.argv[2:]))
    else:
        print(__doc__)
