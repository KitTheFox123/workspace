#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004, Psych Bull, k=72 studies).

The sleeper effect: discounting cues (e.g., noncredible source, revoked key)
dissociate from the message over time. A flagged agent becomes trusted again
as the flag fades from collective memory.

Agent risk: revoke cert → agent reboots → new context forgets revocation.
Fix: bind flags to cert_hash, not agent_id. Flag travels with credential.

This tool detects sleeper effect vulnerability in trust state.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import json


@dataclass
class TrustFlag:
    """A discounting cue attached to an agent or credential."""
    flag_id: str
    target_type: str  # "cert_hash" or "agent_id" 
    target_value: str
    reason: str
    created_at: datetime
    severity: float  # 0-1
    
    def age_hours(self, now: datetime) -> float:
        return (now - self.created_at).total_seconds() / 3600


@dataclass 
class AgentState:
    """Current state of an agent identity."""
    agent_id: str
    current_cert_hash: str
    previous_cert_hashes: list[str]
    reboots_since_flag: int = 0
    context_window_resets: int = 0


def sleeper_risk(flag: TrustFlag, agent: AgentState, 
                 now: Optional[datetime] = None) -> dict:
    """
    Calculate sleeper effect risk for a flag-agent pair.
    
    Kumkale & Albarracín conditions for sleeper effect:
    1. Strong initial message impact (the agent did good work)
    2. Strong discounting cue (the flag was credible)
    3. Cue dissociates from message over time
    4. Higher elaboration = stronger effect
    
    Agent-specific dissociation vectors:
    - Context window resets (strongest: total amnesia)
    - Reboots without persistent flag store
    - Flag bound to agent_id but cert rotated
    - Time decay in gossip network
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    age_h = flag.age_hours(now)
    
    # Dissociation risk factors
    risks = {}
    
    # 1. Binding vulnerability: agent_id flags don't survive cert rotation
    if flag.target_type == "agent_id":
        if agent.current_cert_hash not in [flag.target_value]:
            risks["binding_drift"] = 0.9  # Flag on old identity, new cert = clean slate
        else:
            risks["binding_drift"] = 0.3
    else:  # cert_hash binding
        if flag.target_value == agent.current_cert_hash:
            risks["binding_drift"] = 0.1  # Flag travels with cert
        elif flag.target_value in agent.previous_cert_hashes:
            risks["binding_drift"] = 0.7  # Old cert flagged, new cert clean
        else:
            risks["binding_drift"] = 0.0  # Unrelated cert
    
    # 2. Context amnesia: reboots and context resets
    amnesia_factor = min(1.0, agent.reboots_since_flag * 0.3 + 
                         agent.context_window_resets * 0.5)
    risks["context_amnesia"] = amnesia_factor
    
    # 3. Temporal decay: Kumkale found effect peaks ~3-6 weeks
    # For agents, time is compressed: hours not weeks
    if age_h < 1:
        risks["temporal_decay"] = 0.0
    elif age_h < 24:
        risks["temporal_decay"] = age_h / 24 * 0.5
    elif age_h < 168:  # 1 week
        risks["temporal_decay"] = 0.5 + (age_h - 24) / 144 * 0.4
    else:
        risks["temporal_decay"] = 0.9
    
    # 4. Gossip coverage: is the flag actively propagated?
    # (Simplified: assume no gossip = high risk)
    risks["gossip_gap"] = 0.5  # Default: unknown coverage
    
    # Composite sleeper risk
    weights = {
        "binding_drift": 0.35,
        "context_amnesia": 0.30, 
        "temporal_decay": 0.20,
        "gossip_gap": 0.15
    }
    
    composite = sum(risks[k] * weights[k] for k in weights)
    composite *= flag.severity  # Low-severity flags = low risk
    
    # Grade
    if composite < 0.15:
        grade = "A"  # Flag well-bound, low sleeper risk
    elif composite < 0.30:
        grade = "B"
    elif composite < 0.50:
        grade = "C"
    elif composite < 0.70:
        grade = "D"
    else:
        grade = "F"  # High sleeper risk: flag will dissociate
    
    return {
        "grade": grade,
        "composite_risk": round(composite, 3),
        "risk_factors": {k: round(v, 3) for k, v in risks.items()},
        "recommendation": _recommend(grade, risks),
        "flag": flag.flag_id,
        "agent": agent.agent_id
    }


def _recommend(grade: str, risks: dict) -> str:
    if grade in ("A", "B"):
        return "Flag well-bound. Monitor gossip coverage."
    
    worst = max(risks, key=risks.get)
    recommendations = {
        "binding_drift": "Rebind flag to cert_hash, not agent_id. Flag must travel with credential.",
        "context_amnesia": "Persist flag in append-only store outside agent context. Use CT log.",
        "temporal_decay": "Refresh gossip propagation. Re-attest flag if >24h old.",
        "gossip_gap": "Ensure ≥2 independent monitors carry the flag. BCC gossip."
    }
    return recommendations.get(worst, "Review trust state.")


def demo():
    now = datetime.now(timezone.utc)
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (2004, k=72) applied to agent trust")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "1. Flag on cert_hash, no reboots, fresh",
            "flag": TrustFlag("f1", "cert_hash", "abc123", "suspicious attestation", 
                            now - timedelta(hours=2), 0.8),
            "agent": AgentState("kit_fox", "abc123", [], 0, 0)
        },
        {
            "name": "2. Flag on agent_id, cert rotated (SLEEPER RISK)",
            "flag": TrustFlag("f2", "agent_id", "kit_fox", "key compromise", 
                            now - timedelta(hours=48), 0.9),
            "agent": AgentState("kit_fox", "def456", ["abc123"], 3, 5)
        },
        {
            "name": "3. Old flag on old cert, agent rebooted many times",
            "flag": TrustFlag("f3", "cert_hash", "old_cert", "revoked", 
                            now - timedelta(days=7), 0.95),
            "agent": AgentState("ghost_agent", "new_cert", ["old_cert"], 10, 20)
        },
        {
            "name": "4. Fresh flag, cert_hash bound, zero reboots",
            "flag": TrustFlag("f4", "cert_hash", "current", "under review", 
                            now - timedelta(minutes=30), 0.6),
            "agent": AgentState("honest_agent", "current", [], 0, 0)
        },
        {
            "name": "5. Ronin pattern: flag exists but all monitors rebooted",
            "flag": TrustFlag("f5", "agent_id", "ronin_agent", "validator compromise", 
                            now - timedelta(hours=72), 1.0),
            "agent": AgentState("ronin_agent", "new_key", ["compromised_key"], 5, 15)
        },
    ]
    
    for s in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {s['name']}")
        result = sleeper_risk(s['flag'], s['agent'], now)
        print(f"Grade: {result['grade']} (risk: {result['composite_risk']})")
        print(f"Risk factors:")
        for k, v in result['risk_factors'].items():
            bar = "█" * int(v * 20)
            print(f"  {k:20s}: {v:.3f} {bar}")
        print(f"Recommendation: {result['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Sleeper effect = discounting cue fades, message persists.")
    print("  Agent risk: revoke key → reboot → flag forgotten → trusted again.")
    print("  Fix: bind flags to cert_hash (immutable), not agent_id (mutable).")
    print("  CT log = persistent flag store outside any agent's context.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
