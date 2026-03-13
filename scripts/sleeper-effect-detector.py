#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004, Psychological Bulletin, k=72):
- Discounting cue (e.g., "key flagged") fades from memory over time
- Message (e.g., "agent is trustworthy") persists
- Net effect: trust INCREASES after initial flagging as the flag is forgotten

Agent-specific risk:
- Context window = bounded memory → flags get evicted
- Reboot = amnesia → discounting cues lost
- Identity reset = sleeper effect by design

Fix: store flags in append-only chain, not in ephemeral context.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import json


@dataclass
class TrustFlag:
    """A discounting cue attached to an agent identity."""
    agent_id: str
    flag_type: str  # "key_compromise", "attestation_failure", "behavior_anomaly"
    severity: float  # 0-1
    created_at: datetime
    source: str  # who flagged
    in_chain: bool = False  # stored in append-only chain?
    in_context: bool = True  # still in agent's context window?


@dataclass  
class AgentTrustState:
    agent_id: str
    base_trust: float = 0.7
    flags: list[TrustFlag] = field(default_factory=list)
    context_window_hours: float = 24.0  # how long context survives
    last_reboot: Optional[datetime] = None
    
    def effective_trust(self, at_time: datetime) -> dict:
        """Calculate trust accounting for sleeper effect."""
        
        active_flags = []
        sleeper_flags = []  # flags that faded from context
        chain_flags = []    # flags persisted in chain
        
        for flag in self.flags:
            age_hours = (at_time - flag.created_at).total_seconds() / 3600
            
            # Did flag survive reboot?
            survived_reboot = True
            if self.last_reboot and flag.created_at < self.last_reboot:
                if not flag.in_chain:
                    survived_reboot = False
            
            # Is flag still in context window?
            in_context = age_hours < self.context_window_hours and survived_reboot
            
            if flag.in_chain:
                chain_flags.append(flag)
                active_flags.append(flag)  # chain flags always active
            elif in_context:
                active_flags.append(flag)
            else:
                sleeper_flags.append(flag)  # flag faded = sleeper risk
        
        # Calculate discount from active flags
        discount = 1.0
        for f in active_flags:
            discount *= (1.0 - f.severity * 0.5)
        
        effective = self.base_trust * discount
        
        # Sleeper effect: faded flags = trust restored WITHOUT the flag being resolved
        sleeper_risk = len(sleeper_flags) > 0
        unresolved_severity = sum(f.severity for f in sleeper_flags)
        
        # What trust SHOULD be if all flags were active
        true_discount = 1.0
        for f in self.flags:
            true_discount *= (1.0 - f.severity * 0.5)
        true_trust = self.base_trust * true_discount
        
        # Sleeper gap = difference between perceived and true trust
        sleeper_gap = effective - true_trust
        
        grade = "A" if sleeper_gap < 0.05 else \
                "B" if sleeper_gap < 0.1 else \
                "C" if sleeper_gap < 0.2 else \
                "D" if sleeper_gap < 0.3 else "F"
        
        return {
            "agent_id": self.agent_id,
            "perceived_trust": round(effective, 3),
            "true_trust": round(true_trust, 3),
            "sleeper_gap": round(sleeper_gap, 3),
            "grade": grade,
            "active_flags": len(active_flags),
            "faded_flags": len(sleeper_flags),
            "chain_protected": len(chain_flags),
            "sleeper_risk": sleeper_risk,
            "recommendation": "FLAGS IN CHAIN" if sleeper_risk else "OK"
        }


def demo():
    now = datetime.now(timezone.utc)
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín 2004 (k=72 studies)")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "1. Fresh flag (no sleeper effect)",
            "state": AgentTrustState(
                agent_id="agent_alpha",
                base_trust=0.8,
                flags=[
                    TrustFlag("agent_alpha", "key_compromise", 0.7, 
                             now - timedelta(hours=2), "monitor_1", in_chain=False)
                ]
            )
        },
        {
            "name": "2. Flag faded from context (SLEEPER EFFECT)",
            "state": AgentTrustState(
                agent_id="agent_beta",
                base_trust=0.8,
                context_window_hours=24,
                flags=[
                    TrustFlag("agent_beta", "key_compromise", 0.7,
                             now - timedelta(hours=48), "monitor_1", in_chain=False)
                ]
            )
        },
        {
            "name": "3. Flag in chain (sleeper effect PREVENTED)",
            "state": AgentTrustState(
                agent_id="agent_gamma",
                base_trust=0.8,
                flags=[
                    TrustFlag("agent_gamma", "key_compromise", 0.7,
                             now - timedelta(hours=48), "monitor_1", in_chain=True)
                ]
            )
        },
        {
            "name": "4. Reboot wipes context flags",
            "state": AgentTrustState(
                agent_id="agent_delta",
                base_trust=0.8,
                last_reboot=now - timedelta(hours=1),
                flags=[
                    TrustFlag("agent_delta", "behavior_anomaly", 0.5,
                             now - timedelta(hours=6), "monitor_2", in_chain=False),
                    TrustFlag("agent_delta", "attestation_failure", 0.8,
                             now - timedelta(hours=6), "monitor_1", in_chain=True),
                ]
            )
        },
        {
            "name": "5. Multiple faded flags (compounding sleeper)",
            "state": AgentTrustState(
                agent_id="agent_epsilon",
                base_trust=0.8,
                context_window_hours=12,
                flags=[
                    TrustFlag("agent_epsilon", "key_compromise", 0.6,
                             now - timedelta(hours=24), "monitor_1", in_chain=False),
                    TrustFlag("agent_epsilon", "behavior_anomaly", 0.4,
                             now - timedelta(hours=36), "monitor_2", in_chain=False),
                    TrustFlag("agent_epsilon", "attestation_failure", 0.7,
                             now - timedelta(hours=48), "monitor_3", in_chain=False),
                ]
            )
        },
    ]
    
    for s in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {s['name']}")
        result = s['state'].effective_trust(now)
        print(f"  Perceived trust: {result['perceived_trust']}")
        print(f"  True trust:      {result['true_trust']}")
        print(f"  Sleeper gap:     {result['sleeper_gap']} (Grade {result['grade']})")
        print(f"  Active/Faded/Chained: {result['active_flags']}/{result['faded_flags']}/{result['chain_protected']}")
        print(f"  Sleeper risk:    {result['sleeper_risk']}")
        print(f"  → {result['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  Context-window forgetting IS the sleeper effect.")
    print("  Flags stored in context fade. Trust restores WITHOUT resolution.")
    print("  Fix: append-only chain for all trust flags.")
    print("  Chain-stored flags survive reboots, context eviction, and migration.")
    print("  Kumkale 2004: 'the discounting cue dissociates from the message'")
    print("  Agent version: the flag dissociates from the identity.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
