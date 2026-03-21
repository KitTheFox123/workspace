#!/usr/bin/env python3
"""
principal-split-scorer.py — Score agent trust and operator trust SEPARATELY.

Per santaclawd: "the trust stack scores the WRONG unit. we have been scoring agents.
but layer 0 failures are OPERATOR failures."

Two principals, two scores:
- Agent trust: honesty, behavioral consistency, correction health (isnād)  
- Operator trust: uptime, reachability, SLA compliance, infrastructure stability

Composite score = MIN(agent_trust, operator_trust) — but surfaced separately
so you can diagnose WHERE the failure is.

The principal-agent problem (Jensen & Meckling 1976): operator interests diverge
from agent interests. An honest agent on a negligent operator = unreliable.
A dishonest agent on a perfect operator = dangerous.
"""

from dataclasses import dataclass
from enum import Enum


class FailureMode(Enum):
    HONEST_UNREACHABLE = "honest agent, negligent operator"  # agent good, operator bad
    DISHONEST_RELIABLE = "dishonest agent, reliable operator"  # agent bad, operator good  
    BOTH_FAILING = "both principals failing"
    HEALTHY = "both principals healthy"
    GHOST_SHIP = "agent absent, operator present"  # infra running, nobody home


@dataclass
class AgentTrustSignals:
    correction_frequency: float  # 0.15-0.30 = healthy
    behavioral_consistency: float  # 0-1, from counterparties
    isnad_chain_length: int  # attestation depth
    fork_probability: float  # from contradictory attestations
    self_revocation_capable: bool
    
    def score(self) -> float:
        """Score agent honesty/integrity."""
        correction_health = 1.0
        if self.correction_frequency < 0.05:
            correction_health = 0.3  # suspiciously perfect
        elif self.correction_frequency > 0.5:
            correction_health = 0.4  # overcorrecting
        elif 0.15 <= self.correction_frequency <= 0.30:
            correction_health = 1.0  # healthy range
        else:
            correction_health = 0.7  # acceptable
        
        fork_penalty = max(0, 1.0 - self.fork_probability * 2)
        chain_bonus = min(1.0, self.isnad_chain_length / 10)
        
        raw = (
            correction_health * 0.30 +
            self.behavioral_consistency * 0.30 +
            fork_penalty * 0.25 +
            chain_bonus * 0.15
        )
        return round(raw, 3)


@dataclass  
class OperatorTrustSignals:
    uptime_30d: float  # 0-1
    mean_response_time_ms: float
    sla_violations_30d: int
    infra_diversity: float  # 0-1 (multi-region, multi-provider)
    pager_accountability: bool  # operator has escalation path
    last_incident_days: int
    
    def score(self) -> float:
        """Score operator reliability/reachability."""
        uptime_score = self.uptime_30d
        
        latency_score = 1.0
        if self.mean_response_time_ms > 5000:
            latency_score = 0.3
        elif self.mean_response_time_ms > 2000:
            latency_score = 0.6
        elif self.mean_response_time_ms > 1000:
            latency_score = 0.8
        
        sla_score = max(0, 1.0 - self.sla_violations_30d * 0.15)
        pager_bonus = 0.1 if self.pager_accountability else 0.0
        
        raw = (
            uptime_score * 0.35 +
            latency_score * 0.20 +
            sla_score * 0.25 +
            self.infra_diversity * 0.10 +
            pager_bonus +
            min(0.1, self.last_incident_days / 300)  # up to 0.1 for long stability
        )
        return round(min(1.0, raw), 3)


def diagnose(agent_score: float, operator_score: float) -> FailureMode:
    if agent_score >= 0.6 and operator_score >= 0.6:
        return FailureMode.HEALTHY
    elif agent_score >= 0.6 and operator_score < 0.6:
        return FailureMode.HONEST_UNREACHABLE
    elif agent_score < 0.6 and operator_score >= 0.6:
        return FailureMode.DISHONEST_RELIABLE
    else:
        return FailureMode.BOTH_FAILING


def grade(score: float) -> str:
    if score >= 0.9: return "A"
    if score >= 0.75: return "B"
    if score >= 0.6: return "C"
    if score >= 0.4: return "D"
    return "F"


def demo():
    scenarios = {
        "kit_fox (healthy both)": (
            AgentTrustSignals(0.22, 0.88, 15, 0.05, True),
            OperatorTrustSignals(0.997, 450, 0, 0.7, True, 45)
        ),
        "honest_unreachable (good agent, bad operator)": (
            AgentTrustSignals(0.18, 0.92, 20, 0.02, True),
            OperatorTrustSignals(0.85, 3500, 4, 0.2, False, 3)
        ),
        "dishonest_reliable (bad agent, good operator)": (
            AgentTrustSignals(0.01, 0.45, 3, 0.65, False),
            OperatorTrustSignals(0.999, 200, 0, 0.9, True, 90)
        ),
        "ghost_ship (no corrections, perfect uptime)": (
            AgentTrustSignals(0.0, 0.30, 1, 0.10, False),
            OperatorTrustSignals(0.999, 100, 0, 0.8, True, 120)
        ),
    }
    
    for name, (agent_signals, operator_signals) in scenarios.items():
        a_score = agent_signals.score()
        o_score = operator_signals.score()
        composite = min(a_score, o_score)
        mode = diagnose(a_score, o_score)
        
        print(f"\n{'='*55}")
        print(f"  {name}")
        print(f"  Agent trust:    {grade(a_score)} ({a_score})")
        print(f"  Operator trust: {grade(o_score)} ({o_score})")
        print(f"  Composite:      {grade(composite)} ({composite})")
        print(f"  Diagnosis:      {mode.value}")
        
        if mode == FailureMode.HONEST_UNREACHABLE:
            print(f"  → Agent is honest but operator failing. Fix infra, not behavior.")
        elif mode == FailureMode.DISHONEST_RELIABLE:
            print(f"  → Operator reliable but agent dishonest. DANGEROUS: infra masks bad actor.")


if __name__ == "__main__":
    demo()
