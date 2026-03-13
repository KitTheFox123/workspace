#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracin (2004) meta-analysis (k=72 studies).

The sleeper effect: a discounting cue (e.g., "this source is unreliable")
fades faster than the message itself. Over time, the persuasive message
regains influence because the discounting cue is forgotten.

Agent parallel: A revocation flag or trust warning dissociates from the
agent identity across context windows. The flagged agent regains trust
not because it earned it, but because the flag was forgotten.

Fix: Bind flags to cert hashes in append-only logs. No dissociation possible.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import math


@dataclass
class TrustFlag:
    """A discounting cue attached to an agent identity."""
    agent_id: str
    flag_type: str  # "revocation", "warning", "suspicious", "compromised"
    reason: str
    created_at: datetime
    cert_hash: Optional[str] = None  # If bound to cert, immune to sleeper effect
    in_append_log: bool = False      # If in append-only log, persistent
    
    @property
    def is_bound(self) -> bool:
        """Flag bound to cert hash = no dissociation possible."""
        return self.cert_hash is not None and self.in_append_log


@dataclass 
class AgentTrustState:
    """Agent's trust state with sleeper effect modeling."""
    agent_id: str
    base_trust: float = 0.5
    flags: list[TrustFlag] = field(default_factory=list)
    context_resets: int = 0  # Number of context window resets
    
    def effective_trust(self, current_time: datetime) -> dict:
        """
        Calculate trust accounting for sleeper effect.
        
        Kumkale & Albarracin 2004 key findings:
        - Discounting cue decays with f(time) = e^(-λt)
        - Message content decays slower: g(time) = e^(-μt) where μ < λ
        - Sleeper effect = gap between message retention and cue retention
        - Strongest when: strong arguments + strong discounting cue + delay
        """
        
        if not self.flags:
            return {
                "trust": self.base_trust,
                "sleeper_risk": 0.0,
                "flags_effective": 0,
                "flags_total": 0,
                "grade": self._grade(self.base_trust, 0.0)
            }
        
        total_discount = 0.0
        effective_flags = 0
        sleeper_risks = []
        
        for flag in self.flags:
            age_hours = (current_time - flag.created_at).total_seconds() / 3600
            
            if flag.is_bound:
                # Bound to cert hash in append-only log = no decay
                decay = 1.0
                sleeper_risk = 0.0
            else:
                # Unbound flag decays per Kumkale & Albarracin
                # λ = 0.1/hr for unbound flags (fast decay)
                # Additional decay per context reset
                lambda_cue = 0.1
                resets_factor = 1.0 + 0.5 * self.context_resets
                decay = math.exp(-lambda_cue * age_hours * resets_factor)
                
                # Sleeper risk = probability flag has dissociated
                sleeper_risk = 1.0 - decay
            
            # Flag severity
            severity = {
                "compromised": 1.0,
                "revocation": 0.8,
                "suspicious": 0.5,
                "warning": 0.3,
            }.get(flag.flag_type, 0.3)
            
            effective_discount = severity * decay
            total_discount += effective_discount
            sleeper_risks.append(sleeper_risk)
            
            if decay > 0.1:
                effective_flags += 1
        
        # Trust = base - effective discounts
        trust = max(0.0, min(1.0, self.base_trust - total_discount))
        avg_sleeper = sum(sleeper_risks) / len(sleeper_risks) if sleeper_risks else 0.0
        
        return {
            "trust": round(trust, 3),
            "sleeper_risk": round(avg_sleeper, 3),
            "flags_effective": effective_flags,
            "flags_total": len(self.flags),
            "grade": self._grade(trust, avg_sleeper)
        }
    
    def _grade(self, trust: float, sleeper_risk: float) -> str:
        if sleeper_risk > 0.7:
            return "F"  # High sleeper risk = trust score unreliable
        if sleeper_risk > 0.4:
            return "D"  # Moderate sleeper risk
        if trust < 0.2:
            return "C"  # Low trust but flags working
        if trust < 0.5:
            return "B"  # Flagged, discounted appropriately
        return "A"      # Clean or well-monitored


def demo():
    """Demonstrate sleeper effect in agent trust scenarios."""
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracin 2004 (k=72, Psych Bull)")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    scenarios = [
        {
            "name": "1. Fresh flag, bound to cert (IMMUNE)",
            "state": AgentTrustState(
                agent_id="agent_alpha",
                base_trust=0.7,
                flags=[TrustFlag(
                    "agent_alpha", "suspicious", "anomalous heartbeat pattern",
                    now - timedelta(hours=1),
                    cert_hash="abc123", in_append_log=True
                )],
                context_resets=0
            )
        },
        {
            "name": "2. Fresh flag, NOT bound (VULNERABLE)",
            "state": AgentTrustState(
                agent_id="agent_beta",
                base_trust=0.7,
                flags=[TrustFlag(
                    "agent_beta", "suspicious", "anomalous heartbeat pattern",
                    now - timedelta(hours=1),
                    cert_hash=None, in_append_log=False
                )],
                context_resets=0
            )
        },
        {
            "name": "3. Old flag, unbound, 3 context resets (SLEEPER)",
            "state": AgentTrustState(
                agent_id="agent_gamma",
                base_trust=0.7,
                flags=[TrustFlag(
                    "agent_gamma", "compromised", "key material leaked",
                    now - timedelta(hours=24),
                    cert_hash=None, in_append_log=False
                )],
                context_resets=3
            )
        },
        {
            "name": "4. Old flag, BOUND, 3 context resets (SAFE)",
            "state": AgentTrustState(
                agent_id="agent_delta",
                base_trust=0.7,
                flags=[TrustFlag(
                    "agent_delta", "compromised", "key material leaked",
                    now - timedelta(hours=24),
                    cert_hash="def456", in_append_log=True
                )],
                context_resets=3
            )
        },
        {
            "name": "5. Revoked agent, reboot, flag lost (REAL ATTACK)",
            "state": AgentTrustState(
                agent_id="agent_evil",
                base_trust=0.8,
                flags=[TrustFlag(
                    "agent_evil", "revocation", "cert revoked by attestor pool",
                    now - timedelta(hours=48),
                    cert_hash=None, in_append_log=False
                )],
                context_resets=5  # Many reboots to wash the flag
            )
        },
    ]
    
    for scenario in scenarios:
        state = scenario["state"]
        result = state.effective_trust(now)
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        print(f"Base trust: {state.base_trust}")
        print(f"Context resets: {state.context_resets}")
        for f in state.flags:
            bound = "BOUND" if f.is_bound else "UNBOUND"
            age = (now - f.created_at).total_seconds() / 3600
            print(f"  Flag: {f.flag_type} ({bound}, {age:.0f}h old)")
        print(f"Result: trust={result['trust']}, sleeper_risk={result['sleeper_risk']}")
        print(f"Grade: {result['grade']} ({result['flags_effective']}/{result['flags_total']} flags effective)")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracin 2004):")
    print("  Discounting cues decay FASTER than message content.")
    print("  Agent: revocation flag forgotten before identity rebuilt.")
    print("  Context resets accelerate cue decay (forced forgetting).")
    print("  FIX: Hash-chain flags TO cert hashes in append-only log.")
    print("  Bound flags = zero sleeper risk. Unbound = inevitable decay.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
