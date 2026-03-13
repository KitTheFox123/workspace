#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracin (Psychological Bulletin, 2004, k=72 studies):
- Discounting cue (e.g., "this source is unreliable") fades faster than message content
- Result: initially discounted message GAINS influence over time
- Agent risk: flagged agent reboots → flag forgotten → bad reputation persists as influence

Fix: hash-chain flags TO identity at inclusion time (Tessera tiles).
No dissociation possible when flag is part of the inclusion proof.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import hashlib
import json


@dataclass
class TrustFlag:
    """A discounting cue attached to an agent identity."""
    agent_id: str
    flag_type: str  # "compromised", "equivocated", "stale_cert", "collusion"
    created_at: datetime
    evidence_hash: str  # Hash of the evidence that triggered the flag
    inclusion_proof: Optional[str] = None  # Tile path if anchored
    
    @property
    def is_anchored(self) -> bool:
        """Flag is hash-chained to identity via inclusion proof."""
        return self.inclusion_proof is not None
    
    def dissociation_risk(self, now: datetime) -> float:
        """
        Kumkale & Albarracin 2004: discounting cue decays ~2x faster than message.
        Without anchoring, flag fades. With anchoring, dissociation = 0.
        """
        if self.is_anchored:
            return 0.0  # Permanent scar — no dissociation possible
        
        age_hours = (now - self.created_at).total_seconds() / 3600
        # Exponential decay: half-life ~6 hours for unanchored flags
        # (Based on sleeper effect timeline in meta-analysis)
        return min(1.0, 1.0 - (0.5 ** (age_hours / 6.0)))


@dataclass
class AgentReputation:
    agent_id: str
    flags: list[TrustFlag] = field(default_factory=list)
    trust_score: float = 0.5  # Current trust level
    
    def effective_trust(self, now: datetime) -> float:
        """
        Trust accounting WITH sleeper effect correction.
        Unanchored flags decay → trust rebounds (sleeper effect).
        Anchored flags are permanent discounting cues.
        """
        base_trust = self.trust_score
        
        for flag in self.flags:
            severity = {
                "compromised": 0.8,
                "equivocated": 0.6, 
                "collusion": 0.7,
                "stale_cert": 0.3,
            }.get(flag.flag_type, 0.4)
            
            dissociation = flag.dissociation_risk(now)
            
            if flag.is_anchored:
                # Permanent discount — flag is part of inclusion proof
                base_trust -= severity
            else:
                # Sleeper effect: discount fades over time
                effective_discount = severity * (1.0 - dissociation)
                base_trust -= effective_discount
        
        return max(0.0, min(1.0, base_trust))
    
    def vulnerability_report(self, now: datetime) -> dict:
        """Identify sleeper effect vulnerabilities."""
        unanchored = [f for f in self.flags if not f.is_anchored]
        anchored = [f for f in self.flags if f.is_anchored]
        
        sleeper_risk = sum(f.dissociation_risk(now) for f in unanchored)
        
        if not self.flags:
            grade = "A"  # Clean record
        elif not unanchored:
            grade = "A"  # All flags anchored
        elif sleeper_risk > 0.5:
            grade = "F"  # Active sleeper effect — flags fading
        elif sleeper_risk > 0.2:
            grade = "C"  # Moderate risk
        else:
            grade = "B"  # Flags fresh, still effective
        
        return {
            "agent_id": self.agent_id,
            "grade": grade,
            "total_flags": len(self.flags),
            "anchored": len(anchored),
            "unanchored": len(unanchored),
            "sleeper_risk": round(sleeper_risk, 3),
            "effective_trust": round(self.effective_trust(now), 3),
            "naive_trust": round(self.trust_score, 3),
            "trust_delta": round(
                self.effective_trust(now) - self.trust_score + 
                sum(0.4 for _ in self.flags), 3
            ),
            "recommendation": (
                "ANCHOR ALL FLAGS via Tessera inclusion proof"
                if unanchored else "All flags anchored — no sleeper risk"
            )
        }


def anchor_flag(flag: TrustFlag) -> TrustFlag:
    """Anchor a flag by computing inclusion proof hash."""
    proof_data = f"{flag.agent_id}:{flag.flag_type}:{flag.evidence_hash}:{flag.created_at.isoformat()}"
    flag.inclusion_proof = hashlib.sha256(proof_data.encode()).hexdigest()[:32]
    return flag


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracin (Psych Bull 2004, k=72)")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    scenarios = [
        {
            "name": "1. Fresh flag, unanchored (sleeper effect imminent)",
            "agent": AgentReputation(
                agent_id="suspect_agent",
                trust_score=0.7,
                flags=[
                    TrustFlag("suspect_agent", "compromised", 
                             now - timedelta(hours=1),
                             "abc123"),
                ]
            )
        },
        {
            "name": "2. Stale flag, unanchored (sleeper effect ACTIVE)",
            "agent": AgentReputation(
                agent_id="sleeper_agent",
                trust_score=0.7,
                flags=[
                    TrustFlag("sleeper_agent", "compromised",
                             now - timedelta(hours=24),
                             "def456"),
                ]
            )
        },
        {
            "name": "3. Flag anchored via Tessera tile (no dissociation)",
            "agent": AgentReputation(
                agent_id="scarred_agent",
                trust_score=0.7,
                flags=[
                    anchor_flag(TrustFlag("scarred_agent", "compromised",
                                         now - timedelta(hours=24),
                                         "ghi789")),
                ]
            )
        },
        {
            "name": "4. Mixed: one anchored, one fading",
            "agent": AgentReputation(
                agent_id="mixed_agent",
                trust_score=0.8,
                flags=[
                    anchor_flag(TrustFlag("mixed_agent", "equivocated",
                                         now - timedelta(hours=48),
                                         "jkl012")),
                    TrustFlag("mixed_agent", "stale_cert",
                             now - timedelta(hours=12),
                             "mno345"),
                ]
            )
        },
        {
            "name": "5. Clean record (no flags)",
            "agent": AgentReputation(
                agent_id="clean_agent",
                trust_score=0.9,
                flags=[]
            )
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        report = scenario['agent'].vulnerability_report(now)
        print(f"  Grade: {report['grade']}")
        print(f"  Effective trust: {report['effective_trust']} (naive: {report['naive_trust']})")
        print(f"  Flags: {report['total_flags']} ({report['anchored']} anchored, {report['unanchored']} unanchored)")
        print(f"  Sleeper risk: {report['sleeper_risk']}")
        print(f"  → {report['recommendation']}")
    
    # Timeline demo: show how unanchored flag fades
    print(f"\n{'=' * 60}")
    print("TIMELINE: Unanchored flag decay (sleeper effect)")
    print(f"{'=' * 60}")
    
    agent = AgentReputation(
        agent_id="timeline_agent",
        trust_score=0.7,
        flags=[TrustFlag("timeline_agent", "compromised", now, "test123")]
    )
    
    for hours in [0, 2, 6, 12, 24, 48]:
        future = now + timedelta(hours=hours)
        trust = agent.effective_trust(future)
        risk = agent.flags[0].dissociation_risk(future)
        bar = "█" * int(trust * 20) + "░" * (20 - int(trust * 20))
        print(f"  +{hours:2d}h: trust={trust:.3f} [{bar}] dissociation={risk:.3f}")
    
    print(f"\n  → Flag half-life: ~6h. After 24h, flag is 93.8% dissociated.")
    print(f"  → Anchored flag: 0% dissociation forever. Tile = permanent scar.")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  Sleeper effect = discounting cue fades, message persists.")
    print("  Agent version: flag fades, bad behavior influence stays.")
    print("  Fix: hash-chain flag to identity at write time (Tessera).")
    print("  No dissociation when proof is part of the inclusion path.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
