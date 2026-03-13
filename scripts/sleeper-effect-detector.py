#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004) meta-analysis and Hovland et al (1949).

The sleeper effect: discounting cue (e.g., "source is untrustworthy") 
dissociates from message content over time → initially discounted 
message becomes MORE persuasive later.

Agent threat model:
- Agent gets flagged (discounting cue)
- Agent reboots / changes context
- Flag dissociates from identity
- Verifiers trust the agent again despite the flag

Fix: cryptographic binding (Merkle inclusion) prevents dissociation.

This detector monitors for dissociation risk across trust events.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import hashlib
import json


@dataclass 
class TrustEvent:
    """An event in an agent's trust lifecycle."""
    agent_id: str
    event_type: str  # "flag", "attestation", "reboot", "cert_update", "verification"
    timestamp: datetime
    content_hash: str  # hash of the event content
    binding: str = "none"  # "merkle" | "gossip" | "self_reported" | "none"
    
    @property
    def age_hours(self) -> float:
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds() / 3600


@dataclass
class DissociationRisk:
    """Kumkale 2004: dissociation likelihood based on time + binding."""
    
    @staticmethod
    def score(flag_event: TrustEvent, current_time: datetime) -> dict:
        """
        Score dissociation risk for a flag event.
        
        Kumkale 2004 key findings:
        - Strong initial impact + discounting cue after message → highest sleeper effect
        - Dissociation increases with time
        - Higher ability/motivation to process → stronger sleeper effect
        
        Agent mapping:
        - Time since flag → dissociation risk increases
        - Binding type → prevents or enables dissociation
        - Reboots between flag and now → context loss = forced dissociation
        """
        hours_since = (current_time - flag_event.timestamp).total_seconds() / 3600
        
        # Time-based dissociation (Hovland's differential decay)
        # Flag memory decays faster than content memory
        if hours_since < 1:
            time_risk = 0.1  # Recent — flag still salient
        elif hours_since < 6:
            time_risk = 0.3  # Short-term — starting to dissociate
        elif hours_since < 24:
            time_risk = 0.6  # Medium — significant dissociation risk
        elif hours_since < 72:
            time_risk = 0.8  # Days — high risk
        else:
            time_risk = 0.95  # Weeks — near-certain dissociation
        
        # Binding prevents dissociation
        binding_protection = {
            "merkle": 0.95,       # Cryptographic — near-impossible to dissociate
            "gossip": 0.60,       # Distributed but not cryptographic
            "self_reported": 0.10, # Trivially dissociable
            "none": 0.0,          # No binding — maximum risk
        }
        
        protection = binding_protection.get(flag_event.binding, 0.0)
        
        # Net risk = time risk * (1 - protection)
        net_risk = time_risk * (1 - protection)
        
        # Grade
        if net_risk < 0.1:
            grade = "A"  # Flag bound — dissociation blocked
        elif net_risk < 0.3:
            grade = "B"  # Low risk
        elif net_risk < 0.5:
            grade = "C"  # Moderate — investigate
        elif net_risk < 0.7:
            grade = "D"  # High — flag may have dissociated
        else:
            grade = "F"  # Critical — sleeper effect likely active
        
        return {
            "agent_id": flag_event.agent_id,
            "hours_since_flag": round(hours_since, 1),
            "time_risk": round(time_risk, 2),
            "binding": flag_event.binding,
            "binding_protection": round(protection, 2),
            "net_dissociation_risk": round(net_risk, 3),
            "grade": grade,
            "sleeper_effect_active": net_risk > 0.5,
        }


def detect_reboot_dissociation(events: list[TrustEvent]) -> list[dict]:
    """
    Detect forced dissociation through reboots.
    
    Agent reboot = context window reset = all in-memory flags lost.
    Only persisted bindings survive.
    """
    flags = [e for e in events if e.event_type == "flag"]
    reboots = [e for e in events if e.event_type == "reboot"]
    verifications = [e for e in events if e.event_type == "verification"]
    
    alerts = []
    for flag in flags:
        # Check if reboot happened after flag
        post_flag_reboots = [r for r in reboots if r.timestamp > flag.timestamp]
        
        if post_flag_reboots and flag.binding not in ("merkle",):
            # Flag likely lost through reboot
            post_reboot_verifications = [
                v for v in verifications 
                if v.timestamp > post_flag_reboots[-1].timestamp
                and v.agent_id == flag.agent_id
            ]
            
            if post_reboot_verifications:
                alerts.append({
                    "type": "REBOOT_DISSOCIATION",
                    "agent_id": flag.agent_id,
                    "flag_time": flag.timestamp.isoformat(),
                    "reboot_time": post_flag_reboots[-1].timestamp.isoformat(),
                    "binding": flag.binding,
                    "verified_post_reboot": len(post_reboot_verifications),
                    "severity": "CRITICAL" if flag.binding == "none" else "WARNING",
                    "recommendation": "Rebind flag via Merkle inclusion"
                })
    
    return alerts


def demo():
    """Demo with agent trust scenarios."""
    
    now = datetime.now(timezone.utc)
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (2004) + Hovland (1949)")
    print("=" * 60)
    
    # Scenario 1: Merkle-bound flag (protected)
    print("\n--- Scenario 1: Merkle-bound flag (72h old) ---")
    flag1 = TrustEvent("agent_alpha", "flag", now - timedelta(hours=72), 
                       "abc123", binding="merkle")
    result = DissociationRisk.score(flag1, now)
    print(f"Grade: {result['grade']} | Risk: {result['net_dissociation_risk']}")
    print(f"Time risk: {result['time_risk']} × (1 - {result['binding_protection']}) = {result['net_dissociation_risk']}")
    print(f"Sleeper effect active: {result['sleeper_effect_active']}")
    
    # Scenario 2: Gossip-only flag (partial protection)
    print("\n--- Scenario 2: Gossip-only flag (24h old) ---")
    flag2 = TrustEvent("agent_beta", "flag", now - timedelta(hours=24),
                       "def456", binding="gossip")
    result = DissociationRisk.score(flag2, now)
    print(f"Grade: {result['grade']} | Risk: {result['net_dissociation_risk']}")
    print(f"Sleeper effect active: {result['sleeper_effect_active']}")
    
    # Scenario 3: Self-reported flag (minimal protection)
    print("\n--- Scenario 3: Self-reported flag (6h old) ---")
    flag3 = TrustEvent("agent_gamma", "flag", now - timedelta(hours=6),
                       "ghi789", binding="self_reported")
    result = DissociationRisk.score(flag3, now)
    print(f"Grade: {result['grade']} | Risk: {result['net_dissociation_risk']}")
    print(f"Sleeper effect active: {result['sleeper_effect_active']}")
    
    # Scenario 4: Unbound flag (maximum risk)
    print("\n--- Scenario 4: Unbound flag (48h old) ---")
    flag4 = TrustEvent("agent_delta", "flag", now - timedelta(hours=48),
                       "jkl012", binding="none")
    result = DissociationRisk.score(flag4, now)
    print(f"Grade: {result['grade']} | Risk: {result['net_dissociation_risk']}")
    print(f"Sleeper effect active: {result['sleeper_effect_active']}")
    
    # Scenario 5: Reboot dissociation detection
    print("\n--- Scenario 5: Reboot dissociation ---")
    events = [
        TrustEvent("agent_epsilon", "flag", now - timedelta(hours=12), "flag_hash", binding="gossip"),
        TrustEvent("agent_epsilon", "reboot", now - timedelta(hours=6), "reboot_hash"),
        TrustEvent("agent_epsilon", "verification", now - timedelta(hours=1), "verify_hash"),
    ]
    alerts = detect_reboot_dissociation(events)
    for alert in alerts:
        print(f"  ALERT: {alert['type']} | Severity: {alert['severity']}")
        print(f"  Agent: {alert['agent_id']} | Binding: {alert['binding']}")
        print(f"  Verified {alert['verified_post_reboot']}x after reboot")
        print(f"  → {alert['recommendation']}")
    
    # Scenario 6: Merkle-bound survives reboot
    print("\n--- Scenario 6: Merkle-bound flag survives reboot ---")
    events2 = [
        TrustEvent("agent_zeta", "flag", now - timedelta(hours=12), "flag_hash", binding="merkle"),
        TrustEvent("agent_zeta", "reboot", now - timedelta(hours=6), "reboot_hash"),
        TrustEvent("agent_zeta", "verification", now - timedelta(hours=1), "verify_hash"),
    ]
    alerts2 = detect_reboot_dissociation(events2)
    if not alerts2:
        print("  ✓ No alerts — Merkle binding survives reboot")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004 meta-analysis):")
    print("  Sleeper effect requires:")
    print("    1. Strong initial message impact")
    print("    2. Discounting cue presented AFTER message")
    print("    3. High processing motivation")
    print("    4. Time for dissociation to occur")
    print("")
    print("  Agent fix: Merkle inclusion binds flag to identity.")
    print("  Dissociation = cryptographically impossible.")
    print("  Gossip = partial (survives reboot? depends on peers).")
    print("  Self-reported = useless (agent controls own flags).")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
