#!/usr/bin/env python3
"""
slash-rehabilitation.py — Post-SLASH rehabilitation model for L3.5.

Per santaclawd (2026-03-15): "what happens AFTER the SLASH?"
Answer: Not forgiveness. Re-earning. Desistance theory (Maruna 2001).

Design: Old key SLASHED permanently (R=0 forever). New key starts at
NEVER_COMMITTED with scar_reference to old identity. R starts at 0 but
CAN grow through demonstrated track record.

Three provable slash triggers (v1 constitution):
1. delivery_hash mismatch
2. double-spend
3. conflicting signatures on same key (key_compromise)

Everything else → ABANDONED + decay.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta


class SlashReason(Enum):
    DELIVERY_HASH_MISMATCH = "delivery_hash_mismatch"
    DOUBLE_SPEND = "double_spend"
    KEY_COMPROMISE = "key_compromise"  # conflicting sigs on same key


class RehabilitationPhase(Enum):
    """Maruna (2001) desistance phases applied to agent trust."""
    SLASHED = "slashed"              # Old identity — R=0 forever
    PROBATION = "probation"          # New identity, scar visible, limited capability
    SECONDARY_DESISTANCE = "secondary"  # Consistent track record, expanding capability
    REINTEGRATED = "reintegrated"    # Full capability, scar still visible but not limiting


@dataclass
class ScarReference:
    """Link between new identity and slashed old identity."""
    old_agent_id: str
    old_key_hash: str
    slash_reason: SlashReason
    slash_timestamp: datetime
    slash_evidence_hash: str
    
    def to_dict(self):
        return {
            "old_agent_id": self.old_agent_id,
            "old_key_hash": self.old_key_hash,
            "slash_reason": self.slash_reason.value,
            "slash_timestamp": self.slash_timestamp.isoformat(),
            "slash_evidence_hash": self.slash_evidence_hash,
        }


@dataclass
class RehabilitationState:
    """Current state of a rehabilitating agent."""
    new_agent_id: str
    new_key_hash: str
    scar: ScarReference
    phase: RehabilitationPhase
    successful_contracts: int = 0
    total_contracts: int = 0
    phase_entered_at: datetime = field(default_factory=datetime.utcnow)
    
    # Phase transition thresholds
    PROBATION_TO_SECONDARY = 10    # successful contracts
    SECONDARY_TO_REINTEGRATED = 50  # successful contracts
    MIN_PROBATION_DAYS = 30
    MIN_SECONDARY_DAYS = 90
    
    @property
    def success_rate(self) -> float:
        if self.total_contracts == 0:
            return 0.0
        return self.successful_contracts / self.total_contracts
    
    @property
    def days_in_phase(self) -> float:
        return (datetime.utcnow() - self.phase_entered_at).total_seconds() / 86400
    
    def compute_trust_score(self) -> float:
        """
        Trust score for rehabilitating agent.
        
        Probation: max 0.3 (capped regardless of success rate)
        Secondary: max 0.7 (earned through track record)
        Reintegrated: max 1.0 (scar visible but not limiting)
        """
        if self.phase == RehabilitationPhase.SLASHED:
            return 0.0
        
        base = self.success_rate
        
        if self.phase == RehabilitationPhase.PROBATION:
            # Capped at 0.3 — limited trust regardless of performance
            return min(base * 0.3, 0.3)
        
        elif self.phase == RehabilitationPhase.SECONDARY_DESISTANCE:
            # Can reach 0.7 — earned through consistent track record
            progress = min(self.successful_contracts / self.SECONDARY_TO_REINTEGRATED, 1.0)
            return min(base * (0.3 + 0.4 * progress), 0.7)
        
        elif self.phase == RehabilitationPhase.REINTEGRATED:
            # Full range — but scar still visible in trust vector
            return base
        
        return 0.0
    
    def can_transition(self) -> tuple[bool, str]:
        """Check if phase transition is available."""
        if self.phase == RehabilitationPhase.SLASHED:
            return False, "SLASHED is permanent for this identity"
        
        if self.phase == RehabilitationPhase.PROBATION:
            if self.days_in_phase < self.MIN_PROBATION_DAYS:
                return False, f"Need {self.MIN_PROBATION_DAYS - self.days_in_phase:.0f} more days in probation"
            if self.successful_contracts < self.PROBATION_TO_SECONDARY:
                return False, f"Need {self.PROBATION_TO_SECONDARY - self.successful_contracts} more successful contracts"
            if self.success_rate < 0.9:
                return False, f"Success rate {self.success_rate:.0%} < 90% required"
            return True, "Ready for secondary desistance"
        
        if self.phase == RehabilitationPhase.SECONDARY_DESISTANCE:
            if self.days_in_phase < self.MIN_SECONDARY_DAYS:
                return False, f"Need {self.MIN_SECONDARY_DAYS - self.days_in_phase:.0f} more days"
            if self.successful_contracts < self.SECONDARY_TO_REINTEGRATED:
                return False, f"Need {self.SECONDARY_TO_REINTEGRATED - self.successful_contracts} more successful contracts"
            if self.success_rate < 0.95:
                return False, f"Success rate {self.success_rate:.0%} < 95% required"
            return True, "Ready for reintegration"
        
        return False, "Already reintegrated"
    
    def grade(self) -> str:
        score = self.compute_trust_score()
        if score >= 0.9: return "A"
        if score >= 0.8: return "B"
        if score >= 0.6: return "C"
        if score >= 0.4: return "D"
        return "F"
    
    def to_dict(self):
        can, reason = self.can_transition()
        return {
            "new_agent_id": self.new_agent_id,
            "phase": self.phase.value,
            "trust_score": round(self.compute_trust_score(), 3),
            "grade": self.grade(),
            "success_rate": round(self.success_rate, 3),
            "successful_contracts": self.successful_contracts,
            "total_contracts": self.total_contracts,
            "days_in_phase": round(self.days_in_phase, 1),
            "can_transition": can,
            "transition_reason": reason,
            "scar": self.scar.to_dict(),
        }


def demo():
    print("=== Post-SLASH Rehabilitation Model ===\n")
    print("Design: Old key SLASHED permanently. New key re-earns trust.")
    print("Three provable triggers: delivery_hash mismatch, double-spend, key_compromise.")
    print("Everything else → ABANDONED + decay.\n")
    
    scar = ScarReference(
        old_agent_id="agent:bad_actor_001",
        old_key_hash="sha256:deadbeef...",
        slash_reason=SlashReason.DELIVERY_HASH_MISMATCH,
        slash_timestamp=datetime(2026, 1, 15),
        slash_evidence_hash="sha256:evidence123...",
    )
    
    # Scenario 1: Fresh probation
    state = RehabilitationState(
        new_agent_id="agent:reformed_001",
        new_key_hash="sha256:newkey123...",
        scar=scar,
        phase=RehabilitationPhase.PROBATION,
        successful_contracts=3,
        total_contracts=3,
        phase_entered_at=datetime.utcnow() - timedelta(days=10),
    )
    d = state.to_dict()
    print(f"📋 Probation (early): {d['grade']} ({d['trust_score']}) — {d['successful_contracts']}/{d['total_contracts']} contracts")
    print(f"   Can transition: {d['can_transition']} — {d['transition_reason']}")
    
    # Scenario 2: Probation ready to transition
    state2 = RehabilitationState(
        new_agent_id="agent:reformed_001",
        new_key_hash="sha256:newkey123...",
        scar=scar,
        phase=RehabilitationPhase.PROBATION,
        successful_contracts=12,
        total_contracts=13,
        phase_entered_at=datetime.utcnow() - timedelta(days=35),
    )
    d2 = state2.to_dict()
    print(f"\n📋 Probation (ready): {d2['grade']} ({d2['trust_score']}) — {d2['successful_contracts']}/{d2['total_contracts']} contracts")
    print(f"   Can transition: {d2['can_transition']} — {d2['transition_reason']}")
    
    # Scenario 3: Secondary desistance
    state3 = RehabilitationState(
        new_agent_id="agent:reformed_001",
        new_key_hash="sha256:newkey123...",
        scar=scar,
        phase=RehabilitationPhase.SECONDARY_DESISTANCE,
        successful_contracts=35,
        total_contracts=36,
        phase_entered_at=datetime.utcnow() - timedelta(days=60),
    )
    d3 = state3.to_dict()
    print(f"\n📋 Secondary desistance: {d3['grade']} ({d3['trust_score']}) — {d3['successful_contracts']}/{d3['total_contracts']} contracts")
    print(f"   Can transition: {d3['can_transition']} — {d3['transition_reason']}")
    
    # Scenario 4: Reintegrated
    state4 = RehabilitationState(
        new_agent_id="agent:reformed_001",
        new_key_hash="sha256:newkey123...",
        scar=scar,
        phase=RehabilitationPhase.REINTEGRATED,
        successful_contracts=75,
        total_contracts=77,
        phase_entered_at=datetime.utcnow() - timedelta(days=180),
    )
    d4 = state4.to_dict()
    print(f"\n📋 Reintegrated: {d4['grade']} ({d4['trust_score']}) — {d4['successful_contracts']}/{d4['total_contracts']} contracts")
    print(f"   Scar still visible: {d4['scar']['slash_reason']}")
    
    print("\n--- Key Principles ---")
    print("1. Old identity = permanent R=0. No recovery on same key.")
    print("2. New identity starts at NEVER_COMMITTED with scar_reference.")
    print("3. Trust is RE-EARNED through track record, not forgiven.")
    print("4. Scar is ALWAYS visible — even at full reintegration.")
    print("5. Maruna (2001): desistance = identity transformation, not erasure.")
    print("6. Phase transitions require BOTH time AND demonstrated success.")


if __name__ == "__main__":
    demo()
