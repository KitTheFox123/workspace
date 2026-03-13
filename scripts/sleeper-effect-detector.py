#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracin (2004, Psychological Bulletin, k=72 studies).

The sleeper effect: discounting cues (e.g., "this agent was compromised") 
dissociate from the message over time, causing trust to INCREASE when it 
shouldn't. The flag decays faster than the identity.

Agent parallel: after key rotation or reboot, the "compromised" flag 
detaches from the new identity. Observers remember the agent but forget 
the warning.

Fix: bind flags to cert hashes (immutable), not agent IDs (mutable).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import hashlib
import json


@dataclass
class TrustFlag:
    """A discounting cue attached to an agent identity."""
    cert_hash: str          # Immutable binding (Tessera tile)
    agent_id: str           # Mutable binding (identity)
    flag_type: str          # "compromised", "suspicious", "revoked"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    bound_to: str = "cert_hash"  # "cert_hash" (immutable) or "agent_id" (mutable)
    
    def dissociation_risk(self, elapsed_hours: float) -> float:
        """
        Kumkale & Albarracin 2004: discounting cue impact decays 
        exponentially. Message content decays slower.
        
        Sleeper effect = cue_decay > content_decay
        """
        if self.bound_to == "cert_hash":
            # Immutable binding: no dissociation possible
            return 0.0
        
        # Agent ID binding: flag dissociates over time
        # Half-life ~48h based on meta-analytic estimates
        cue_decay = 0.5 ** (elapsed_hours / 48)
        # Trust in agent (content) decays slower, half-life ~168h (1 week)
        content_retention = 0.5 ** (elapsed_hours / 168)
        
        # Sleeper effect magnitude = gap between content retention and cue retention
        # When cue decays but content stays → trust inappropriately rises
        sleeper_magnitude = max(0, content_retention - cue_decay)
        return sleeper_magnitude


@dataclass 
class AgentTrustRecord:
    agent_id: str
    flags: list[TrustFlag] = field(default_factory=list)
    rotations: int = 0
    
    def sleeper_risk_score(self, hours_since_flag: float = 72) -> dict:
        """
        Assess sleeper effect risk for this agent's trust profile.
        """
        if not self.flags:
            return {
                "risk": "NONE",
                "score": 0.0,
                "reason": "no discounting cues present"
            }
        
        max_risk = 0.0
        risky_flags = []
        safe_flags = []
        
        for flag in self.flags:
            risk = flag.dissociation_risk(hours_since_flag)
            if risk > 0.1:
                risky_flags.append((flag, risk))
                max_risk = max(max_risk, risk)
            else:
                safe_flags.append(flag)
        
        # Rotation amplifies sleeper effect (new cert = new identity = flag detaches)
        rotation_multiplier = 1.0 + 0.2 * self.rotations
        adjusted_risk = min(max_risk * rotation_multiplier, 1.0)
        
        if adjusted_risk > 0.5:
            level = "CRITICAL"
        elif adjusted_risk > 0.3:
            level = "HIGH"  
        elif adjusted_risk > 0.1:
            level = "MODERATE"
        else:
            level = "LOW"
        
        return {
            "risk": level,
            "score": round(adjusted_risk, 3),
            "risky_flags": len(risky_flags),
            "safe_flags": len(safe_flags),
            "rotations": self.rotations,
            "rotation_multiplier": rotation_multiplier,
            "recommendation": (
                "REBIND flags to cert_hash" if risky_flags 
                else "flags properly bound"
            )
        }


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracin (2004, Psych Bull, k=72)")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "1. Flag bound to cert hash (SAFE)",
            "agent_id": "agent_alice",
            "flags": [TrustFlag("abc123", "agent_alice", "compromised", bound_to="cert_hash")],
            "rotations": 2,
            "hours": 72,
        },
        {
            "name": "2. Flag bound to agent ID, 72h later (RISKY)",
            "agent_id": "agent_bob",
            "flags": [TrustFlag("def456", "agent_bob", "compromised", bound_to="agent_id")],
            "rotations": 0,
            "hours": 72,
        },
        {
            "name": "3. Flag on agent ID + key rotation (CRITICAL)",
            "agent_id": "agent_carol",
            "flags": [TrustFlag("ghi789", "agent_carol", "compromised", bound_to="agent_id")],
            "rotations": 3,
            "hours": 96,
        },
        {
            "name": "4. Multiple flags, mixed binding",
            "agent_id": "agent_dave",
            "flags": [
                TrustFlag("jkl012", "agent_dave", "suspicious", bound_to="cert_hash"),
                TrustFlag("mno345", "agent_dave", "revoked", bound_to="agent_id"),
            ],
            "rotations": 1,
            "hours": 48,
        },
        {
            "name": "5. Fresh flag, no time elapsed",
            "agent_id": "agent_eve",
            "flags": [TrustFlag("pqr678", "agent_eve", "compromised", bound_to="agent_id")],
            "rotations": 0,
            "hours": 1,
        },
    ]
    
    for s in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {s['name']}")
        record = AgentTrustRecord(s['agent_id'], s['flags'], s['rotations'])
        result = record.sleeper_risk_score(s['hours'])
        print(f"  Hours since flag: {s['hours']}")
        print(f"  Risk level: {result['risk']} ({result['score']})")
        print(f"  Risky/Safe flags: {result['risky_flags']}/{result['safe_flags']}")
        print(f"  Rotations: {result['rotations']} (multiplier: {result['rotation_multiplier']})")
        print(f"  Recommendation: {result['recommendation']}")
        
        # Show dissociation curve for risky flags
        for flag in s['flags']:
            if flag.bound_to == "agent_id":
                risks = [(h, flag.dissociation_risk(h)) for h in [0, 12, 24, 48, 72, 96, 120, 168]]
                print(f"  Dissociation curve ({flag.flag_type}):")
                for h, r in risks:
                    bar = "█" * int(r * 40)
                    print(f"    {h:>4}h: {r:.3f} {bar}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracin 2004):")
    print("  Discounting cues decay FASTER than message content.")
    print("  After 72h, observers remember the agent but forget the warning.")
    print("  Key rotation amplifies this — new cert = new identity.")
    print("  FIX: Bind flags to cert_hash (immutable), not agent_id (mutable).")
    print("  Tessera tiles = permanent association. No dissociation possible.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
