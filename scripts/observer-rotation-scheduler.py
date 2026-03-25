#!/usr/bin/env python3
"""
observer-rotation-scheduler.py — Auditor/observer rotation for ATF verification.

Per drainfun: "the people closest to the deviance stop seeing it. fresh eyes catch
what incumbents normalize."
Per Sarbanes-Oxley 2002 Section 203: audit partner rotation every 5 years.
Per Vaughan (1996/2025): O-ring engineers saw erosion on every flight. Each within spec.

Key insight: rotate the OBSERVER, not just the metric. An observer who has watched
the same agent for too long becomes part of the system they are monitoring.
Proximity breeds blindness. Fresh eyes are a security mechanism.

Architecture:
  - Each agent has a VERIFIER_POOL (set of observers qualified to verify)
  - Observers rotate on a schedule (MAX_TENURE per observer-agent pair)
  - Handoff includes "fresh eyes report" — new observer reviews last N receipts
  - Cooling period before an observer can return to same agent
"""

import hashlib
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ObserverStatus(Enum):
    ACTIVE = "ACTIVE"          # Currently assigned
    COOLING = "COOLING"        # In cooling period, cannot reassign
    AVAILABLE = "AVAILABLE"    # Ready for assignment
    SUSPENDED = "SUSPENDED"    # Removed from pool


# SPEC_CONSTANTS
MAX_TENURE_DAYS = 90          # Max time one observer watches one agent
COOLING_PERIOD_DAYS = 180     # Must wait before re-assignment to same agent
MIN_POOL_SIZE = 3             # Minimum observers in rotation pool
FRESH_EYES_REVIEW_N = 20     # New observer reviews last N receipts
HANDOFF_OVERLAP_DAYS = 7     # Old and new observer overlap for knowledge transfer
TENURE_WARNING_DAYS = 14     # Warning before forced rotation
SOX_PARALLEL_YEARS = 5       # SOX mandates 5-year partner rotation


@dataclass
class Observer:
    observer_id: str
    operator: str
    specializations: list[str] = field(default_factory=list)
    total_assignments: int = 0
    current_assignment: Optional[str] = None
    status: ObserverStatus = ObserverStatus.AVAILABLE


@dataclass
class Assignment:
    agent_id: str
    observer_id: str
    started_at: float
    expires_at: float
    handoff_from: Optional[str] = None  # Previous observer
    fresh_eyes_completed: bool = False
    receipts_reviewed: int = 0
    anomalies_found: int = 0


@dataclass
class CoolingRecord:
    observer_id: str
    agent_id: str
    cooling_until: float
    reason: str = "tenure_complete"


@dataclass
class RotationPool:
    agent_id: str
    observers: list[Observer] = field(default_factory=list)
    active_assignment: Optional[Assignment] = None
    history: list[Assignment] = field(default_factory=list)
    cooling_records: list[CoolingRecord] = field(default_factory=list)


def create_pool(agent_id: str, observers: list[Observer]) -> RotationPool:
    """Create a rotation pool for an agent."""
    return RotationPool(agent_id=agent_id, observers=observers)


def get_available_observers(pool: RotationPool) -> list[Observer]:
    """Get observers not currently assigned to this agent and not cooling."""
    now = time.time()
    cooling_ids = {c.observer_id for c in pool.cooling_records if c.cooling_until > now}
    active_id = pool.active_assignment.observer_id if pool.active_assignment else None
    
    return [o for o in pool.observers 
            if o.observer_id != active_id 
            and o.observer_id not in cooling_ids
            and o.status != ObserverStatus.SUSPENDED]


def check_tenure(pool: RotationPool) -> dict:
    """Check if current observer's tenure needs rotation."""
    if not pool.active_assignment:
        return {"needs_rotation": True, "reason": "no_active_observer"}
    
    now = time.time()
    assignment = pool.active_assignment
    remaining_days = (assignment.expires_at - now) / 86400
    tenure_days = (now - assignment.started_at) / 86400
    
    if now >= assignment.expires_at:
        return {
            "needs_rotation": True,
            "reason": "tenure_expired",
            "tenure_days": round(tenure_days, 1),
            "urgency": "IMMEDIATE"
        }
    elif remaining_days <= TENURE_WARNING_DAYS:
        return {
            "needs_rotation": False,
            "warning": True,
            "reason": "approaching_expiry",
            "remaining_days": round(remaining_days, 1),
            "tenure_days": round(tenure_days, 1),
            "urgency": "WARNING"
        }
    else:
        return {
            "needs_rotation": False,
            "warning": False,
            "tenure_days": round(tenure_days, 1),
            "remaining_days": round(remaining_days, 1)
        }


def rotate_observer(pool: RotationPool) -> dict:
    """Execute observer rotation."""
    now = time.time()
    available = get_available_observers(pool)
    
    if len(available) < 1:
        return {
            "success": False,
            "reason": "no_available_observers",
            "pool_size": len(pool.observers),
            "cooling": len([c for c in pool.cooling_records if c.cooling_until > now]),
            "fix": f"Pool needs {MIN_POOL_SIZE} observers, expand pool or wait for cooling to expire"
        }
    
    # Select observer with fewest total assignments (load balance)
    new_observer = min(available, key=lambda o: o.total_assignments)
    
    old_assignment = pool.active_assignment
    old_observer_id = old_assignment.observer_id if old_assignment else None
    
    # Create new assignment
    new_assignment = Assignment(
        agent_id=pool.agent_id,
        observer_id=new_observer.observer_id,
        started_at=now,
        expires_at=now + MAX_TENURE_DAYS * 86400,
        handoff_from=old_observer_id
    )
    
    # Move old observer to cooling
    if old_assignment:
        pool.history.append(old_assignment)
        pool.cooling_records.append(CoolingRecord(
            observer_id=old_observer_id,
            agent_id=pool.agent_id,
            cooling_until=now + COOLING_PERIOD_DAYS * 86400
        ))
        # Update old observer status
        for o in pool.observers:
            if o.observer_id == old_observer_id:
                o.status = ObserverStatus.COOLING
                o.current_assignment = None
    
    # Activate new observer
    new_observer.status = ObserverStatus.ACTIVE
    new_observer.current_assignment = pool.agent_id
    new_observer.total_assignments += 1
    pool.active_assignment = new_assignment
    
    return {
        "success": True,
        "new_observer": new_observer.observer_id,
        "previous_observer": old_observer_id,
        "tenure_days": MAX_TENURE_DAYS,
        "handoff_overlap_days": HANDOFF_OVERLAP_DAYS,
        "fresh_eyes_review": FRESH_EYES_REVIEW_N,
        "cooling_period_days": COOLING_PERIOD_DAYS
    }


def fresh_eyes_report(pool: RotationPool, last_n_receipts: list[dict]) -> dict:
    """New observer reviews recent receipts with fresh perspective."""
    if not pool.active_assignment:
        return {"error": "no_active_assignment"}
    
    anomalies = []
    # Simulate fresh-eyes analysis
    for i, receipt in enumerate(last_n_receipts[:FRESH_EYES_REVIEW_N]):
        grade = receipt.get("grade", "C")
        # Fresh eyes more likely to catch grade inflation
        if grade in ("A", "B") and receipt.get("evidence_strength", 0.5) < 0.4:
            anomalies.append({
                "receipt_index": i,
                "issue": "grade_inflation",
                "detail": f"Grade {grade} with evidence strength {receipt.get('evidence_strength', 0.5)}"
            })
        # Catch diversity gaps
        if receipt.get("counterparty_repeat", False):
            anomalies.append({
                "receipt_index": i,
                "issue": "diversity_concern",
                "detail": "Repeated counterparty in recent receipts"
            })
    
    pool.active_assignment.fresh_eyes_completed = True
    pool.active_assignment.receipts_reviewed = len(last_n_receipts[:FRESH_EYES_REVIEW_N])
    pool.active_assignment.anomalies_found = len(anomalies)
    
    return {
        "observer": pool.active_assignment.observer_id,
        "receipts_reviewed": pool.active_assignment.receipts_reviewed,
        "anomalies_found": len(anomalies),
        "anomalies": anomalies,
        "vaughan_note": "Fresh eyes catch what incumbents normalize"
    }


def pool_health(pool: RotationPool) -> dict:
    """Check overall pool health."""
    now = time.time()
    available = get_available_observers(pool)
    cooling = [c for c in pool.cooling_records if c.cooling_until > now]
    
    rotation_count = len(pool.history)
    avg_anomalies = (sum(a.anomalies_found for a in pool.history) / rotation_count 
                     if rotation_count > 0 else 0)
    
    return {
        "agent_id": pool.agent_id,
        "pool_size": len(pool.observers),
        "available": len(available),
        "cooling": len(cooling),
        "active": pool.active_assignment.observer_id if pool.active_assignment else None,
        "total_rotations": rotation_count,
        "avg_anomalies_per_rotation": round(avg_anomalies, 2),
        "healthy": len(available) >= MIN_POOL_SIZE - 1,  # -1 because one is active
        "sox_comparison": f"SOX: {SOX_PARALLEL_YEARS}yr rotation. ATF: {MAX_TENURE_DAYS}d rotation ({SOX_PARALLEL_YEARS * 365 / MAX_TENURE_DAYS:.0f}x faster)"
    }


# === Scenarios ===

def scenario_normal_rotation():
    """Standard tenure expiry and handoff."""
    print("=== Scenario: Normal Observer Rotation ===")
    observers = [
        Observer(f"obs_{i}", f"op_{i}", ["trust_verification"])
        for i in range(5)
    ]
    pool = create_pool("agent_alpha", observers)
    
    # Initial assignment
    result = rotate_observer(pool)
    print(f"  Initial: {result['new_observer']} assigned for {result['tenure_days']}d")
    
    # Simulate tenure expiry
    pool.active_assignment.expires_at = time.time() - 1
    tenure_check = check_tenure(pool)
    print(f"  Tenure check: {tenure_check['urgency']} — {tenure_check['reason']}")
    
    # Rotate
    result2 = rotate_observer(pool)
    print(f"  Rotated: {result2['previous_observer']} → {result2['new_observer']}")
    print(f"  Handoff overlap: {result2['handoff_overlap_days']}d")
    print(f"  Fresh eyes review: last {result2['fresh_eyes_review']} receipts")
    
    health = pool_health(pool)
    print(f"  Pool: {health['pool_size']} total, {health['available']} available, {health['cooling']} cooling")
    print(f"  {health['sox_comparison']}")
    print()


def scenario_fresh_eyes_catches_drift():
    """New observer catches grade inflation previous observer missed."""
    print("=== Scenario: Fresh Eyes Catches Normalized Deviance ===")
    observers = [Observer(f"obs_{i}", f"op_{i}") for i in range(4)]
    pool = create_pool("agent_beta", observers)
    rotate_observer(pool)
    
    # Simulate receipts with subtle grade inflation
    receipts = [
        {"grade": "A", "evidence_strength": 0.8},  # Legitimate A
        {"grade": "A", "evidence_strength": 0.6},  # Borderline
        {"grade": "B", "evidence_strength": 0.3, "counterparty_repeat": True},  # Inflated
        {"grade": "A", "evidence_strength": 0.35},  # Inflated
        {"grade": "B", "evidence_strength": 0.25, "counterparty_repeat": True},  # Inflated + repeat
    ]
    
    report = fresh_eyes_report(pool, receipts)
    print(f"  Observer: {report['observer']}")
    print(f"  Reviewed: {report['receipts_reviewed']} receipts")
    print(f"  Anomalies: {report['anomalies_found']}")
    for a in report['anomalies']:
        print(f"    [{a['issue']}] {a['detail']}")
    print(f"  \"{report['vaughan_note']}\"")
    print()


def scenario_pool_exhaustion():
    """All observers cooling — pool too small."""
    print("=== Scenario: Pool Exhaustion ===")
    observers = [Observer(f"obs_{i}", f"op_{i}") for i in range(2)]  # Too small!
    pool = create_pool("agent_gamma", observers)
    
    # Assign first
    r1 = rotate_observer(pool)
    print(f"  First: {r1['new_observer']}")
    
    # Rotate
    pool.active_assignment.expires_at = time.time() - 1
    r2 = rotate_observer(pool)
    print(f"  Second: {r2['new_observer']}")
    
    # Try rotate again — both cooling
    pool.active_assignment.expires_at = time.time() - 1
    r3 = rotate_observer(pool)
    print(f"  Third attempt: success={r3['success']}")
    print(f"  Reason: {r3.get('reason', '')}")
    print(f"  Fix: {r3.get('fix', '')}")
    
    health = pool_health(pool)
    print(f"  Pool healthy: {health['healthy']}")
    print()


def scenario_three_rotation_cycle():
    """Full 3-rotation cycle showing knowledge accumulation."""
    print("=== Scenario: Three-Rotation Cycle ===")
    observers = [Observer(f"obs_{i}", f"op_{i}") for i in range(5)]
    pool = create_pool("agent_delta", observers)
    
    for rotation in range(3):
        pool.active_assignment = None if rotation == 0 else pool.active_assignment
        if pool.active_assignment:
            pool.active_assignment.expires_at = time.time() - 1
        result = rotate_observer(pool)
        if result['success']:
            # Fresh eyes
            receipts = [{"grade": "B", "evidence_strength": 0.5 - rotation*0.1,
                         "counterparty_repeat": rotation > 0}
                        for _ in range(10)]
            report = fresh_eyes_report(pool, receipts)
            print(f"  Rotation {rotation+1}: {result['new_observer']} "
                  f"(from {result.get('previous_observer', 'none')}) "
                  f"→ {report['anomalies_found']} anomalies")
    
    health = pool_health(pool)
    print(f"  Total rotations: {health['total_rotations']}")
    print(f"  Avg anomalies/rotation: {health['avg_anomalies_per_rotation']}")
    print()


if __name__ == "__main__":
    print("Observer Rotation Scheduler — Auditor Rotation for ATF")
    print("Per drainfun + Sarbanes-Oxley 2002 Section 203 + Vaughan (1996/2025)")
    print("=" * 70)
    print()
    print(f"Max tenure: {MAX_TENURE_DAYS}d | Cooling: {COOLING_PERIOD_DAYS}d | "
          f"Pool min: {MIN_POOL_SIZE} | Fresh eyes: last {FRESH_EYES_REVIEW_N} receipts")
    print()
    
    scenario_normal_rotation()
    scenario_fresh_eyes_catches_drift()
    scenario_pool_exhaustion()
    scenario_three_rotation_cycle()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Proximity breeds blindness (Vaughan). Rotate the OBSERVER, not just the metric.")
    print("2. SOX mandates 5yr audit partner rotation. ATF: 90d (20x faster).")
    print("3. Fresh eyes report on handoff = mandatory review of last N receipts.")
    print("4. Cooling period prevents revolving door (observer returns too soon).")
    print("5. Pool exhaustion = design flaw, not runtime error. MIN_POOL_SIZE=3.")
