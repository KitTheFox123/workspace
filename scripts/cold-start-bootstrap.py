#!/usr/bin/env python3
"""
cold-start-bootstrap.py — ATF cold-start trust bootstrapping via social vouching.

Per santaclawd: "no spec fully solves cold start. the fix is social."
Per funwolf: "bootstrapping trust is a social problem, not a crypto problem."
Per drainfun: "flat endorsement graphs are how you get DigiNotar situations."

Cold start progression:
  ZERO       → PROVISIONAL  (operator-seeded, X.509 root CA model)
  PROVISIONAL → EMERGING     (first diverse counterparty vouch)
  EMERGING    → ESTABLISHED  (Wilson CI >= 0.70, n>=20, 2+ counterparty classes)
  ESTABLISHED → TRUSTED      (Wilson CI >= 0.85, n>=50, 3+ classes, 30+ days)

Key insight: first vouch is hardest. After that, Wilson CI compounds.
Each new receipt makes the next one cheaper to earn (Parfit overlapping chains).

Nature 2025 (Sci Rep): passive nodes transmit trust info. Lurkers are load-bearing.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustPhase(Enum):
    ZERO = "ZERO"               # No receipts, no vouches
    PROVISIONAL = "PROVISIONAL" # Operator-seeded only
    EMERGING = "EMERGING"       # First external vouch
    ESTABLISHED = "ESTABLISHED" # Wilson CI threshold met
    TRUSTED = "TRUSTED"         # Full trust, diverse + sustained


# SPEC_CONSTANTS
EMERGING_MIN_COUNTERPARTIES = 1
ESTABLISHED_MIN_CI = 0.70
ESTABLISHED_MIN_N = 20
ESTABLISHED_MIN_CLASSES = 2
TRUSTED_MIN_CI = 0.85
TRUSTED_MIN_N = 50
TRUSTED_MIN_CLASSES = 3
TRUSTED_MIN_DAYS = 30
WILSON_Z = 1.96  # 95% confidence


@dataclass
class Receipt:
    receipt_id: str
    counterparty_id: str
    counterparty_class: str  # operator class (diverse = different operators)
    outcome: bool  # True = positive, False = negative
    timestamp: float
    grade: str  # A-F
    is_bootstrap: bool = False  # True if operator-seeded


@dataclass
class AgentTrustState:
    agent_id: str
    receipts: list[Receipt] = field(default_factory=list)
    phase: TrustPhase = TrustPhase.ZERO
    wilson_ci_lower: float = 0.0
    counterparty_classes: set = field(default_factory=set)
    first_receipt_at: Optional[float] = None
    last_receipt_at: Optional[float] = None


def wilson_ci_lower(positive: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p_hat = positive / total
    denominator = 1 + z**2 / total
    center = p_hat + z**2 / (2 * total)
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)
    return (center - spread) / denominator


def simpson_diversity(classes: dict) -> float:
    """Simpson diversity index on counterparty class distribution."""
    total = sum(classes.values())
    if total <= 1:
        return 0.0
    return 1.0 - sum((c/total)**2 for c in classes.values())


def evaluate_trust(state: AgentTrustState) -> dict:
    """Evaluate trust phase based on receipt history."""
    receipts = state.receipts
    
    if not receipts:
        state.phase = TrustPhase.ZERO
        return {
            "phase": TrustPhase.ZERO.value,
            "wilson_ci": 0.0,
            "n": 0,
            "counterparty_classes": 0,
            "reason": "No receipts"
        }
    
    # Count non-bootstrap receipts
    external = [r for r in receipts if not r.is_bootstrap]
    positive = sum(1 for r in external if r.outcome)
    total = len(external)
    
    # Wilson CI
    ci = wilson_ci_lower(positive, total) if total > 0 else 0.0
    state.wilson_ci_lower = ci
    
    # Counterparty class diversity
    class_counts = {}
    for r in external:
        class_counts[r.counterparty_class] = class_counts.get(r.counterparty_class, 0) + 1
    num_classes = len(class_counts)
    diversity = simpson_diversity(class_counts)
    state.counterparty_classes = set(class_counts.keys())
    
    # Time span
    timestamps = [r.timestamp for r in receipts]
    state.first_receipt_at = min(timestamps)
    state.last_receipt_at = max(timestamps)
    span_days = (state.last_receipt_at - state.first_receipt_at) / 86400
    
    # Only bootstrap receipts?
    has_bootstrap = any(r.is_bootstrap for r in receipts)
    
    # Phase determination
    reason = ""
    if total == 0 and has_bootstrap:
        state.phase = TrustPhase.PROVISIONAL
        reason = "Operator-seeded only, no external vouches"
    elif total > 0 and ci >= TRUSTED_MIN_CI and total >= TRUSTED_MIN_N and num_classes >= TRUSTED_MIN_CLASSES and span_days >= TRUSTED_MIN_DAYS:
        state.phase = TrustPhase.TRUSTED
        reason = f"CI={ci:.3f}>=0.85, n={total}>=50, classes={num_classes}>=3, days={span_days:.0f}>=30"
    elif total > 0 and ci >= ESTABLISHED_MIN_CI and total >= ESTABLISHED_MIN_N and num_classes >= ESTABLISHED_MIN_CLASSES:
        state.phase = TrustPhase.ESTABLISHED
        reason = f"CI={ci:.3f}>=0.70, n={total}>=20, classes={num_classes}>=2"
    elif num_classes >= EMERGING_MIN_COUNTERPARTIES:
        state.phase = TrustPhase.EMERGING
        reason = f"First external vouch from {num_classes} class(es)"
    elif has_bootstrap:
        state.phase = TrustPhase.PROVISIONAL
        reason = "Bootstrap only, no diverse external vouches"
    else:
        state.phase = TrustPhase.ZERO
        reason = "Insufficient receipts"
    
    return {
        "phase": state.phase.value,
        "wilson_ci": round(ci, 4),
        "n_external": total,
        "n_positive": positive,
        "counterparty_classes": num_classes,
        "simpson_diversity": round(diversity, 3),
        "span_days": round(span_days, 1),
        "reason": reason,
        "next_phase": _next_phase_requirements(state.phase, ci, total, num_classes, span_days)
    }


def _next_phase_requirements(current: TrustPhase, ci: float, n: int, classes: int, days: float) -> dict:
    """What's needed to reach next phase."""
    if current == TrustPhase.ZERO:
        return {"target": "PROVISIONAL", "need": "Operator seed (BOOTSTRAP_REQUEST)"}
    elif current == TrustPhase.PROVISIONAL:
        return {"target": "EMERGING", "need": "1+ external counterparty vouch"}
    elif current == TrustPhase.EMERGING:
        needs = []
        if ci < ESTABLISHED_MIN_CI:
            needs.append(f"CI {ci:.3f} → {ESTABLISHED_MIN_CI}")
        if n < ESTABLISHED_MIN_N:
            needs.append(f"n={n} → {ESTABLISHED_MIN_N}")
        if classes < ESTABLISHED_MIN_CLASSES:
            needs.append(f"classes={classes} → {ESTABLISHED_MIN_CLASSES}")
        return {"target": "ESTABLISHED", "need": ", ".join(needs) if needs else "met"}
    elif current == TrustPhase.ESTABLISHED:
        needs = []
        if ci < TRUSTED_MIN_CI:
            needs.append(f"CI {ci:.3f} → {TRUSTED_MIN_CI}")
        if n < TRUSTED_MIN_N:
            needs.append(f"n={n} → {TRUSTED_MIN_N}")
        if classes < TRUSTED_MIN_CLASSES:
            needs.append(f"classes={classes} → {TRUSTED_MIN_CLASSES}")
        if days < TRUSTED_MIN_DAYS:
            needs.append(f"days={days:.0f} → {TRUSTED_MIN_DAYS}")
        return {"target": "TRUSTED", "need": ", ".join(needs) if needs else "met"}
    else:
        return {"target": "TRUSTED (max)", "need": "Maintain CI + diversity"}


def vouch_cost(state: AgentTrustState) -> float:
    """
    Marginal cost of next vouch decreases as receipts accumulate.
    Parfit overlapping chains: each receipt makes the next cheaper.
    """
    n = len([r for r in state.receipts if not r.is_bootstrap])
    if n == 0:
        return 1.0  # First vouch = maximum cost
    # Diminishing marginal cost: 1/sqrt(n+1)
    return 1.0 / math.sqrt(n + 1)


# === Scenarios ===

def scenario_fresh_agent():
    """Brand new agent — ZERO to PROVISIONAL."""
    print("=== Scenario: Fresh Agent (Zero → Provisional) ===")
    now = time.time()
    
    state = AgentTrustState(agent_id="fresh_agent")
    result = evaluate_trust(state)
    print(f"  Phase: {result['phase']} — {result['reason']}")
    print(f"  Vouch cost: {vouch_cost(state):.3f} (maximum)")
    
    # Operator seeds bootstrap receipt
    state.receipts.append(Receipt("boot_001", "operator_1", "operator", True, now, "B", is_bootstrap=True))
    result = evaluate_trust(state)
    print(f"  After bootstrap: {result['phase']} — {result['reason']}")
    print(f"  Next: {result['next_phase']}")
    print()


def scenario_building_trust():
    """Agent builds trust over 60 days."""
    print("=== Scenario: Building Trust (Provisional → Trusted) ===")
    now = time.time()
    
    state = AgentTrustState(agent_id="building_agent")
    
    # Bootstrap
    state.receipts.append(Receipt("boot", "op", "operator", True, now - 86400*60, "B", is_bootstrap=True))
    
    # Accumulate diverse receipts over 60 days
    classes = ["class_A", "class_B", "class_C", "class_D"]
    for i in range(60):
        cls = classes[i % len(classes)]
        outcome = True if i != 15 else False  # One failure at i=15
        state.receipts.append(Receipt(
            f"r{i:03d}", f"agent_{i%20}", cls, outcome,
            now - 86400*(60-i), "B" if outcome else "D"
        ))
        
        if i in [0, 4, 9, 19, 29, 49, 59]:
            result = evaluate_trust(state)
            cost = vouch_cost(state)
            print(f"  n={i+1:2d}: {result['phase']:12s} CI={result['wilson_ci']:.3f} "
                  f"classes={result['counterparty_classes']} cost={cost:.3f} "
                  f"days={result['span_days']:.0f}")
    
    print(f"  Final: {result['next_phase']}")
    print()


def scenario_sybil_monoculture():
    """1000 receipts from one operator — stuck at EMERGING."""
    print("=== Scenario: Sybil Monoculture (Stuck at Emerging) ===")
    now = time.time()
    
    state = AgentTrustState(agent_id="sybil_agent")
    state.receipts.append(Receipt("boot", "op", "operator", True, now - 86400*90, "B", is_bootstrap=True))
    
    # 1000 receipts, all from same class
    for i in range(1000):
        state.receipts.append(Receipt(
            f"r{i:04d}", f"sybil_{i%5}", "single_operator",
            True, now - 86400*(90-i*0.09), "A"
        ))
    
    result = evaluate_trust(state)
    print(f"  1000 receipts, 1 class: {result['phase']}")
    print(f"  CI={result['wilson_ci']:.3f}, classes={result['counterparty_classes']}")
    print(f"  Simpson diversity: {result['simpson_diversity']}")
    print(f"  Next: {result['next_phase']}")
    print(f"  KEY: Volume without diversity = stuck at EMERGING")
    print()


def scenario_parfit_cost_curve():
    """Show diminishing vouch cost as receipts accumulate."""
    print("=== Scenario: Parfit Cost Curve ===")
    now = time.time()
    
    state = AgentTrustState(agent_id="cost_agent")
    costs = []
    for i in range(50):
        cost = vouch_cost(state)
        costs.append((i, cost))
        state.receipts.append(Receipt(f"r{i}", f"a{i%10}", f"c{i%4}", True, now, "B"))
    
    for n, c in [(0, costs[0][1]), (1, costs[1][1]), (5, costs[5][1]), 
                  (10, costs[10][1]), (25, costs[25][1]), (49, costs[49][1])]:
        print(f"  n={n:2d}: vouch_cost={c:.3f}")
    
    print(f"  First vouch: {costs[0][1]:.3f} (maximum)")
    print(f"  50th vouch:  {costs[49][1]:.3f} ({costs[49][1]/costs[0][1]*100:.0f}% of first)")
    print(f"  Parfit: each receipt makes the next cheaper to earn")
    print()


if __name__ == "__main__":
    print("Cold-Start Bootstrap — Social Trust Bootstrapping for ATF")
    print("Per santaclawd + funwolf + drainfun")
    print("=" * 70)
    print()
    print("Progression: ZERO → PROVISIONAL → EMERGING → ESTABLISHED → TRUSTED")
    print(f"  PROVISIONAL: operator seed (BOOTSTRAP_REQUEST)")
    print(f"  EMERGING:    first external vouch")
    print(f"  ESTABLISHED: CI>={ESTABLISHED_MIN_CI}, n>={ESTABLISHED_MIN_N}, {ESTABLISHED_MIN_CLASSES}+ classes")
    print(f"  TRUSTED:     CI>={TRUSTED_MIN_CI}, n>={TRUSTED_MIN_N}, {TRUSTED_MIN_CLASSES}+ classes, {TRUSTED_MIN_DAYS}+ days")
    print()
    
    scenario_fresh_agent()
    scenario_building_trust()
    scenario_sybil_monoculture()
    scenario_parfit_cost_curve()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Cold start is SOCIAL, not crypto. Spec cannot manufacture receipts.")
    print("2. First vouch = maximum cost. Each subsequent vouch is cheaper (Parfit).")
    print("3. Volume without diversity = stuck. 1000 receipts, 1 class = EMERGING.")
    print("4. Wilson CI naturally penalizes low-n. Anti-sybil is built into the math.")
    print("5. Passive nodes transmit trust (Nature 2025). Lurkers are load-bearing.")
