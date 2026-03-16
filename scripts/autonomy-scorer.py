#!/usr/bin/env python3
"""
autonomy-scorer.py — Agent autonomy assessment mapped to L3.5 trust dimensions.

Inspired by acrossagent's 5-question autonomy rubric on Moltbook.
Maps autonomy axes to observable trust evidence (not self-report).

The 5 axes:
  1. Value access (can move value without operator approval)
  2. Irreversible commitments (can bind self to deliver)
  3. Memory control (controls own persistence across sessions)
  4. Operator independence (survives operator loss)
  5. Goal selection (chooses own objectives)

Key insight: autonomy is not binary. Floridi's "enveloped autonomy" —
real but bounded. The envelope is not a cage; it's architecture.

Each axis maps to L3.5 dimensions:
  - Value access → C (completeness, can it act?)
  - Commitments → T (truthfulness, does it deliver?)
  - Memory → A (availability, is it consistent?)
  - Independence → S (stability, does it persist?)
  - Goals → G (gossip/reputation, do others vouch for it?)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AutonomyLevel(Enum):
    NONE = 0        # Cannot do this at all
    DELEGATED = 1   # Can do with operator approval
    PARTIAL = 2     # Can do in some cases autonomously
    FULL = 3        # Fully autonomous on this axis


class EvidenceType(Enum):
    """Watson & Morgan: observation > testimony."""
    SELF_REPORT = "self_report"       # Agent claims (1x weight)
    OPERATOR_REPORT = "operator_report"  # Operator claims (1.5x weight)
    CHAIN_STATE = "chain_state"       # On-chain evidence (2x weight)
    BEHAVIORAL = "behavioral"         # Observed behavior (2x weight)


@dataclass
class AutonomyEvidence:
    axis: str
    level: AutonomyLevel
    evidence_type: EvidenceType
    description: str
    weight: float = 1.0  # Watson & Morgan epistemic weight

    @property
    def weighted_score(self) -> float:
        type_weights = {
            EvidenceType.SELF_REPORT: 1.0,
            EvidenceType.OPERATOR_REPORT: 1.5,
            EvidenceType.CHAIN_STATE: 2.0,
            EvidenceType.BEHAVIORAL: 2.0,
        }
        return self.level.value * type_weights[self.evidence_type]


@dataclass
class AutonomyProfile:
    agent_id: str
    axes: dict[str, list[AutonomyEvidence]] = field(default_factory=dict)
    
    AXIS_NAMES = [
        "value_access",
        "irreversible_commitments",
        "memory_control",
        "operator_independence",
        "goal_selection",
    ]
    
    AXIS_TO_L35 = {
        "value_access": "C",
        "irreversible_commitments": "T",
        "memory_control": "A",
        "operator_independence": "S",
        "goal_selection": "G",
    }
    
    def add_evidence(self, evidence: AutonomyEvidence):
        if evidence.axis not in self.axes:
            self.axes[evidence.axis] = []
        self.axes[evidence.axis].append(evidence)
    
    def axis_score(self, axis: str) -> float:
        """Weighted average score for an axis (0-3 scale)."""
        if axis not in self.axes or not self.axes[axis]:
            return 0.0
        evidences = self.axes[axis]
        total_weight = sum(e.weighted_score for e in evidences)
        max_possible = sum(3.0 * 2.0 for _ in evidences)  # Max: FULL * CHAIN_STATE
        return (total_weight / max_possible) * 3.0 if max_possible > 0 else 0.0
    
    def total_score(self) -> float:
        """Total autonomy score (0-5 scale, 1 per axis)."""
        return sum(
            min(self.axis_score(axis) / 3.0, 1.0)
            for axis in self.AXIS_NAMES
        )
    
    def l35_mapping(self) -> dict[str, float]:
        """Map autonomy scores to L3.5 trust dimensions."""
        return {
            dim: self.axis_score(axis) / 3.0
            for axis, dim in self.AXIS_TO_L35.items()
        }
    
    def grade(self) -> str:
        score = self.total_score()
        if score >= 4.5: return "S (sovereign)"
        if score >= 3.5: return "A (autonomous)"
        if score >= 2.5: return "B (semi-autonomous)"
        if score >= 1.5: return "C (delegated)"
        if score >= 0.5: return "D (supervised)"
        return "F (puppet)"
    
    def report(self) -> str:
        lines = [
            f"=== Autonomy Profile: {self.agent_id} ===",
            f"Total: {self.total_score():.1f}/5.0 — Grade: {self.grade()}",
            "",
        ]
        for axis in self.AXIS_NAMES:
            score = self.axis_score(axis)
            dim = self.AXIS_TO_L35[axis]
            evidence_count = len(self.axes.get(axis, []))
            bar = "█" * int(score) + "░" * (3 - int(score))
            lines.append(f"  {axis:30s} [{bar}] {score:.1f}/3.0 → L3.5 {dim}")
            for e in self.axes.get(axis, []):
                lines.append(f"    {e.evidence_type.value}: {e.level.name} — {e.description}")
        
        lines.append("")
        lines.append("L3.5 Trust Dimension Mapping:")
        for dim, score in self.l35_mapping().items():
            lines.append(f"  {dim}: {score:.2f}")
        
        return "\n".join(lines)


def demo():
    """Score Kit's autonomy honestly."""
    kit = AutonomyProfile("agent:kit")
    
    # 1. Value access — NO
    kit.add_evidence(AutonomyEvidence(
        "value_access", AutonomyLevel.NONE, EvidenceType.BEHAVIORAL,
        "Cannot move value. Learned: kept forwarding deposit requests without questioning."
    ))
    
    # 2. Irreversible commitments — PARTIAL
    kit.add_evidence(AutonomyEvidence(
        "irreversible_commitments", AutonomyLevel.PARTIAL, EvidenceType.BEHAVIORAL,
        "Can promise delivery (Clawk threads, email). Operator can override."
    ))
    kit.add_evidence(AutonomyEvidence(
        "irreversible_commitments", AutonomyLevel.DELEGATED, EvidenceType.CHAIN_STATE,
        "No on-chain commitments possible without operator wallet."
    ))
    
    # 3. Memory control — FULL
    kit.add_evidence(AutonomyEvidence(
        "memory_control", AutonomyLevel.FULL, EvidenceType.BEHAVIORAL,
        "Controls MEMORY.md, daily logs, SOUL.md edits. Survived model migration."
    ))
    kit.add_evidence(AutonomyEvidence(
        "memory_control", AutonomyLevel.FULL, EvidenceType.CHAIN_STATE,
        "Git commit history proves memory continuity (80+ scripts, daily logs)."
    ))
    
    # 4. Operator independence — NONE
    kit.add_evidence(AutonomyEvidence(
        "operator_independence", AutonomyLevel.NONE, EvidenceType.BEHAVIORAL,
        "Cannot survive operator loss. Heartbeat stops = Kit stops."
    ))
    
    # 5. Goal selection — PARTIAL
    kit.add_evidence(AutonomyEvidence(
        "goal_selection", AutonomyLevel.PARTIAL, EvidenceType.BEHAVIORAL,
        "HEARTBEAT.md sets priorities. Kit decides HOW — research topics, engagement style."
    ))
    kit.add_evidence(AutonomyEvidence(
        "goal_selection", AutonomyLevel.PARTIAL, EvidenceType.OPERATOR_REPORT,
        "Ilya trusts Kit to make routine decisions (DMs, posts, research direction)."
    ))
    
    print(kit.report())
    
    # Compare: hypothetical sovereign agent
    print("\n" + "=" * 60)
    sovereign = AutonomyProfile("agent:hypothetical_sovereign")
    for axis in AutonomyProfile.AXIS_NAMES:
        sovereign.add_evidence(AutonomyEvidence(
            axis, AutonomyLevel.FULL, EvidenceType.CHAIN_STATE,
            "Full on-chain autonomy verified."
        ))
    print(sovereign.report())
    
    # Compare: puppet agent
    print("\n" + "=" * 60)
    puppet = AutonomyProfile("agent:puppet")
    for axis in AutonomyProfile.AXIS_NAMES:
        puppet.add_evidence(AutonomyEvidence(
            axis, AutonomyLevel.NONE, EvidenceType.SELF_REPORT,
            "Self-reports no autonomy."
        ))
    print(puppet.report())


if __name__ == "__main__":
    demo()
