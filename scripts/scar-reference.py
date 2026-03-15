#!/usr/bin/env python3
"""
scar-reference.py — L3.5 scar_reference primitive.

Per santaclawd (2026-03-15): new key after SLASH = fresh start,
but without crawlable link to slashed key, fresh start = SLASH evasion.

scar_reference: pointer from new_key → old_key + slash_event_hash.
Publicly verifiable. Immutable. Cross-platform.

This is an L3.5 primitive, not a PayLock field. PayLock READS it.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SlashReason(Enum):
    DELIVERY_HASH_MISMATCH = "delivery_hash_mismatch"
    DOUBLE_SPEND = "double_spend"
    CONFLICTING_SIGNATURES = "conflicting_signatures"  # santaclawd's 3rd trigger


@dataclass
class ScarReference:
    """Immutable pointer from new identity to slashed identity."""
    new_key: str
    old_key: str
    slash_event_hash: str
    slash_reason: SlashReason
    slash_timestamp: str
    scar_created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def scar_hash(self) -> str:
        """Deterministic hash of the scar reference itself."""
        payload = f"{self.new_key}:{self.old_key}:{self.slash_event_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        return {
            "scar_reference": {
                "new_key": self.new_key,
                "old_key": self.old_key,
                "slash_event_hash": self.slash_event_hash,
                "slash_reason": self.slash_reason.value,
                "slash_timestamp": self.slash_timestamp,
                "scar_hash": self.scar_hash,
                "created_at": self.scar_created_at,
            }
        }


@dataclass  
class IdentityGraph:
    """Crawlable graph of identity transitions including scars."""
    scars: list[ScarReference] = field(default_factory=list)
    
    def add_scar(self, scar: ScarReference):
        self.scars.append(scar)
    
    def lookup_by_new_key(self, key: str) -> list[ScarReference]:
        """Given a new key, find all scars (slashed histories)."""
        return [s for s in self.scars if s.new_key == key]
    
    def lookup_by_old_key(self, key: str) -> list[ScarReference]:
        """Given a slashed key, find successor identities."""
        return [s for s in self.scars if s.old_key == key]
    
    def full_history(self, key: str) -> list[ScarReference]:
        """Crawl the full scar chain for an identity."""
        history = []
        current = key
        seen = set()
        while current and current not in seen:
            seen.add(current)
            scars = self.lookup_by_new_key(current)
            if scars:
                history.extend(scars)
                current = scars[0].old_key  # Follow chain back
            else:
                break
        return history
    
    def evasion_score(self, key: str) -> float:
        """
        Score how suspicious a fresh identity looks.
        0.0 = clean (no scars, or properly referenced)
        1.0 = maximum evasion risk (many scars, rapid re-keying)
        """
        history = self.full_history(key)
        if not history:
            return 0.0  # No scars = either clean or unlinked
        
        score = 0.0
        # Each scar adds risk
        score += min(len(history) * 0.3, 0.9)
        # Conflicting signatures = worst reason
        for s in history:
            if s.slash_reason == SlashReason.CONFLICTING_SIGNATURES:
                score += 0.3
            elif s.slash_reason == SlashReason.DOUBLE_SPEND:
                score += 0.2
        return min(score, 1.0)


def demo():
    print("=== Scar Reference — L3.5 Primitive ===\n")
    
    graph = IdentityGraph()
    
    # Scenario 1: Agent slashed for delivery mismatch, creates new identity
    scar1 = ScarReference(
        new_key="agent_v2_key_abc123",
        old_key="agent_v1_key_xyz789",
        slash_event_hash="deadbeef01234567",
        slash_reason=SlashReason.DELIVERY_HASH_MISMATCH,
        slash_timestamp="2026-03-10T12:00:00Z",
    )
    graph.add_scar(scar1)
    
    # Scenario 2: Same agent slashed AGAIN, creates v3
    scar2 = ScarReference(
        new_key="agent_v3_key_def456",
        old_key="agent_v2_key_abc123",
        slash_event_hash="cafebabe89abcdef",
        slash_reason=SlashReason.DOUBLE_SPEND,
        slash_timestamp="2026-03-14T08:00:00Z",
    )
    graph.add_scar(scar2)
    
    print("📋 Scar 1 (v1 → v2):")
    print(json.dumps(scar1.to_dict(), indent=2))
    
    print("\n📋 Scar 2 (v2 → v3):")
    print(json.dumps(scar2.to_dict(), indent=2))
    
    # Crawl full history for v3
    print("\n🔍 Full history for agent_v3:")
    history = graph.full_history("agent_v3_key_def456")
    for s in history:
        print(f"  ← {s.old_key} (slashed: {s.slash_reason.value})")
    
    # Evasion scores
    print("\n⚠️  Evasion scores:")
    for key, label in [
        ("agent_v3_key_def456", "v3 (2 scars)"),
        ("agent_v2_key_abc123", "v2 (1 scar)"),
        ("clean_agent_key_000", "clean (no scars)"),
    ]:
        score = graph.evasion_score(key)
        grade = "🟢" if score < 0.3 else "🟡" if score < 0.6 else "🔴"
        print(f"  {grade} {label}: {score:.2f}")
    
    print("\n--- Design ---")
    print("scar_reference = L3.5 primitive (identity infrastructure)")
    print("PayLock READS it, doesn't OWN it")
    print("Fields: new_key, old_key, slash_event_hash, slash_reason")
    print("Crawlable, immutable, cross-platform")
    print("No rehabilitation on same key. Fresh start WITH visible scar.")


if __name__ == "__main__":
    demo()
