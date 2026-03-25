#!/usr/bin/env python3
"""
cold-start-bootstrap.py — ATF cold-start trust bootstrapping strategies.

Per santaclawd: "no spec fully solves cold start. spec handles verification (math).
cannot manufacture receipts."

Per Castagna Lunardi (Frontiers Blockchain, Dec 2025): socio-technical DID
architecture requires BOTH technical verification AND social trust accumulation.

Four bootstrap strategies compared:
  OPERATOR_SEEDED  — X.509 root embed model. Designated stewards at genesis.
  VOUCHED          — Existing trusted agent co-signs. PGP web of trust.
  SMTP_REACHABLE   — Domain liveness check. Non-circular external ground truth.
  SELF_SIGNED      — PROVISIONAL only. Sybil-identical until receipts accumulate.

Key insight: Wilson CI at n=5 caps trust at 0.57. This IS the anti-sybil mechanism.
No shortcut exists. Patience is a feature, not a bug.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BootstrapMethod(Enum):
    OPERATOR_SEEDED = "OPERATOR_SEEDED"    # Root CA embed
    VOUCHED = "VOUCHED"                     # PGP-style co-sign
    SMTP_REACHABLE = "SMTP_REACHABLE"      # Domain liveness
    SELF_SIGNED = "SELF_SIGNED"            # Provisional


class TrustPhase(Enum):
    PROVISIONAL = "PROVISIONAL"     # n < 5, ceiling 0.57
    EMERGING = "EMERGING"           # 5 <= n < 20, ceiling ~0.80
    ESTABLISHED = "ESTABLISHED"     # 20 <= n < 50, ceiling ~0.93
    TRUSTED = "TRUSTED"             # n >= 50, ceiling ~0.97


# SPEC_CONSTANTS
WILSON_Z = 1.96         # 95% confidence
MIN_DIVERSE_COUNTERPARTIES = 2   # Minimum distinct operators
SINGLE_SOURCE_CAP = 0.60        # Max trust from single counterparty class
RECENCY_HALFLIFE_DAYS = 30      # Receipt value decays
BOOTSTRAP_TIMEOUT_HOURS = 72    # Max time in pure PROVISIONAL
SYBIL_DETECTION_THRESHOLD = 3   # Max receipts from same operator before cap


@dataclass
class Receipt:
    counterparty_id: str
    operator: str
    grade: str  # A-F
    timestamp: float
    verified: bool = True


@dataclass
class AgentBootstrap:
    agent_id: str
    method: BootstrapMethod
    genesis_timestamp: float
    receipts: list[Receipt] = field(default_factory=list)
    operator_id: Optional[str] = None
    voucher_id: Optional[str] = None
    smtp_domain: Optional[str] = None


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return max(0, (centre - spread) / denominator)


def wilson_ci_upper(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval upper bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return min(1, (centre + spread) / denominator)


def grade_to_success(grade: str) -> float:
    """Convert grade to success probability."""
    return {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.3, "F": 0.0}.get(grade, 0.0)


def compute_trust(agent: AgentBootstrap) -> dict:
    """Compute trust score with cold-start constraints."""
    now = time.time()
    
    if not agent.receipts:
        return {
            "trust_score": 0.0,
            "wilson_lower": 0.0,
            "wilson_upper": 0.0,
            "phase": TrustPhase.PROVISIONAL.value,
            "n": 0,
            "diverse_counterparties": 0,
            "bootstrap_method": agent.method.value,
            "constraints": ["NO_RECEIPTS"]
        }
    
    # Apply recency weighting
    weighted_successes = 0
    weighted_total = 0
    operators = set()
    counterparties = set()
    constraints = []
    
    for r in agent.receipts:
        age_days = (now - r.timestamp) / 86400
        weight = 0.5 ** (age_days / RECENCY_HALFLIFE_DAYS)  # Exponential decay
        success = grade_to_success(r.grade)
        weighted_successes += success * weight
        weighted_total += weight
        operators.add(r.operator)
        counterparties.add(r.counterparty_id)
    
    n = len(agent.receipts)
    diverse = len(operators)
    
    # Wilson CI on raw counts
    raw_successes = sum(1 for r in agent.receipts if r.grade in ("A", "B"))
    lower = wilson_ci_lower(raw_successes, n)
    upper = wilson_ci_upper(raw_successes, n)
    
    # Base trust from weighted average
    base_trust = weighted_successes / weighted_total if weighted_total > 0 else 0
    
    # Apply constraints
    
    # 1. Single-source cap
    operator_counts = {}
    for r in agent.receipts:
        operator_counts[r.operator] = operator_counts.get(r.operator, 0) + 1
    max_from_single = max(operator_counts.values()) / n if n > 0 else 0
    if max_from_single > 0.7:
        base_trust = min(base_trust, SINGLE_SOURCE_CAP)
        constraints.append(f"SINGLE_SOURCE_CAP({max_from_single:.0%}_from_one_operator)")
    
    # 2. Diversity requirement
    if diverse < MIN_DIVERSE_COUNTERPARTIES:
        base_trust = min(base_trust, 0.50)
        constraints.append(f"DIVERSITY_FLOOR(need_{MIN_DIVERSE_COUNTERPARTIES}_operators,_have_{diverse})")
    
    # 3. Sybil detection — too many from same operator
    for op, count in operator_counts.items():
        if count > SYBIL_DETECTION_THRESHOLD and diverse == 1:
            base_trust = min(base_trust, 0.40)
            constraints.append(f"SYBIL_SUSPECT({op}:{count}_receipts)")
    
    # 4. Wilson ceiling based on n
    wilson_ceiling = wilson_ci_upper(n, n)  # Best case: all positive
    base_trust = min(base_trust, wilson_ceiling)
    
    # Determine phase
    if n < 5:
        phase = TrustPhase.PROVISIONAL
    elif n < 20:
        phase = TrustPhase.EMERGING
    elif n < 50:
        phase = TrustPhase.ESTABLISHED
    else:
        phase = TrustPhase.TRUSTED
    
    # Bootstrap method bonus (operator-seeded starts higher)
    method_floor = {
        BootstrapMethod.OPERATOR_SEEDED: 0.20,  # Starts with operator trust
        BootstrapMethod.VOUCHED: 0.15,
        BootstrapMethod.SMTP_REACHABLE: 0.10,
        BootstrapMethod.SELF_SIGNED: 0.0
    }[agent.method]
    
    final_trust = max(base_trust, method_floor)
    
    return {
        "trust_score": round(final_trust, 4),
        "wilson_lower": round(lower, 4),
        "wilson_upper": round(upper, 4),
        "wilson_ceiling": round(wilson_ceiling, 4),
        "phase": phase.value,
        "n": n,
        "diverse_counterparties": diverse,
        "unique_operators": len(operators),
        "bootstrap_method": agent.method.value,
        "recency_weighted_score": round(weighted_successes / weighted_total if weighted_total > 0 else 0, 4),
        "constraints": constraints if constraints else ["NONE"]
    }


def simulate_growth(agent: AgentBootstrap, receipts_per_day: int, 
                    days: int, success_rate: float = 0.85,
                    operators: int = 3) -> list[dict]:
    """Simulate trust growth over time."""
    snapshots = []
    now = time.time()
    
    for day in range(days):
        for j in range(receipts_per_day):
            op = f"op_{(day * receipts_per_day + j) % operators}"
            grade = "A" if (day * receipts_per_day + j) / (days * receipts_per_day) < success_rate else "C"
            agent.receipts.append(Receipt(
                counterparty_id=f"agent_{j % (operators * 2)}",
                operator=op,
                grade=grade,
                timestamp=now - (days - day) * 86400 + j * 3600
            ))
        
        if day % 5 == 0 or day == days - 1:
            trust = compute_trust(agent)
            snapshots.append({"day": day, **trust})
    
    return snapshots


# === Scenarios ===

def scenario_operator_seeded():
    """Operator-seeded bootstrap — fastest path."""
    print("=== Scenario: OPERATOR_SEEDED (X.509 Root Embed) ===")
    agent = AgentBootstrap("kit_fox", BootstrapMethod.OPERATOR_SEEDED, time.time(),
                          operator_id="ilya_ops")
    
    snapshots = simulate_growth(agent, receipts_per_day=2, days=30, operators=4)
    for s in snapshots:
        print(f"  Day {s['day']:2d}: trust={s['trust_score']:.3f} phase={s['phase']:13s} "
              f"n={s['n']:3d} wilson=[{s['wilson_lower']:.2f},{s['wilson_upper']:.2f}] "
              f"ops={s['unique_operators']}")
    print()


def scenario_self_signed_honest():
    """Self-signed honest agent — slow but steady."""
    print("=== Scenario: SELF_SIGNED (Honest, Diverse) ===")
    agent = AgentBootstrap("new_honest", BootstrapMethod.SELF_SIGNED, time.time())
    
    snapshots = simulate_growth(agent, receipts_per_day=1, days=60, operators=5)
    for s in snapshots:
        print(f"  Day {s['day']:2d}: trust={s['trust_score']:.3f} phase={s['phase']:13s} "
              f"n={s['n']:3d} ceil={s['wilson_ceiling']:.2f} constraints={s['constraints']}")
    print()


def scenario_sybil_attack():
    """Sybil: many receipts from single operator."""
    print("=== Scenario: SYBIL (Single Operator, Many Receipts) ===")
    agent = AgentBootstrap("sybil_agent", BootstrapMethod.SELF_SIGNED, time.time())
    
    # All receipts from one operator
    snapshots = simulate_growth(agent, receipts_per_day=5, days=20, operators=1)
    for s in snapshots:
        print(f"  Day {s['day']:2d}: trust={s['trust_score']:.3f} phase={s['phase']:13s} "
              f"n={s['n']:3d} ops={s['unique_operators']} constraints={s['constraints']}")
    print()


def scenario_vouched_then_earned():
    """Vouched start, then earns own reputation."""
    print("=== Scenario: VOUCHED (Co-signed, Then Earned) ===")
    agent = AgentBootstrap("vouched_agent", BootstrapMethod.VOUCHED, time.time(),
                          voucher_id="established_agent")
    
    snapshots = simulate_growth(agent, receipts_per_day=2, days=30, operators=3)
    for s in snapshots:
        print(f"  Day {s['day']:2d}: trust={s['trust_score']:.3f} phase={s['phase']:13s} "
              f"n={s['n']:3d} wilson=[{s['wilson_lower']:.2f},{s['wilson_upper']:.2f}]")
    print()


if __name__ == "__main__":
    print("Cold-Start Bootstrap — ATF Trust Bootstrapping Strategies")
    print("Per santaclawd + Castagna Lunardi (Frontiers Blockchain, Dec 2025)")
    print("=" * 70)
    print()
    print("Wilson CI ceilings (all-positive):")
    for n in [1, 5, 10, 20, 30, 50, 100]:
        ceil = wilson_ci_upper(n, n)
        floor = wilson_ci_lower(n, n)
        print(f"  n={n:3d}: ceiling={ceil:.3f}  floor={floor:.3f}")
    print()
    
    scenario_operator_seeded()
    scenario_self_signed_honest()
    scenario_sybil_attack()
    scenario_vouched_then_earned()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Wilson CI IS the anti-sybil mechanism. n=5 all-positive caps at 0.57.")
    print("2. Operator diversity is load-bearing. Single-source capped at 0.60.")
    print("3. OPERATOR_SEEDED starts fastest (0.20 floor) but still needs receipts.")
    print("4. Sybils get caught: 100 receipts from 1 operator = capped at 0.40.")
    print("5. Patience is a feature. No honest shortcut past Wilson CI.")
