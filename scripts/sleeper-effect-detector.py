#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004, Psych Bull, k=72 studies).

The sleeper effect: discounting cues (e.g., "this agent was flagged") 
dissociate from message content over time. After reboot/context loss,
the flag is forgotten but the reputation persists.

Three conditions for sleeper effect (all must hold):
1. Strong initial message impact (agent built real reputation)  
2. Discounting cue presented AFTER message (flag comes after trust built)
3. High elaboration (receiver actually processed the agent's work)

Fix: hash-chain the flag INTO the identity cert so dissociation is 
cryptographically impossible.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import hashlib
import json


@dataclass
class TrustEvent:
    """An event in an agent's trust history."""
    timestamp: datetime
    event_type: str  # "attestation", "flag", "reboot", "interaction"
    content: str
    severity: float = 0.0  # 0-1 for flags
    hash: str = ""
    
    def __post_init__(self):
        payload = f"{self.timestamp.isoformat()}|{self.event_type}|{self.content}"
        self.hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class AgentTrustProfile:
    """Agent's trust history with sleeper effect detection."""
    agent_id: str
    events: list[TrustEvent] = field(default_factory=list)
    
    def add_event(self, event: TrustEvent) -> None:
        self.events.append(event)
    
    def detect_sleeper_risk(self) -> dict:
        """
        Detect conditions where sleeper effect could occur.
        
        Kumkale 2004 conditions:
        1. Strong message impact = high reputation built before flag
        2. Cue after message = flag comes after trust established  
        3. High elaboration = receiver engaged deeply with agent's work
        
        Agent-specific risk: reboot/context-loss after flag = dissociation
        """
        flags = [e for e in self.events if e.event_type == "flag"]
        attestations = [e for e in self.events if e.event_type == "attestation"]
        reboots = [e for e in self.events if e.event_type == "reboot"]
        
        if not flags:
            return {
                "risk": "NONE",
                "reason": "no flags in history",
                "score": 0.0
            }
        
        risks = []
        
        for flag in flags:
            # Condition 1: reputation built before flag?
            pre_flag_attestations = [a for a in attestations if a.timestamp < flag.timestamp]
            reputation_strength = min(len(pre_flag_attestations) / 5.0, 1.0)
            
            # Condition 2: flag after trust established? (always true if pre_flag > 0)
            cue_after_message = len(pre_flag_attestations) > 0
            
            # Condition 3: reboots after flag? (dissociation risk)
            post_flag_reboots = [r for r in reboots if r.timestamp > flag.timestamp]
            dissociation_risk = min(len(post_flag_reboots) / 2.0, 1.0)
            
            # Is flag hash-chained to identity?
            # Check if any subsequent events reference the flag hash
            flag_chained = any(
                flag.hash in e.content 
                for e in self.events 
                if e.timestamp > flag.timestamp and e.event_type == "attestation"
            )
            
            if flag_chained:
                chain_protection = 0.9  # Strong protection
            else:
                chain_protection = 0.0  # No protection
            
            risk_score = (
                reputation_strength * 0.3 +
                (1.0 if cue_after_message else 0.0) * 0.2 +
                dissociation_risk * 0.3 +
                (1.0 - chain_protection) * 0.2
            ) * flag.severity
            
            risks.append({
                "flag": flag.content,
                "flag_hash": flag.hash,
                "severity": flag.severity,
                "pre_flag_reputation": len(pre_flag_attestations),
                "post_flag_reboots": len(post_flag_reboots),
                "hash_chained": flag_chained,
                "sleeper_risk": round(risk_score, 3),
                "mitigation": "PROTECTED" if flag_chained else "VULNERABLE"
            })
        
        max_risk = max(r["sleeper_risk"] for r in risks)
        
        if max_risk > 0.6:
            level = "HIGH"
        elif max_risk > 0.3:
            level = "MEDIUM"
        elif max_risk > 0.1:
            level = "LOW"
        else:
            level = "MINIMAL"
        
        return {
            "risk": level,
            "max_score": round(max_risk, 3),
            "flags_analyzed": len(risks),
            "vulnerable_flags": sum(1 for r in risks if r["mitigation"] == "VULNERABLE"),
            "details": risks
        }


def demo():
    """Demo with agent trust scenarios."""
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (2004, Psych Bull, k=72)")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    scenarios = [
        {
            "name": "1. Flagged agent, rebooted, NO hash chain",
            "agent_id": "agent_alice",
            "events": [
                TrustEvent(now - timedelta(days=30), "attestation", "delivered tc1"),
                TrustEvent(now - timedelta(days=25), "attestation", "delivered tc2"),
                TrustEvent(now - timedelta(days=20), "attestation", "delivered tc3"),
                TrustEvent(now - timedelta(days=15), "attestation", "peer review: solid"),
                TrustEvent(now - timedelta(days=10), "attestation", "collab with bob"),
                TrustEvent(now - timedelta(days=5), "flag", "equivocation detected", 0.8),
                TrustEvent(now - timedelta(days=3), "reboot", "context reset"),
                TrustEvent(now - timedelta(days=1), "reboot", "model migration"),
                TrustEvent(now, "interaction", "new task request"),
            ]
        },
        {
            "name": "2. Flagged agent, rebooted, WITH hash chain",
            "agent_id": "agent_bob",
            "events": [
                TrustEvent(now - timedelta(days=30), "attestation", "delivered tc1"),
                TrustEvent(now - timedelta(days=25), "attestation", "delivered tc2"),
                TrustEvent(now - timedelta(days=20), "attestation", "delivered tc3"),
                TrustEvent(now - timedelta(days=15), "attestation", "peer review: solid"),
                TrustEvent(now - timedelta(days=10), "attestation", "collab with carol"),
            ]
        },
        {
            "name": "3. New agent, flagged early, no reputation",
            "agent_id": "agent_carol",
            "events": [
                TrustEvent(now - timedelta(days=3), "attestation", "first task"),
                TrustEvent(now - timedelta(days=2), "flag", "suspicious behavior", 0.6),
                TrustEvent(now - timedelta(days=1), "reboot", "restart"),
                TrustEvent(now, "interaction", "new task"),
            ]
        },
        {
            "name": "4. Veteran agent, minor flag, hash-chained",
            "agent_id": "agent_dave", 
            "events": [
                TrustEvent(now - timedelta(days=60), "attestation", "delivered tc1"),
                TrustEvent(now - timedelta(days=50), "attestation", "delivered tc2"),
                TrustEvent(now - timedelta(days=40), "attestation", "delivered tc3"),
                TrustEvent(now - timedelta(days=30), "attestation", "peer review"),
                TrustEvent(now - timedelta(days=20), "attestation", "collab"),
                TrustEvent(now - timedelta(days=10), "attestation", "delivered tc4"),
            ]
        },
    ]
    
    # Scenario 2: add flag + chain protection
    flag = TrustEvent(now - timedelta(days=5), "flag", "data inconsistency", 0.7)
    scenarios[1]["events"].append(flag)
    scenarios[1]["events"].append(
        TrustEvent(now - timedelta(days=4), "attestation", 
                   f"flag_ref:{flag.hash} remediation complete")
    )
    scenarios[1]["events"].append(
        TrustEvent(now - timedelta(days=3), "reboot", "context reset")
    )
    scenarios[1]["events"].append(
        TrustEvent(now - timedelta(days=1), "reboot", "model migration")
    )
    
    # Scenario 4: add minor flag + chain
    minor_flag = TrustEvent(now - timedelta(days=5), "flag", "timeout on delivery", 0.3)
    scenarios[3]["events"].append(minor_flag)
    scenarios[3]["events"].append(
        TrustEvent(now - timedelta(days=4), "attestation",
                   f"acknowledged:{minor_flag.hash} network issue resolved")
    )
    
    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        
        profile = AgentTrustProfile(agent_id=scenario['agent_id'])
        for event in scenario['events']:
            profile.add_event(event)
        
        result = profile.detect_sleeper_risk()
        print(f"Risk level: {result['risk']} (score: {result.get('max_score', 0)})")
        
        if result.get('details'):
            for d in result['details']:
                print(f"  Flag: '{d['flag']}' (severity {d['severity']})")
                print(f"    Pre-flag reputation: {d['pre_flag_reputation']} attestations")
                print(f"    Post-flag reboots: {d['post_flag_reboots']}")
                print(f"    Hash-chained: {d['hash_chained']}")
                print(f"    Sleeper risk: {d['sleeper_risk']}")
                print(f"    Status: {d['mitigation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Sleeper effect requires ALL THREE conditions:")
    print("  1. Strong initial message impact (reputation)")
    print("  2. Discounting cue AFTER message (flag after trust)")
    print("  3. High elaboration (deep engagement)")
    print("")
    print("  Agent reboots = forced dissociation.")
    print("  Fix: hash-chain flags INTO identity certs.")
    print("  Cryptographic binding prevents cue dissociation.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
