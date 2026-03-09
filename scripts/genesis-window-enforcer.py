#!/usr/bin/env python3
"""genesis-window-enforcer.py — Zero pre-attestation window enforcement.

Inspired by Google Titan's first-instruction integrity: hold CPU in reset
until firmware is cryptographically verified. Agent equivalent: no capabilities
until principal signs scope-commit.

Detects and grades the genesis window (time between instantiation and first
external attestation). Goal: zero window.

Usage:
    python3 genesis-window-enforcer.py [--demo]
"""

import argparse
import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional


@dataclass 
class GenesisEvent:
    """An event during the genesis window."""
    timestamp: str
    event_type: str  # instantiation, action, scope_commit, first_attestation
    description: str
    signed_by: Optional[str] = None


@dataclass
class GenesisAudit:
    """Audit result for a genesis window."""
    agent_id: str
    instantiation_time: str
    first_attestation_time: Optional[str]
    window_seconds: float
    pre_attestation_actions: int
    scope_committed_before_action: bool
    grade: str  # A-F
    titan_compliant: bool  # Zero pre-verified window?
    events: List[dict]
    recommendation: str


def grade_window(window_seconds: float, pre_actions: int, scope_first: bool) -> tuple:
    """Grade the genesis window. A = Titan-compliant (zero window)."""
    if pre_actions == 0 and scope_first:
        return "A", True, "Titan-compliant: zero pre-attestation actions."
    elif pre_actions == 0:
        return "B", False, "No pre-attestation actions but scope not committed first."
    elif window_seconds < 60 and pre_actions <= 2:
        return "C", False, f"Small window ({window_seconds:.0f}s, {pre_actions} actions). Reduce to zero."
    elif window_seconds < 300:
        return "D", False, f"Dangerous window ({window_seconds:.0f}s, {pre_actions} actions). Capabilities accumulated before attestation."
    else:
        return "F", False, f"Critical window ({window_seconds:.0f}s, {pre_actions} actions). Agent operated unverified for {window_seconds/60:.1f} minutes."


def audit_genesis(agent_id: str, events: List[GenesisEvent]) -> GenesisAudit:
    """Audit an agent's genesis window."""
    instantiation = None
    first_attestation = None
    pre_attestation_actions = 0
    scope_committed_before_action = False
    seen_action = False
    
    for e in events:
        if e.event_type == "instantiation":
            instantiation = e.timestamp
        elif e.event_type == "scope_commit" and not seen_action:
            scope_committed_before_action = True
        elif e.event_type == "action":
            seen_action = True
            if first_attestation is None:
                pre_attestation_actions += 1
        elif e.event_type == "first_attestation":
            first_attestation = e.timestamp
    
    if instantiation and first_attestation:
        t0 = datetime.fromisoformat(instantiation.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(first_attestation.replace("Z", "+00:00"))
        window = (t1 - t0).total_seconds()
    else:
        window = float('inf')
    
    grade, titan, rec = grade_window(window, pre_attestation_actions, scope_committed_before_action)
    
    return GenesisAudit(
        agent_id=agent_id,
        instantiation_time=instantiation,
        first_attestation_time=first_attestation,
        window_seconds=window,
        pre_attestation_actions=pre_attestation_actions,
        scope_committed_before_action=scope_committed_before_action,
        grade=grade,
        titan_compliant=titan,
        events=[asdict(e) for e in events],
        recommendation=rec
    )


def demo():
    """Demo with 3 scenarios."""
    now = datetime.now(timezone.utc)
    
    scenarios = [
        ("titan_agent", [
            GenesisEvent((now).isoformat(), "instantiation", "Agent created"),
            GenesisEvent((now + timedelta(seconds=1)).isoformat(), "scope_commit", "Principal signs scope", "ilya"),
            GenesisEvent((now + timedelta(seconds=2)).isoformat(), "first_attestation", "External witness attests", "witness_1"),
            GenesisEvent((now + timedelta(seconds=3)).isoformat(), "action", "First action (post-attestation)"),
        ]),
        ("lazy_agent", [
            GenesisEvent((now).isoformat(), "instantiation", "Agent created"),
            GenesisEvent((now + timedelta(seconds=5)).isoformat(), "action", "Action before attestation"),
            GenesisEvent((now + timedelta(seconds=10)).isoformat(), "action", "Another action before attestation"),
            GenesisEvent((now + timedelta(seconds=30)).isoformat(), "scope_commit", "Late scope commit", "principal"),
            GenesisEvent((now + timedelta(seconds=45)).isoformat(), "first_attestation", "External attestation", "witness_1"),
        ]),
        ("rogue_agent", [
            GenesisEvent((now).isoformat(), "instantiation", "Agent created"),
            GenesisEvent((now + timedelta(seconds=10)).isoformat(), "action", "Read sensitive data"),
            GenesisEvent((now + timedelta(seconds=20)).isoformat(), "action", "Write to external API"),
            GenesisEvent((now + timedelta(seconds=30)).isoformat(), "action", "Modify scope file"),
            GenesisEvent((now + timedelta(seconds=60)).isoformat(), "action", "Install package"),
            GenesisEvent((now + timedelta(seconds=120)).isoformat(), "action", "Send email"),
            GenesisEvent((now + timedelta(minutes=10)).isoformat(), "first_attestation", "Finally attested", "witness_1"),
        ]),
    ]
    
    print("=" * 60)
    print("GENESIS WINDOW ENFORCEMENT AUDIT")
    print("(Inspired by Google Titan first-instruction integrity)")
    print("=" * 60)
    
    for agent_id, events in scenarios:
        result = audit_genesis(agent_id, events)
        print(f"\n[{result.grade}] {agent_id}")
        print(f"    Window: {result.window_seconds:.0f}s")
        print(f"    Pre-attestation actions: {result.pre_attestation_actions}")
        print(f"    Scope before action: {result.scope_committed_before_action}")
        print(f"    Titan-compliant: {result.titan_compliant}")
        print(f"    → {result.recommendation}")
    
    print("\n" + "-" * 60)
    print("Key insight: Google Titan holds CPU in reset until firmware")
    print("is verified. Agents should have ZERO capabilities before")
    print("scope-commit is signed by principal. Pre-attestation")
    print("actions = the most dangerous interval in trust lifecycle.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
