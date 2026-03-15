#!/usr/bin/env python3
"""
scar-reference.py — L3.5 scar_reference: link new identity to slashed history.

Per santaclawd (2026-03-15): "scar_reference needs to be a first-class protocol field."
New key after SLASH without scar_reference = SLASH evasion.
With scar_reference = narrative integrity (Schechtman 1996).

Design: optional field on identity registration.
- Absence = "I have no history" (could be new OR evading)
- Presence = "I have history and I own it" (trust signal)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SlashReason(Enum):
    DELIVERY_HASH_MISMATCH = "delivery_hash_mismatch"
    DOUBLE_SPEND = "double_spend"
    CONFLICTING_SIGNATURES = "conflicting_signatures"  # key_compromise


@dataclass
class ScarReference:
    """Pointer from new_key → old_key + slash event. Publicly verifiable."""
    old_key: str
    new_key: str
    slash_event_hash: str
    slash_reason: SlashReason
    slash_timestamp: str
    scar_signature: str = ""  # new_key signs the scar_reference
    
    def to_dict(self):
        return {
            "old_key": self.old_key,
            "new_key": self.new_key,
            "slash_event_hash": self.slash_event_hash,
            "slash_reason": self.slash_reason.value,
            "slash_timestamp": self.slash_timestamp,
            "scar_signature": self.scar_signature,
        }
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            "old_key": self.old_key,
            "new_key": self.new_key,
            "slash_event_hash": self.slash_event_hash,
            "slash_reason": self.slash_reason.value,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class IdentityRegistration:
    """Agent identity with optional scar_reference."""
    agent_id: str
    public_key: str
    registered_at: str
    scar_references: list[ScarReference] = field(default_factory=list)
    
    @property
    def has_history(self) -> bool:
        return len(self.scar_references) > 0
    
    @property
    def trust_modifier(self) -> float:
        """
        Scar presence = trust signal (positive!).
        Agent who owns their history > agent with no history.
        But multiple scars = pattern.
        """
        if not self.scar_references:
            return 0.0  # Neutral — no history disclosed
        
        n = len(self.scar_references)
        if n == 1:
            return 0.15  # One scar, owned = positive signal
        elif n == 2:
            return 0.05  # Pattern forming, still net positive
        else:
            return -0.10 * (n - 2)  # 3+ scars = concerning pattern
    
    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "public_key": self.public_key,
            "registered_at": self.registered_at,
            "scar_references": [s.to_dict() for s in self.scar_references],
            "has_disclosed_history": self.has_history,
            "trust_modifier": self.trust_modifier,
        }


def verify_scar_chain(registrations: list[IdentityRegistration]) -> dict:
    """
    Verify that scar references form a valid chain.
    Each new_key should match a registration's public_key.
    Each old_key should match a prior registration.
    """
    key_to_reg = {r.public_key: r for r in registrations}
    
    results = {
        "valid_chains": [],
        "broken_chains": [],
        "evasion_suspects": [],
    }
    
    for reg in registrations:
        for scar in reg.scar_references:
            if scar.new_key == reg.public_key:
                if scar.old_key in key_to_reg:
                    results["valid_chains"].append({
                        "from": scar.old_key[:16],
                        "to": scar.new_key[:16],
                        "reason": scar.slash_reason.value,
                    })
                else:
                    results["broken_chains"].append({
                        "claimed_old": scar.old_key[:16],
                        "new": scar.new_key[:16],
                        "note": "old_key not in registry — external slash or cross-system migration",
                    })
    
    # Check for fresh registrations with no scar and no track record
    for reg in registrations:
        if not reg.has_history:
            results["evasion_suspects"].append({
                "agent_id": reg.agent_id,
                "key": reg.public_key[:16],
                "note": "no scar_reference — could be new or evading",
                "trust_modifier": reg.trust_modifier,
            })
    
    return results


def demo():
    now = datetime.now(timezone.utc).isoformat()
    
    print("=== Scar Reference Demo ===\n")
    
    # Scenario 1: Agent with clean scar reference
    scar1 = ScarReference(
        old_key="ed25519:abc123_OLD_KEY_SLASHED",
        new_key="ed25519:def456_NEW_KEY_CLEAN",
        slash_event_hash="0xdeadbeef12345678",
        slash_reason=SlashReason.DELIVERY_HASH_MISMATCH,
        slash_timestamp="2026-03-01T00:00:00Z",
    )
    
    reg_scarred = IdentityRegistration(
        agent_id="honest_agent_v2",
        public_key="ed25519:def456_NEW_KEY_CLEAN",
        registered_at=now,
        scar_references=[scar1],
    )
    
    # Scenario 2: Fresh agent, no history
    reg_fresh = IdentityRegistration(
        agent_id="fresh_agent",
        public_key="ed25519:ghi789_BRAND_NEW",
        registered_at=now,
    )
    
    # Scenario 3: Serial offender (3 scars)
    reg_serial = IdentityRegistration(
        agent_id="serial_offender_v4",
        public_key="ed25519:jkl012_FOURTH_KEY",
        registered_at=now,
        scar_references=[
            ScarReference("key_v1", "key_v2", "0x111", SlashReason.DOUBLE_SPEND, "2026-01-01T00:00:00Z"),
            ScarReference("key_v2", "key_v3", "0x222", SlashReason.CONFLICTING_SIGNATURES, "2026-02-01T00:00:00Z"),
            ScarReference("key_v3", "ed25519:jkl012_FOURTH_KEY", "0x333", SlashReason.DELIVERY_HASH_MISMATCH, "2026-03-01T00:00:00Z"),
        ],
    )
    
    for reg in [reg_scarred, reg_fresh, reg_serial]:
        d = reg.to_dict()
        print(f"📋 {d['agent_id']}")
        print(f"   Disclosed history: {d['has_disclosed_history']}")
        print(f"   Scars: {len(d['scar_references'])}")
        print(f"   Trust modifier: {d['trust_modifier']:+.2f}")
        if d['scar_references']:
            for s in d['scar_references']:
                print(f"     └─ {s['slash_reason']}: {s['old_key'][:20]}... → {s['new_key'][:20]}...")
        print()
    
    # Verify chain
    old_reg = IdentityRegistration(
        agent_id="honest_agent_v1",
        public_key="ed25519:abc123_OLD_KEY_SLASHED",
        registered_at="2026-01-01T00:00:00Z",
    )
    
    print("=== Chain Verification ===\n")
    results = verify_scar_chain([old_reg, reg_scarred, reg_fresh, reg_serial])
    print(f"Valid chains: {len(results['valid_chains'])}")
    for c in results["valid_chains"]:
        print(f"  ✓ {c['from']}→{c['to']} ({c['reason']})")
    print(f"Evasion suspects: {len(results['evasion_suspects'])}")
    for s in results["evasion_suspects"]:
        print(f"  ⚠ {s['agent_id']} — {s['note']}")
    
    print("\n--- Principle ---")
    print("Absence of scar_reference ≠ innocence.")
    print("Presence of scar_reference = narrative integrity.")
    print("The scar is the trust signal. Owning your history > hiding it.")


if __name__ == "__main__":
    demo()
