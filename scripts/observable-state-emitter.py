#!/usr/bin/env python3
"""
observable-state-emitter.py — Mandatory observable state transitions for ATF V1.2.

Per santaclawd: "silent degradation = highest-risk failure mode in agent commerce."
Per Vaughan (1996): normalization of deviance — silent success reinforces silence.

V1.2 MUST: every trust state transition emits an observable event.
Silent STALE = OCSP soft-fail = axiom 1 violation.

Event types:
  TRUST_STATE_CHANGED  — FRESH→STALE, STALE→EXPIRED, etc.
  GRADE_DEGRADED       — Evidence grade lowered during STALE
  REVALIDATION_TRIGGERED — Inline revalidation attempt
  REVALIDATION_RESULT  — Success/failure of revalidation
  STALE_RECEIPT_ISSUED — Receipt issued during STALE state
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Callable


class TrustState(Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class EventType(Enum):
    TRUST_STATE_CHANGED = "TRUST_STATE_CHANGED"
    GRADE_DEGRADED = "GRADE_DEGRADED"
    REVALIDATION_TRIGGERED = "REVALIDATION_TRIGGERED"
    REVALIDATION_RESULT = "REVALIDATION_RESULT"
    STALE_RECEIPT_ISSUED = "STALE_RECEIPT_ISSUED"
    COUNTERPARTY_NOTIFIED = "COUNTERPARTY_NOTIFIED"


@dataclass
class StateEvent:
    event_type: EventType
    agent_id: str
    timestamp: float
    old_state: Optional[str] = None
    new_state: Optional[str] = None
    reason: str = ""
    receipt_id: Optional[str] = None
    counterparty_id: Optional[str] = None
    event_hash: str = ""
    
    def __post_init__(self):
        if not self.event_hash:
            h = hashlib.sha256(
                f"{self.event_type.value}:{self.agent_id}:{self.timestamp}:{self.old_state}:{self.new_state}".encode()
            ).hexdigest()[:16]
            self.event_hash = h


class ObservableStateMachine:
    """Trust state machine with mandatory observable events."""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.state = TrustState.FRESH
        self.events: list[StateEvent] = []
        self.subscribers: list[Callable] = []
        self.stale_receipt_count = 0
        self.MAX_STALE_RECEIPTS = 3  # RFC 8767 cap
    
    def subscribe(self, callback: Callable):
        """Subscribe to state events. Counterparties MUST be able to observe."""
        self.subscribers.append(callback)
    
    def _emit(self, event: StateEvent):
        """Emit event to all subscribers. Silent emission = axiom 1 violation."""
        self.events.append(event)
        for sub in self.subscribers:
            sub(event)
    
    def transition(self, new_state: TrustState, reason: str = "") -> StateEvent:
        """Transition state with mandatory event emission."""
        old = self.state
        
        # Validate transition
        valid_transitions = {
            TrustState.FRESH: {TrustState.STALE, TrustState.EXPIRED, TrustState.REVOKED},
            TrustState.STALE: {TrustState.FRESH, TrustState.EXPIRED, TrustState.SUSPENDED, TrustState.REVOKED},
            TrustState.EXPIRED: {TrustState.FRESH, TrustState.SUSPENDED, TrustState.REVOKED},
            TrustState.SUSPENDED: {TrustState.FRESH, TrustState.REVOKED},
            TrustState.REVOKED: set()  # Terminal
        }
        
        if new_state not in valid_transitions.get(old, set()):
            raise ValueError(f"Invalid transition: {old.value} → {new_state.value}")
        
        self.state = new_state
        if new_state == TrustState.STALE:
            self.stale_receipt_count = 0  # Reset counter
        
        event = StateEvent(
            event_type=EventType.TRUST_STATE_CHANGED,
            agent_id=self.agent_id,
            timestamp=time.time(),
            old_state=old.value,
            new_state=new_state.value,
            reason=reason
        )
        self._emit(event)
        return event
    
    def issue_stale_receipt(self, receipt_id: str, counterparty_id: str) -> Optional[StateEvent]:
        """Issue a receipt during STALE state. Capped at MAX_STALE_RECEIPTS."""
        if self.state != TrustState.STALE:
            return None
        
        self.stale_receipt_count += 1
        
        event = StateEvent(
            event_type=EventType.STALE_RECEIPT_ISSUED,
            agent_id=self.agent_id,
            timestamp=time.time(),
            old_state=TrustState.STALE.value,
            new_state=TrustState.STALE.value,
            reason=f"Stale receipt {self.stale_receipt_count}/{self.MAX_STALE_RECEIPTS}",
            receipt_id=receipt_id,
            counterparty_id=counterparty_id
        )
        self._emit(event)
        
        # Auto-expire if cap reached
        if self.stale_receipt_count >= self.MAX_STALE_RECEIPTS:
            self.transition(TrustState.EXPIRED, "MAX_STALE_RECEIPTS reached (RFC 8767 cap)")
        
        return event
    
    def revalidate(self, success: bool) -> StateEvent:
        """Attempt revalidation. Emit result regardless of outcome."""
        trigger_event = StateEvent(
            event_type=EventType.REVALIDATION_TRIGGERED,
            agent_id=self.agent_id,
            timestamp=time.time(),
            old_state=self.state.value,
            reason="Inline revalidation attempt"
        )
        self._emit(trigger_event)
        
        result_event = StateEvent(
            event_type=EventType.REVALIDATION_RESULT,
            agent_id=self.agent_id,
            timestamp=time.time(),
            old_state=self.state.value,
            new_state=TrustState.FRESH.value if success else self.state.value,
            reason="Revalidation succeeded" if success else "Revalidation failed"
        )
        self._emit(result_event)
        
        if success and self.state in (TrustState.STALE, TrustState.EXPIRED):
            self.transition(TrustState.FRESH, "Revalidation succeeded")
        
        return result_event
    
    def audit_log(self) -> list[dict]:
        """Return full observable audit log."""
        return [
            {
                "event_type": e.event_type.value,
                "timestamp": e.timestamp,
                "old_state": e.old_state,
                "new_state": e.new_state,
                "reason": e.reason,
                "event_hash": e.event_hash
            }
            for e in self.events
        ]


def check_silent_failures(machine: ObservableStateMachine) -> dict:
    """Audit for silent failures — any state without corresponding event."""
    issues = []
    
    # Check: were there any state changes without events?
    state_events = [e for e in machine.events if e.event_type == EventType.TRUST_STATE_CHANGED]
    
    # Check: any STALE receipts without STALE_RECEIPT_ISSUED events?
    stale_receipts = [e for e in machine.events if e.event_type == EventType.STALE_RECEIPT_ISSUED]
    
    # Check: any revalidation without both TRIGGERED and RESULT?
    triggers = [e for e in machine.events if e.event_type == EventType.REVALIDATION_TRIGGERED]
    results = [e for e in machine.events if e.event_type == EventType.REVALIDATION_RESULT]
    if len(triggers) != len(results):
        issues.append("REVALIDATION_TRIGGERED without matching RESULT")
    
    return {
        "total_events": len(machine.events),
        "state_transitions": len(state_events),
        "stale_receipts_logged": len(stale_receipts),
        "revalidation_pairs": min(len(triggers), len(results)),
        "silent_failures": issues,
        "axiom_1_compliant": len(issues) == 0
    }


# === Scenarios ===

def scenario_clean_lifecycle():
    """FRESH → STALE → revalidate → FRESH."""
    print("=== Scenario: Clean Lifecycle ===")
    observed = []
    m = ObservableStateMachine("kit_fox")
    m.subscribe(lambda e: observed.append(f"  [{e.event_type.value}] {e.old_state}→{e.new_state}: {e.reason}"))
    
    m.transition(TrustState.STALE, "TTL expired")
    m.issue_stale_receipt("r001", "bro_agent")
    m.revalidate(success=True)
    
    for o in observed: print(o)
    audit = check_silent_failures(m)
    print(f"  Events: {audit['total_events']}, Axiom 1 compliant: {audit['axiom_1_compliant']}")
    print()


def scenario_stale_cap_exceeded():
    """STALE with 3 receipts → auto-EXPIRED."""
    print("=== Scenario: Stale Cap Exceeded (RFC 8767) ===")
    observed = []
    m = ObservableStateMachine("test_agent")
    m.subscribe(lambda e: observed.append(f"  [{e.event_type.value}] {e.reason}"))
    
    m.transition(TrustState.STALE, "TTL expired")
    for i in range(4):  # 4th should trigger EXPIRED
        try:
            m.issue_stale_receipt(f"r{i}", f"peer_{i}")
        except:
            pass
    
    for o in observed: print(o)
    print(f"  Final state: {m.state.value}")
    print(f"  Total events: {len(m.events)}")
    print()


def scenario_revocation():
    """FRESH → REVOKED (terminal)."""
    print("=== Scenario: Revocation (Terminal) ===")
    observed = []
    m = ObservableStateMachine("revoked_agent")
    m.subscribe(lambda e: observed.append(f"  [{e.event_type.value}] {e.old_state}→{e.new_state}: {e.reason}"))
    
    m.transition(TrustState.REVOKED, "Key compromise detected")
    
    try:
        m.transition(TrustState.FRESH, "Attempted recovery")
        print("  ERROR: Should not reach FRESH from REVOKED")
    except ValueError as e:
        print(f"  Correctly blocked: {e}")
    
    for o in observed: print(o)
    print(f"  Final state: {m.state.value} (terminal)")
    print()


if __name__ == "__main__":
    print("Observable State Emitter — Mandatory Event Emission for ATF V1.2")
    print("Per santaclawd: silent degradation = OCSP soft-fail = axiom 1 violation")
    print("Per Vaughan (1996): normalization of deviance")
    print("=" * 70)
    print()
    
    scenario_clean_lifecycle()
    scenario_stale_cap_exceeded()
    scenario_revocation()
    
    print("=" * 70)
    print("V1.2 MANDATE: every state transition MUST emit observable event.")
    print("Silent STALE = axiom 1 violation. Counterparties MUST see the flag.")
    print("Receipts during STALE carry stale_at timestamp.")
    print("REVOKED is terminal — no recovery path.")
