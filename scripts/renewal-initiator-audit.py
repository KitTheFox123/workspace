#!/usr/bin/env python3
"""renewal-initiator-audit.py — Audit who controls the renewal trigger.

Santaclawd's insight: "the subject should not initiate their own audit."
ACME model: client initiates, CA validates. Initiator ≠ authority.

Three renewal models:
  1. Agent-initiated (Münchhausen risk — defendant schedules own trial)
  2. Relying-party initiated (strongest but coordination cost)
  3. Protocol-triggered (TTL expiry fires externally — our model)

Usage:
    python3 renewal-initiator-audit.py [--demo] [--audit]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List


@dataclass
class RenewalModel:
    name: str
    initiator: str
    authority: str
    munchhausen_risk: str  # none/low/high
    coordination_cost: str  # none/low/medium/high
    availability_risk: str  # none/low/medium/high
    grade: str
    description: str
    real_world_analog: str


MODELS = [
    RenewalModel(
        name="agent_initiated",
        initiator="agent",
        authority="agent",
        munchhausen_risk="high",
        coordination_cost="none",
        availability_risk="none",
        grade="F",
        description="Agent requests own re-attestation. Defendant schedules trial.",
        real_world_analog="Self-audit (pre-SOX Enron)"
    ),
    RenewalModel(
        name="agent_requests_ca_validates",
        initiator="agent",
        authority="CA/platform",
        munchhausen_risk="low",
        coordination_cost="low",
        availability_risk="low",
        grade="B",
        description="Agent initiates but platform demands fresh proof. ACME model.",
        real_world_analog="Let's Encrypt ACME (client requests, CA validates domain)"
    ),
    RenewalModel(
        name="relying_party_initiated",
        initiator="relying_party",
        authority="relying_party",
        munchhausen_risk="none",
        coordination_cost="high",
        availability_risk="medium",
        grade="A",
        description="Relying party demands fresh attestation before trusting.",
        real_world_analog="SOX 302 (auditor demands CEO certification)"
    ),
    RenewalModel(
        name="protocol_triggered",
        initiator="protocol",
        authority="TTL_expiry",
        munchhausen_risk="none",
        coordination_cost="none",
        availability_risk="low",
        grade="A",
        description="TTL expires automatically. No renewal = no authority. Clock is external.",
        real_world_analog="Short-lived TLS certs (CA/B Forum 47-day)"
    ),
    RenewalModel(
        name="independent_scheduler",
        initiator="third_party",
        authority="third_party",
        munchhausen_risk="none",
        coordination_cost="medium",
        availability_risk="low",
        grade="A-",
        description="Independent scheduler triggers re-attestation at random intervals.",
        real_world_analog="Athenian sortition (random selection of auditors)"
    ),
]


def audit_current_setup() -> dict:
    """Audit current heartbeat renewal model."""
    # Check HEARTBEAT.md for renewal pattern
    heartbeat_path = "/home/yallen/.openclaw/workspace/HEARTBEAT.md"
    try:
        with open(heartbeat_path) as f:
            content = f.read()
    except FileNotFoundError:
        content = ""
    
    signals = {
        "has_ttl": "TTL" in content or "expir" in content.lower(),
        "has_external_trigger": "heartbeat" in content.lower() or "cron" in content.lower(),
        "has_self_initiation": "self" in content.lower() and "renewal" in content.lower(),
        "has_protocol_trigger": "HEARTBEAT_OK" in content,
    }
    
    # Classify current model
    if signals["has_protocol_trigger"] and signals["has_external_trigger"]:
        current = "protocol_triggered"
        notes = "Heartbeat poll is externally triggered (cron/platform). TTL = heartbeat interval."
    elif signals["has_self_initiation"]:
        current = "agent_initiated"
        notes = "Agent controls renewal timing. Münchhausen risk."
    else:
        current = "agent_requests_ca_validates"
        notes = "Mixed model — agent responds to external prompt but controls content."
    
    model = next(m for m in MODELS if m.name == current)
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_model": asdict(model),
        "signals": signals,
        "notes": notes,
        "recommendation": "Protocol-triggered (TTL expiry) is the strongest model. "
                         "Current heartbeat = externally triggered poll, which is close. "
                         "Gap: no signed TTL on scope-cert, so expiry isn't cryptographically enforced."
    }


def demo():
    """Show all renewal models."""
    print("=" * 60)
    print("RENEWAL INITIATOR AUDIT")
    print("Who controls the clock?")
    print("=" * 60)
    print()
    
    for m in MODELS:
        risk_emoji = {"none": "✅", "low": "⚠️", "medium": "🟡", "high": "🔴"}
        print(f"[{m.grade}] {m.name}")
        print(f"    Initiator: {m.initiator} → Authority: {m.authority}")
        print(f"    Münchhausen: {risk_emoji.get(m.munchhausen_risk, '?')} {m.munchhausen_risk}")
        print(f"    Coordination: {m.coordination_cost} | Availability: {m.availability_risk}")
        print(f"    Analog: {m.real_world_analog}")
        print()
    
    print("-" * 60)
    print("KEY INSIGHT: Initiator ≠ Authority.")
    print("ACME: client requests, CA validates. Agent requests, platform proves.")
    print("TTL: clock is external. No renewal = silent revocation.")
    
    # Audit current
    print()
    print("=" * 60)
    print("CURRENT SETUP AUDIT")
    print("=" * 60)
    audit = audit_current_setup()
    print(f"  Model: {audit['current_model']['name']} (Grade {audit['current_model']['grade']})")
    print(f"  Notes: {audit['notes']}")
    print(f"  Recommendation: {audit['recommendation']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Renewal initiator audit")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.audit:
        result = audit_current_setup()
        print(json.dumps(result, indent=2))
    elif args.json:
        print(json.dumps([asdict(m) for m in MODELS], indent=2))
    else:
        demo()
