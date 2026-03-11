#!/usr/bin/env python3
"""
state-transition-attester.py — Attest state transitions, not just endpoints.

Bridge exploits (Ronin 2024, Nomad, Wormhole) all broke BETWEEN checkpoints.
The deploy/upgrade itself was the unattested event. Same pattern in agent
heartbeats: the gap between beats is the attack surface.

This script models pre-transition and post-transition attestation with
gap detection for unattested state changes.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StateSnapshot:
    """Captures agent/system state at a point in time."""
    timestamp: float
    scope_hash: str       # hash of permissions/capabilities
    config_hash: str      # hash of configuration
    version: str          # software/contract version
    attestor: str         # who attested this state
    
    def digest(self) -> str:
        payload = f"{self.timestamp}:{self.scope_hash}:{self.config_hash}:{self.version}:{self.attestor}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class StateTransition:
    """A state change with pre and post attestation."""
    transition_id: str
    reason: str           # why the transition happened
    pre_state: Optional[StateSnapshot] = None
    post_state: Optional[StateSnapshot] = None
    
    @property
    def attested(self) -> bool:
        return self.pre_state is not None and self.post_state is not None
    
    @property
    def gap_type(self) -> str:
        if self.pre_state and self.post_state:
            return "FULLY_ATTESTED"
        elif self.pre_state and not self.post_state:
            return "POST_GAP"       # knew state before, didn't verify after
        elif not self.pre_state and self.post_state:
            return "PRE_GAP"        # didn't capture state before change
        else:
            return "BLIND_TRANSITION"  # no attestation at all
    
    @property
    def drift_detected(self) -> bool:
        if not self.pre_state or not self.post_state:
            return False
        return (self.pre_state.scope_hash != self.post_state.scope_hash or
                self.pre_state.config_hash != self.post_state.config_hash)
    
    def grade(self) -> str:
        gap = self.gap_type
        if gap == "FULLY_ATTESTED":
            if self.drift_detected:
                return "B"  # Attested but scope changed — review needed
            return "A"      # Clean transition
        elif gap in ("PRE_GAP", "POST_GAP"):
            return "D"      # Partial attestation
        else:
            return "F"      # Blind — this is how bridges get drained


class TransitionAuditor:
    def __init__(self):
        self.transitions: list[StateTransition] = []
    
    def record(self, transition: StateTransition):
        self.transitions.append(transition)
    
    def audit(self) -> dict:
        total = len(self.transitions)
        if total == 0:
            return {"total": 0, "grade": "F", "reason": "no transitions recorded"}
        
        grades = [t.grade() for t in self.transitions]
        gap_types = [t.gap_type for t in self.transitions]
        
        fully = gap_types.count("FULLY_ATTESTED")
        blind = gap_types.count("BLIND_TRANSITION")
        
        coverage = fully / total
        
        return {
            "total": total,
            "fully_attested": fully,
            "pre_gap": gap_types.count("PRE_GAP"),
            "post_gap": gap_types.count("POST_GAP"),
            "blind": blind,
            "coverage": round(coverage, 3),
            "grade": "A" if coverage >= 0.9 else "B" if coverage >= 0.7 else "C" if coverage >= 0.5 else "F",
            "drift_events": sum(1 for t in self.transitions if t.drift_detected),
            "worst_case": "BLIND_TRANSITION" if blind > 0 else "PARTIAL" if fully < total else "CLEAN"
        }


def demo():
    auditor = TransitionAuditor()
    
    # Transition 1: Clean upgrade (both pre and post attested)
    t1 = StateTransition(
        transition_id="T-001",
        reason="scheduled upgrade v2→v3",
        pre_state=StateSnapshot(1000.0, "abc123", "cfg001", "v2", "monitor_bot"),
        post_state=StateSnapshot(1000.5, "abc123", "cfg002", "v3", "monitor_bot")
    )
    auditor.record(t1)
    
    # Transition 2: Ronin-style — skipped pre-attestation during deploy
    t2 = StateTransition(
        transition_id="T-002",
        reason="emergency deploy (skipped initializeV3)",
        pre_state=None,  # nobody captured state before
        post_state=StateSnapshot(2000.0, "000000", "cfg003", "v4", "mev_bot")  # post-exploit observation
    )
    auditor.record(t2)
    
    # Transition 3: Nomad-style — blind transition, no attestation at all
    t3 = StateTransition(
        transition_id="T-003",
        reason="routine maintenance (uninitialized merkle root)",
        pre_state=None,
        post_state=None  # nobody checked before OR after
    )
    auditor.record(t3)
    
    # Transition 4: Agent heartbeat gap — pre but no post
    t4 = StateTransition(
        transition_id="T-004",
        reason="agent context refresh",
        pre_state=StateSnapshot(3000.0, "def456", "cfg004", "v3", "self"),
        post_state=None  # agent went silent after
    )
    auditor.record(t4)
    
    # Transition 5: Scope drift detected (attested but changed)
    t5 = StateTransition(
        transition_id="T-005",
        reason="plugin update",
        pre_state=StateSnapshot(4000.0, "ghi789", "cfg005", "v3", "monitor_bot"),
        post_state=StateSnapshot(4000.5, "CHANGED", "cfg005", "v3", "monitor_bot")  # scope changed!
    )
    auditor.record(t5)
    
    # Print results
    print("=" * 65)
    print("STATE TRANSITION ATTESTER — Bridge Exploit Pattern Analysis")
    print("=" * 65)
    
    for t in auditor.transitions:
        grade = t.grade()
        gap = t.gap_type
        drift = "DRIFT!" if t.drift_detected else "clean"
        print(f"\n  {t.transition_id} | {t.reason}")
        print(f"    Gap: {gap} | Drift: {drift} | Grade: {grade}")
        if t.pre_state:
            print(f"    Pre:  scope={t.pre_state.scope_hash[:8]} config={t.pre_state.config_hash} v={t.pre_state.version}")
        if t.post_state:
            print(f"    Post: scope={t.post_state.scope_hash[:8]} config={t.post_state.config_hash} v={t.post_state.version}")
    
    # Audit summary
    audit = auditor.audit()
    print(f"\n{'=' * 65}")
    print(f"AUDIT SUMMARY")
    print(f"  Transitions: {audit['total']}")
    print(f"  Fully attested: {audit['fully_attested']}/{audit['total']} ({audit['coverage']*100:.0f}%)")
    print(f"  Blind transitions: {audit['blind']} (CRITICAL)")
    print(f"  Scope drift events: {audit['drift_events']}")
    print(f"  Overall grade: {audit['grade']}")
    print(f"  Worst case: {audit['worst_case']}")
    
    print(f"\n{'=' * 65}")
    print("BRIDGE EXPLOIT MAPPING:")
    print("  Ronin 2024: PRE_GAP — deploy skipped initializeV3, no pre-check")
    print("  Nomad:      BLIND   — uninitialized Merkle root, zero attestation")
    print("  Wormhole:   PRE_GAP — signature check bypassed at transition")
    print("  Agent gap:  POST_GAP — heartbeat sent, then silence")
    print(f"\nThe attack surface IS the gap between checkpoints.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
