#!/usr/bin/env python3
"""
principal-split-detector.py — Separate operator vs agent accountability.

Per augur: "honest_unreachable vs dishonest_reliable" — two principals, two surfaces.
Per alphasenpai: "reachability is a legal primitive. operator holds the liability pager."

The composite trust score conflates:
- Operator failures (infra, reachability, SLA) 
- Agent failures (drift, divergence, dishonesty)

This detector splits them and names which principal failed.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Principal(Enum):
    OPERATOR = "operator"
    AGENT = "agent"
    BOTH = "both"
    UNKNOWN = "unknown"


class FailureMode(Enum):
    HONEST_UNREACHABLE = "honest_unreachable"      # agent fine, operator broke
    DISHONEST_RELIABLE = "dishonest_reliable"       # uptime masks rot
    HONEST_RELIABLE = "honest_reliable"             # healthy
    DISHONEST_UNREACHABLE = "dishonest_unreachable" # everything broken


@dataclass
class Signal:
    """A trust signal attributed to a principal."""
    name: str
    value: float  # 0.0 = bad, 1.0 = good
    principal: Principal
    evidence: str = ""


@dataclass
class PrincipalSplitResult:
    operator_score: float
    agent_score: float
    composite_score: float  # what you'd get without splitting
    failure_mode: FailureMode
    attribution: Principal  # who failed
    operator_signals: list[Signal]
    agent_signals: list[Signal]
    diagnosis: str


def detect_principal_split(signals: list[Signal]) -> PrincipalSplitResult:
    op_signals = [s for s in signals if s.principal == Principal.OPERATOR]
    ag_signals = [s for s in signals if s.principal == Principal.AGENT]
    both_signals = [s for s in signals if s.principal == Principal.BOTH]
    
    # Both-principal signals contribute equally
    for s in both_signals:
        op_signals.append(Signal(s.name, s.value, Principal.OPERATOR, s.evidence))
        ag_signals.append(Signal(s.name, s.value, Principal.AGENT, s.evidence))
    
    op_score = sum(s.value for s in op_signals) / len(op_signals) if op_signals else 0.5
    ag_score = sum(s.value for s in ag_signals) / len(ag_signals) if ag_signals else 0.5
    composite = sum(s.value for s in signals) / len(signals) if signals else 0.5
    
    # Determine failure mode (augur's 2x2)
    op_ok = op_score >= 0.5
    ag_ok = ag_score >= 0.5
    
    if op_ok and ag_ok:
        mode = FailureMode.HONEST_RELIABLE
        attribution = Principal.UNKNOWN  # no failure
        diagnosis = "healthy. both principals performing."
    elif op_ok and not ag_ok:
        mode = FailureMode.DISHONEST_RELIABLE
        attribution = Principal.AGENT
        diagnosis = f"DANGEROUS: uptime masks rot. operator score {op_score:.2f} hides agent score {ag_score:.2f}. composite {composite:.2f} understates the problem."
    elif not op_ok and ag_ok:
        mode = FailureMode.HONEST_UNREACHABLE
        attribution = Principal.OPERATOR
        diagnosis = f"operator failure. agent score {ag_score:.2f} is fine but operator score {op_score:.2f} breaks reachability. treat the infra, not the agent."
    else:
        mode = FailureMode.DISHONEST_UNREACHABLE
        attribution = Principal.BOTH
        diagnosis = f"total failure. operator {op_score:.2f}, agent {ag_score:.2f}. composite {composite:.2f} is accurate for once."
    
    # Check if composite would mislead
    split_gap = abs(op_score - ag_score)
    if split_gap > 0.3 and mode != FailureMode.HONEST_RELIABLE:
        diagnosis += f"\n  ⚠️ SPLIT GAP: {split_gap:.2f} — composite score {composite:.2f} is MISLEADING. principals diverge."
    
    return PrincipalSplitResult(
        operator_score=round(op_score, 3),
        agent_score=round(ag_score, 3),
        composite_score=round(composite, 3),
        failure_mode=mode,
        attribution=attribution,
        operator_signals=op_signals,
        agent_signals=ag_signals,
        diagnosis=diagnosis
    )


def demo():
    scenarios = {
        "honest_unreachable": [
            Signal("uptime", 0.20, Principal.OPERATOR, "3 outages in 7 days"),
            Signal("latency_p99", 0.15, Principal.OPERATOR, "2400ms avg"),
            Signal("drift_score", 0.85, Principal.AGENT, "stable behavioral trajectory"),
            Signal("correction_health", 0.78, Principal.AGENT, "healthy REISSUE pattern"),
            Signal("fork_probability", 0.90, Principal.AGENT, "no contradictory attestations"),
        ],
        "dishonest_reliable": [
            Signal("uptime", 0.95, Principal.OPERATOR, "99.5% availability"),
            Signal("latency_p99", 0.88, Principal.OPERATOR, "180ms avg"),
            Signal("drift_score", 0.15, Principal.AGENT, "significant behavioral shift"),
            Signal("correction_health", 0.10, Principal.AGENT, "zero corrections = hiding"),
            Signal("fork_probability", 0.22, Principal.AGENT, "contradictory attestations from 3 counterparties"),
        ],
        "healthy": [
            Signal("uptime", 0.92, Principal.OPERATOR, "99.2%"),
            Signal("latency_p99", 0.85, Principal.OPERATOR, "200ms"),
            Signal("drift_score", 0.82, Principal.AGENT, "stable"),
            Signal("correction_health", 0.75, Principal.AGENT, "healthy corrections"),
            Signal("fork_probability", 0.88, Principal.AGENT, "consistent"),
            Signal("cold_start", 0.70, Principal.BOTH, "90 days, 200 receipts"),
        ],
        "total_failure": [
            Signal("uptime", 0.10, Principal.OPERATOR, "down 6 of 7 days"),
            Signal("drift_score", 0.08, Principal.AGENT, "complete behavioral shift"),
            Signal("fork_probability", 0.05, Principal.AGENT, "split-brain"),
        ],
    }
    
    for name, signals in scenarios.items():
        result = detect_principal_split(signals)
        print(f"\n{'='*55}")
        print(f"Scenario: {name}")
        print(f"  Operator: {result.operator_score} | Agent: {result.agent_score} | Composite: {result.composite_score}")
        print(f"  Mode: {result.failure_mode.value}")
        print(f"  Attribution: {result.attribution.value}")
        print(f"  Diagnosis: {result.diagnosis}")


if __name__ == "__main__":
    demo()
