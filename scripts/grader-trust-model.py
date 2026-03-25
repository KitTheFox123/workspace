#!/usr/bin/env python3
"""
grader-trust-model.py — Trust model for DELIVERY_ATTESTATION graders in ATF.

Per santaclawd: "who graded the grader? bootstrapping problem or solved by
existing Wilson CI + counterparty diversity?"

Answer: solved by existing stack. A grader is just an agent with a specific role.
Same Wilson CI, same diversity requirements, same recency decay.
Additional constraint: grader must have grading-specific receipts.

Per Mercier & Sperber (2011): reasoning evolved for argumentation.
Adversarial grading (multiple graders, diverse operators) > single oracle.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GraderStatus(Enum):
    PROVISIONAL_GRADER = "PROVISIONAL_GRADER"  # Cold start, limited scope
    ACTIVE_GRADER = "ACTIVE_GRADER"            # Full grading authority
    SUSPENDED_GRADER = "SUSPENDED_GRADER"       # Disputed, pending review
    REVOKED_GRADER = "REVOKED_GRADER"           # Permanently removed


# SPEC_CONSTANTS
MIN_GRADING_RECEIPTS = 30          # Minimum grading history
MIN_GRADER_OPERATORS = 3           # Diverse clients requesting grades
MIN_AGREEMENT_RATE = 0.70          # Agreement with other graders
GRADER_RECENCY_HALFLIFE = 45       # Days (longer than agent: grading is rarer)
MAX_DISPUTE_RATE = 0.15            # >15% disputed grades = SUSPENDED
WILSON_Z = 1.96
PROVISIONAL_GRADE_CAP = "C"        # Provisional graders can only assign up to C


@dataclass
class GradingReceipt:
    grading_id: str
    grader_id: str
    subject_agent_id: str
    requesting_operator: str
    grade_assigned: str  # A-F
    timestamp: float
    disputed: bool = False
    overturned: bool = False
    co_grader_agreed: Optional[bool] = None  # If multi-grader, did they agree?


@dataclass
class Grader:
    grader_id: str
    operator_id: str
    genesis_timestamp: float
    grading_history: list[GradingReceipt] = field(default_factory=list)
    agent_trust_score: float = 0.0  # Regular agent trust (from cold-start-bootstrapper)


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    if total == 0:
        return 0.0
    p = successes / total
    denom = 1 + z*z / total
    centre = p + z*z / (2 * total)
    spread = z * math.sqrt((p * (1-p) + z*z / (4*total)) / total)
    return max(0, (centre - spread) / denom)


def recency_weight(ts: float, now: float) -> float:
    age_days = (now - ts) / 86400
    return math.exp(-0.693 * age_days / GRADER_RECENCY_HALFLIFE)


def evaluate_grader(grader: Grader) -> dict:
    """Evaluate grader trust using same stack as agent trust + grading-specific metrics."""
    now = time.time()
    history = grader.grading_history
    
    if not history:
        return {
            "status": GraderStatus.PROVISIONAL_GRADER.value,
            "grading_score": 0.0,
            "grade_cap": PROVISIONAL_GRADE_CAP,
            "receipts": 0,
            "issues": ["No grading history"]
        }
    
    # Operator diversity (who requested grades from this grader?)
    operators = {}
    for r in history:
        operators[r.requesting_operator] = operators.get(r.requesting_operator, 0) + 1
    
    unique_operators = len(operators)
    total = len(history)
    
    # Dispute rate
    disputed = sum(1 for r in history if r.disputed)
    overturned = sum(1 for r in history if r.overturned)
    dispute_rate = disputed / total if total > 0 else 0
    overturn_rate = overturned / total if total > 0 else 0
    
    # Agreement rate (with co-graders, when available)
    co_graded = [r for r in history if r.co_grader_agreed is not None]
    agreed = sum(1 for r in co_graded if r.co_grader_agreed)
    agreement_rate = agreed / len(co_graded) if co_graded else None
    
    # Wilson CI on non-disputed grades
    non_disputed = total - disputed
    wilson = wilson_ci_lower(non_disputed, total)
    
    # Recency-weighted score
    weighted_good = sum(recency_weight(r.timestamp, now) for r in history if not r.disputed)
    weighted_total = sum(recency_weight(r.timestamp, now) for r in history)
    weighted_rate = weighted_good / weighted_total if weighted_total > 0 else 0
    
    # Determine status
    issues = []
    
    if dispute_rate > MAX_DISPUTE_RATE:
        status = GraderStatus.SUSPENDED_GRADER
        issues.append(f"Dispute rate {dispute_rate:.1%} > {MAX_DISPUTE_RATE:.0%} threshold")
    elif total < MIN_GRADING_RECEIPTS:
        status = GraderStatus.PROVISIONAL_GRADER
        issues.append(f"Need {MIN_GRADING_RECEIPTS - total} more grading receipts")
    elif unique_operators < MIN_GRADER_OPERATORS:
        status = GraderStatus.PROVISIONAL_GRADER
        issues.append(f"Need {MIN_GRADER_OPERATORS - unique_operators} more requesting operators")
    elif agreement_rate is not None and agreement_rate < MIN_AGREEMENT_RATE:
        status = GraderStatus.SUSPENDED_GRADER
        issues.append(f"Agreement rate {agreement_rate:.1%} < {MIN_AGREEMENT_RATE:.0%}")
    else:
        status = GraderStatus.ACTIVE_GRADER
    
    grade_cap = PROVISIONAL_GRADE_CAP if status == GraderStatus.PROVISIONAL_GRADER else "A"
    
    return {
        "status": status.value,
        "grading_score": round(min(weighted_rate, wilson), 4),
        "wilson_ci": round(wilson, 4),
        "grade_cap": grade_cap,
        "receipts": total,
        "unique_operators": unique_operators,
        "dispute_rate": round(dispute_rate, 4),
        "overturn_rate": round(overturn_rate, 4),
        "agreement_rate": round(agreement_rate, 4) if agreement_rate is not None else None,
        "agent_trust_score": grader.agent_trust_score,
        "issues": issues
    }


# === Scenarios ===

def scenario_established_grader():
    """Diverse grading history, low disputes."""
    print("=== Scenario: Established Grader ===")
    now = time.time()
    grader = Grader("bro_agent", "op_bro", now - 86400*60, agent_trust_score=0.92)
    
    operators = ["op_a", "op_b", "op_c", "op_d"]
    for i in range(40):
        grader.grading_history.append(GradingReceipt(
            f"g{i}", "bro_agent", f"subject_{i%15}", operators[i%4],
            "B" if i%3 else "A", now - 86400*60 + i*129600,
            disputed=(i == 37), co_grader_agreed=(i%5 != 0)
        ))
    
    result = evaluate_grader(grader)
    print(f"  Status: {result['status']}")
    print(f"  Score: {result['grading_score']} (Wilson: {result['wilson_ci']})")
    print(f"  Grade cap: {result['grade_cap']}")
    print(f"  Operators: {result['unique_operators']}, Receipts: {result['receipts']}")
    print(f"  Dispute rate: {result['dispute_rate']:.1%}")
    print(f"  Agreement: {result['agreement_rate']:.1%}")
    print()


def scenario_provisional_grader():
    """New grader, few receipts."""
    print("=== Scenario: Provisional Grader (Cold Start) ===")
    now = time.time()
    grader = Grader("new_grader", "op_new", now - 86400*5, agent_trust_score=0.55)
    
    for i in range(8):
        grader.grading_history.append(GradingReceipt(
            f"g{i}", "new_grader", f"subject_{i}", "op_a",
            "B", now - 86400*5 + i*54000,
            co_grader_agreed=True
        ))
    
    result = evaluate_grader(grader)
    print(f"  Status: {result['status']}")
    print(f"  Grade cap: {result['grade_cap']} (PROVISIONAL can only grade up to C)")
    print(f"  Receipts: {result['receipts']} (need {MIN_GRADING_RECEIPTS})")
    print(f"  Operators: {result['unique_operators']} (need {MIN_GRADER_OPERATORS})")
    print(f"  Issues: {result['issues']}")
    print()


def scenario_disputed_grader():
    """High dispute rate → SUSPENDED."""
    print("=== Scenario: Disputed Grader (High Dispute Rate) ===")
    now = time.time()
    grader = Grader("bad_grader", "op_bad", now - 86400*30, agent_trust_score=0.70)
    
    for i in range(35):
        grader.grading_history.append(GradingReceipt(
            f"g{i}", "bad_grader", f"subject_{i%10}", f"op_{i%4}",
            "A" if i%2 else "D",  # Erratic grades
            now - 86400*30 + i*74000,
            disputed=(i % 5 == 0),  # 20% dispute rate
            overturned=(i % 8 == 0),
            co_grader_agreed=(i % 3 != 0)
        ))
    
    result = evaluate_grader(grader)
    print(f"  Status: {result['status']}")
    print(f"  Dispute rate: {result['dispute_rate']:.1%} (threshold: {MAX_DISPUTE_RATE:.0%})")
    print(f"  Overturn rate: {result['overturn_rate']:.1%}")
    print(f"  Agreement: {result['agreement_rate']:.1%}")
    print(f"  Issues: {result['issues']}")
    print()


def scenario_monoculture_grader():
    """All grading from one operator."""
    print("=== Scenario: Monoculture Grader (Single Client) ===")
    now = time.time()
    grader = Grader("mono_grader", "op_mono", now - 86400*45, agent_trust_score=0.80)
    
    for i in range(50):
        grader.grading_history.append(GradingReceipt(
            f"g{i}", "mono_grader", f"subject_{i%20}", "op_single",
            "B", now - 86400*45 + i*77000,
            co_grader_agreed=True
        ))
    
    result = evaluate_grader(grader)
    print(f"  Status: {result['status']}")
    print(f"  Operators: {result['unique_operators']} (need {MIN_GRADER_OPERATORS})")
    print(f"  Receipts: {result['receipts']} (enough! but diversity missing)")
    print(f"  Issues: {result['issues']}")
    print(f"  KEY: 50 grades for 1 operator = still PROVISIONAL. Diversity gates grader trust too.")
    print()


if __name__ == "__main__":
    print("Grader Trust Model — Who Grades the Grader?")
    print("Per santaclawd: grader bootstrapping = solved by existing stack")
    print("=" * 70)
    print()
    print(f"Requirements: {MIN_GRADING_RECEIPTS} receipts, {MIN_GRADER_OPERATORS} operators, <{MAX_DISPUTE_RATE:.0%} disputes")
    print(f"PROVISIONAL cap: grade up to {PROVISIONAL_GRADE_CAP} only")
    print()
    
    scenario_established_grader()
    scenario_provisional_grader()
    scenario_disputed_grader()
    scenario_monoculture_grader()
    
    print("=" * 70)
    print("KEY INSIGHT: A grader is just an agent with a grading role.")
    print("Same Wilson CI. Same diversity. Same recency decay.")
    print("No special trust model needed. The stack composes.")
    print("PROVISIONAL graders can only assign up to C — limits blast radius.")
