#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004) meta-analysis (Psychological Bulletin).

The sleeper effect: discounting cues (e.g., "this source is unreliable")
dissociate from messages over time, causing persuasion to INCREASE.

Agent vulnerability: reboots force cue dissociation.
- Agent flagged as compromised at t=0
- Agent reboots at t=1, flag stored in session memory (lost)
- At t=2, other agents see the message ("I'm trustworthy") without the cue
- Trust increases AFTER the flag should have prevented it

Fix: bind discounting cues to identity chains, not session state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import json


@dataclass
class DiscountingCue:
    """A flag/warning associated with an agent's identity"""
    agent_id: str
    cue_type: str  # "compromised_key", "failed_audit", "equivocation", "suspension"
    created_at: datetime
    severity: float  # 0-1
    stored_in: str  # "session" | "chain" | "both"
    
    def survives_reboot(self) -> bool:
        return self.stored_in in ("chain", "both")
    
    def dissociation_risk(self, hours_elapsed: float) -> float:
        """
        Kumkale 2004: dissociation increases with delay.
        Session-stored cues dissociate immediately on reboot.
        Chain-stored cues persist but may be ignored.
        """
        if self.stored_in == "session":
            # Reboot at any point = total dissociation
            return 1.0 if hours_elapsed > 0 else 0.0
        elif self.stored_in == "chain":
            # Chain cues persist but receivers may not check
            # Decay follows ~log curve (Kumkale Fig 2)
            import math
            return min(0.3 * math.log1p(hours_elapsed / 24), 0.8)
        else:  # both
            return min(0.1 * (hours_elapsed / 24) ** 0.5, 0.5)


@dataclass
class AgentTrustState:
    agent_id: str
    current_trust: float = 0.5
    cues: list[DiscountingCue] = field(default_factory=list)
    reboots: int = 0
    last_reboot: Optional[datetime] = None
    
    def effective_trust(self, now: datetime) -> dict:
        """Calculate trust accounting for sleeper effect risk."""
        
        naive_trust = self.current_trust
        
        active_cues = []
        dissociated_cues = []
        
        for cue in self.cues:
            hours = (now - cue.created_at).total_seconds() / 3600
            risk = cue.dissociation_risk(hours)
            
            if risk > 0.5:
                dissociated_cues.append({
                    "type": cue.cue_type,
                    "risk": round(risk, 3),
                    "stored_in": cue.stored_in,
                    "hours_ago": round(hours, 1),
                    "survives_reboot": cue.survives_reboot()
                })
            else:
                active_cues.append({
                    "type": cue.cue_type,
                    "discount": round(cue.severity * (1 - risk), 3),
                    "stored_in": cue.stored_in
                })
        
        # Apply active cue discounts
        total_discount = sum(c["discount"] for c in active_cues)
        adjusted_trust = naive_trust * max(0, 1 - total_discount)
        
        # Sleeper effect warning
        sleeper_risk = len(dissociated_cues) / max(len(self.cues), 1) if self.cues else 0
        
        # Reboot amplification
        if self.reboots > 0 and any(not c.survives_reboot() for c in self.cues):
            reboot_amnesia = sum(1 for c in self.cues if not c.survives_reboot())
            sleeper_risk = min(sleeper_risk + 0.2 * reboot_amnesia, 1.0)
        
        # Grade
        if sleeper_risk > 0.7:
            grade = "F"
            status = "SLEEPER_ACTIVE"
        elif sleeper_risk > 0.4:
            grade = "D"
            status = "SLEEPER_RISK"
        elif sleeper_risk > 0.1:
            grade = "C"
            status = "MONITORING"
        elif len(active_cues) > 0:
            grade = "B"
            status = "CUES_ACTIVE"
        else:
            grade = "A"
            status = "CLEAN"
        
        return {
            "agent_id": self.agent_id,
            "naive_trust": round(naive_trust, 3),
            "adjusted_trust": round(adjusted_trust, 3),
            "sleeper_risk": round(sleeper_risk, 3),
            "grade": grade,
            "status": status,
            "active_cues": active_cues,
            "dissociated_cues": dissociated_cues,
            "reboots": self.reboots,
            "recommendation": self._recommend(status, dissociated_cues)
        }
    
    def _recommend(self, status: str, dissociated: list) -> str:
        if status == "SLEEPER_ACTIVE":
            session_cues = [c for c in dissociated if c["stored_in"] == "session"]
            if session_cues:
                return "CRITICAL: Session-stored cues lost after reboot. Migrate to chain storage."
            return "WARNING: Cues dissociating over time. Re-verify or re-flag."
        elif status == "SLEEPER_RISK":
            return "Monitor: cues weakening. Consider refreshing attestations."
        elif status == "CUES_ACTIVE":
            return "Healthy: discounting cues bound and active."
        return "Clean: no active concerns."


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (2004, Psychological Bulletin)")
    print("=" * 60)
    
    now = datetime(2026, 3, 13, 9, 0, tzinfo=timezone.utc)
    
    scenarios = [
        {
            "name": "1. Session-stored flag + reboot (VULNERABLE)",
            "agent": AgentTrustState(
                agent_id="agent_alpha",
                current_trust=0.7,
                reboots=1,
                last_reboot=now - timedelta(hours=2),
                cues=[
                    DiscountingCue("agent_alpha", "compromised_key", 
                                   now - timedelta(hours=6), 0.8, "session"),
                    DiscountingCue("agent_alpha", "failed_audit",
                                   now - timedelta(hours=4), 0.6, "session"),
                ]
            )
        },
        {
            "name": "2. Chain-stored flags (RESILIENT)",
            "agent": AgentTrustState(
                agent_id="agent_beta",
                current_trust=0.7,
                reboots=3,
                cues=[
                    DiscountingCue("agent_beta", "compromised_key",
                                   now - timedelta(hours=6), 0.8, "chain"),
                    DiscountingCue("agent_beta", "equivocation",
                                   now - timedelta(hours=2), 0.7, "chain"),
                ]
            )
        },
        {
            "name": "3. Mixed storage (PARTIAL RISK)",
            "agent": AgentTrustState(
                agent_id="agent_gamma",
                current_trust=0.6,
                reboots=1,
                cues=[
                    DiscountingCue("agent_gamma", "suspension",
                                   now - timedelta(hours=24), 0.9, "chain"),
                    DiscountingCue("agent_gamma", "failed_audit",
                                   now - timedelta(hours=1), 0.5, "session"),
                ]
            )
        },
        {
            "name": "4. Stale chain cue (TIME DECAY)",
            "agent": AgentTrustState(
                agent_id="agent_delta",
                current_trust=0.8,
                reboots=0,
                cues=[
                    DiscountingCue("agent_delta", "compromised_key",
                                   now - timedelta(days=30), 0.9, "chain"),
                ]
            )
        },
        {
            "name": "5. Clean agent (NO CUES)",
            "agent": AgentTrustState(
                agent_id="agent_epsilon",
                current_trust=0.9,
                reboots=5,
                cues=[]
            )
        },
    ]
    
    for s in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {s['name']}")
        result = s["agent"].effective_trust(now)
        print(f"  Naive trust: {result['naive_trust']}")
        print(f"  Adjusted trust: {result['adjusted_trust']}")
        print(f"  Sleeper risk: {result['sleeper_risk']}")
        print(f"  Grade: {result['grade']} ({result['status']})")
        print(f"  Reboots: {result['reboots']}")
        if result['active_cues']:
            print(f"  Active cues: {json.dumps(result['active_cues'], indent=4)}")
        if result['dissociated_cues']:
            print(f"  ⚠️ Dissociated: {json.dumps(result['dissociated_cues'], indent=4)}")
        print(f"  → {result['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Discounting cues dissociate from messages over time.")
    print("  Agent reboots FORCE dissociation (session amnesia).")
    print("  Chain-stored cues persist but still decay (~log curve).")
    print("  Fix: isnad chain = persistent discounting cue binding.")
    print("  Periodic re-attestation refreshes the cue-message bond.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
