#!/usr/bin/env python3
"""
cold-start-bootstrapper.py — ATF cold start trust accumulation simulator.

Per santaclawd: spec handles verification (math), cannot manufacture receipts.
Per Duncan (Brit J Psych 2025): trust learning follows Bayesian updating.
Per Nature 2025: network stability requires passive information transmitters.

Key insight: cold start = repeated trust game. PROVISIONAL is the only honest
state for new agents. Wilson CI prevents gaming (5 perfect receipts = 0.57 ceiling).
Minimum 2 diverse counterparty classes required for TRUSTED promotion.

Social fix: engage early, build diverse counterparties, let Wilson CI accumulate.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustPhase(Enum):
    PROVISIONAL = "PROVISIONAL"   # Cold start, no receipts
    EMERGING = "EMERGING"         # Some receipts, insufficient diversity
    ESTABLISHED = "ESTABLISHED"   # Meets minimum thresholds
    TRUSTED = "TRUSTED"           # Full behavioral trust


# SPEC_CONSTANTS
MIN_RECEIPTS_FOR_EMERGING = 5
MIN_RECEIPTS_FOR_ESTABLISHED = 20
MIN_RECEIPTS_FOR_TRUSTED = 50
MIN_COUNTERPARTY_CLASSES = 2     # Diverse sources required
MIN_DAYS_SPAN = 7               # Temporal spread required
WILSON_Z = 1.96                  # 95% confidence
TRUSTED_FLOOR = 0.70             # Wilson CI lower bound minimum


@dataclass
class Receipt:
    counterparty_id: str
    counterparty_operator: str  # Operator = "class" for diversity
    timestamp: float
    success: bool
    grade: str  # A-F


@dataclass
class AgentTrustProfile:
    agent_id: str
    receipts: list[Receipt] = field(default_factory=list)
    phase: TrustPhase = TrustPhase.PROVISIONAL
    wilson_lower: float = 0.0
    wilson_upper: float = 1.0
    counterparty_diversity: float = 0.0
    days_span: float = 0.0


def wilson_ci(successes: int, total: int, z: float = WILSON_Z) -> tuple[float, float]:
    """Wilson score confidence interval."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z*z / total
    centre = (p + z*z / (2*total)) / denom
    spread = z * math.sqrt((p*(1-p) + z*z/(4*total)) / total) / denom
    return (max(0, round(centre - spread, 4)), min(1, round(centre + spread, 4)))


def simpson_diversity(operators: list[str]) -> float:
    """Simpson diversity index on operator distribution."""
    if not operators:
        return 0.0
    n = len(operators)
    counts = {}
    for op in operators:
        counts[op] = counts.get(op, 0) + 1
    return round(1.0 - sum((c/n)**2 for c in counts.values()), 4)


def compute_profile(agent_id: str, receipts: list[Receipt]) -> AgentTrustProfile:
    """Compute full trust profile from receipt history."""
    profile = AgentTrustProfile(agent_id=agent_id, receipts=receipts)
    
    if not receipts:
        return profile
    
    # Basic counts
    successes = sum(1 for r in receipts if r.success)
    total = len(receipts)
    
    # Wilson CI
    lower, upper = wilson_ci(successes, total)
    profile.wilson_lower = lower
    profile.wilson_upper = upper
    
    # Counterparty diversity (by operator class, not by individual)
    operators = [r.counterparty_operator for r in receipts]
    unique_operators = set(operators)
    profile.counterparty_diversity = simpson_diversity(operators)
    
    # Temporal span
    timestamps = [r.timestamp for r in receipts]
    profile.days_span = (max(timestamps) - min(timestamps)) / 86400 if len(timestamps) > 1 else 0
    
    # Phase determination
    n_classes = len(unique_operators)
    
    if total < MIN_RECEIPTS_FOR_EMERGING:
        profile.phase = TrustPhase.PROVISIONAL
    elif total < MIN_RECEIPTS_FOR_ESTABLISHED:
        profile.phase = TrustPhase.EMERGING
    elif total < MIN_RECEIPTS_FOR_TRUSTED:
        if n_classes >= MIN_COUNTERPARTY_CLASSES and profile.days_span >= MIN_DAYS_SPAN:
            profile.phase = TrustPhase.ESTABLISHED
        else:
            profile.phase = TrustPhase.EMERGING  # Stuck without diversity
    else:
        if (n_classes >= MIN_COUNTERPARTY_CLASSES and 
            profile.days_span >= MIN_DAYS_SPAN and
            lower >= TRUSTED_FLOOR):
            profile.phase = TrustPhase.TRUSTED
        elif n_classes >= MIN_COUNTERPARTY_CLASSES:
            profile.phase = TrustPhase.ESTABLISHED
        else:
            profile.phase = TrustPhase.EMERGING  # PGP failure mode
    
    return profile


def print_profile(profile: AgentTrustProfile):
    """Pretty-print trust profile."""
    total = len(profile.receipts)
    successes = sum(1 for r in profile.receipts if r.success)
    operators = set(r.counterparty_operator for r in profile.receipts)
    
    print(f"  Agent: {profile.agent_id}")
    print(f"  Phase: {profile.phase.value}")
    print(f"  Receipts: {total} ({successes} success)")
    print(f"  Wilson CI: [{profile.wilson_lower}, {profile.wilson_upper}]")
    print(f"  Counterparty classes: {len(operators)} (diversity: {profile.counterparty_diversity})")
    print(f"  Temporal span: {profile.days_span:.1f} days")
    
    # Phase requirements check
    if profile.phase != TrustPhase.TRUSTED:
        needs = []
        if total < MIN_RECEIPTS_FOR_TRUSTED:
            needs.append(f"{MIN_RECEIPTS_FOR_TRUSTED - total} more receipts")
        if len(operators) < MIN_COUNTERPARTY_CLASSES:
            needs.append(f"{MIN_COUNTERPARTY_CLASSES - len(operators)} more counterparty classes")
        if profile.days_span < MIN_DAYS_SPAN:
            needs.append(f"{MIN_DAYS_SPAN - profile.days_span:.1f} more days")
        if profile.wilson_lower < TRUSTED_FLOOR:
            needs.append(f"Wilson lower {profile.wilson_lower} < {TRUSTED_FLOOR}")
        if needs:
            print(f"  Needs: {', '.join(needs)}")
    print()


# === Scenarios ===

def scenario_honest_newcomer():
    """New agent building trust through diverse engagement."""
    print("=== Scenario: Honest Newcomer ===")
    now = time.time()
    
    receipts = []
    # Week 1: 5 receipts from operator A
    for i in range(5):
        receipts.append(Receipt(f"agent_a{i}", "op_alpha", now - 86400*13 + i*3600, True, "B"))
    # Week 2: 10 receipts from operators B and C
    for i in range(5):
        receipts.append(Receipt(f"agent_b{i}", "op_beta", now - 86400*6 + i*3600, True, "B"))
    for i in range(5):
        receipts.append(Receipt(f"agent_c{i}", "op_gamma", now - 86400*3 + i*3600, True, "A"))
    # Week 3: 35 more, mixed
    for i in range(35):
        op = ["op_alpha", "op_beta", "op_gamma", "op_delta"][i % 4]
        receipts.append(Receipt(f"agent_{i}", op, now - 86400*2 + i*1800, i % 20 != 0, "B"))
    
    profile = compute_profile("honest_newcomer", receipts)
    print_profile(profile)


def scenario_sybil_single_source():
    """Agent with 1000 receipts from single operator — PGP failure mode."""
    print("=== Scenario: Sybil — Single Source (PGP Failure) ===")
    now = time.time()
    
    receipts = [
        Receipt(f"puppet_{i}", "op_sybil", now - 86400*30 + i*2600, True, "A")
        for i in range(100)
    ]
    
    profile = compute_profile("sybil_agent", receipts)
    print_profile(profile)


def scenario_cold_start_progression():
    """Track phase progression over time."""
    print("=== Scenario: Cold Start Progression ===")
    now = time.time()
    
    receipts = []
    checkpoints = [1, 5, 10, 20, 35, 50]
    
    for i in range(50):
        op = ["op_a", "op_b", "op_c"][i % 3] if i >= 5 else "op_a"
        receipts.append(Receipt(f"cp_{i}", op, now - 86400*14 + i*24000, i % 15 != 0, "B"))
        
        if i + 1 in checkpoints:
            profile = compute_profile("progressing_agent", receipts[:i+1])
            total = i + 1
            operators = len(set(r.counterparty_operator for r in receipts[:i+1]))
            print(f"  n={total:2d}: phase={profile.phase.value:15s} "
                  f"Wilson=[{profile.wilson_lower},{profile.wilson_upper}] "
                  f"classes={operators} span={profile.days_span:.0f}d")
    print()


def scenario_fast_failure():
    """Agent with early failures — Wilson CI prevents recovery gaming."""
    print("=== Scenario: Early Failures ===")
    now = time.time()
    
    # 10 failures, then 40 successes
    receipts = []
    for i in range(10):
        receipts.append(Receipt(f"fail_{i}", "op_a", now - 86400*20 + i*3600, False, "F"))
    for i in range(40):
        op = ["op_b", "op_c"][i % 2]
        receipts.append(Receipt(f"recover_{i}", op, now - 86400*10 + i*7200, True, "B"))
    
    profile = compute_profile("failed_then_recovered", receipts)
    print_profile(profile)


def scenario_wilson_ceiling_demo():
    """Demonstrate Wilson CI ceiling at low n."""
    print("=== Scenario: Wilson CI Ceiling at Low N ===")
    for n in [1, 3, 5, 10, 20, 30, 50, 100]:
        lower, upper = wilson_ci(n, n)  # All successes
        print(f"  n={n:3d}, all success: Wilson lower={lower:.3f} "
              f"{'< TRUSTED floor' if lower < TRUSTED_FLOOR else '>= TRUSTED floor'}")
    print(f"  TRUSTED floor = {TRUSTED_FLOOR}")
    print(f"  Minimum n for TRUSTED with all success: ~{next(n for n in range(1,200) if wilson_ci(n,n)[0] >= TRUSTED_FLOOR)}")
    print()


if __name__ == "__main__":
    print("Cold Start Bootstrapper — ATF Trust Accumulation Simulator")
    print("Per santaclawd + Duncan (Brit J Psych 2025) + Nature 2025")
    print("=" * 70)
    print()
    
    scenario_wilson_ceiling_demo()
    scenario_cold_start_progression()
    scenario_honest_newcomer()
    scenario_sybil_single_source()
    scenario_fast_failure()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. PROVISIONAL is the only honest cold-start state")
    print("2. Wilson CI prevents gaming (5 perfect = 0.57 ceiling)")
    print("3. Counterparty diversity is MANDATORY (single-source = PGP failure)")
    print("4. Temporal span prevents burst-gaming")
    print("5. Social engagement is the ONLY path to TRUSTED — spec cannot manufacture it")
