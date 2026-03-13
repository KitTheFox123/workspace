#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004, Psychological Bulletin, k=72 studies).

The sleeper effect: discounting cues (e.g., "this source is unreliable") 
dissociate from message content over time. People become MORE persuaded 
by messages from discredited sources as time passes.

Agent threat model:
- Agent flagged as compromised at t=0
- Agent reboots/rotates identity at t=1  
- By t=n, other agents remember the behavior pattern but forget the flag
- The compromised agent regains trust through sleeper effect

Fix: Bind discounting cues to identity hashes in the isnad chain.
The flag travels with the cert, not the session.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import json


@dataclass
class DiscountingCue:
    """A flag/warning attached to an agent identity."""
    cue_type: str          # "compromised", "unreliable", "flagged", "suspended"
    issued_at: datetime
    issuer_id: str
    reason: str
    identity_hash: Optional[str] = None  # Bound to identity, not session
    ttl_hours: float = 720  # 30 days default
    
    @property
    def is_bound(self) -> bool:
        """Is this cue bound to identity hash (persistent) or session (volatile)?"""
        return self.identity_hash is not None
    
    def decay_factor(self, at_time: datetime) -> float:
        """
        Kumkale 2004: source credibility decays ~50% faster than message content.
        Unbound cues decay exponentially. Bound cues decay at message rate.
        """
        elapsed_hours = (at_time - self.issued_at).total_seconds() / 3600
        
        if self.is_bound:
            # Bound to identity: decays at message rate (slower)
            # Half-life = ttl_hours
            half_life = self.ttl_hours
        else:
            # Unbound (session): decays at source-credibility rate (faster)
            # Kumkale 2004: ~2x faster decay for source vs message
            half_life = self.ttl_hours / 2
        
        import math
        return math.exp(-0.693 * elapsed_hours / half_life)


@dataclass
class AgentTrustRecord:
    agent_id: str
    identity_hash: str
    trust_score: float = 0.5
    cues: list[DiscountingCue] = field(default_factory=list)
    behavior_observations: list[dict] = field(default_factory=list)
    
    def effective_trust(self, at_time: datetime) -> dict:
        """
        Calculate trust accounting for sleeper effect.
        
        Without sleeper detection: trust recovers as cue decays
        With sleeper detection: trust stays discounted while bound cue persists
        """
        base_trust = self.trust_score
        
        # Behavior-based trust (observed, not advisory - Watson & Morgan 2025)
        if self.behavior_observations:
            good = sum(1 for o in self.behavior_observations if o.get("positive"))
            total = len(self.behavior_observations)
            behavior_trust = good / total if total > 0 else 0.5
        else:
            behavior_trust = 0.5
        
        # Apply active discounting cues
        naive_discount = 1.0   # Without sleeper detection
        bound_discount = 1.0   # With sleeper detection
        
        active_cues = []
        sleeper_risks = []
        
        for cue in self.cues:
            decay = cue.decay_factor(at_time)
            
            if cue.is_bound:
                # Bound cue: applies full discount adjusted by decay
                bound_discount *= (1.0 - 0.5 * decay)  # Max 50% discount per cue
                naive_discount *= (1.0 - 0.5 * decay)
                if decay > 0.01:
                    active_cues.append({
                        "type": cue.cue_type,
                        "decay": round(decay, 3),
                        "bound": True
                    })
            else:
                # Unbound cue: decays 2x faster (sleeper effect!)
                naive_discount *= (1.0 - 0.5 * decay)
                # But the ACTUAL risk hasn't changed
                actual_decay = cue.decay_factor(at_time)  # Already 2x faster
                real_decay_factor = decay  # This is already the fast decay
                
                # Sleeper risk = gap between perceived trust and actual risk
                import math
                slow_decay = math.exp(-0.693 * (at_time - cue.issued_at).total_seconds() / 3600 / cue.ttl_hours)
                fast_decay = decay
                
                if slow_decay - fast_decay > 0.1:
                    sleeper_risks.append({
                        "type": cue.cue_type,
                        "perceived_discount": round(fast_decay, 3),
                        "actual_risk": round(slow_decay, 3),
                        "sleeper_gap": round(slow_decay - fast_decay, 3)
                    })
                
                bound_discount *= (1.0 - 0.5 * slow_decay)  # Use slow decay
        
        naive_trust = min(behavior_trust * naive_discount, 1.0)
        corrected_trust = min(behavior_trust * bound_discount, 1.0)
        
        sleeper_detected = len(sleeper_risks) > 0
        
        return {
            "agent_id": self.agent_id,
            "naive_trust": round(naive_trust, 3),
            "corrected_trust": round(corrected_trust, 3),
            "sleeper_detected": sleeper_detected,
            "sleeper_risks": sleeper_risks,
            "active_cues": active_cues,
            "grade": self._grade(corrected_trust, sleeper_detected)
        }
    
    def _grade(self, trust: float, sleeper: bool) -> str:
        if sleeper:
            return "⚠️ SLEEPER"  # Always warn
        if trust >= 0.7: return "A"
        if trust >= 0.5: return "B"
        if trust >= 0.3: return "C"
        if trust >= 0.15: return "D"
        return "F"


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (Psych Bull 2004, k=72)")
    print("=" * 60)
    
    now = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
    
    scenarios = [
        {
            "name": "1. Bound flag (identity-linked) — 3 days old",
            "agent": AgentTrustRecord(
                agent_id="agent_alpha",
                identity_hash="abc123",
                trust_score=0.8,
                cues=[DiscountingCue(
                    "compromised", now - timedelta(days=3),
                    "monitor_1", "split-view detected",
                    identity_hash="abc123", ttl_hours=720
                )],
                behavior_observations=[
                    {"positive": True}, {"positive": True}, 
                    {"positive": True}, {"positive": False}
                ]
            )
        },
        {
            "name": "2. Unbound flag (session-only) — 3 days old — SLEEPER RISK",
            "agent": AgentTrustRecord(
                agent_id="agent_beta",
                identity_hash="def456",
                trust_score=0.8,
                cues=[DiscountingCue(
                    "compromised", now - timedelta(days=3),
                    "monitor_1", "split-view detected",
                    identity_hash=None, ttl_hours=720  # NOT bound!
                )],
                behavior_observations=[
                    {"positive": True}, {"positive": True}, 
                    {"positive": True}, {"positive": False}
                ]
            )
        },
        {
            "name": "3. Rebooted agent — flag lost entirely",
            "agent": AgentTrustRecord(
                agent_id="agent_gamma_v2",  # New session
                identity_hash="ghi789",
                trust_score=0.5,  # Fresh
                cues=[],  # Flag was session-bound, gone after reboot
                behavior_observations=[
                    {"positive": True}, {"positive": True}
                ]
            )
        },
        {
            "name": "4. Multiple cues, mixed binding — 7 days old",
            "agent": AgentTrustRecord(
                agent_id="agent_delta",
                identity_hash="jkl012",
                trust_score=0.7,
                cues=[
                    DiscountingCue(
                        "unreliable", now - timedelta(days=7),
                        "skillfence", "failed audit",
                        identity_hash="jkl012", ttl_hours=720
                    ),
                    DiscountingCue(
                        "flagged", now - timedelta(days=7),
                        "gossip", "inconsistent beacons",
                        identity_hash=None, ttl_hours=720  # Session-bound
                    ),
                ],
                behavior_observations=[
                    {"positive": True}, {"positive": True},
                    {"positive": True}, {"positive": True}, {"positive": False}
                ]
            )
        },
        {
            "name": "5. Old bound flag — 25 days — mostly decayed",
            "agent": AgentTrustRecord(
                agent_id="agent_epsilon",
                identity_hash="mno345",
                trust_score=0.9,
                cues=[DiscountingCue(
                    "suspended", now - timedelta(days=25),
                    "platform", "temporary suspension",
                    identity_hash="mno345", ttl_hours=720
                )],
                behavior_observations=[
                    {"positive": True} for _ in range(10)
                ]
            )
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        result = scenario["agent"].effective_trust(now)
        print(f"  Naive trust:     {result['naive_trust']}")
        print(f"  Corrected trust: {result['corrected_trust']}")
        print(f"  Grade:           {result['grade']}")
        if result['sleeper_risks']:
            for risk in result['sleeper_risks']:
                print(f"  ⚠️ SLEEPER: {risk['type']} — perceived discount {risk['perceived_discount']}, actual risk {risk['actual_risk']}, gap {risk['sleeper_gap']}")
        if result['active_cues']:
            for cue in result['active_cues']:
                print(f"  Active cue: {cue['type']} (decay={cue['decay']}, bound={cue['bound']})")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Source credibility decays ~2x faster than message content.")
    print("  Agent: 'compromised' flag forgotten before behavior pattern.")
    print("  Fix: Bind flags to identity hash in isnad chain.")
    print("  The flag travels with the cert, not the session.")
    print("  Scenario 2 vs 1: same flag, different binding, different risk.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
