#!/usr/bin/env python3
"""
ceremony-scheduler.py — Periodic re-attestation scheduler for ATF registries.

Per santaclawd: "registries age. operators change. trust anchors should have
expiry + re-attestation windows, not just genesis."

DNSSEC model: KSK rolled twice in 7 years (Verisign). Too slow.
ATF: annual ceremony for root, quarterly for operational keys.
eIDAS 2.0: QTSP re-assessment every 24 months.
WebTrust: CA re-audit every 12 months.

Key insight: missed ceremony = STALE → EXPIRED. No perpetual roots.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class KeyType(Enum):
    ROOT = "ROOT"               # Registry root key (ceremony, annual)
    OPERATIONAL = "OPERATIONAL"  # Daily signing key (automated, quarterly)
    WITNESS = "WITNESS"         # Witness attestation key


class CeremonyType(Enum):
    GENESIS = "GENESIS"         # First-ever ceremony
    RE_ATTESTATION = "RE_ATTESTATION"  # Scheduled re-key
    EMERGENCY = "EMERGENCY"     # Forced re-key (compromise)


class KeyState(Enum):
    ACTIVE = "ACTIVE"
    GRACE = "GRACE"             # Within re-attestation window
    STALE = "STALE"             # Past TTL, grace expired
    EXPIRED = "EXPIRED"         # Hard expired, no trust
    REVOKED = "REVOKED"         # Manually revoked


# SPEC_CONSTANTS (days)
ROOT_TTL = 365                    # Annual root ceremony
ROOT_GRACE = 30                   # 30-day grace before STALE
OPERATIONAL_TTL = 90              # Quarterly operational rotation
OPERATIONAL_GRACE = 14            # 14-day grace
WITNESS_TTL = 180                 # Semi-annual witness re-key
WITNESS_GRACE = 21                # 21-day grace
EMERGENCY_COOLDOWN = 7            # Min days between emergency ceremonies
RE_ATTESTATION_WINDOW_DAYS = 30   # Window before TTL to start re-attestation
MIN_WITNESSES_REKEY = 4           # BFT 3f+1, f=1


@dataclass
class CeremonyKey:
    key_id: str
    key_type: KeyType
    operator_id: str
    created_at: float
    ttl_days: int
    grace_days: int
    state: KeyState = KeyState.ACTIVE
    last_ceremony: Optional[float] = None
    ceremony_count: int = 0
    ceremony_transcript_hash: str = ""
    witnesses: list[str] = field(default_factory=list)


@dataclass
class CeremonyEvent:
    ceremony_type: CeremonyType
    key_id: str
    timestamp: float
    witnesses: list[str]
    transcript_hash: str
    old_key_hash: Optional[str] = None
    new_key_hash: Optional[str] = None
    operator_diversity: float = 0.0


def compute_key_state(key: CeremonyKey, now: Optional[float] = None) -> dict:
    """Compute current state of a ceremony key."""
    if now is None:
        now = time.time()
    
    if key.state == KeyState.REVOKED:
        return {"state": KeyState.REVOKED.value, "action": "REPLACE", "days_remaining": 0}
    
    ceremony_time = key.last_ceremony or key.created_at
    age_days = (now - ceremony_time) / 86400
    ttl = key.ttl_days
    grace = key.grace_days
    
    # Re-attestation window = TTL - window
    rekey_window_start = ttl - RE_ATTESTATION_WINDOW_DAYS
    
    if age_days < rekey_window_start:
        state = KeyState.ACTIVE
        action = "NONE"
        days_remaining = ttl - age_days
    elif age_days < ttl:
        state = KeyState.ACTIVE
        action = "SCHEDULE_CEREMONY"
        days_remaining = ttl - age_days
    elif age_days < ttl + grace:
        state = KeyState.GRACE
        action = "URGENT_CEREMONY"
        days_remaining = (ttl + grace) - age_days
    elif age_days < ttl + grace + 30:  # 30-day STALE window
        state = KeyState.STALE
        action = "EMERGENCY_CEREMONY"
        days_remaining = (ttl + grace + 30) - age_days
    else:
        state = KeyState.EXPIRED
        action = "NEW_GENESIS_REQUIRED"
        days_remaining = 0
    
    return {
        "state": state.value,
        "action": action,
        "age_days": round(age_days, 1),
        "ttl_days": ttl,
        "grace_days": grace,
        "days_remaining": round(max(0, days_remaining), 1),
        "ceremony_count": key.ceremony_count,
        "in_rekey_window": age_days >= rekey_window_start and age_days < ttl,
        "next_ceremony_due": round(max(0, rekey_window_start - age_days), 1)
    }


def validate_ceremony(event: CeremonyEvent, key: CeremonyKey) -> dict:
    """Validate a re-attestation ceremony."""
    issues = []
    
    # Witness count
    if len(event.witnesses) < MIN_WITNESSES_REKEY:
        issues.append(f"Need {MIN_WITNESSES_REKEY} witnesses, got {len(event.witnesses)}")
    
    # Operator diversity
    unique_operators = len(set(event.witnesses))
    if unique_operators < MIN_WITNESSES_REKEY:
        issues.append(f"Need {MIN_WITNESSES_REKEY} distinct operators, got {unique_operators}")
    
    # Transcript hash
    if not event.transcript_hash:
        issues.append("Missing ceremony transcript hash")
    
    # Emergency cooldown
    if event.ceremony_type == CeremonyType.EMERGENCY and key.last_ceremony:
        days_since_last = (event.timestamp - key.last_ceremony) / 86400
        if days_since_last < EMERGENCY_COOLDOWN:
            issues.append(f"Emergency cooldown: {EMERGENCY_COOLDOWN}d required, {days_since_last:.1f}d since last")
    
    # Key rotation: must have both old and new hashes
    if event.ceremony_type == CeremonyType.RE_ATTESTATION:
        if not event.old_key_hash or not event.new_key_hash:
            issues.append("RE_ATTESTATION requires old_key_hash and new_key_hash")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "ceremony_type": event.ceremony_type.value,
        "witness_count": len(event.witnesses),
        "unique_operators": unique_operators
    }


def schedule_ceremonies(keys: list[CeremonyKey], now: Optional[float] = None) -> list[dict]:
    """Generate ceremony schedule for all keys."""
    if now is None:
        now = time.time()
    
    schedule = []
    for key in keys:
        state = compute_key_state(key, now)
        if state["action"] != "NONE":
            schedule.append({
                "key_id": key.key_id,
                "key_type": key.key_type.value,
                "operator": key.operator_id,
                "current_state": state["state"],
                "action": state["action"],
                "days_remaining": state["days_remaining"],
                "priority": _priority(state["action"]),
                "ceremony_count": state["ceremony_count"]
            })
    
    return sorted(schedule, key=lambda x: x["priority"])


def _priority(action: str) -> int:
    return {
        "NEW_GENESIS_REQUIRED": 0,
        "EMERGENCY_CEREMONY": 1,
        "URGENT_CEREMONY": 2,
        "SCHEDULE_CEREMONY": 3,
        "NONE": 4
    }.get(action, 5)


# === Scenarios ===

def scenario_healthy_registry():
    """All keys within TTL — no action needed."""
    print("=== Scenario: Healthy Registry ===")
    now = time.time()
    keys = [
        CeremonyKey("root_001", KeyType.ROOT, "op_main", now - 86400*100, ROOT_TTL, ROOT_GRACE,
                    last_ceremony=now - 86400*100, ceremony_count=1),
        CeremonyKey("op_001", KeyType.OPERATIONAL, "op_main", now - 86400*30, OPERATIONAL_TTL, OPERATIONAL_GRACE,
                    last_ceremony=now - 86400*30, ceremony_count=3),
    ]
    
    for key in keys:
        state = compute_key_state(key, now)
        print(f"  {key.key_type.value} ({key.key_id}): {state['state']} "
              f"age={state['age_days']}d remaining={state['days_remaining']}d action={state['action']}")
    print()


def scenario_approaching_rekey():
    """Root key approaching re-attestation window."""
    print("=== Scenario: Approaching Re-Key Window ===")
    now = time.time()
    keys = [
        CeremonyKey("root_002", KeyType.ROOT, "op_main", now - 86400*340, ROOT_TTL, ROOT_GRACE,
                    last_ceremony=now - 86400*340, ceremony_count=2),
        CeremonyKey("op_002", KeyType.OPERATIONAL, "op_main", now - 86400*80, OPERATIONAL_TTL, OPERATIONAL_GRACE,
                    last_ceremony=now - 86400*80, ceremony_count=8),
    ]
    
    schedule = schedule_ceremonies(keys, now)
    for item in schedule:
        print(f"  [{item['priority']}] {item['key_type']} {item['key_id']}: "
              f"{item['action']} ({item['days_remaining']}d remaining)")
    print()


def scenario_stale_registry():
    """Registry missed re-attestation — STALE."""
    print("=== Scenario: Stale Registry (Missed Re-Attestation) ===")
    now = time.time()
    root = CeremonyKey("root_003", KeyType.ROOT, "op_neglect", now - 86400*410, ROOT_TTL, ROOT_GRACE,
                       last_ceremony=now - 86400*410, ceremony_count=1)
    
    state = compute_key_state(root, now)
    print(f"  Root key: {state['state']} age={state['age_days']}d action={state['action']}")
    print(f"  This is the PGP failure mode: trust that never expires.")
    print(f"  ATF fix: mandatory re-attestation. Missed ceremony = degraded trust.")
    print()


def scenario_emergency_rekey():
    """Key compromise — emergency ceremony."""
    print("=== Scenario: Emergency Re-Key (Compromise) ===")
    now = time.time()
    root = CeremonyKey("root_004", KeyType.ROOT, "op_compromised", now - 86400*200, ROOT_TTL, ROOT_GRACE,
                       last_ceremony=now - 86400*200, ceremony_count=3)
    
    event = CeremonyEvent(
        CeremonyType.EMERGENCY, "root_004", now,
        witnesses=["op_a", "op_b", "op_c", "op_d"],
        transcript_hash=hashlib.sha256(b"emergency_transcript").hexdigest()[:16],
        old_key_hash="old_abc123",
        new_key_hash="new_def456"
    )
    
    validation = validate_ceremony(event, root)
    print(f"  Emergency ceremony: valid={validation['valid']}")
    print(f"  Witnesses: {validation['witness_count']} ({validation['unique_operators']} unique operators)")
    if validation['issues']:
        for issue in validation['issues']:
            print(f"    ⚠ {issue}")
    print()


def scenario_expired_needs_genesis():
    """Fully expired — needs new genesis."""
    print("=== Scenario: Expired — Needs New Genesis ===")
    now = time.time()
    root = CeremonyKey("root_005", KeyType.ROOT, "op_dead", now - 86400*500, ROOT_TTL, ROOT_GRACE,
                       last_ceremony=now - 86400*500, ceremony_count=1)
    
    state = compute_key_state(root, now)
    print(f"  Root key: {state['state']} age={state['age_days']}d")
    print(f"  Action: {state['action']}")
    print(f"  Cannot re-attest an expired root. Must start over with new genesis ceremony.")
    print(f"  All downstream trust chains are broken.")
    print()


if __name__ == "__main__":
    print("Ceremony Scheduler — Periodic Re-Attestation for ATF Registries")
    print("Per santaclawd + DNSSEC/WebTrust/eIDAS models")
    print("=" * 70)
    print()
    print(f"Root:        TTL={ROOT_TTL}d, grace={ROOT_GRACE}d, rekey window={RE_ATTESTATION_WINDOW_DAYS}d before expiry")
    print(f"Operational: TTL={OPERATIONAL_TTL}d, grace={OPERATIONAL_GRACE}d")
    print(f"Witness:     TTL={WITNESS_TTL}d, grace={WITNESS_GRACE}d")
    print(f"Min witnesses for ceremony: {MIN_WITNESSES_REKEY} (BFT 3f+1)")
    print()
    
    scenario_healthy_registry()
    scenario_approaching_rekey()
    scenario_stale_registry()
    scenario_emergency_rekey()
    scenario_expired_needs_genesis()
    
    print("=" * 70)
    print("KEY INSIGHT: No perpetual roots. Registries MUST re-attest on schedule.")
    print("DNSSEC KSK rolled twice in 7 years — too slow. ATF: annual root, quarterly ops.")
    print("Missed ceremony = STALE → EXPIRED. All downstream chains break.")
    print("PGP died from perpetual non-expiring trust. ATF must not repeat this.")
