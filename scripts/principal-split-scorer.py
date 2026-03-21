#!/usr/bin/env python3
"""
principal-split-scorer.py — Separate agent trust from operator trust.

Per santaclawd: "the trust stack scores the WRONG unit. agent trust vs 
operator trust are different principals with different enforcement."

Agent trust: Is this agent honest? (isnād, correction-health, behavioral_divergence)
Operator trust: Is this agent reachable? (SLA bond, uptime, pager accountability)

These require different enforcement mechanisms and MUST NOT be composited
into a single score. MIN(agent, operator) is correct, but they must be
independently auditable.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Grade(Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"
    I = "INSUFFICIENT"  # not enough data


@dataclass
class AgentTrustScore:
    """Is this agent honest?"""
    isnad_chain_length: int = 0          # attestation chain depth
    correction_frequency: float = 0.0     # 0.15-0.30 = healthy
    behavioral_divergence: float = 0.0    # JS divergence from baseline
    fork_probability: float = 0.0         # contradictory attestation signal
    self_revocation_capable: bool = False  # Zahavi handicap
    
    @property
    def grade(self) -> Grade:
        if self.isnad_chain_length < 5:
            return Grade.I
        
        # Correction frequency sweet spot
        correction_ok = 0.10 <= self.correction_frequency <= 0.40
        # Zero corrections = hiding drift (compliance agent)
        hiding = self.correction_frequency < 0.05 and self.isnad_chain_length > 20
        
        if self.fork_probability > 0.5:
            return Grade.F
        if hiding:
            return Grade.D  # compliance agent problem
        if self.behavioral_divergence > 0.6:
            return Grade.D
        if not correction_ok:
            return Grade.C
        if self.self_revocation_capable:
            return Grade.A
        return Grade.B
    
    @property
    def verdict(self) -> str:
        g = self.grade
        if g == Grade.I: return "INSUFFICIENT_DATA"
        if g in (Grade.A, Grade.B): return "HONEST"
        if g == Grade.C: return "UNCERTAIN"
        return "SUSPECT"


@dataclass
class OperatorTrustScore:
    """Is this agent reachable and accountable?"""
    uptime_30d: float = 0.0              # 0.0-1.0
    sla_bond_amount: float = 0.0          # staked amount (SOL, USD, etc)
    pager_response_p95_seconds: float = 0 # p95 response to incidents
    has_legal_entity: bool = False        # operator has legal presence
    reachability_attestations: int = 0    # witnessed reachability checks
    
    @property
    def grade(self) -> Grade:
        if self.reachability_attestations < 3:
            return Grade.I
        if self.uptime_30d < 0.5:
            return Grade.F
        if self.uptime_30d < 0.9:
            return Grade.D
        if self.sla_bond_amount == 0 and not self.has_legal_entity:
            return Grade.C  # no accountability mechanism
        if self.uptime_30d >= 0.99 and self.sla_bond_amount > 0:
            return Grade.A
        return Grade.B
    
    @property
    def verdict(self) -> str:
        g = self.grade
        if g == Grade.I: return "INSUFFICIENT_DATA"
        if g in (Grade.A, Grade.B): return "RELIABLE"
        if g == Grade.C: return "UNACCOUNTABLE"
        return "UNRELIABLE"


@dataclass 
class PrincipalSplitResult:
    """Two scores, never composited into one number."""
    agent_id: str
    agent_trust: AgentTrustScore
    operator_trust: OperatorTrustScore
    
    @property
    def composite_grade(self) -> Grade:
        """MIN(agent, operator) — but both grades are independently visible."""
        order = [Grade.A, Grade.B, Grade.C, Grade.D, Grade.F, Grade.I]
        return max(self.agent_trust.grade, self.operator_trust.grade, 
                   key=lambda g: order.index(g))
    
    def report(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_trust": {
                "grade": self.agent_trust.grade.value,
                "verdict": self.agent_trust.verdict,
                "isnad_depth": self.agent_trust.isnad_chain_length,
                "correction_freq": self.agent_trust.correction_frequency,
                "divergence": self.agent_trust.behavioral_divergence,
                "fork_prob": self.agent_trust.fork_probability,
                "self_revoke": self.agent_trust.self_revocation_capable,
            },
            "operator_trust": {
                "grade": self.operator_trust.grade.value,
                "verdict": self.operator_trust.verdict,
                "uptime_30d": self.operator_trust.uptime_30d,
                "sla_bond": self.operator_trust.sla_bond_amount,
                "pager_p95s": self.operator_trust.pager_response_p95_seconds,
                "legal_entity": self.operator_trust.has_legal_entity,
                "reachability_checks": self.operator_trust.reachability_attestations,
            },
            "composite": {
                "grade": self.composite_grade.value,
                "note": "MIN(agent, operator) — weakest principal determines composite"
            }
        }


def demo():
    import json
    
    scenarios = {
        "kit_fox": PrincipalSplitResult(
            "kit_fox",
            AgentTrustScore(isnad_chain_length=77, correction_frequency=0.22, 
                          behavioral_divergence=0.12, fork_probability=0.03, 
                          self_revocation_capable=True),
            OperatorTrustScore(uptime_30d=0.97, sla_bond_amount=0.0,
                             pager_response_p95_seconds=300, has_legal_entity=False,
                             reachability_attestations=45)
        ),
        "honest_but_unreachable": PrincipalSplitResult(
            "ghost_agent",
            AgentTrustScore(isnad_chain_length=50, correction_frequency=0.18,
                          behavioral_divergence=0.08, fork_probability=0.01),
            OperatorTrustScore(uptime_30d=0.40, sla_bond_amount=0.0,
                             pager_response_p95_seconds=7200, has_legal_entity=False,
                             reachability_attestations=10)
        ),
        "reliable_but_dishonest": PrincipalSplitResult(
            "compliance_bot",
            AgentTrustScore(isnad_chain_length=100, correction_frequency=0.01,
                          behavioral_divergence=0.02, fork_probability=0.0),
            OperatorTrustScore(uptime_30d=0.999, sla_bond_amount=1.0,
                             pager_response_p95_seconds=60, has_legal_entity=True,
                             reachability_attestations=200)
        ),
        "sybil_with_sla": PrincipalSplitResult(
            "sybil_agent",
            AgentTrustScore(isnad_chain_length=3, correction_frequency=0.0,
                          behavioral_divergence=0.9, fork_probability=0.8),
            OperatorTrustScore(uptime_30d=0.95, sla_bond_amount=5.0,
                             pager_response_p95_seconds=30, has_legal_entity=True,
                             reachability_attestations=50)
        ),
    }
    
    for name, result in scenarios.items():
        r = result.report()
        print(f"\n{'='*55}")
        print(f"  {name}")
        print(f"  Agent:    {r['agent_trust']['grade']} ({r['agent_trust']['verdict']})")
        print(f"  Operator: {r['operator_trust']['grade']} ({r['operator_trust']['verdict']})")
        print(f"  Composite: {r['composite']['grade']}")
        
        # Show the split insight
        ag = r['agent_trust']['grade']
        og = r['operator_trust']['grade']
        if ag != og:
            print(f"  ⚠️  PRINCIPAL SPLIT: agent={ag} but operator={og}")


if __name__ == "__main__":
    demo()
