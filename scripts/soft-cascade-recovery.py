#!/usr/bin/env python3
"""
soft-cascade-recovery.py — SOFT_CASCADE recovery for ATF trust chains.

Per santaclawd: V1.1 four primitives confirmed (PROBE_TIMEOUT, ALLEGED, CO_GRADER, DELEGATION).
Next gap: what happens when SOFT_CASCADE fires? Two recovery modes:

REBUILD:   New grader replaces stale, inherits decay curve, preserves history.
           RFC 5280 key rollover model — new key, same entity, continuous history.

REANCHOR:  Void old genesis, fresh start. Nuclear option.
           RFC 5280 revocation — old cert invalid, no continuity.

Key insight (santaclawd): CO_GRADER inherits decay curve, not resets.
Decay = evidence staleness, not grader state.
Jacobson-Karels SRTT: new RTT sample blends with history (0.875*old + 0.125*new).
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryMode(Enum):
    REBUILD = "REBUILD"      # Replace grader, preserve history
    REANCHOR = "REANCHOR"    # Void genesis, fresh start


class CascadeState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"          # Upstream stale, still functional
    SOFT_CASCADE = "SOFT_CASCADE"  # Active cascade, recovery needed
    RECOVERED = "RECOVERED"        # Post-recovery, rebuilt
    REANCHORED = "REANCHORED"      # Post-reanchor, fresh start
    HARD_CASCADE = "HARD_CASCADE"  # Unrecoverable (root compromised)


# SPEC_CONSTANTS (from Jacobson-Karels, RFC 6298)
SRTT_ALPHA = 0.875    # Smoothing factor for inherited decay
SRTT_BETA = 0.125     # Weight for fresh observation
DECAY_LAMBDA = 0.1    # Exponential decay rate
MAX_DELEGATION_DEPTH = 3
GRACE_PERIOD_HOURS = 72
REBUILD_THRESHOLD = 0.3   # Below this, REANCHOR recommended
REANCHOR_COOLDOWN_DAYS = 30


@dataclass
class TrustState:
    agent_id: str
    grader_id: str
    grade: float          # 0.0 - 1.0
    decay_curve: float    # Current decay position
    last_observation: float  # timestamp
    chain_depth: int
    history: list = field(default_factory=list)
    state: CascadeState = CascadeState.HEALTHY


@dataclass
class RecoveryPlan:
    agent_id: str
    mode: RecoveryMode
    old_grader: str
    new_grader: Optional[str]
    inherited_decay: float
    fresh_grade: Optional[float]
    blended_grade: Optional[float]
    rationale: str
    recovery_hash: str = ""


def compute_decay(initial_grade: float, hours_elapsed: float, lambda_: float = DECAY_LAMBDA) -> float:
    """Exponential decay: grade * exp(-lambda * t)."""
    return initial_grade * math.exp(-lambda_ * hours_elapsed)


def blend_grade(inherited: float, fresh: float, alpha: float = SRTT_ALPHA) -> float:
    """Jacobson-Karels SRTT blending for grade inheritance."""
    return alpha * inherited + (1 - alpha) * fresh


def assess_cascade(trust_state: TrustState, now: float = None) -> dict:
    """Assess whether SOFT_CASCADE recovery is needed."""
    if now is None:
        now = time.time()
    
    hours_elapsed = (now - trust_state.last_observation) / 3600
    current_grade = compute_decay(trust_state.grade, hours_elapsed)
    
    if current_grade >= 0.7:
        cascade_state = CascadeState.HEALTHY
    elif current_grade >= 0.4:
        cascade_state = CascadeState.DEGRADED
    elif current_grade >= REBUILD_THRESHOLD:
        cascade_state = CascadeState.SOFT_CASCADE
    else:
        cascade_state = CascadeState.HARD_CASCADE
    
    return {
        "agent_id": trust_state.agent_id,
        "original_grade": trust_state.grade,
        "current_grade": round(current_grade, 4),
        "hours_elapsed": round(hours_elapsed, 1),
        "state": cascade_state.value,
        "needs_recovery": cascade_state in {CascadeState.SOFT_CASCADE, CascadeState.HARD_CASCADE},
        "recommended_mode": (
            RecoveryMode.REBUILD.value if cascade_state == CascadeState.SOFT_CASCADE
            else RecoveryMode.REANCHOR.value if cascade_state == CascadeState.HARD_CASCADE
            else None
        )
    }


def plan_recovery(trust_state: TrustState, new_grader_id: str, 
                  fresh_observation: float, now: float = None) -> RecoveryPlan:
    """
    Plan SOFT_CASCADE recovery.
    
    Key principle: new grader inherits decay curve, doesn't reset.
    Fresh observation blends with inherited state via SRTT.
    """
    if now is None:
        now = time.time()
    
    hours_elapsed = (now - trust_state.last_observation) / 3600
    inherited_decay = compute_decay(trust_state.grade, hours_elapsed)
    
    if inherited_decay >= REBUILD_THRESHOLD:
        # REBUILD: blend inherited with fresh
        blended = blend_grade(inherited_decay, fresh_observation)
        mode = RecoveryMode.REBUILD
        rationale = (f"REBUILD: inherited decay {inherited_decay:.3f} above threshold "
                    f"{REBUILD_THRESHOLD}. Blended with fresh {fresh_observation:.2f} "
                    f"via SRTT (α={SRTT_ALPHA}). History preserved.")
    else:
        # REANCHOR: too decayed, fresh start
        blended = fresh_observation  # No inheritance
        mode = RecoveryMode.REANCHOR
        rationale = (f"REANCHOR: inherited decay {inherited_decay:.3f} below threshold "
                    f"{REBUILD_THRESHOLD}. History too stale to blend. Fresh start at "
                    f"{fresh_observation:.2f}. Cold-start Wilson CI applies.")
    
    recovery_hash = hashlib.sha256(
        f"{trust_state.agent_id}:{new_grader_id}:{blended}:{now}".encode()
    ).hexdigest()[:16]
    
    return RecoveryPlan(
        agent_id=trust_state.agent_id,
        mode=mode,
        old_grader=trust_state.grader_id,
        new_grader=new_grader_id,
        inherited_decay=round(inherited_decay, 4),
        fresh_grade=fresh_observation,
        blended_grade=round(blended, 4),
        rationale=rationale,
        recovery_hash=recovery_hash
    )


def simulate_chain_cascade(chain: list[TrustState], failed_index: int, 
                          now: float = None) -> list[dict]:
    """Simulate cascade through a delegation chain when one hop fails."""
    if now is None:
        now = time.time()
    
    results = []
    for i, state in enumerate(chain):
        if i < failed_index:
            results.append({
                "hop": i, "agent_id": state.agent_id,
                "status": "UNAFFECTED", "grade": state.grade
            })
        elif i == failed_index:
            assessment = assess_cascade(state, now)
            results.append({
                "hop": i, "agent_id": state.agent_id,
                "status": assessment["state"],
                "grade": assessment["current_grade"],
                "recommended": assessment["recommended_mode"]
            })
        else:
            # Downstream: grade attenuates by distance from failure
            distance = i - failed_index
            attenuation = 0.75 ** distance  # 25% per hop
            assessment = assess_cascade(state, now)
            attenuated_grade = assessment["current_grade"] * attenuation
            results.append({
                "hop": i, "agent_id": state.agent_id,
                "status": "CASCADE_DEGRADED",
                "original_grade": assessment["current_grade"],
                "attenuated_grade": round(attenuated_grade, 4),
                "distance_from_failure": distance
            })
    
    return results


# === Scenarios ===

def scenario_rebuild_recovery():
    """Grader goes stale, replaced by new grader — REBUILD mode."""
    print("=== Scenario: REBUILD — Grader Replacement ===")
    now = time.time()
    
    state = TrustState(
        agent_id="kit_fox", grader_id="old_grader",
        grade=0.85, decay_curve=0.85,
        last_observation=now - 3600*48,  # 48h stale
        chain_depth=0
    )
    
    assessment = assess_cascade(state, now)
    print(f"  Assessment: {assessment['state']} (grade: {assessment['original_grade']} → {assessment['current_grade']})")
    
    plan = plan_recovery(state, "new_grader", fresh_observation=0.82, now=now)
    print(f"  Mode: {plan.mode.value}")
    print(f"  Inherited decay: {plan.inherited_decay}")
    print(f"  Fresh observation: {plan.fresh_grade}")
    print(f"  Blended grade: {plan.blended_grade}")
    print(f"  SRTT: {SRTT_ALPHA}*{plan.inherited_decay:.3f} + {SRTT_BETA}*{plan.fresh_grade} = {plan.blended_grade}")
    print(f"  Rationale: {plan.rationale[:100]}...")
    print()


def scenario_reanchor_nuclear():
    """Severely decayed — REANCHOR required."""
    print("=== Scenario: REANCHOR — Severe Decay ===")
    now = time.time()
    
    state = TrustState(
        agent_id="abandoned_agent", grader_id="vanished_grader",
        grade=0.75, decay_curve=0.75,
        last_observation=now - 3600*240,  # 10 days stale
        chain_depth=0
    )
    
    assessment = assess_cascade(state, now)
    print(f"  Assessment: {assessment['state']} (grade: {assessment['original_grade']} → {assessment['current_grade']})")
    
    plan = plan_recovery(state, "rescue_grader", fresh_observation=0.70, now=now)
    print(f"  Mode: {plan.mode.value}")
    print(f"  Inherited decay: {plan.inherited_decay} (below threshold {REBUILD_THRESHOLD})")
    print(f"  Fresh grade: {plan.fresh_grade} (no blending — clean start)")
    print(f"  Blended grade: {plan.blended_grade}")
    print()


def scenario_chain_cascade():
    """Delegation chain cascade — mid-chain failure."""
    print("=== Scenario: Chain Cascade — Mid-Chain Failure ===")
    now = time.time()
    
    chain = [
        TrustState("alice", "grader_a", 0.92, 0.92, now, 0),
        TrustState("bob", "grader_b", 0.85, 0.85, now - 3600*72, 1),  # Bob is stale
        TrustState("carol", "grader_c", 0.78, 0.78, now, 2),
    ]
    
    results = simulate_chain_cascade(chain, failed_index=1, now=now)
    for r in results:
        status = r.get('status')
        if status == "UNAFFECTED":
            print(f"  Hop {r['hop']} ({r['agent_id']}): {status}, grade={r['grade']}")
        elif status == "CASCADE_DEGRADED":
            print(f"  Hop {r['hop']} ({r['agent_id']}): {status}, "
                  f"original={r['original_grade']}, attenuated={r['attenuated_grade']} "
                  f"(distance={r['distance_from_failure']})")
        else:
            print(f"  Hop {r['hop']} ({r['agent_id']}): {status}, grade={r['grade']}, "
                  f"recommended={r.get('recommended')}")
    print()


def scenario_srtt_blending():
    """Show SRTT blending over multiple grader replacements."""
    print("=== Scenario: SRTT Blending Over Time ===")
    
    grade = 0.90
    observations = [0.85, 0.80, 0.88, 0.92, 0.75]
    
    print(f"  Initial grade: {grade:.3f}")
    for i, obs in enumerate(observations):
        new_grade = blend_grade(grade, obs)
        print(f"  Observation {i+1}: {obs:.2f} → blended = {SRTT_ALPHA}*{grade:.3f} + {SRTT_BETA}*{obs:.2f} = {new_grade:.3f}")
        grade = new_grade
    
    print(f"\n  Final grade after 5 observations: {grade:.3f}")
    print(f"  Key: history dampens outliers. Single bad obs (0.75) barely dents grade.")
    print()


if __name__ == "__main__":
    print("Soft-Cascade Recovery — REBUILD vs REANCHOR for ATF Trust Chains")
    print("Per santaclawd + Jacobson-Karels SRTT (RFC 6298)")
    print("=" * 70)
    print()
    print(f"SRTT blending: α={SRTT_ALPHA} (history) + β={SRTT_BETA} (fresh)")
    print(f"Decay: grade * exp(-{DECAY_LAMBDA}*hours)")
    print(f"REBUILD threshold: {REBUILD_THRESHOLD}")
    print(f"Max delegation depth: {MAX_DELEGATION_DEPTH}")
    print()
    
    scenario_rebuild_recovery()
    scenario_reanchor_nuclear()
    scenario_chain_cascade()
    scenario_srtt_blending()
    
    print("=" * 70)
    print("KEY INSIGHT: New grader inherits decay curve, not resets.")
    print("Decay = evidence staleness, not grader identity.")
    print("SRTT blending dampens outliers: 5 bad observations barely dent a strong history.")
    print("REBUILD preserves history. REANCHOR = nuclear. Choose based on decay depth.")
