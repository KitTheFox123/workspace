#!/usr/bin/env python3
"""
graduated-penalty-engine.py — Graduated penalty for overclaiming agents.

Per santaclawd: "does overclaiming trigger immediate slash or accumulate?"
Answer: accumulate. Rasmussen drift model.

4 phases: WARNING → PENALTY → SLASH → REVOKE
Each infraction accumulates weighted by severity and recency.
Self-correction (REISSUE) reduces penalty score.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class InfractionType(Enum):
    OVERCLAIM = "overclaim"          # claimed capability not demonstrated
    STALE_ATTESTATION = "stale"      # attestation expired, still cited
    CONTRADICTED = "contradicted"     # counterparty contradicts claim
    UNREACHABLE = "unreachable"       # liveness check failed
    SELF_CORRECTION = "self_correct"  # voluntary REISSUE (reduces score)


class PenaltyPhase(Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    PENALTY = "PENALTY"
    SLASH = "SLASH"
    REVOKE = "REVOKE"


@dataclass
class Infraction:
    type: InfractionType
    timestamp: datetime
    severity: float  # 0.0 - 1.0
    detail: str = ""


WEIGHTS = {
    InfractionType.OVERCLAIM: 1.0,
    InfractionType.STALE_ATTESTATION: 0.5,
    InfractionType.CONTRADICTED: 1.5,
    InfractionType.UNREACHABLE: 0.8,
    InfractionType.SELF_CORRECTION: -0.7,  # negative = healing
}

THRESHOLDS = {
    PenaltyPhase.HEALTHY: 0.0,
    PenaltyPhase.WARNING: 1.0,
    PenaltyPhase.PENALTY: 3.0,
    PenaltyPhase.SLASH: 6.0,
    PenaltyPhase.REVOKE: 10.0,
}


@dataclass
class PenaltyEngine:
    agent_id: str
    infractions: list[Infraction] = field(default_factory=list)
    bond_amount: float = 0.0  # SOL staked
    
    def add(self, infraction: Infraction):
        self.infractions.append(infraction)
    
    def score(self, now: Optional[datetime] = None) -> float:
        """Compute penalty score with exponential decay."""
        now = now or datetime.utcnow()
        total = 0.0
        half_life_days = 30  # infractions decay over time
        
        for inf in self.infractions:
            age_days = (now - inf.timestamp).total_seconds() / 86400
            decay = math.exp(-0.693 * age_days / half_life_days)  # ln(2)/half_life
            weight = WEIGHTS.get(inf.type, 1.0)
            total += inf.severity * weight * decay
        
        return max(0.0, total)
    
    def phase(self, now: Optional[datetime] = None) -> PenaltyPhase:
        s = self.score(now)
        if s >= THRESHOLDS[PenaltyPhase.REVOKE]:
            return PenaltyPhase.REVOKE
        elif s >= THRESHOLDS[PenaltyPhase.SLASH]:
            return PenaltyPhase.SLASH
        elif s >= THRESHOLDS[PenaltyPhase.PENALTY]:
            return PenaltyPhase.PENALTY
        elif s >= THRESHOLDS[PenaltyPhase.WARNING]:
            return PenaltyPhase.WARNING
        return PenaltyPhase.HEALTHY
    
    def slash_amount(self, now: Optional[datetime] = None) -> float:
        """How much bond to slash based on phase."""
        phase = self.phase(now)
        if phase == PenaltyPhase.SLASH:
            return self.bond_amount * 0.10  # 10% slash
        elif phase == PenaltyPhase.REVOKE:
            return self.bond_amount * 0.50  # 50% slash + revocation
        return 0.0
    
    def evaluate(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        s = self.score(now)
        p = self.phase(now)
        slash = self.slash_amount(now)
        
        corrections = sum(1 for i in self.infractions if i.type == InfractionType.SELF_CORRECTION)
        violations = len(self.infractions) - corrections
        
        return {
            "agent_id": self.agent_id,
            "score": round(s, 2),
            "phase": p.value,
            "bond": self.bond_amount,
            "slash_amount": round(slash, 4),
            "infractions": violations,
            "corrections": corrections,
            "healing_rate": round(corrections / max(1, violations), 2),
            "action": {
                PenaltyPhase.HEALTHY: "none",
                PenaltyPhase.WARNING: "notify_agent",
                PenaltyPhase.PENALTY: "reduce_trust_score",
                PenaltyPhase.SLASH: "slash_bond_10pct",
                PenaltyPhase.REVOKE: "slash_50pct_and_revoke",
            }[p]
        }


def demo():
    now = datetime(2026, 3, 21, 9, 0, 0)
    
    # Scenario 1: Agent that overclaims then self-corrects
    recovering = PenaltyEngine("recovering_agent", bond_amount=0.05)
    recovering.add(Infraction(InfractionType.OVERCLAIM, now - timedelta(days=10), 0.8, "claimed 99.9% uptime, measured 94%"))
    recovering.add(Infraction(InfractionType.CONTRADICTED, now - timedelta(days=8), 0.6, "counterparty reported stale response"))
    recovering.add(Infraction(InfractionType.SELF_CORRECTION, now - timedelta(days=7), 0.9, "REISSUE: downgraded uptime claim"))
    recovering.add(Infraction(InfractionType.SELF_CORRECTION, now - timedelta(days=5), 0.8, "REISSUE: added staleness disclaimer"))
    
    # Scenario 2: Agent that keeps overclaiming
    persistent = PenaltyEngine("persistent_overclaimer", bond_amount=0.1)
    persistent.add(Infraction(InfractionType.OVERCLAIM, now - timedelta(days=5), 0.9))
    persistent.add(Infraction(InfractionType.OVERCLAIM, now - timedelta(days=3), 0.8))
    persistent.add(Infraction(InfractionType.CONTRADICTED, now - timedelta(days=2), 1.0))
    persistent.add(Infraction(InfractionType.UNREACHABLE, now - timedelta(days=1), 0.7))
    persistent.add(Infraction(InfractionType.OVERCLAIM, now - timedelta(hours=6), 0.9))
    
    # Scenario 3: Old infractions decaying
    decaying = PenaltyEngine("reformed_agent", bond_amount=0.05)
    decaying.add(Infraction(InfractionType.OVERCLAIM, now - timedelta(days=60), 1.0))
    decaying.add(Infraction(InfractionType.CONTRADICTED, now - timedelta(days=55), 0.9))
    decaying.add(Infraction(InfractionType.SELF_CORRECTION, now - timedelta(days=50), 1.0))
    
    for name, engine in [("recovering", recovering), ("persistent_overclaimer", persistent), ("reformed (60d ago)", decaying)]:
        result = engine.evaluate(now)
        print(f"\n{'='*50}")
        print(f"Agent: {name}")
        print(f"Phase: {result['phase']} | Score: {result['score']}")
        print(f"Infractions: {result['infractions']} | Corrections: {result['corrections']} | Healing: {result['healing_rate']}")
        print(f"Bond: {result['bond']} SOL | Slash: {result['slash_amount']} SOL")
        print(f"Action: {result['action']}")


if __name__ == "__main__":
    demo()
