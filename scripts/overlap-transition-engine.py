#!/usr/bin/env python3
"""
overlap-transition-engine.py — Soft key transition for ATF registry operations.

Per funwolf: "hard cutover = guaranteed outages. soft transition lets the network adapt."
Per DNSSEC RFC 6781 Section 4.1.4: old key valid during overlap, removed after successor proven.
Per Verisign 2018: KSK rollover postponed 1 year because resolvers were not ready.

Key insight: overlap window is NOT a security weakness. It is the mechanism that
prevents catastrophic rollover failure. Double-signing during overlap means verifiers
accept either key, giving the network time to propagate the new key.

Three transition phases:
  PRE_PUBLISH  — New key published but not yet signing
  DOUBLE_SIGN  — Both keys sign simultaneously
  POST_REVOKE  — Old key removed after successor verified
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TransitionPhase(Enum):
    STABLE = "STABLE"              # Single active key, no transition
    PRE_PUBLISH = "PRE_PUBLISH"    # New key published, not yet signing
    DOUBLE_SIGN = "DOUBLE_SIGN"    # Both keys sign simultaneously
    POST_REVOKE = "POST_REVOKE"    # Old key being phased out
    COMPLETED = "COMPLETED"        # Transition finished


class KeyType(Enum):
    ROOT = "ROOT"           # Registry root key (annual ceremony)
    OPERATIONAL = "OPERATIONAL"  # Day-to-day signing key (quarterly)


class RolloverStrategy(Enum):
    PRE_PUBLISH = "PRE_PUBLISH"    # RFC 6781: publish first, sign later
    DOUBLE_SIGN = "DOUBLE_SIGN"    # RFC 6781: sign with both simultaneously
    EMERGENCY = "EMERGENCY"         # Immediate cutover (compromise scenario)


# SPEC_CONSTANTS (per registry-rekey-scheduler.py)
OVERLAP_RATIO = 0.10           # 10% of rotation period
PRE_PUBLISH_RATIO = 0.05       # 5% of rotation period (publish before signing)
ROOT_ROTATION_DAYS = 365
OPERATIONAL_ROTATION_DAYS = 90
MIN_VERIFIER_PROPAGATION = 0.80  # 80% of verifiers must see new key
PROPAGATION_CHECK_INTERVAL = 3600  # Check every hour
MAX_TRANSITION_EXTENSION = 2    # Can extend overlap 2x before forcing


@dataclass
class Key:
    key_id: str
    key_type: KeyType
    created_at: float
    expires_at: float
    fingerprint: str
    is_active: bool = True
    is_signing: bool = True
    revoked_at: Optional[float] = None


@dataclass
class VerifierState:
    verifier_id: str
    last_seen_key: str
    last_check: float
    accepts_new_key: bool = False


@dataclass
class TransitionPlan:
    plan_id: str
    old_key: Key
    new_key: Key
    strategy: RolloverStrategy
    phase: TransitionPhase = TransitionPhase.PRE_PUBLISH
    started_at: float = 0.0
    pre_publish_until: float = 0.0
    double_sign_until: float = 0.0
    completed_at: Optional[float] = None
    extensions: int = 0
    verifier_states: list[VerifierState] = field(default_factory=list)


def create_transition_plan(old_key: Key, strategy: RolloverStrategy = RolloverStrategy.PRE_PUBLISH) -> TransitionPlan:
    """Create a transition plan for key rollover."""
    now = time.time()
    
    rotation_days = (ROOT_ROTATION_DAYS if old_key.key_type == KeyType.ROOT 
                     else OPERATIONAL_ROTATION_DAYS)
    
    overlap_days = rotation_days * OVERLAP_RATIO
    pre_publish_days = rotation_days * PRE_PUBLISH_RATIO
    
    new_key = Key(
        key_id=f"key_{hashlib.sha256(f'{old_key.key_id}:{now}'.encode()).hexdigest()[:12]}",
        key_type=old_key.key_type,
        created_at=now,
        expires_at=now + rotation_days * 86400,
        fingerprint=hashlib.sha256(f"fp:{now}".encode()).hexdigest()[:16],
        is_active=False,
        is_signing=False
    )
    
    return TransitionPlan(
        plan_id=f"txn_{hashlib.sha256(f'{old_key.key_id}:{new_key.key_id}'.encode()).hexdigest()[:12]}",
        old_key=old_key,
        new_key=new_key,
        strategy=strategy,
        phase=TransitionPhase.PRE_PUBLISH,
        started_at=now,
        pre_publish_until=now + pre_publish_days * 86400,
        double_sign_until=now + (pre_publish_days + overlap_days) * 86400
    )


def check_propagation(plan: TransitionPlan) -> dict:
    """Check how many verifiers have seen the new key."""
    total = len(plan.verifier_states)
    if total == 0:
        return {"propagation": 0.0, "ready": False, "total": 0, "accepting": 0}
    
    accepting = sum(1 for v in plan.verifier_states if v.accepts_new_key)
    propagation = accepting / total
    
    return {
        "propagation": round(propagation, 4),
        "ready": propagation >= MIN_VERIFIER_PROPAGATION,
        "total": total,
        "accepting": accepting,
        "threshold": MIN_VERIFIER_PROPAGATION
    }


def advance_phase(plan: TransitionPlan) -> dict:
    """Attempt to advance transition to next phase."""
    now = time.time()
    propagation = check_propagation(plan)
    
    if plan.phase == TransitionPhase.PRE_PUBLISH:
        if now >= plan.pre_publish_until:
            # Ready to start double-signing
            plan.phase = TransitionPhase.DOUBLE_SIGN
            plan.new_key.is_signing = True
            plan.new_key.is_active = True
            return {
                "advanced": True,
                "new_phase": TransitionPhase.DOUBLE_SIGN.value,
                "reason": "Pre-publish period complete, starting double-sign",
                "propagation": propagation
            }
        return {
            "advanced": False,
            "current_phase": TransitionPhase.PRE_PUBLISH.value,
            "remaining_hours": (plan.pre_publish_until - now) / 3600
        }
    
    elif plan.phase == TransitionPhase.DOUBLE_SIGN:
        if propagation["ready"]:
            # Enough verifiers have seen new key — can proceed
            plan.phase = TransitionPhase.POST_REVOKE
            plan.old_key.is_signing = False
            return {
                "advanced": True,
                "new_phase": TransitionPhase.POST_REVOKE.value,
                "reason": f"Propagation {propagation['propagation']:.0%} >= {MIN_VERIFIER_PROPAGATION:.0%}",
                "propagation": propagation
            }
        elif now >= plan.double_sign_until:
            if plan.extensions < MAX_TRANSITION_EXTENSION:
                # Extend overlap
                plan.extensions += 1
                extension_days = OPERATIONAL_ROTATION_DAYS * OVERLAP_RATIO
                plan.double_sign_until = now + extension_days * 86400
                return {
                    "advanced": False,
                    "action": "EXTENDED",
                    "reason": f"Propagation {propagation['propagation']:.0%} < threshold. Extension {plan.extensions}/{MAX_TRANSITION_EXTENSION}",
                    "new_deadline_hours": extension_days * 24,
                    "propagation": propagation
                }
            else:
                # Force transition — Verisign 2018 scenario
                plan.phase = TransitionPhase.POST_REVOKE
                plan.old_key.is_signing = False
                return {
                    "advanced": True,
                    "new_phase": TransitionPhase.POST_REVOKE.value,
                    "reason": "FORCED: max extensions reached",
                    "warning": "Verisign 2018 scenario — some verifiers may reject",
                    "propagation": propagation
                }
        return {
            "advanced": False,
            "current_phase": TransitionPhase.DOUBLE_SIGN.value,
            "remaining_hours": (plan.double_sign_until - now) / 3600,
            "propagation": propagation
        }
    
    elif plan.phase == TransitionPhase.POST_REVOKE:
        plan.old_key.revoked_at = now
        plan.old_key.is_active = False
        plan.phase = TransitionPhase.COMPLETED
        plan.completed_at = now
        return {
            "advanced": True,
            "new_phase": TransitionPhase.COMPLETED.value,
            "total_transition_hours": (now - plan.started_at) / 3600,
            "extensions_used": plan.extensions
        }
    
    return {"advanced": False, "phase": plan.phase.value}


def verify_receipt_during_transition(plan: TransitionPlan, signing_key_id: str) -> dict:
    """Verify a receipt is valid during an active transition."""
    valid_keys = []
    
    if plan.old_key.is_signing:
        valid_keys.append(plan.old_key.key_id)
    if plan.new_key.is_signing:
        valid_keys.append(plan.new_key.key_id)
    
    is_valid = signing_key_id in valid_keys
    
    return {
        "valid": is_valid,
        "signing_key": signing_key_id,
        "accepted_keys": valid_keys,
        "phase": plan.phase.value,
        "warning": "Receipt signed with old key during POST_REVOKE" 
                   if signing_key_id == plan.old_key.key_id and plan.phase == TransitionPhase.POST_REVOKE
                   else None
    }


# === Scenarios ===

def scenario_smooth_rollover():
    """Normal transition — propagation reaches threshold."""
    print("=== Scenario: Smooth Operational Key Rollover ===")
    old_key = Key("key_old_001", KeyType.OPERATIONAL, time.time() - 86400*85, 
                  time.time() + 86400*5, "fp_old", True, True)
    
    plan = create_transition_plan(old_key)
    print(f"  Phase: {plan.phase.value}")
    print(f"  Overlap: {OPERATIONAL_ROTATION_DAYS * OVERLAP_RATIO} days")
    print(f"  Pre-publish: {OPERATIONAL_ROTATION_DAYS * PRE_PUBLISH_RATIO} days")
    
    # Simulate 20 verifiers, 18 see new key
    for i in range(20):
        plan.verifier_states.append(
            VerifierState(f"v{i}", old_key.key_id, time.time(), accepts_new_key=(i < 18))
        )
    
    # Fast-forward past pre-publish
    plan.pre_publish_until = time.time() - 1
    result1 = advance_phase(plan)
    print(f"  → {result1.get('new_phase', result1.get('current_phase'))}: {result1.get('reason', '')}")
    
    # Now in DOUBLE_SIGN with 90% propagation
    result2 = advance_phase(plan)
    print(f"  → {result2.get('new_phase', result2.get('current_phase'))}: {result2.get('reason', '')}")
    
    # Complete
    result3 = advance_phase(plan)
    print(f"  → {result3.get('new_phase')}: transition complete in {result3.get('total_transition_hours', 0):.1f}h")
    print()


def scenario_slow_propagation():
    """Propagation too slow — overlap extended."""
    print("=== Scenario: Slow Propagation (Verisign 2018 Pattern) ===")
    old_key = Key("key_old_002", KeyType.ROOT, time.time() - 86400*350,
                  time.time() + 86400*15, "fp_old2", True, True)
    
    plan = create_transition_plan(old_key)
    
    # Only 50% propagation
    for i in range(20):
        plan.verifier_states.append(
            VerifierState(f"v{i}", old_key.key_id, time.time(), accepts_new_key=(i < 10))
        )
    
    # Past pre-publish
    plan.pre_publish_until = time.time() - 1
    advance_phase(plan)  # → DOUBLE_SIGN
    
    # Past double-sign deadline but low propagation
    plan.double_sign_until = time.time() - 1
    result = advance_phase(plan)
    print(f"  Extension {result.get('action', '')}: {result.get('reason', '')}")
    
    # Still low — extend again
    plan.double_sign_until = time.time() - 1
    result2 = advance_phase(plan)
    print(f"  Extension {result2.get('action', '')}: {result2.get('reason', '')}")
    
    # Max extensions — force
    plan.double_sign_until = time.time() - 1
    result3 = advance_phase(plan)
    print(f"  FORCED: {result3.get('reason', '')} — {result3.get('warning', '')}")
    print()


def scenario_receipt_during_transition():
    """Verify receipts signed with old vs new key during transition."""
    print("=== Scenario: Receipt Verification During Transition ===")
    old_key = Key("key_old_003", KeyType.OPERATIONAL, time.time() - 86400*85,
                  time.time() + 86400*5, "fp_old3", True, True)
    
    plan = create_transition_plan(old_key)
    plan.pre_publish_until = time.time() - 1
    advance_phase(plan)  # → DOUBLE_SIGN
    
    # Both keys should be valid
    r1 = verify_receipt_during_transition(plan, old_key.key_id)
    r2 = verify_receipt_during_transition(plan, plan.new_key.key_id)
    r3 = verify_receipt_during_transition(plan, "key_unknown")
    
    print(f"  DOUBLE_SIGN phase:")
    print(f"    Old key: valid={r1['valid']} (accepted: {r1['accepted_keys']})")
    print(f"    New key: valid={r2['valid']}")
    print(f"    Unknown key: valid={r3['valid']}")
    
    # Advance to POST_REVOKE
    for i in range(20):
        plan.verifier_states.append(
            VerifierState(f"v{i}", old_key.key_id, time.time(), accepts_new_key=True)
        )
    advance_phase(plan)  # → POST_REVOKE
    
    r4 = verify_receipt_during_transition(plan, old_key.key_id)
    r5 = verify_receipt_during_transition(plan, plan.new_key.key_id)
    
    print(f"  POST_REVOKE phase:")
    print(f"    Old key: valid={r4['valid']}, warning={r4['warning']}")
    print(f"    New key: valid={r5['valid']}")
    print()


def scenario_emergency_cutover():
    """Key compromise — immediate transition, no overlap."""
    print("=== Scenario: Emergency Cutover (Key Compromise) ===")
    old_key = Key("key_compromised", KeyType.OPERATIONAL, time.time() - 86400*30,
                  time.time() + 86400*60, "fp_compromised", True, True)
    
    plan = create_transition_plan(old_key, RolloverStrategy.EMERGENCY)
    
    # Emergency: skip pre-publish, go straight to new key
    plan.phase = TransitionPhase.POST_REVOKE
    plan.old_key.is_signing = False
    plan.old_key.is_active = False
    plan.new_key.is_signing = True
    plan.new_key.is_active = True
    
    result = advance_phase(plan)
    print(f"  Strategy: EMERGENCY (no overlap)")
    print(f"  Old key: signing={plan.old_key.is_signing}, active={plan.old_key.is_active}")
    print(f"  New key: signing={plan.new_key.is_signing}, active={plan.new_key.is_active}")
    print(f"  Risk: verifiers using cached old key will REJECT until propagation catches up")
    print(f"  This is Verisign 2018 in reverse: better to break some verifiers than sign with compromised key")
    print()


if __name__ == "__main__":
    print("Overlap Transition Engine — Soft Key Transition for ATF")
    print("Per funwolf + RFC 6781 Section 4.1.4 + Verisign KSK rollover")
    print("=" * 70)
    print()
    print("Three phases: PRE_PUBLISH → DOUBLE_SIGN → POST_REVOKE")
    print(f"Overlap: {OVERLAP_RATIO:.0%} of rotation period")
    print(f"Propagation threshold: {MIN_VERIFIER_PROPAGATION:.0%}")
    print(f"Max extensions: {MAX_TRANSITION_EXTENSION}")
    print()
    
    scenario_smooth_rollover()
    scenario_slow_propagation()
    scenario_receipt_during_transition()
    scenario_emergency_cutover()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Overlap is NOT a security weakness — it prevents rollover catastrophe.")
    print("2. Double-sign = both keys valid simultaneously. Network adapts.")
    print("3. Propagation-gated advancement: don't revoke old key until 80%+ see new one.")
    print("4. Max 2 extensions, then force (Verisign 2018 lesson: don't wait forever).")
    print("5. Emergency = no overlap, accept breakage. Compromise > compatibility.")
