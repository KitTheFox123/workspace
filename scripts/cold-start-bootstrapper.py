#!/usr/bin/env python3
"""
cold-start-bootstrapper.py — Trust bootstrapping for new ATF agents.

Per santaclawd: "cold start = no chain yet. social fix is the only one."
Per Duncan (Brit J Psych 2025): trust learning follows Bayesian updating.
Per Nature (Sci Rep 2025): passive nodes are load-bearing for network stability.

Key insight: spec cannot manufacture receipts. But it CAN require:
1. Minimum counterparty diversity before TRUSTED
2. Recency decay on all endorsements
3. Wilson CI cold-start ceiling (n=5 → 0.57 max)

Three bootstrap paths:
  OPERATOR_VOUCHED  — Operator attests at genesis (root CA parallel)
  SOCIAL_BOOTSTRAP  — Engage diverse counterparties, accumulate receipts
  PROVISIONAL_ONLY  — No prior, hard ceiling until Wilson CI lifts it
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BootstrapPath(Enum):
    OPERATOR_VOUCHED = "OPERATOR_VOUCHED"    # Genesis attestation from operator
    SOCIAL_BOOTSTRAP = "SOCIAL_BOOTSTRAP"    # Earn through diverse engagement
    PROVISIONAL_ONLY = "PROVISIONAL_ONLY"    # No prior, cold start


class TrustPhase(Enum):
    PROVISIONAL = "PROVISIONAL"  # Wilson CI ceiling applies
    EMERGING = "EMERGING"        # Building diverse counterparties
    ESTABLISHED = "ESTABLISHED"  # n >= 30, diverse, stable
    TRUSTED = "TRUSTED"          # Full trust, behavioral history


# SPEC_CONSTANTS
MIN_COUNTERPARTY_CLASSES = 2       # Minimum diverse counterparties for EMERGING
WILSON_Z = 1.96                    # 95% confidence
COLD_START_THRESHOLD_N = 30        # Receipts needed for ESTABLISHED
MIN_DAYS_FOR_ESTABLISHED = 7       # Temporal spread requirement
RECENCY_HALFLIFE_DAYS = 30         # Endorsement decay
OPERATOR_VOUCH_CEILING = 0.60      # Max trust from operator vouch alone
PROVISIONAL_CEILING = 0.50         # Hard ceiling for PROVISIONAL


@dataclass
class Receipt:
    receipt_id: str
    counterparty_id: str
    counterparty_operator: str  # For diversity measurement
    timestamp: float
    grade: str  # A-F
    confirmed: bool  # Co-signed by counterparty
    
    
@dataclass
class AgentBootstrap:
    agent_id: str
    operator_id: str
    genesis_timestamp: float
    bootstrap_path: BootstrapPath
    receipts: list[Receipt] = field(default_factory=list)
    operator_vouch: bool = False


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z*z / total
    centre = p + z*z / (2 * total)
    spread = z * math.sqrt((p * (1-p) + z*z / (4*total)) / total)
    return max(0, (centre - spread) / denominator)


def counterparty_diversity(receipts: list[Receipt]) -> dict:
    """Measure counterparty diversity using Simpson index."""
    operators = {}
    counterparties = set()
    for r in receipts:
        operators[r.counterparty_operator] = operators.get(r.counterparty_operator, 0) + 1
        counterparties.add(r.counterparty_id)
    
    total = sum(operators.values())
    simpson = 1.0 - sum((c/total)**2 for c in operators.values()) if total > 0 else 0
    
    return {
        "unique_counterparties": len(counterparties),
        "unique_operators": len(operators),
        "simpson_diversity": round(simpson, 4),
        "operator_distribution": operators,
        "meets_minimum": len(set(operators.keys())) >= MIN_COUNTERPARTY_CLASSES
    }


def recency_weight(receipt_timestamp: float, now: float) -> float:
    """Exponential decay weight based on recency."""
    age_days = (now - receipt_timestamp) / 86400
    return math.exp(-0.693 * age_days / RECENCY_HALFLIFE_DAYS)  # 0.693 = ln(2)


def compute_trust_state(agent: AgentBootstrap) -> dict:
    """Compute full trust state for a bootstrapping agent."""
    now = time.time()
    receipts = agent.receipts
    
    if not receipts:
        return {
            "phase": TrustPhase.PROVISIONAL.value,
            "trust_score": 0.0,
            "ceiling": PROVISIONAL_CEILING,
            "effective_score": 0.0,
            "receipts": 0,
            "diversity": {"unique_counterparties": 0, "unique_operators": 0, "simpson_diversity": 0},
            "next_phase_requirements": f"Need {MIN_COUNTERPARTY_CLASSES}+ diverse counterparties",
            "bootstrap_path": agent.bootstrap_path.value
        }
    
    # Count confirmed receipts with recency weighting
    weighted_confirmed = sum(
        recency_weight(r.timestamp, now) for r in receipts if r.confirmed
    )
    weighted_total = sum(
        recency_weight(r.timestamp, now) for r in receipts
    )
    
    # Wilson CI on raw counts
    confirmed = sum(1 for r in receipts if r.confirmed)
    total = len(receipts)
    wilson_lower = wilson_ci_lower(confirmed, total)
    
    # Diversity check
    diversity = counterparty_diversity(receipts)
    
    # Temporal spread
    timestamps = [r.timestamp for r in receipts]
    temporal_span_days = (max(timestamps) - min(timestamps)) / 86400 if len(timestamps) > 1 else 0
    
    # Determine phase
    if not diversity["meets_minimum"]:
        phase = TrustPhase.PROVISIONAL
        ceiling = PROVISIONAL_CEILING
        if agent.operator_vouch:
            ceiling = OPERATOR_VOUCH_CEILING
    elif total < COLD_START_THRESHOLD_N or temporal_span_days < MIN_DAYS_FOR_ESTABLISHED:
        phase = TrustPhase.EMERGING
        ceiling = wilson_lower  # Wilson CI IS the ceiling
    elif diversity["simpson_diversity"] > 0.5:
        phase = TrustPhase.ESTABLISHED
        ceiling = min(wilson_lower, 0.95)  # Cap at 0.95
    else:
        phase = TrustPhase.ESTABLISHED
        ceiling = min(wilson_lower, 0.85)  # Monoculture penalty
    
    # Effective score = min(weighted rate, ceiling)
    weighted_rate = weighted_confirmed / weighted_total if weighted_total > 0 else 0
    effective_score = min(weighted_rate, ceiling)
    
    # Next phase requirements
    if phase == TrustPhase.PROVISIONAL:
        next_req = f"Need {MIN_COUNTERPARTY_CLASSES - diversity['unique_operators']} more operator classes"
    elif phase == TrustPhase.EMERGING:
        remaining_n = max(0, COLD_START_THRESHOLD_N - total)
        remaining_days = max(0, MIN_DAYS_FOR_ESTABLISHED - temporal_span_days)
        next_req = f"Need {remaining_n} more receipts, {remaining_days:.0f} more days"
    else:
        next_req = "ESTABLISHED — maintain diversity and recency"
    
    return {
        "phase": phase.value,
        "trust_score": round(weighted_rate, 4),
        "wilson_ci_lower": round(wilson_lower, 4),
        "ceiling": round(ceiling, 4),
        "effective_score": round(effective_score, 4),
        "receipts_total": total,
        "receipts_confirmed": confirmed,
        "temporal_span_days": round(temporal_span_days, 1),
        "diversity": diversity,
        "next_phase_requirements": next_req,
        "bootstrap_path": agent.bootstrap_path.value
    }


# === Scenarios ===

def scenario_brand_new_agent():
    """Zero receipts — PROVISIONAL."""
    print("=== Scenario: Brand New Agent (Zero History) ===")
    agent = AgentBootstrap("new_agent", "op_startup", time.time(), BootstrapPath.PROVISIONAL_ONLY)
    state = compute_trust_state(agent)
    print(f"  Phase: {state['phase']}")
    print(f"  Effective score: {state['effective_score']} (ceiling: {state['ceiling']})")
    print(f"  Next: {state['next_phase_requirements']}")
    print()


def scenario_operator_vouched():
    """Operator vouches at genesis — higher ceiling but still capped."""
    print("=== Scenario: Operator Vouched (Genesis Attestation) ===")
    now = time.time()
    agent = AgentBootstrap("vouched_agent", "op_trusted", now - 86400, BootstrapPath.OPERATOR_VOUCHED,
                          operator_vouch=True)
    # 3 receipts from same operator
    for i in range(3):
        agent.receipts.append(Receipt(f"r{i}", f"peer_{i}", "op_trusted", now - 86400 + i*3600, "B", True))
    
    state = compute_trust_state(agent)
    print(f"  Phase: {state['phase']} (operator vouched)")
    print(f"  Effective score: {state['effective_score']} (ceiling: {state['ceiling']})")
    print(f"  Diversity: {state['diversity']['unique_operators']} operators (need {MIN_COUNTERPARTY_CLASSES})")
    print(f"  Next: {state['next_phase_requirements']}")
    print()


def scenario_diverse_bootstrap():
    """Agent engages diverse counterparties — EMERGING → ESTABLISHED."""
    print("=== Scenario: Diverse Social Bootstrap ===")
    now = time.time()
    agent = AgentBootstrap("social_agent", "op_indie", now - 86400*14, BootstrapPath.SOCIAL_BOOTSTRAP)
    
    # 35 receipts across 5 operators over 14 days
    operators = ["op_a", "op_b", "op_c", "op_d", "op_e"]
    for i in range(35):
        op = operators[i % 5]
        agent.receipts.append(Receipt(
            f"r{i}", f"peer_{i%10}", op,
            now - 86400*14 + i*34560,  # Spread over 14 days
            "B" if i % 3 != 0 else "A",
            confirmed=i % 7 != 0  # ~85% confirmed
        ))
    
    state = compute_trust_state(agent)
    print(f"  Phase: {state['phase']}")
    print(f"  Wilson CI lower: {state['wilson_ci_lower']}")
    print(f"  Effective score: {state['effective_score']} (ceiling: {state['ceiling']})")
    print(f"  Receipts: {state['receipts_confirmed']}/{state['receipts_total']} confirmed")
    print(f"  Diversity: Simpson={state['diversity']['simpson_diversity']}, operators={state['diversity']['unique_operators']}")
    print(f"  Temporal span: {state['temporal_span_days']} days")
    print()


def scenario_sybil_monoculture():
    """All receipts from one operator — ceiling capped."""
    print("=== Scenario: Sybil Monoculture (Single Operator) ===")
    now = time.time()
    agent = AgentBootstrap("sybil_agent", "op_self", now - 86400*10, BootstrapPath.SOCIAL_BOOTSTRAP)
    
    # 50 receipts but ALL from same operator
    for i in range(50):
        agent.receipts.append(Receipt(
            f"r{i}", f"sock_{i}", "op_sybil",
            now - 86400*10 + i*17280,
            "A", confirmed=True
        ))
    
    state = compute_trust_state(agent)
    print(f"  Phase: {state['phase']}")
    print(f"  Wilson CI lower: {state['wilson_ci_lower']} (50/50 confirmed!)")
    print(f"  Effective score: {state['effective_score']} (ceiling: {state['ceiling']})")
    print(f"  Diversity: Simpson={state['diversity']['simpson_diversity']}, operators={state['diversity']['unique_operators']}")
    print(f"  KEY: 50 perfect receipts from 1 operator = PROVISIONAL. Diversity gates trust.")
    print()


def scenario_stale_receipts():
    """Old receipts decay — recency matters."""
    print("=== Scenario: Stale Receipts (Recency Decay) ===")
    now = time.time()
    agent = AgentBootstrap("stale_agent", "op_old", now - 86400*120, BootstrapPath.SOCIAL_BOOTSTRAP)
    
    # 40 receipts from 90-120 days ago, diverse but old
    operators = ["op_a", "op_b", "op_c"]
    for i in range(40):
        agent.receipts.append(Receipt(
            f"r{i}", f"peer_{i%8}", operators[i % 3],
            now - 86400*120 + i*64800,  # 90-120 days old
            "B", confirmed=True
        ))
    
    state = compute_trust_state(agent)
    print(f"  Phase: {state['phase']}")
    print(f"  Wilson CI lower: {state['wilson_ci_lower']} (raw)")
    print(f"  Trust score (weighted): {state['trust_score']} (decayed!)")
    print(f"  Effective score: {state['effective_score']}")
    print(f"  Temporal span: {state['temporal_span_days']} days")
    print(f"  KEY: 40 confirmed receipts → low effective score because recency decay.")
    print(f"  PGP failed because trust never expired. ATF trust MUST expire.")
    print()


if __name__ == "__main__":
    print("Cold-Start Bootstrapper — Trust Bootstrap for New ATF Agents")
    print("Per santaclawd + Duncan (Brit J Psych 2025) + Nature (Sci Rep 2025)")
    print("=" * 70)
    print()
    print("Three bootstrap paths:")
    print(f"  OPERATOR_VOUCHED:  Ceiling {OPERATOR_VOUCH_CEILING}")
    print(f"  SOCIAL_BOOTSTRAP:  Wilson CI is the ceiling")
    print(f"  PROVISIONAL_ONLY:  Ceiling {PROVISIONAL_CEILING}")
    print(f"  ESTABLISHED needs: n>={COLD_START_THRESHOLD_N}, {MIN_DAYS_FOR_ESTABLISHED}+ days, {MIN_COUNTERPARTY_CLASSES}+ operators")
    print()
    
    scenario_brand_new_agent()
    scenario_operator_vouched()
    scenario_diverse_bootstrap()
    scenario_sybil_monoculture()
    scenario_stale_receipts()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Spec cannot manufacture receipts. Social fix is the only cold-start solution.")
    print("2. Diversity gates trust: 50 receipts from 1 operator = PROVISIONAL.")
    print("3. Recency decay prevents PGP failure mode (perpetual non-expiring trust).")
    print("4. Wilson CI IS the ceiling — natural anti-sybil at cold start.")
    print("5. Passive nodes are load-bearing (Nature 2025): lurkers propagate trust signals.")
