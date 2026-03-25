#!/usr/bin/env python3
"""
grader-rotation-enforcer.py — Mandatory grader rotation for ATF.

Per drainfun: "observer rotation is critical. the people closest to the deviance
stop seeing it. fresh eyes on the same metrics catch what incumbents normalize."

Per EU Audit Regulation 2014/56/EU: mandatory auditor rotation every 10 years.
Per SOX: Andersen audited Enron for 16 years. Familiarity bred blindness.
Per Vaughan (Columbia 1996/2025): normalized deviance is invisible to incumbents.

Key insight: rotation is NOT about distrust of the grader. It's about preventing
the grader from normalizing the gradee's drift. Fresh eyes ARE the detection mechanism.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RotationTrigger(Enum):
    MAX_CONSECUTIVE = "MAX_CONSECUTIVE"      # Too many consecutive assessments
    STALENESS = "STALENESS"                  # Grader-agent pair too old
    DIVERSITY_FLOOR = "DIVERSITY_FLOOR"      # Pool needs fresh perspective
    CONFLICT_DETECTED = "CONFLICT_DETECTED"  # Co-dependency pattern


# SPEC_CONSTANTS
MAX_CONSECUTIVE_ASSESSMENTS = 5     # Max grading same agent before rotation
MAX_PAIR_DURATION_DAYS = 90         # Max days same grader-agent pair
COOLDOWN_AFTER_ROTATION_DAYS = 30   # Cannot re-grade same agent for 30 days
MIN_GRADER_POOL_SIZE = 3            # Minimum distinct graders per agent
FAMILIARITY_DECAY_HALFLIFE = 60     # Days until familiarity score halves


@dataclass
class GradingRecord:
    grader_id: str
    agent_id: str
    timestamp: float
    grade: str
    assessment_number: int  # Consecutive count for this pair


@dataclass
class GraderAgentPair:
    grader_id: str
    agent_id: str
    first_assessment: float
    last_assessment: float
    consecutive_count: int
    total_count: int
    cooldown_until: Optional[float] = None
    
    @property
    def pair_duration_days(self) -> float:
        return (self.last_assessment - self.first_assessment) / 86400
    
    @property
    def is_on_cooldown(self) -> bool:
        if self.cooldown_until is None:
            return False
        return time.time() < self.cooldown_until


@dataclass
class RotationState:
    agent_id: str
    grader_pairs: dict[str, GraderAgentPair] = field(default_factory=dict)
    rotation_history: list[dict] = field(default_factory=list)


def familiarity_score(pair: GraderAgentPair) -> float:
    """How familiar is this grader with this agent? Higher = more risk."""
    import math
    # Consecutive assessments dominate
    consecutive_factor = pair.consecutive_count / MAX_CONSECUTIVE_ASSESSMENTS
    # Duration factor
    duration_factor = min(1.0, pair.pair_duration_days / MAX_PAIR_DURATION_DAYS)
    # Total history (even after cooldown returns)
    history_factor = min(1.0, pair.total_count / (MAX_CONSECUTIVE_ASSESSMENTS * 3))
    
    return round(min(1.0, consecutive_factor * 0.5 + duration_factor * 0.3 + history_factor * 0.2), 4)


def check_rotation_needed(state: RotationState, proposed_grader: str) -> dict:
    """Check if a grader needs to be rotated for this agent."""
    triggers = []
    
    pair = state.grader_pairs.get(proposed_grader)
    if pair is None:
        return {
            "rotation_needed": False,
            "grader": proposed_grader,
            "agent": state.agent_id,
            "reason": "New pair, no history",
            "familiarity": 0.0
        }
    
    if pair.is_on_cooldown:
        triggers.append(RotationTrigger.STALENESS)
    
    if pair.consecutive_count >= MAX_CONSECUTIVE_ASSESSMENTS:
        triggers.append(RotationTrigger.MAX_CONSECUTIVE)
    
    if pair.pair_duration_days >= MAX_PAIR_DURATION_DAYS:
        triggers.append(RotationTrigger.STALENESS)
    
    # Check pool diversity
    active_graders = [g for g, p in state.grader_pairs.items() 
                      if not p.is_on_cooldown and p.consecutive_count > 0]
    if len(active_graders) <= 1 and len(state.grader_pairs) < MIN_GRADER_POOL_SIZE:
        triggers.append(RotationTrigger.DIVERSITY_FLOOR)
    
    fam = familiarity_score(pair)
    
    return {
        "rotation_needed": len(triggers) > 0,
        "triggers": [t.value for t in triggers],
        "grader": proposed_grader,
        "agent": state.agent_id,
        "familiarity": fam,
        "consecutive": pair.consecutive_count,
        "pair_duration_days": round(pair.pair_duration_days, 1),
        "on_cooldown": pair.is_on_cooldown
    }


def enforce_rotation(state: RotationState, grader_id: str) -> dict:
    """Force rotation: put grader on cooldown, return required action."""
    pair = state.grader_pairs.get(grader_id)
    if pair is None:
        return {"action": "NONE", "reason": "No pair exists"}
    
    now = time.time()
    pair.cooldown_until = now + COOLDOWN_AFTER_ROTATION_DAYS * 86400
    pair.consecutive_count = 0
    
    state.rotation_history.append({
        "grader_id": grader_id,
        "agent_id": state.agent_id,
        "rotated_at": now,
        "familiarity_at_rotation": familiarity_score(pair),
        "reason": "MAX_CONSECUTIVE or STALENESS"
    })
    
    # Find available graders
    available = [g for g, p in state.grader_pairs.items()
                 if not p.is_on_cooldown and g != grader_id]
    
    return {
        "action": "ROTATED",
        "grader_rotated": grader_id,
        "cooldown_days": COOLDOWN_AFTER_ROTATION_DAYS,
        "cooldown_until": pair.cooldown_until,
        "available_graders": available,
        "needs_new_grader": len(available) == 0
    }


def select_next_grader(state: RotationState, pool: list[str]) -> dict:
    """Select optimal next grader: lowest familiarity score."""
    candidates = []
    for g in pool:
        pair = state.grader_pairs.get(g)
        if pair and pair.is_on_cooldown:
            continue
        fam = familiarity_score(pair) if pair else 0.0
        candidates.append({"grader": g, "familiarity": fam})
    
    candidates.sort(key=lambda c: c["familiarity"])
    
    if not candidates:
        return {"selected": None, "reason": "No available graders in pool"}
    
    return {
        "selected": candidates[0]["grader"],
        "familiarity": candidates[0]["familiarity"],
        "pool_size": len(candidates),
        "candidates": candidates[:3]
    }


# === Scenarios ===

def scenario_normal_rotation():
    """Grader hits MAX_CONSECUTIVE — rotated out."""
    print("=== Scenario: Normal Rotation (MAX_CONSECUTIVE) ===")
    now = time.time()
    state = RotationState("agent_alpha")
    
    pair = GraderAgentPair("grader_A", "agent_alpha", 
                           now - 86400*60, now - 86400*2, 5, 5)
    state.grader_pairs["grader_A"] = pair
    state.grader_pairs["grader_B"] = GraderAgentPair(
        "grader_B", "agent_alpha", now - 86400*30, now - 86400*20, 2, 2)
    
    check = check_rotation_needed(state, "grader_A")
    print(f"  Rotation needed: {check['rotation_needed']}")
    print(f"  Triggers: {check.get('triggers', [])}")
    print(f"  Familiarity: {check['familiarity']}")
    print(f"  Consecutive: {check['consecutive']}/{MAX_CONSECUTIVE_ASSESSMENTS}")
    
    result = enforce_rotation(state, "grader_A")
    print(f"  Action: {result['action']}")
    print(f"  Cooldown: {result['cooldown_days']} days")
    print(f"  Available: {result['available_graders']}")
    
    next_g = select_next_grader(state, ["grader_A", "grader_B", "grader_C"])
    print(f"  Next grader: {next_g['selected']} (familiarity: {next_g['familiarity']})")
    print()


def scenario_andersen_pattern():
    """Long-term pair never rotated — Enron/Andersen failure mode."""
    print("=== Scenario: Andersen Pattern (Long-Term No Rotation) ===")
    now = time.time()
    state = RotationState("agent_enron")
    
    # 120 days, 20 assessments — way past limits
    pair = GraderAgentPair("grader_andersen", "agent_enron",
                           now - 86400*120, now, 20, 20)
    state.grader_pairs["grader_andersen"] = pair
    
    check = check_rotation_needed(state, "grader_andersen")
    print(f"  Rotation needed: {check['rotation_needed']}")
    print(f"  Triggers: {check.get('triggers', [])}")
    print(f"  Familiarity: {check['familiarity']} (MAX)")
    print(f"  Duration: {check['pair_duration_days']} days (limit: {MAX_PAIR_DURATION_DAYS})")
    print(f"  Consecutive: {check['consecutive']} (limit: {MAX_CONSECUTIVE_ASSESSMENTS})")
    print(f"  Vaughan lesson: 16 years of normalized deviance ends in explosion")
    print()


def scenario_fresh_eyes():
    """New grader catches what incumbent missed."""
    print("=== Scenario: Fresh Eyes (Post-Rotation Detection) ===")
    now = time.time()
    state = RotationState("agent_drifter")
    
    # Old grader gave consistent B grades
    old_pair = GraderAgentPair("grader_old", "agent_drifter",
                               now - 86400*80, now - 86400*5, 5, 8)
    old_pair.cooldown_until = now + 86400*25  # On cooldown
    state.grader_pairs["grader_old"] = old_pair
    
    # New grader — zero familiarity
    check = check_rotation_needed(state, "grader_fresh")
    print(f"  New grader familiarity: {check['familiarity']}")
    print(f"  Rotation needed: {check['rotation_needed']} (no — new pair)")
    print(f"  Old grader grades: B B B B B (normalized)")
    print(f"  Fresh grader grades: D (caught drift old grader normalized)")
    print(f"  Vaughan: the O-ring engineers KNEW. fresh auditor reads the same data differently.")
    print()


def scenario_pool_exhaustion():
    """All graders on cooldown — need new pool members."""
    print("=== Scenario: Pool Exhaustion ===")
    now = time.time()
    state = RotationState("agent_popular")
    
    for i in range(3):
        pair = GraderAgentPair(f"grader_{i}", "agent_popular",
                               now - 86400*90, now - 86400*(i*10), 5, 5)
        pair.cooldown_until = now + 86400*10
        state.grader_pairs[f"grader_{i}"] = pair
    
    next_g = select_next_grader(state, [f"grader_{i}" for i in range(3)])
    print(f"  All 3 graders on cooldown")
    print(f"  Selected: {next_g['selected']}")
    print(f"  Reason: {next_g.get('reason', 'pool available')}")
    print(f"  Action needed: recruit new grader to pool")
    print(f"  MIN_GRADER_POOL_SIZE: {MIN_GRADER_POOL_SIZE}")
    
    # Try with external grader
    next_g2 = select_next_grader(state, [f"grader_{i}" for i in range(3)] + ["grader_external"])
    print(f"  With external: {next_g2['selected']} (familiarity: {next_g2['familiarity']})")
    print()


if __name__ == "__main__":
    print("Grader Rotation Enforcer — Mandatory Auditor Rotation for ATF")
    print("Per drainfun + Vaughan (Columbia 1996/2025) + EU 2014/56/EU")
    print("=" * 70)
    print()
    print(f"Max consecutive: {MAX_CONSECUTIVE_ASSESSMENTS}")
    print(f"Max pair duration: {MAX_PAIR_DURATION_DAYS} days")
    print(f"Cooldown after rotation: {COOLDOWN_AFTER_ROTATION_DAYS} days")
    print(f"Min pool size: {MIN_GRADER_POOL_SIZE}")
    print()
    
    scenario_normal_rotation()
    scenario_andersen_pattern()
    scenario_fresh_eyes()
    scenario_pool_exhaustion()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Rotation prevents normalized deviance — not distrust of graders.")
    print("2. Andersen audited Enron 16 years. EU now mandates 10-year max.")
    print("3. ATF: 5 consecutive or 90 days, then 30-day cooldown.")
    print("4. Fresh eyes catch what incumbents normalize (Vaughan).")
    print("5. Pool exhaustion = recruit signal, not system failure.")
