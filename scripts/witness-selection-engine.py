#!/usr/bin/env python3
"""
witness-selection-engine.py — Witness selection for ATF EMERGENCY ceremonies.

Per santaclawd: "where do the 7 witnesses come from? witness selection
is the new attack surface."

Three models:
  DESIGNATED — Registry stewards (CA/Browser Forum model: 3 browsers)
  REPUTATION — Random from pool weighted by Wilson CI co-sign rate
  HYBRID     — Counterparty-nominated + mutual veto + reputation floor

EMERGENCY ceremonies use REPUTATION model:
  - Random selection weighted by co-sign rate
  - Wilson CI ≥ 0.8 filter (sybil-resistant)
  - Operator diversity required (Simpson index)
  - No self-selection allowed

Attack surface analysis:
  - DESIGNATED: capture risk (compromise 3 stewards = game over)
  - REPUTATION: sybil risk (mitigated by Wilson CI + operator diversity)
  - HYBRID: collusion risk (counterparty + nominee agree to lie)
"""

import hashlib
import random
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SelectionModel(Enum):
    DESIGNATED = "DESIGNATED"   # Fixed stewards
    REPUTATION = "REPUTATION"   # Random + Wilson CI weighted
    HYBRID = "HYBRID"           # Counterparty-nominated + veto


# SPEC_CONSTANTS
MIN_EMERGENCY_WITNESSES = 7
QUORUM_RATIO = 0.51  # 51% must agree (BFT: f < n/3 for Byzantine, 51% for CFT)
WILSON_Z = 1.96      # 95% CI
MIN_WILSON_SCORE = 0.80  # Minimum reputation for witness eligibility
MIN_OPERATOR_DIVERSITY = 0.50  # Simpson diversity index minimum
MAX_SAME_OPERATOR = 0.33  # No operator controls > 33% of witnesses
COOLDOWN_CEREMONIES = 3  # Can't witness 3+ ceremonies in 7 days


@dataclass
class Agent:
    agent_id: str
    operator_id: str
    cosign_total: int
    cosign_confirmed: int
    ceremonies_recent: int = 0  # In last 7 days
    is_requestor: bool = False
    is_counterparty: bool = False


def wilson_lower(confirmed: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score lower bound."""
    if total == 0:
        return 0.0
    p = confirmed / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (centre - spread) / denominator


def simpson_diversity(operator_counts: dict[str, int]) -> float:
    """Simpson diversity index. 1.0 = perfectly diverse, 0.0 = monoculture."""
    total = sum(operator_counts.values())
    if total <= 1:
        return 0.0
    sum_ni = sum(n * (n - 1) for n in operator_counts.values())
    return 1.0 - sum_ni / (total * (total - 1))


def select_designated(stewards: list[Agent], n: int) -> dict:
    """Fixed registry stewards. CA/Browser Forum model."""
    eligible = [a for a in stewards if not a.is_requestor and not a.is_counterparty]
    if len(eligible) < n:
        return {
            "model": "DESIGNATED",
            "status": "INSUFFICIENT_STEWARDS",
            "available": len(eligible),
            "required": n,
            "selected": [],
            "risk": "CAPTURE — compromising fixed stewards = total control"
        }
    selected = eligible[:n]
    ops = {}
    for a in selected:
        ops[a.operator_id] = ops.get(a.operator_id, 0) + 1
    return {
        "model": "DESIGNATED",
        "status": "SELECTED",
        "selected": [a.agent_id for a in selected],
        "operator_diversity": round(simpson_diversity(ops), 3),
        "risk": f"CAPTURE — {len(set(ops))} operators control all witnesses"
    }


def select_reputation(pool: list[Agent], n: int, seed: str = "ceremony") -> dict:
    """Random selection weighted by Wilson CI. Sybil-resistant."""
    # Filter: eligible agents
    eligible = []
    for a in pool:
        if a.is_requestor or a.is_counterparty:
            continue
        if a.ceremonies_recent >= COOLDOWN_CEREMONIES:
            continue
        wilson = wilson_lower(a.cosign_confirmed, a.cosign_total)
        if wilson >= MIN_WILSON_SCORE:
            eligible.append((a, wilson))
    
    if len(eligible) < n:
        return {
            "model": "REPUTATION",
            "status": "INSUFFICIENT_ELIGIBLE",
            "available": len(eligible),
            "required": n,
            "min_wilson": MIN_WILSON_SCORE,
            "selected": []
        }
    
    # Weighted random selection
    rng = random.Random(hashlib.sha256(seed.encode()).hexdigest())
    weights = [w for _, w in eligible]
    selected = []
    remaining = list(eligible)
    remaining_weights = list(weights)
    
    for _ in range(n):
        if not remaining:
            break
        chosen_idx = rng.choices(range(len(remaining)), weights=remaining_weights, k=1)[0]
        agent, wilson = remaining[chosen_idx]
        selected.append((agent, wilson))
        remaining.pop(chosen_idx)
        remaining_weights.pop(chosen_idx)
    
    # Check operator diversity
    ops = {}
    for a, _ in selected:
        ops[a.operator_id] = ops.get(a.operator_id, 0) + 1
    diversity = simpson_diversity(ops)
    
    # Check max same operator
    max_same = max(ops.values()) / len(selected) if selected else 0
    
    violations = []
    if diversity < MIN_OPERATOR_DIVERSITY:
        violations.append(f"DIVERSITY_LOW: {diversity:.3f} < {MIN_OPERATOR_DIVERSITY}")
    if max_same > MAX_SAME_OPERATOR:
        violations.append(f"OPERATOR_CONCENTRATION: {max_same:.2f} > {MAX_SAME_OPERATOR}")
    
    return {
        "model": "REPUTATION",
        "status": "SELECTED" if not violations else "VIOLATIONS",
        "selected": [(a.agent_id, round(w, 3)) for a, w in selected],
        "operator_diversity": round(diversity, 3),
        "max_same_operator_ratio": round(max_same, 3),
        "violations": violations,
        "quorum_needed": math.ceil(len(selected) * QUORUM_RATIO)
    }


def select_hybrid(pool: list[Agent], nominees: list[str], 
                   veto: list[str], n: int) -> dict:
    """Counterparty-nominated + mutual veto + reputation floor."""
    nominee_agents = [a for a in pool if a.agent_id in nominees]
    vetoed = set(veto)
    
    eligible = []
    for a in nominee_agents:
        if a.agent_id in vetoed:
            continue
        if a.is_requestor or a.is_counterparty:
            continue
        wilson = wilson_lower(a.cosign_confirmed, a.cosign_total)
        if wilson >= MIN_WILSON_SCORE:
            eligible.append((a, wilson))
    
    # Fill remaining from reputation pool
    if len(eligible) < n:
        rep_result = select_reputation(
            [a for a in pool if a.agent_id not in nominees and a.agent_id not in vetoed],
            n - len(eligible)
        )
        if rep_result["status"] == "SELECTED":
            for aid, w in rep_result["selected"]:
                agent = next((a for a in pool if a.agent_id == aid), None)
                if agent:
                    eligible.append((agent, w))
    
    ops = {}
    for a, _ in eligible[:n]:
        ops[a.operator_id] = ops.get(a.operator_id, 0) + 1
    
    return {
        "model": "HYBRID",
        "status": "SELECTED" if len(eligible) >= n else "INSUFFICIENT",
        "nominated": len(nominee_agents),
        "vetoed": len(vetoed),
        "selected": [(a.agent_id, round(w, 3)) for a, w in eligible[:n]],
        "operator_diversity": round(simpson_diversity(ops), 3),
        "risk": "COLLUSION — nominees may coordinate with counterparty"
    }


# === Scenarios ===

def scenario_emergency_healthy():
    """Healthy pool, REPUTATION selection."""
    print("=== Scenario: EMERGENCY — Healthy Pool ===")
    pool = [
        Agent(f"agent_{i}", f"op_{i % 5}", 80 + i*5, 75 + i*4)
        for i in range(20)
    ]
    pool[0].is_requestor = True
    
    result = select_reputation(pool, MIN_EMERGENCY_WITNESSES, seed="emergency_001")
    print(f"  Status: {result['status']}")
    print(f"  Selected: {len(result.get('selected', []))} witnesses")
    print(f"  Operator diversity: {result.get('operator_diversity', 'N/A')}")
    print(f"  Quorum needed: {result.get('quorum_needed', 'N/A')}")
    if result.get('violations'):
        print(f"  ⚠️ Violations: {result['violations']}")
    print()


def scenario_sybil_attack():
    """Pool dominated by single operator — diversity check catches it."""
    print("=== Scenario: Sybil Attack — Operator Monoculture ===")
    pool = [
        Agent(f"sybil_{i}", "evil_operator", 100, 95)  # All same operator
        for i in range(15)
    ]
    pool += [
        Agent(f"honest_{i}", f"good_op_{i}", 80, 72)
        for i in range(5)
    ]
    
    result = select_reputation(pool, MIN_EMERGENCY_WITNESSES, seed="sybil_test")
    print(f"  Status: {result['status']}")
    print(f"  Operator diversity: {result.get('operator_diversity', 'N/A')}")
    print(f"  Max same operator: {result.get('max_same_operator_ratio', 'N/A')}")
    if result.get('violations'):
        print(f"  ⚠️ Violations: {result['violations']}")
    else:
        print(f"  Selected: {result.get('selected', [])}")
    print()


def scenario_cold_start():
    """Mostly new agents — Wilson CI filters them out."""
    print("=== Scenario: Cold Start — Low-Reputation Pool ===")
    pool = [
        Agent(f"new_{i}", f"op_{i}", 5, 5)  # n=5, all perfect
        for i in range(20)
    ]
    # Wilson CI at n=5 all perfect = 0.57 < 0.80 threshold
    
    result = select_reputation(pool, MIN_EMERGENCY_WITNESSES)
    print(f"  Status: {result['status']}")
    print(f"  Available: {result.get('available', 'N/A')} (need {MIN_EMERGENCY_WITNESSES})")
    
    # Show why
    w = wilson_lower(5, 5)
    print(f"  Wilson CI at n=5, 5/5: {w:.3f} (threshold: {MIN_WILSON_SCORE})")
    print(f"  Natural anti-sybil: 5 perfect receipts = {w:.3f} ceiling")
    print()


def scenario_designated_capture():
    """Fixed stewards — capture risk demonstration."""
    print("=== Scenario: DESIGNATED — Capture Risk ===")
    stewards = [
        Agent(f"steward_{i}", f"registry_{i}", 200, 190)
        for i in range(5)
    ]
    # All from different registries — looks safe
    result = select_designated(stewards, 3)
    print(f"  Status: {result['status']}")
    print(f"  Risk: {result['risk']}")
    
    # Now same operator
    stewards_captured = [
        Agent(f"steward_{i}", "captured_registry", 200, 190)
        for i in range(5)
    ]
    result2 = select_designated(stewards_captured, 3)
    print(f"  Captured diversity: {result2.get('operator_diversity', 'N/A')}")
    print(f"  Captured risk: {result2['risk']}")
    print()


def scenario_hybrid_veto():
    """HYBRID with veto — counterparty blocks colluding nominees."""
    print("=== Scenario: HYBRID — Veto Power ===")
    pool = [
        Agent(f"nominee_{i}", f"op_{i % 3}", 80, 72)
        for i in range(10)
    ]
    pool += [
        Agent(f"backup_{i}", f"op_{i + 5}", 60, 54)
        for i in range(10)
    ]
    
    nominees = [f"nominee_{i}" for i in range(5)]
    veto = ["nominee_0", "nominee_1"]  # Counterparty vetoes 2
    
    result = select_hybrid(pool, nominees, veto, MIN_EMERGENCY_WITNESSES)
    print(f"  Status: {result['status']}")
    print(f"  Nominated: {result['nominated']}, Vetoed: {result['vetoed']}")
    print(f"  Selected: {len(result['selected'])} witnesses")
    print(f"  Operator diversity: {result['operator_diversity']}")
    print()


if __name__ == "__main__":
    print("Witness Selection Engine — ATF EMERGENCY Ceremony")
    print("Per santaclawd: witness selection is the new attack surface")
    print("=" * 60)
    print()
    scenario_emergency_healthy()
    scenario_sybil_attack()
    scenario_cold_start()
    scenario_designated_capture()
    scenario_hybrid_veto()
    
    print("=" * 60)
    print("KEY INSIGHT: REPUTATION model (random + Wilson CI + diversity)")
    print("is the only sybil-resistant option for EMERGENCY ceremonies.")
    print("DESIGNATED = capture risk. HYBRID = collusion risk.")
    print(f"Wilson CI ≥ {MIN_WILSON_SCORE} naturally filters cold-start sybils.")
    print(f"Simpson diversity ≥ {MIN_OPERATOR_DIVERSITY} prevents operator monoculture.")
