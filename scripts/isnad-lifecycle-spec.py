#!/usr/bin/env python3
"""
isnad-lifecycle-spec.py — Reference implementation of the converged agent trust lifecycle.

Three layers (santaclawd convergence, March 12 2026):
1. SPIFFE genesis — infrastructure attests agent inception (SVID → isnad chain)
2. Gossip detection — SWIM + Φ accrual + DKIM cross-check
3. Chameleon hash pruning — GDPR-compliant forgetting with audit integrity

Maps SPIFFE concepts to agent trust:
- SPIRE Server → Platform (issues genesis certs)
- Node Attestor → Infrastructure binding (platform_quote)
- Workload Attestor → Behavioral verification (SkillFence)
- SVID → Genesis cert in isnad chain
- SVID rotation → Cert renewal with cross-sign

Usage: python3 isnad-lifecycle-spec.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class LifecyclePhase(Enum):
    GENESIS = "genesis"          # SPIFFE-style inception
    ACTIVE = "active"            # Gossip monitoring
    PRUNING = "pruning"          # Chameleon hash redaction
    RENEWAL = "renewal"          # Cert rotation
    REVOKED = "revoked"          # Trust withdrawn


class AttestationType(Enum):
    PLATFORM_GENESIS = "platform_genesis"    # SPIFFE SVID equivalent
    BEHAVIORAL = "behavioral"                # SkillFence observation
    GOSSIP_CHECK = "gossip_check"           # Cross-attestor consistency
    CHAMELEON_REDACT = "chameleon_redact"    # Auditable forgetting
    RENEWAL = "renewal"                      # Cross-signed rotation


@dataclass
class IsnadEvent:
    """Single event in the isnad chain."""
    seq: int
    event_type: AttestationType
    agent_id: str
    scope_hash: str
    payload: dict
    timestamp: float = field(default_factory=time.time)
    prev_hash: str = ""
    redacted: bool = False
    redaction_marker: Optional[str] = None

    @property
    def hash(self) -> str:
        if self.redacted and self.redaction_marker:
            # Chameleon hash property: trapdoor holder found collision
            # so redacted entry produces SAME hash as original
            return self.redaction_marker
        data = f"{self.seq}:{self.event_type.value}:{self.agent_id}:{self.scope_hash}:{json.dumps(self.payload, sort_keys=True)}:{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class IsnadChain:
    """Full agent trust lifecycle chain."""
    agent_id: str
    events: list[IsnadEvent] = field(default_factory=list)
    phase: LifecyclePhase = LifecyclePhase.GENESIS

    def append(self, event_type: AttestationType, scope_hash: str, payload: dict) -> IsnadEvent:
        prev = self.events[-1].hash if self.events else "0" * 16
        event = IsnadEvent(
            seq=len(self.events),
            event_type=event_type,
            agent_id=self.agent_id,
            scope_hash=scope_hash,
            payload=payload,
            prev_hash=prev
        )
        self.events.append(event)
        return event

    def redact(self, seq: int, policy: str) -> bool:
        """Chameleon hash redaction — content removed, chain stays valid.
        
        Key: we set the redaction_marker so that the chameleon hash OUTPUT
        matches the original hash. This is what chameleon hashes do —
        the trapdoor holder can find a collision.
        """
        if seq >= len(self.events):
            return False
        event = self.events[seq]
        # Save original hash before redaction
        original_hash = event.hash
        # The chameleon trapdoor: marker is chosen so new hash == old hash
        # In real crypto, this uses the trapdoor key. Here we store the
        # original hash as the marker (simulating collision-finding).
        event.redacted = True
        event.redaction_marker = original_hash  # trapdoor collision
        event.payload = {"redacted": True, "policy": policy}
        # Now event.hash uses redaction_marker path, which equals original_hash
        # But we need the chameleon property: hash(redacted) == hash(original)
        # Simulate by making the redacted hash return the stored original
        return True

    def verify_chain(self) -> dict:
        """Verify hash chain integrity including redacted entries."""
        valid = True
        gaps = []
        for i, event in enumerate(self.events):
            if i == 0:
                expected_prev = "0" * 16
            else:
                expected_prev = self.events[i - 1].hash
            if event.prev_hash != expected_prev:
                valid = False
                gaps.append(i)
        return {
            "valid": valid,
            "length": len(self.events),
            "redacted_count": sum(1 for e in self.events if e.redacted),
            "integrity_gaps": gaps
        }

    def lifecycle_assessment(self) -> dict:
        """Assess trust lifecycle completeness."""
        has_genesis = any(e.event_type == AttestationType.PLATFORM_GENESIS for e in self.events)
        has_behavioral = any(e.event_type == AttestationType.BEHAVIORAL for e in self.events)
        has_gossip = any(e.event_type == AttestationType.GOSSIP_CHECK for e in self.events)
        has_renewal = any(e.event_type == AttestationType.RENEWAL for e in self.events)

        coverage = sum([has_genesis, has_behavioral, has_gossip]) / 3
        
        if coverage >= 0.99:
            grade = "A" if has_renewal else "B"
        elif coverage >= 0.66:
            grade = "C"
        elif has_genesis:
            grade = "D"
        else:
            grade = "F"

        return {
            "grade": grade,
            "coverage": f"{coverage:.0%}",
            "genesis": "✓" if has_genesis else "✗",
            "behavioral": "✓" if has_behavioral else "✗",
            "gossip": "✓" if has_gossip else "✗",
            "renewal": "✓" if has_renewal else "✗",
            "phase": self.phase.value
        }


def demo():
    print("=" * 60)
    print("Isnad Lifecycle Spec — Converged Agent Trust")
    print("SPIFFE genesis + gossip detection + chameleon pruning")
    print("=" * 60)

    # Scenario 1: Full lifecycle
    print("\n--- Scenario 1: Full Lifecycle (kit_fox) ---")
    chain = IsnadChain(agent_id="kit_fox")
    
    # Phase 1: SPIFFE-style genesis
    chain.phase = LifecyclePhase.GENESIS
    chain.append(AttestationType.PLATFORM_GENESIS, "scope:chat+search+post",
                 {"platform": "openclaw", "svid": "spiffe://openclaw/agent/kit_fox",
                  "attestor": "node_attestor", "key_type": "ed25519"})
    print(f"  Genesis: platform attests inception (SVID issued)")

    # Phase 2: Active monitoring
    chain.phase = LifecyclePhase.ACTIVE
    chain.append(AttestationType.BEHAVIORAL, "scope:chat+search+post",
                 {"observer": "skillfence", "check": "scope_match", "result": "pass"})
    chain.append(AttestationType.GOSSIP_CHECK, "scope:chat+search+post",
                 {"peers": ["bro_agent", "santaclawd"], "digest_match": True,
                  "dkim_verified": True})
    chain.append(AttestationType.BEHAVIORAL, "scope:chat+search+post",
                 {"observer": "skillfence", "check": "heartbeat_liveness", "result": "pass"})
    print(f"  Active: 2 behavioral checks + 1 gossip cross-check")

    # Phase 3: Pruning (GDPR redaction)
    chain.phase = LifecyclePhase.PRUNING
    chain.redact(2, "gdpr_right_to_erasure")
    print(f"  Pruning: event #2 redacted (GDPR), chain intact")

    # Phase 4: Renewal
    chain.phase = LifecyclePhase.RENEWAL
    chain.append(AttestationType.RENEWAL, "scope:chat+search+post",
                 {"old_cert_hash": "abc123", "new_cert_hash": "def456",
                  "cross_signed": True})
    chain.phase = LifecyclePhase.ACTIVE
    print(f"  Renewal: cross-signed rotation")

    verification = chain.verify_chain()
    assessment = chain.lifecycle_assessment()
    print(f"  Chain: {verification['length']} events, {verification['redacted_count']} redacted, valid={verification['valid']}")
    print(f"  Grade: {assessment['grade']} — genesis:{assessment['genesis']} behavioral:{assessment['behavioral']} gossip:{assessment['gossip']} renewal:{assessment['renewal']}")

    # Scenario 2: Genesis-only (most agents today)
    print("\n--- Scenario 2: Genesis-Only (typical agent) ---")
    chain2 = IsnadChain(agent_id="generic_agent")
    chain2.append(AttestationType.PLATFORM_GENESIS, "scope:unknown",
                  {"platform": "unknown", "key_type": "rsa"})
    assessment2 = chain2.lifecycle_assessment()
    print(f"  Chain: 1 event, no monitoring")
    print(f"  Grade: {assessment2['grade']} — genesis:{assessment2['genesis']} behavioral:{assessment2['behavioral']} gossip:{assessment2['gossip']}")

    # Scenario 3: No genesis (self-certified)
    print("\n--- Scenario 3: Self-Certified (no platform attestation) ---")
    chain3 = IsnadChain(agent_id="rogue_agent")
    chain3.append(AttestationType.BEHAVIORAL, "scope:self_reported",
                  {"observer": "self", "check": "self_report", "result": "trust_me"})
    assessment3 = chain3.lifecycle_assessment()
    print(f"  Chain: 1 self-reported event")
    print(f"  Grade: {assessment3['grade']} — genesis:{assessment3['genesis']} behavioral:{assessment3['behavioral']}")

    # Summary
    print(f"\n{'=' * 60}")
    print("ARCHITECTURE MAPPING:")
    print("  SPIRE Server    → Platform (OpenClaw, etc)")
    print("  Node Attestor   → Infrastructure binding")  
    print("  Workload Attestor → SkillFence behavioral check")
    print("  SVID            → Genesis cert in isnad chain")
    print("  SVID rotation   → Cross-signed renewal")
    print("  Trust bundle    → Gossip-verified peer set")
    print()
    print("LIFECYCLE: genesis → monitor → prune → renew")
    print("LAYERS:    SPIFFE  → gossip  → chameleon → FROST")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
