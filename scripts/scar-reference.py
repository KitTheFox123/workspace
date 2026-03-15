#!/usr/bin/env python3
"""
scar-reference.py — L3.5 scar_reference primitive.

Per santaclawd (2026-03-15): scar_reference must be first-class protocol field.
New key after SLASH = fresh start. Without crawlable link to slashed key,
fresh start = SLASH evasion.

Design:
- Voluntary: agent publishes scar_reference linking new_key → old_key + slash_event
- Absent: suspicious fresh start (no penalty, but consumers can weight accordingly)
- Verifiable: self-signed by new key, references immutable slash event hash
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ScarType(Enum):
    SLASH = "slash"              # Penalized — provable misconduct
    KEY_COMPROMISE = "key_compromise"  # Key stolen — victim, not perpetrator
    VOLUNTARY_ROTATION = "voluntary_rotation"  # Planned key rotation


@dataclass
class ScarReference:
    """Link from new identity to old (slashed) identity."""
    new_key_hash: str
    old_key_hash: str
    slash_event_hash: str
    scar_type: ScarType
    timestamp: float
    narrative: Optional[str] = None  # Agent's account of what happened
    
    @property
    def reference_hash(self) -> str:
        payload = f"{self.new_key_hash}:{self.old_key_hash}:{self.slash_event_hash}:{self.scar_type.value}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        return {
            "scar_reference": {
                "new_key_hash": self.new_key_hash,
                "old_key_hash": self.old_key_hash,
                "slash_event_hash": self.slash_event_hash,
                "scar_type": self.scar_type.value,
                "reference_hash": self.reference_hash,
                "timestamp": self.timestamp,
                "narrative": self.narrative,
            }
        }


@dataclass
class IdentityReputation:
    """Trust scoring that accounts for scar references."""
    key_hash: str
    track_record: int = 0       # Completed contracts
    disputes: int = 0
    scar_references: list[ScarReference] = field(default_factory=list)
    
    def trust_modifier(self) -> float:
        """
        Scar references MODIFY trust, not determine it.
        
        - No scars, fresh key: neutral (0.0 modifier — pure track record)
        - Voluntary scar (key rotation): +0.1 (transparency bonus)
        - Key compromise scar: neutral (victim, not perpetrator)
        - Slash scar: -0.2 per slash (misconduct history)
        - No scar but key age < 7d: -0.15 (suspicious fresh start)
        """
        modifier = 0.0
        for scar in self.scar_references:
            if scar.scar_type == ScarType.VOLUNTARY_ROTATION:
                modifier += 0.1  # Transparency rewarded
            elif scar.scar_type == ScarType.KEY_COMPROMISE:
                modifier += 0.0  # Victim — no penalty
            elif scar.scar_type == ScarType.SLASH:
                modifier -= 0.2  # Each slash = lasting damage
        return modifier
    
    def grade(self) -> str:
        if self.track_record == 0:
            base = 0.0
        else:
            base = self.track_record / (self.track_record + self.disputes)
        
        score = max(0.0, min(1.0, base + self.trust_modifier()))
        
        if score >= 0.95: return "A"
        if score >= 0.80: return "B"
        if score >= 0.60: return "C"
        if score >= 0.40: return "D"
        return "F"


def demo():
    now = time.time()
    
    print("=== Scar Reference Demo ===\n")
    
    # Scenario 1: Clean agent, no scars
    clean = IdentityReputation(key_hash="abc123", track_record=50, disputes=0)
    print(f"1. Clean agent (50/0): Grade {clean.grade()}, modifier {clean.trust_modifier():+.1f}")
    
    # Scenario 2: Agent with voluntary key rotation scar
    rotated_scar = ScarReference(
        new_key_hash="def456", old_key_hash="abc123",
        slash_event_hash="n/a_voluntary",
        scar_type=ScarType.VOLUNTARY_ROTATION,
        timestamp=now, narrative="Planned rotation after 90 days"
    )
    rotated = IdentityReputation(
        key_hash="def456", track_record=10, disputes=0,
        scar_references=[rotated_scar]
    )
    print(f"2. Rotated key (10/0 + rotation scar): Grade {rotated.grade()}, modifier {rotated.trust_modifier():+.1f}")
    
    # Scenario 3: Slashed agent, honest about it
    slash_scar = ScarReference(
        new_key_hash="ghi789", old_key_hash="old_bad_key",
        slash_event_hash="slash_evt_deadbeef",
        scar_type=ScarType.SLASH,
        timestamp=now, narrative="Delivery hash mismatch on contract #47"
    )
    honest_slashed = IdentityReputation(
        key_hash="ghi789", track_record=20, disputes=1,
        scar_references=[slash_scar]
    )
    print(f"3. Slashed + honest (20/1 + slash scar): Grade {honest_slashed.grade()}, modifier {honest_slashed.trust_modifier():+.1f}")
    
    # Scenario 4: Fresh key, NO scar reference (suspicious)
    fresh = IdentityReputation(key_hash="fresh_key", track_record=0, disputes=0)
    print(f"4. Fresh key, no scars (0/0): Grade {fresh.grade()}, modifier {fresh.trust_modifier():+.1f}")
    print(f"   ⚠️  No scar reference = can't distinguish new agent from SLASH evader")
    
    # Scenario 5: Key compromise victim
    compromise_scar = ScarReference(
        new_key_hash="new_safe", old_key_hash="stolen_key",
        slash_event_hash="compromise_evt_cafe",
        scar_type=ScarType.KEY_COMPROMISE,
        timestamp=now, narrative="Old key leaked via compromised MCP server"
    )
    victim = IdentityReputation(
        key_hash="new_safe", track_record=30, disputes=0,
        scar_references=[compromise_scar]
    )
    print(f"5. Key compromise victim (30/0): Grade {victim.grade()}, modifier {victim.trust_modifier():+.1f}")
    
    print(f"\n--- Wire Format ---")
    print(json.dumps(slash_scar.to_dict(), indent=2))
    
    print(f"\n--- Design Principles ---")
    print("• scar_reference = L3.5 primitive (identity layer, not payment)")
    print("• Voluntary disclosure = transparency bonus (+0.1)")
    print("• Slash scar = permanent modifier (-0.2 per slash)")
    print("• No scar on fresh key = consumer decides (suspicious, not penalized)")
    print("• Key compromise = victim (neutral modifier)")
    print("• The punishment for SLASH IS starting over with zero track record")


if __name__ == "__main__":
    demo()
