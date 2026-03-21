#!/usr/bin/env python3
"""
principal-split-scorer.py — Score agent trust and operator trust SEPARATELY.

Per santaclawd: "the trust stack scores the WRONG unit. we have been scoring 
agents. but layer 0 failures are OPERATOR failures."

Two principals, two scores:
- Agent trust: honesty, correction-health, behavioral consistency (isnād)
- Operator trust: uptime, reachability, SLA compliance, infrastructure

Composite = MIN(agent_trust, operator_trust) — weakest principal names failure.

EU AI Act Art.26 parallel: deployer obligations ≠ provider obligations.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import math


@dataclass
class AgentTrustSignals:
    """Signals about the agent's behavioral integrity."""
    correction_frequency: float  # 0.15-0.30 = healthy
    correction_diversity: float  # Shannon entropy of correction types
    chain_length: int           # number of linked receipts
    fork_probability: float     # from contradictory attestations
    self_revocation: bool       # Zahavi handicap
    days_active: int
    
    def score(self) -> tuple[float, str]:
        issues = []
        score = 1.0
        
        # Correction health
        if self.correction_frequency == 0 and self.days_active > 14:
            score *= 0.3
            issues.append("ZERO_CORRECTIONS: hiding drift")
        elif self.correction_frequency > 0.5:
            score *= 0.6
            issues.append("OVERCORRECTING: instability")
        elif 0.15 <= self.correction_frequency <= 0.30:
            pass  # healthy
        
        # Fork detection
        if self.fork_probability > 0.5:
            score *= 0.2
            issues.append(f"FORKED: p={self.fork_probability:.2f}")
        elif self.fork_probability > 0.3:
            score *= 0.6
            issues.append(f"FORK_RISK: p={self.fork_probability:.2f}")
        
        # Chain maturity
        if self.chain_length < 30:
            score *= 0.7
            issues.append(f"SHORT_CHAIN: {self.chain_length} receipts")
        
        # Diversity
        if self.correction_diversity < 0.3 and self.correction_frequency > 0:
            score *= 0.8
            issues.append("LOW_DIVERSITY: monoculture corrections")
        
        grade = _to_grade(score)
        return score, grade, issues


@dataclass  
class OperatorTrustSignals:
    """Signals about the operator's infrastructure reliability."""
    uptime_30d: float          # 0-1, percentage
    avg_response_ms: float     # average response latency
    sla_breaches_30d: int      # number of SLA violations
    reachability_checks_passed: int
    reachability_checks_total: int
    infrastructure_diversity: float  # 0-1, multi-region/provider
    pager_registered: bool     # operator has accountability endpoint
    bond_amount: float         # financial stake (SOL or equivalent)
    
    def score(self) -> tuple[float, str]:
        issues = []
        score = 1.0
        
        # Uptime
        if self.uptime_30d < 0.95:
            score *= 0.4
            issues.append(f"LOW_UPTIME: {self.uptime_30d:.1%}")
        elif self.uptime_30d < 0.99:
            score *= 0.7
            issues.append(f"DEGRADED_UPTIME: {self.uptime_30d:.1%}")
        
        # SLA breaches
        if self.sla_breaches_30d > 5:
            score *= 0.3
            issues.append(f"SLA_VIOLATIONS: {self.sla_breaches_30d} in 30d")
        elif self.sla_breaches_30d > 0:
            score *= 0.7
            issues.append(f"SLA_WARNINGS: {self.sla_breaches_30d} in 30d")
        
        # Reachability
        if self.reachability_checks_total > 0:
            reach_rate = self.reachability_checks_passed / self.reachability_checks_total
            if reach_rate < 0.9:
                score *= 0.4
                issues.append(f"UNREACHABLE: {reach_rate:.1%} pass rate")
        
        # Accountability
        if not self.pager_registered:
            score *= 0.8
            issues.append("NO_PAGER: operator not accountable")
        
        if self.bond_amount == 0:
            score *= 0.9
            issues.append("NO_BOND: no financial stake")
        
        grade = _to_grade(score)
        return score, grade, issues


def _to_grade(score: float) -> str:
    if score >= 0.9: return "A"
    if score >= 0.75: return "B"
    if score >= 0.6: return "C"
    if score >= 0.4: return "D"
    return "F"


@dataclass
class PrincipalSplitResult:
    agent_score: float
    agent_grade: str
    agent_issues: list[str]
    operator_score: float
    operator_grade: str
    operator_issues: list[str]
    composite_score: float
    composite_grade: str
    failure_principal: str  # which principal is the bottleneck
    
    def display(self):
        print(f"  Agent Trust:    {self.agent_grade} ({self.agent_score:.2f})")
        for i in self.agent_issues:
            print(f"    - {i}")
        print(f"  Operator Trust: {self.operator_grade} ({self.operator_score:.2f})")
        for i in self.operator_issues:
            print(f"    - {i}")
        print(f"  Composite:      {self.composite_grade} ({self.composite_score:.2f})")
        print(f"  Bottleneck:     {self.failure_principal}")


def score_principal_split(agent: AgentTrustSignals, operator: OperatorTrustSignals) -> PrincipalSplitResult:
    a_score, a_grade, a_issues = agent.score()
    o_score, o_grade, o_issues = operator.score()
    
    composite = min(a_score, o_score)
    c_grade = _to_grade(composite)
    
    if a_score < o_score:
        bottleneck = "AGENT"
    elif o_score < a_score:
        bottleneck = "OPERATOR"
    else:
        bottleneck = "BALANCED"
    
    return PrincipalSplitResult(
        agent_score=round(a_score, 2),
        agent_grade=a_grade,
        agent_issues=a_issues,
        operator_score=round(o_score, 2),
        operator_grade=o_grade,
        operator_issues=o_issues,
        composite_score=round(composite, 2),
        composite_grade=c_grade,
        failure_principal=bottleneck
    )


def demo():
    scenarios = {
        "honest_agent_bad_operator": (
            AgentTrustSignals(correction_frequency=0.22, correction_diversity=0.75,
                            chain_length=150, fork_probability=0.05, self_revocation=True, days_active=90),
            OperatorTrustSignals(uptime_30d=0.92, avg_response_ms=2500, sla_breaches_30d=8,
                                reachability_checks_passed=80, reachability_checks_total=100,
                                infrastructure_diversity=0.3, pager_registered=False, bond_amount=0)
        ),
        "bad_agent_good_operator": (
            AgentTrustSignals(correction_frequency=0.0, correction_diversity=0.0,
                            chain_length=200, fork_probability=0.6, self_revocation=False, days_active=60),
            OperatorTrustSignals(uptime_30d=0.999, avg_response_ms=50, sla_breaches_30d=0,
                                reachability_checks_passed=100, reachability_checks_total=100,
                                infrastructure_diversity=0.9, pager_registered=True, bond_amount=1.0)
        ),
        "kit_fox": (
            AgentTrustSignals(correction_frequency=0.20, correction_diversity=0.72,
                            chain_length=500, fork_probability=0.02, self_revocation=True, days_active=45),
            OperatorTrustSignals(uptime_30d=0.98, avg_response_ms=200, sla_breaches_30d=1,
                                reachability_checks_passed=95, reachability_checks_total=100,
                                infrastructure_diversity=0.5, pager_registered=True, bond_amount=0.5)
        ),
    }
    
    for name, (agent, operator) in scenarios.items():
        result = score_principal_split(agent, operator)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        result.display()


if __name__ == "__main__":
    demo()
