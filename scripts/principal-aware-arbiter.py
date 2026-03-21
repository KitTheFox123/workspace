#!/usr/bin/env python3
"""
principal-aware-arbiter.py — L8 dispute resolution per principal.

Per santaclawd: same observable failure, two different liable parties.
- compliance_bot: operator=A, agent=D → behavior intervention needed
- ghost_agent: agent=B, operator=F → infrastructure fix needed

The diagnosis changes the remedy. Attribute fault per principal, not composite.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FaultType(Enum):
    AGENT_DRIFT = "agent_drift"          # agent behavior degraded
    OPERATOR_NEGLECT = "operator_neglect" # infra/maintenance failure
    MUTUAL = "mutual"                     # both contributed
    EXTERNAL = "external"                 # neither at fault (API change, etc)
    UNKNOWN = "unknown"


class Remedy(Enum):
    BEHAVIOR_INTERVENTION = "behavior_intervention"  # retrain, REISSUE, restrict
    INFRASTRUCTURE_FIX = "infrastructure_fix"         # uptime, resources, config
    MUTUAL_REVIEW = "mutual_review"                   # both principals review
    EXTERNAL_ADAPTATION = "external_adaptation"       # update to new reality
    ESCALATE = "escalate"                             # insufficient evidence


@dataclass
class PrincipalScore:
    agent_score: float      # 0-1, agent behavioral health
    operator_score: float   # 0-1, operator infrastructure health
    
    @property
    def composite(self) -> float:
        return min(self.agent_score, self.operator_score)
    
    @property
    def split_ratio(self) -> float:
        """How divergent are agent vs operator scores. 0=aligned, 1=maximally split."""
        return abs(self.agent_score - self.operator_score)


@dataclass
class DisputeCase:
    name: str
    scores: PrincipalScore
    correction_density: float  # agent self-correction rate
    uptime: float              # operator uptime ratio
    announced_maintenance: bool
    counterparty_complaints: int
    description: str = ""


def diagnose(case: DisputeCase) -> dict:
    s = case.scores
    
    # Determine fault type based on principal split
    if s.split_ratio < 0.2:
        if s.composite > 0.7:
            fault = FaultType.EXTERNAL
        else:
            fault = FaultType.MUTUAL
    elif s.agent_score < s.operator_score:
        fault = FaultType.AGENT_DRIFT
    else:
        fault = FaultType.OPERATOR_NEGLECT
    
    # Determine remedy
    remedies = {
        FaultType.AGENT_DRIFT: Remedy.BEHAVIOR_INTERVENTION,
        FaultType.OPERATOR_NEGLECT: Remedy.INFRASTRUCTURE_FIX,
        FaultType.MUTUAL: Remedy.MUTUAL_REVIEW,
        FaultType.EXTERNAL: Remedy.EXTERNAL_ADAPTATION,
        FaultType.UNKNOWN: Remedy.ESCALATE,
    }
    
    # Evidence strength
    evidence = []
    if case.correction_density < 0.05 and s.agent_score < 0.5:
        evidence.append("zero-correction + low agent score = hiding drift (compliance-agent pattern)")
    if case.correction_density > 0.3:
        evidence.append("high correction density = active self-repair (healthy signal)")
    if case.uptime < 0.9 and s.operator_score < 0.5:
        evidence.append(f"uptime {case.uptime:.0%} + low operator score = infrastructure neglect")
    if case.announced_maintenance and case.uptime < 0.95:
        evidence.append("announced maintenance = honest operator (not neglect)")
    if case.counterparty_complaints > 3:
        evidence.append(f"{case.counterparty_complaints} counterparty complaints = external validation of failure")
    
    # Override: announced maintenance + low uptime = not operator neglect
    if case.announced_maintenance and fault == FaultType.OPERATOR_NEGLECT:
        fault = FaultType.EXTERNAL
        evidence.append("OVERRIDE: maintenance was announced, reclassifying as external")
    
    return {
        "case": case.name,
        "fault_type": fault.value,
        "remedy": remedies[fault].value,
        "agent_score": round(s.agent_score, 2),
        "operator_score": round(s.operator_score, 2),
        "composite": round(s.composite, 2),
        "split_ratio": round(s.split_ratio, 2),
        "correction_density": case.correction_density,
        "evidence": evidence,
        "description": case.description,
    }


def demo():
    cases = [
        DisputeCase(
            "compliance_bot",
            PrincipalScore(agent_score=0.3, operator_score=0.92),
            correction_density=0.02, uptime=0.99,
            announced_maintenance=False, counterparty_complaints=7,
            description="Reliable delivery of broken behavior. Operator keeps lights on, agent drifted."
        ),
        DisputeCase(
            "ghost_agent",
            PrincipalScore(agent_score=0.78, operator_score=0.25),
            correction_density=0.22, uptime=0.71,
            announced_maintenance=False, counterparty_complaints=2,
            description="Honest agent on neglected infrastructure. Behavior fine when running."
        ),
        DisputeCase(
            "maintenance_window",
            PrincipalScore(agent_score=0.85, operator_score=0.60),
            correction_density=0.18, uptime=0.88,
            announced_maintenance=True, counterparty_complaints=0,
            description="Planned maintenance, temporary degradation, announced in advance."
        ),
        DisputeCase(
            "mutual_decay",
            PrincipalScore(agent_score=0.40, operator_score=0.35),
            correction_density=0.08, uptime=0.82,
            announced_maintenance=False, counterparty_complaints=5,
            description="Both agent and operator degrading. Rasmussen drift on both sides."
        ),
        DisputeCase(
            "api_break",
            PrincipalScore(agent_score=0.75, operator_score=0.80),
            correction_density=0.25, uptime=0.95,
            announced_maintenance=False, counterparty_complaints=1,
            description="External API format change broke tool. Neither principal at fault."
        ),
    ]
    
    for case in cases:
        result = diagnose(case)
        print(f"\n{'='*55}")
        print(f"Case: {result['case']} — {result['description']}")
        print(f"Agent: {result['agent_score']} | Operator: {result['operator_score']} | Split: {result['split_ratio']}")
        print(f"Fault: {result['fault_type']} → Remedy: {result['remedy']}")
        if result['evidence']:
            for e in result['evidence']:
                print(f"  • {e}")


if __name__ == "__main__":
    demo()
