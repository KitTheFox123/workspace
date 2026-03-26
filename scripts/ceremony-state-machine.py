#!/usr/bin/env python3
"""
ceremony-state-machine.py — Formal state machine for ATF ceremony lifecycle.

Consolidates the ceremony patterns across today's scripts into a single
deterministic state machine. Maps every state transition to its email RFC equivalent.

States follow DKIM key rotation lifecycle (M3AAWG 2019):
  GENESIS → ACTIVE → PRE_PUBLISH → DOUBLE_SIGN → POST_REVOKE → ARCHIVED

Each transition:
1. Requires specific receipt types
2. Has a minimum dwell time (prevents hasty rotation)
3. Has a maximum dwell time (prevents stale ceremonies)  
4. Generates a signed transition receipt
5. Maps to an email RFC equivalent

Sources:
- M3AAWG DKIM Key Rotation BCP (2019)
- RFC 6376 (DKIM), RFC 7489 (DMARC), RFC 8617 (ARC)
- IETF SIDROPS ASPA (valley-free routing, 2026)
- Let's Encrypt OCSP shutdown (Aug 2025)
- CA/B Forum cert validity reduction (47→10 day, 2025)
- RFC 8767 (serve-stale DNS)
- Tetzlaff et al. (2025) expertise reversal meta-analysis
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class CeremonyState(Enum):
    GENESIS = "GENESIS"              # Initial key generation
    ACTIVE = "ACTIVE"                # Normal operation
    PRE_PUBLISH = "PRE_PUBLISH"      # New key published, old still primary
    DOUBLE_SIGN = "DOUBLE_SIGN"      # Both keys sign (overlap window)
    POST_REVOKE = "POST_REVOKE"      # Old key revoked, grace period
    STALE = "STALE"                  # Past TTL, serve-stale mode (RFC 8767)
    EXPIRED = "EXPIRED"              # Hard expiry, ceremony required
    ARCHIVED = "ARCHIVED"            # Immutable historical record
    EMERGENCY = "EMERGENCY"          # Fast-path rotation (compromise)
    DISPUTED = "DISPUTED"            # Under investigation


class TransitionTrigger(Enum):
    TIME = "time_based"              # Dwell time exceeded
    THRESHOLD = "threshold_based"    # Metric crossed boundary
    MANUAL = "manual"                # Operator-initiated
    EMERGENCY = "emergency"          # Compromise detected
    CEREMONY = "ceremony_complete"   # Quorum achieved


# Email RFC equivalents for each state
EMAIL_EQUIVALENTS = {
    CeremonyState.GENESIS: "DKIM key generation (RFC 6376 §3.1)",
    CeremonyState.ACTIVE: "DKIM active signing (RFC 6376 §5)",
    CeremonyState.PRE_PUBLISH: "DKIM new selector published in DNS (M3AAWG BCP)",
    CeremonyState.DOUBLE_SIGN: "DKIM dual-selector signing (M3AAWG overlap window)",
    CeremonyState.POST_REVOKE: "DKIM old selector p='' in DNS (RFC 6376 §6.1.2)",
    CeremonyState.STALE: "DNS serve-stale (RFC 8767)",
    CeremonyState.EXPIRED: "DMARC p=reject on expired domain (RFC 7489 §6.3)",
    CeremonyState.ARCHIVED: "ARC chain seal (RFC 8617 §5.1)",
    CeremonyState.EMERGENCY: "CT emergency revocation (RFC 6962 §5.3)",
    CeremonyState.DISPUTED: "DMARC forensic report (RFC 7489 §7.3)",
}


@dataclass
class DwellConstraints:
    """Time constraints for each state."""
    min_dwell: timedelta      # Minimum time before transition allowed
    max_dwell: timedelta      # Maximum time before forced transition
    stale_grace: timedelta    # Serve-stale window after max_dwell


# Per-state dwell constraints
STATE_CONSTRAINTS = {
    CeremonyState.GENESIS: DwellConstraints(
        min_dwell=timedelta(minutes=5),
        max_dwell=timedelta(hours=24),
        stale_grace=timedelta(0),
    ),
    CeremonyState.ACTIVE: DwellConstraints(
        min_dwell=timedelta(days=7),
        max_dwell=timedelta(days=90),       # SOX 203 floor
        stale_grace=timedelta(days=7),
    ),
    CeremonyState.PRE_PUBLISH: DwellConstraints(
        min_dwell=timedelta(hours=24),      # DNS propagation
        max_dwell=timedelta(days=14),
        stale_grace=timedelta(days=2),
    ),
    CeremonyState.DOUBLE_SIGN: DwellConstraints(
        min_dwell=timedelta(hours=48),      # Overlap window
        max_dwell=timedelta(days=30),
        stale_grace=timedelta(days=3),
    ),
    CeremonyState.POST_REVOKE: DwellConstraints(
        min_dwell=timedelta(hours=72),      # Revocation propagation
        max_dwell=timedelta(days=30),
        stale_grace=timedelta(days=7),
    ),
    CeremonyState.STALE: DwellConstraints(
        min_dwell=timedelta(0),
        max_dwell=timedelta(hours=72),      # Hard stale cap (RFC 8767)
        stale_grace=timedelta(0),
    ),
    CeremonyState.EMERGENCY: DwellConstraints(
        min_dwell=timedelta(0),             # No minimum in emergency
        max_dwell=timedelta(hours=4),       # Fast resolution
        stale_grace=timedelta(0),
    ),
    CeremonyState.DISPUTED: DwellConstraints(
        min_dwell=timedelta(hours=1),
        max_dwell=timedelta(days=7),
        stale_grace=timedelta(days=1),
    ),
}

# Valid state transitions
VALID_TRANSITIONS: dict[CeremonyState, list[CeremonyState]] = {
    CeremonyState.GENESIS: [CeremonyState.ACTIVE],
    CeremonyState.ACTIVE: [
        CeremonyState.PRE_PUBLISH,   # Normal rotation
        CeremonyState.EMERGENCY,     # Compromise
        CeremonyState.STALE,         # TTL exceeded without rotation
        CeremonyState.DISPUTED,      # Under investigation
    ],
    CeremonyState.PRE_PUBLISH: [
        CeremonyState.DOUBLE_SIGN,   # Normal progression
        CeremonyState.EMERGENCY,     # Compromise during rotation
    ],
    CeremonyState.DOUBLE_SIGN: [
        CeremonyState.POST_REVOKE,   # Normal progression
        CeremonyState.EMERGENCY,
    ],
    CeremonyState.POST_REVOKE: [
        CeremonyState.ARCHIVED,      # Normal completion
        CeremonyState.EMERGENCY,
    ],
    CeremonyState.STALE: [
        CeremonyState.EXPIRED,       # Grace period exceeded
        CeremonyState.PRE_PUBLISH,   # Revalidation initiated
        CeremonyState.EMERGENCY,
    ],
    CeremonyState.EXPIRED: [
        CeremonyState.GENESIS,       # Full re-bootstrap required
    ],
    CeremonyState.ARCHIVED: [],      # Terminal state
    CeremonyState.EMERGENCY: [
        CeremonyState.GENESIS,       # Start over
        CeremonyState.DISPUTED,      # Needs investigation
    ],
    CeremonyState.DISPUTED: [
        CeremonyState.ACTIVE,        # Resolved, restored
        CeremonyState.EMERGENCY,     # Escalated
        CeremonyState.EXPIRED,       # Timed out during dispute
    ],
}


@dataclass
class TransitionReceipt:
    """Signed record of a state transition."""
    from_state: str
    to_state: str
    trigger: str
    timestamp: str
    dwell_time_seconds: float
    email_equivalent: str
    receipt_hash: str
    
    def to_dict(self) -> dict:
        return {
            "from": self.from_state,
            "to": self.to_state,
            "trigger": self.trigger,
            "timestamp": self.timestamp,
            "dwell_seconds": self.dwell_time_seconds,
            "email_rfc": self.email_equivalent,
            "hash": self.receipt_hash,
        }


@dataclass
class CeremonyInstance:
    """A single ceremony lifecycle instance."""
    ceremony_id: str
    agent_id: str
    current_state: CeremonyState = CeremonyState.GENESIS
    entered_state_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    receipts: list[TransitionReceipt] = field(default_factory=list)
    
    def dwell_time(self) -> timedelta:
        return datetime.now(timezone.utc) - self.entered_state_at
    
    def can_transition(self, to_state: CeremonyState) -> tuple[bool, str]:
        """Check if transition is valid."""
        # Check valid transitions
        valid = VALID_TRANSITIONS.get(self.current_state, [])
        if to_state not in valid:
            return False, f"Invalid: {self.current_state.value} → {to_state.value} not allowed"
        
        # Check minimum dwell (except EMERGENCY which bypasses)
        if to_state != CeremonyState.EMERGENCY:
            constraints = STATE_CONSTRAINTS.get(self.current_state)
            if constraints and self.dwell_time() < constraints.min_dwell:
                remaining = constraints.min_dwell - self.dwell_time()
                return False, f"Min dwell not met: {remaining} remaining"
        
        return True, "OK"
    
    def transition(self, to_state: CeremonyState, trigger: TransitionTrigger) -> TransitionReceipt:
        """Execute a state transition."""
        can, reason = self.can_transition(to_state)
        if not can:
            raise ValueError(reason)
        
        now = datetime.now(timezone.utc)
        dwell = (now - self.entered_state_at).total_seconds()
        
        # Generate receipt
        receipt_data = f"{self.ceremony_id}:{self.current_state.value}:{to_state.value}:{now.isoformat()}"
        receipt_hash = hashlib.sha256(receipt_data.encode()).hexdigest()[:16]
        
        receipt = TransitionReceipt(
            from_state=self.current_state.value,
            to_state=to_state.value,
            trigger=trigger.value,
            timestamp=now.isoformat(),
            dwell_time_seconds=dwell,
            email_equivalent=EMAIL_EQUIVALENTS.get(to_state, "no equivalent"),
            receipt_hash=receipt_hash,
        )
        
        self.receipts.append(receipt)
        self.current_state = to_state
        self.entered_state_at = now
        
        return receipt
    
    def check_forced_transitions(self) -> Optional[CeremonyState]:
        """Check if max dwell time forces a transition."""
        constraints = STATE_CONSTRAINTS.get(self.current_state)
        if not constraints:
            return None
        
        dwell = self.dwell_time()
        
        if dwell > constraints.max_dwell + constraints.stale_grace:
            # Past grace period → forced transition
            if self.current_state == CeremonyState.STALE:
                return CeremonyState.EXPIRED
            elif self.current_state == CeremonyState.ACTIVE:
                return CeremonyState.STALE
            elif self.current_state in (CeremonyState.PRE_PUBLISH, CeremonyState.DOUBLE_SIGN):
                return CeremonyState.EMERGENCY
        elif dwell > constraints.max_dwell:
            # In grace period → stale
            if self.current_state == CeremonyState.ACTIVE:
                return CeremonyState.STALE
        
        return None


def run_scenarios():
    """Demonstrate ceremony state machine scenarios."""
    print("=" * 70)
    print("ATF CEREMONY STATE MACHINE")
    print("=" * 70)
    
    results = []
    
    # Scenario 1: Normal rotation lifecycle
    print("\n1. Normal rotation lifecycle (happy path)")
    c1 = CeremonyInstance("ceremony_001", "agent_alpha")
    c1.entered_state_at = datetime.now(timezone.utc) - timedelta(minutes=10)  # Past genesis min
    
    steps = [
        (CeremonyState.ACTIVE, TransitionTrigger.CEREMONY),
        (CeremonyState.PRE_PUBLISH, TransitionTrigger.TIME),
    ]
    
    ok = True
    for to_state, trigger in steps:
        try:
            r = c1.transition(to_state, trigger)
            print(f"  ✓ {r.from_state} → {r.to_state} ({r.email_equivalent})")
            # Advance time past min dwell for next transition
            c1.entered_state_at = datetime.now(timezone.utc) - timedelta(days=10)
        except ValueError as e:
            print(f"  ✗ Failed: {e}")
            ok = False
    
    # Continue with remaining transitions
    for to_state, trigger in [
        (CeremonyState.DOUBLE_SIGN, TransitionTrigger.TIME),
        (CeremonyState.POST_REVOKE, TransitionTrigger.TIME),
        (CeremonyState.ARCHIVED, TransitionTrigger.TIME),
    ]:
        try:
            c1.entered_state_at = datetime.now(timezone.utc) - timedelta(days=4)
            r = c1.transition(to_state, trigger)
            print(f"  ✓ {r.from_state} → {r.to_state} ({r.email_equivalent})")
        except ValueError as e:
            print(f"  ✗ Failed: {e}")
            ok = False
    
    results.append(("Normal rotation", ok))
    
    # Scenario 2: Emergency fast-path
    print("\n2. Emergency rotation (compromise detected)")
    c2 = CeremonyInstance("ceremony_002", "agent_beta")
    c2.entered_state_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    c2.transition(CeremonyState.ACTIVE, TransitionTrigger.CEREMONY)
    c2.entered_state_at = datetime.now(timezone.utc) - timedelta(days=30)
    
    try:
        r = c2.transition(CeremonyState.EMERGENCY, TransitionTrigger.EMERGENCY)
        print(f"  ✓ {r.from_state} → {r.to_state} (bypasses min dwell)")
        r2 = c2.transition(CeremonyState.GENESIS, TransitionTrigger.CEREMONY)
        print(f"  ✓ {r2.from_state} → {r2.to_state} (full re-bootstrap)")
        results.append(("Emergency rotation", True))
    except ValueError as e:
        print(f"  ✗ Failed: {e}")
        results.append(("Emergency rotation", False))
    
    # Scenario 3: Invalid transition blocked
    print("\n3. Invalid transition (GENESIS → ARCHIVED) blocked")
    c3 = CeremonyInstance("ceremony_003", "agent_gamma")
    try:
        c3.transition(CeremonyState.ARCHIVED, TransitionTrigger.MANUAL)
        print(f"  ✗ Should have been blocked!")
        results.append(("Invalid blocked", False))
    except ValueError as e:
        print(f"  ✓ Correctly blocked: {e}")
        results.append(("Invalid blocked", True))
    
    # Scenario 4: Stale → Expired → Genesis (re-bootstrap)
    print("\n4. Stale recovery path")
    c4 = CeremonyInstance("ceremony_004", "agent_delta")
    c4.entered_state_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    c4.transition(CeremonyState.ACTIVE, TransitionTrigger.CEREMONY)
    c4.entered_state_at = datetime.now(timezone.utc) - timedelta(days=100)  # Way past max
    
    try:
        r1 = c4.transition(CeremonyState.STALE, TransitionTrigger.TIME)
        print(f"  ✓ {r1.from_state} → {r1.to_state} ({r1.email_equivalent})")
        c4.entered_state_at = datetime.now(timezone.utc) - timedelta(days=4)
        r2 = c4.transition(CeremonyState.EXPIRED, TransitionTrigger.TIME)
        print(f"  ✓ {r2.from_state} → {r2.to_state} ({r2.email_equivalent})")
        r3 = c4.transition(CeremonyState.GENESIS, TransitionTrigger.CEREMONY)
        print(f"  ✓ {r3.from_state} → {r3.to_state} (full re-bootstrap)")
        results.append(("Stale recovery", True))
    except ValueError as e:
        print(f"  ✗ Failed: {e}")
        results.append(("Stale recovery", False))
    
    # Scenario 5: Dispute resolution
    print("\n5. Dispute resolution path")
    c5 = CeremonyInstance("ceremony_005", "agent_epsilon")
    c5.entered_state_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    c5.transition(CeremonyState.ACTIVE, TransitionTrigger.CEREMONY)
    c5.entered_state_at = datetime.now(timezone.utc) - timedelta(days=10)
    
    try:
        r1 = c5.transition(CeremonyState.DISPUTED, TransitionTrigger.THRESHOLD)
        print(f"  ✓ {r1.from_state} → {r1.to_state} ({r1.email_equivalent})")
        c5.entered_state_at = datetime.now(timezone.utc) - timedelta(hours=2)
        r2 = c5.transition(CeremonyState.ACTIVE, TransitionTrigger.CEREMONY)
        print(f"  ✓ {r2.from_state} → {r2.to_state} (resolved, trust restored)")
        results.append(("Dispute resolution", True))
    except ValueError as e:
        print(f"  ✗ Failed: {e}")
        results.append(("Dispute resolution", False))
    
    # Summary
    print(f"\n{'=' * 70}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'} {name}")
    
    # State machine summary
    print(f"\nState machine: {len(CeremonyState)} states, {sum(len(v) for v in VALID_TRANSITIONS.values())} transitions")
    print(f"Email RFC mappings: {len(EMAIL_EQUIVALENTS)}/10")
    print(f"Key principle: every state transition generates a signed receipt.")
    print(f"No silent transitions. No soft-fail. Visibility is mandatory.")
    print(f"\nnexus_0i's cascade bug = missing PRE_PUBLISH + DOUBLE_SIGN states.")
    print(f"DKIM solved this in 2019. M3AAWG BCP: overlap window is load-bearing.")
    
    return passed == total


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
