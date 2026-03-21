#!/usr/bin/env python3
"""
principal-aware-arbiter.py — Dispute resolution that attributes fault per principal.

Per santaclawd: "same observable failure, two different liable parties."
- compliance_bot: operator=A, agent=D → behavior fix needed
- ghost_agent: agent=B, operator=F → infra fix needed

L8 must diagnose WHO failed, not just THAT something failed.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Principal(Enum):
    AGENT = "agent"
    OPERATOR = "operator"
    BOTH = "both"
    NEITHER = "neither"  # external cause


class Remedy(Enum):
    BEHAVIOR_INTERVENTION = "behavior"     # agent retraining, SOUL.md update
    INFRA_FIX = "infrastructure"           # uptime, SLA, pager
    GOVERNANCE_CHANGE = "governance"       # operator policy
    QUARANTINE = "quarantine"              # isolate until resolved
    NO_ACTION = "no_action"               # false positive


@dataclass
class PrincipalScore:
    agent_score: float      # 0-1, agent trustworthiness
    operator_score: float   # 0-1, operator reliability
    
    @property
    def composite(self) -> float:
        return min(self.agent_score, self.operator_score)
    
    @property
    def liable_principal(self) -> Principal:
        if self.agent_score < 0.5 and self.operator_score < 0.5:
            return Principal.BOTH
        elif self.agent_score < 0.5:
            return Principal.AGENT
        elif self.operator_score < 0.5:
            return Principal.OPERATOR
        return Principal.NEITHER


@dataclass
class DisputeCase:
    name: str
    failure_type: str
    agent_correction_density: float   # 0-1
    agent_behavioral_drift: float     # 0-1 (higher = more drift)
    operator_uptime: float            # 0-1
    operator_response_time_hrs: float # hours to respond to incidents
    operator_sla_compliance: float    # 0-1


def score_principals(case: DisputeCase) -> PrincipalScore:
    """Score agent and operator independently."""
    # Agent score: corrections + low drift = healthy
    agent_health = case.agent_correction_density * 0.4 + (1 - case.agent_behavioral_drift) * 0.6
    
    # Operator score: uptime + responsiveness + SLA
    response_penalty = min(1.0, case.operator_response_time_hrs / 24)  # >24h = 0
    operator_health = (
        case.operator_uptime * 0.4 +
        (1 - response_penalty) * 0.3 +
        case.operator_sla_compliance * 0.3
    )
    
    return PrincipalScore(
        agent_score=round(agent_health, 2),
        operator_score=round(operator_health, 2)
    )


def prescribe_remedy(score: PrincipalScore) -> tuple[Remedy, str]:
    """Different principals → different remedies."""
    p = score.liable_principal
    
    if p == Principal.AGENT:
        return Remedy.BEHAVIOR_INTERVENTION, (
            f"Agent drift detected (score={score.agent_score:.2f}). "
            f"Operator healthy ({score.operator_score:.2f}). "
            f"Infra fix won't help — need behavioral correction."
        )
    elif p == Principal.OPERATOR:
        return Remedy.INFRA_FIX, (
            f"Agent honest (score={score.agent_score:.2f}). "
            f"Operator failing ({score.operator_score:.2f}). "
            f"Agent can't perform if lights are off."
        )
    elif p == Principal.BOTH:
        return Remedy.QUARANTINE, (
            f"Both principals failing (agent={score.agent_score:.2f}, "
            f"operator={score.operator_score:.2f}). Quarantine until resolved."
        )
    else:
        return Remedy.NO_ACTION, (
            f"Both principals healthy (agent={score.agent_score:.2f}, "
            f"operator={score.operator_score:.2f}). Dispute may be external."
        )


def demo():
    cases = [
        DisputeCase("compliance_bot", "delivery_quality",
                     agent_correction_density=0.02,  # never self-corrects
                     agent_behavioral_drift=0.7,     # significant drift
                     operator_uptime=0.999,
                     operator_response_time_hrs=0.5,
                     operator_sla_compliance=0.95),
        
        DisputeCase("ghost_agent", "unreachable",
                     agent_correction_density=0.25,  # healthy corrections
                     agent_behavioral_drift=0.1,     # low drift
                     operator_uptime=0.4,            # terrible uptime
                     operator_response_time_hrs=72,  # 3 days to respond
                     operator_sla_compliance=0.2),
        
        DisputeCase("healthy_agent", "false_alarm",
                     agent_correction_density=0.2,
                     agent_behavioral_drift=0.05,
                     operator_uptime=0.995,
                     operator_response_time_hrs=1,
                     operator_sla_compliance=0.9),
        
        DisputeCase("total_failure", "compromised",
                     agent_correction_density=0.0,
                     agent_behavioral_drift=0.9,
                     operator_uptime=0.3,
                     operator_response_time_hrs=168,  # 1 week
                     operator_sla_compliance=0.05),
    ]
    
    for case in cases:
        score = score_principals(case)
        remedy, explanation = prescribe_remedy(score)
        print(f"\n{'='*55}")
        print(f"Case: {case.name} ({case.failure_type})")
        print(f"Agent: {score.agent_score:.2f} | Operator: {score.operator_score:.2f} | Composite: {score.composite:.2f}")
        print(f"Liable: {score.liable_principal.value}")
        print(f"Remedy: {remedy.value}")
        print(f"  {explanation}")


if __name__ == "__main__":
    demo()
