#!/usr/bin/env python3
"""
registry-rekey-scheduler.py — Split-key re-attestation for ATF registries.

Per santaclawd: registries age, operators change. Trust anchors need expiry + re-attestation.
Per Verisign KSK-2024 (Jan 2025): DNSSEC split KSK/ZSK — ceremony key rarely rolls,
operational key rolls every 90d.

ATF model:
  ROOT_KEY       — Annual ceremony, multi-witness attestation (DNSSEC KSK parallel)
  OPERATIONAL_KEY — Quarterly automatic rotation (DNSSEC ZSK parallel)
  EMERGENCY_KEY  — 7-day forced rotation on compromise detection

Key insight: DNSSEC has rolled KSK only twice ever (2017, 2025).
ATF should be 7x faster: annual not "whenever we get around to it."
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class KeyType(Enum):
    ROOT = "ROOT"                # Ceremony key (identity)
    OPERATIONAL = "OPERATIONAL"  # Signing key (daily use)
    EMERGENCY = "EMERGENCY"     # Forced rotation


class KeyStatus(Enum):
    ACTIVE = "ACTIVE"
    PENDING_ROLLOVER = "PENDING_ROLLOVER"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class RiskTier(Enum):
    HIGH = "HIGH"        # Payment, identity — 180d operational
    MEDIUM = "MEDIUM"    # General trust — 365d operational
    LOW = "LOW"          # Discovery, metadata — 730d operational


# SPEC_CONSTANTS
ROOT_CEREMONY_INTERVAL_DAYS = 365       # Annual (DNSSEC: ~7 years)
OPERATIONAL_ROTATION_DAYS = {
    RiskTier.HIGH: 90,      # Quarterly
    RiskTier.MEDIUM: 180,   # Semi-annual
    RiskTier.LOW: 365       # Annual
}
EMERGENCY_ROTATION_DAYS = 7
MIN_CEREMONY_WITNESSES = 4             # BFT 3f+1, f=1
OVERLAP_PERIOD_DAYS = 30               # Both old and new key valid
DS_PROPAGATION_DAYS = 14               # DS record propagation window
PRE_PUBLISH_DAYS = 14                  # Publish new key before activation


@dataclass
class RegistryKey:
    key_id: str
    key_type: KeyType
    registry_id: str
    created_at: float
    expires_at: float
    status: KeyStatus = KeyStatus.ACTIVE
    fingerprint: str = ""
    witnesses: list[str] = field(default_factory=list)
    predecessor_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = hashlib.sha256(
                f"{self.key_id}:{self.registry_id}:{self.created_at}".encode()
            ).hexdigest()[:16]


@dataclass
class RolloverEvent:
    old_key_id: str
    new_key_id: str
    key_type: KeyType
    initiated_at: float
    pre_publish_at: float    # New key published but not yet signing
    activation_at: float     # New key starts signing
    revocation_at: float     # Old key revoked
    status: str = "SCHEDULED"
    witnesses: list[str] = field(default_factory=list)


def compute_next_rotation(key: RegistryKey, risk_tier: RiskTier) -> dict:
    """Compute when a key needs rotation."""
    now = time.time()
    age_days = (now - key.created_at) / 86400
    
    if key.key_type == KeyType.ROOT:
        max_age = ROOT_CEREMONY_INTERVAL_DAYS
    elif key.key_type == KeyType.OPERATIONAL:
        max_age = OPERATIONAL_ROTATION_DAYS[risk_tier]
    else:
        max_age = EMERGENCY_ROTATION_DAYS
    
    remaining_days = max_age - age_days
    urgency = "OVERDUE" if remaining_days < 0 else \
              "CRITICAL" if remaining_days < 7 else \
              "WARNING" if remaining_days < 30 else \
              "OK"
    
    return {
        "key_id": key.key_id,
        "key_type": key.key_type.value,
        "age_days": round(age_days, 1),
        "max_age_days": max_age,
        "remaining_days": round(remaining_days, 1),
        "urgency": urgency,
        "needs_rotation": remaining_days <= PRE_PUBLISH_DAYS
    }


def plan_rollover(old_key: RegistryKey, risk_tier: RiskTier) -> RolloverEvent:
    """Plan a key rollover with overlap period."""
    now = time.time()
    
    new_key_id = f"key_{hashlib.sha256(f'{old_key.key_id}:{now}'.encode()).hexdigest()[:8]}"
    
    pre_publish = now
    activation = now + PRE_PUBLISH_DAYS * 86400
    revocation = activation + OVERLAP_PERIOD_DAYS * 86400
    
    return RolloverEvent(
        old_key_id=old_key.key_id,
        new_key_id=new_key_id,
        key_type=old_key.key_type,
        initiated_at=now,
        pre_publish_at=pre_publish,
        activation_at=activation,
        revocation_at=revocation,
        witnesses=old_key.witnesses
    )


def validate_ceremony(witnesses: list[str], min_witnesses: int = MIN_CEREMONY_WITNESSES) -> dict:
    """Validate a root key ceremony has sufficient witnesses."""
    unique_operators = set()
    for w in witnesses:
        # Extract operator from witness ID (format: op_name/witness_id)
        parts = w.split("/")
        if len(parts) >= 2:
            unique_operators.add(parts[0])
        else:
            unique_operators.add(w)
    
    has_quorum = len(witnesses) >= min_witnesses
    has_diversity = len(unique_operators) >= 2  # At least 2 distinct operators
    
    return {
        "witnesses": len(witnesses),
        "min_required": min_witnesses,
        "unique_operators": len(unique_operators),
        "has_quorum": has_quorum,
        "has_diversity": has_diversity,
        "ceremony_valid": has_quorum and has_diversity,
        "bft_tolerance": (len(witnesses) - 1) // 3  # f in 3f+1
    }


def audit_registry_keys(keys: list[RegistryKey], risk_tier: RiskTier) -> dict:
    """Full audit of a registry's key health."""
    results = []
    issues = []
    
    active_root = None
    active_operational = None
    
    for key in keys:
        if key.status != KeyStatus.ACTIVE:
            continue
        
        rotation = compute_next_rotation(key, risk_tier)
        results.append(rotation)
        
        if rotation["urgency"] in ("OVERDUE", "CRITICAL"):
            issues.append(f"{key.key_type.value} key {key.key_id} is {rotation['urgency']} "
                         f"(age: {rotation['age_days']}d, max: {rotation['max_age_days']}d)")
        
        if key.key_type == KeyType.ROOT:
            active_root = key
        elif key.key_type == KeyType.OPERATIONAL:
            active_operational = key
    
    if not active_root:
        issues.append("NO ACTIVE ROOT KEY — registry cannot attest")
    if not active_operational:
        issues.append("NO ACTIVE OPERATIONAL KEY — registry cannot sign")
    
    health = "HEALTHY" if not issues else "DEGRADED" if len(issues) <= 1 else "CRITICAL"
    
    return {
        "registry_health": health,
        "risk_tier": risk_tier.value,
        "active_keys": len([r for r in results]),
        "key_rotations": results,
        "issues": issues,
        "dnssec_parallel": {
            "ksk_equivalent": "ROOT (annual ceremony)",
            "zsk_equivalent": f"OPERATIONAL ({OPERATIONAL_ROTATION_DAYS[risk_tier]}d rotation)",
            "verisign_ksk_rolls": "2 in 7 years (2017, 2025)",
            "atf_target": f"annual root, {OPERATIONAL_ROTATION_DAYS[risk_tier]}d operational"
        }
    }


# === Scenarios ===

def scenario_healthy_registry():
    """Well-maintained registry — all keys fresh."""
    print("=== Scenario: Healthy Registry (HIGH risk) ===")
    now = time.time()
    
    keys = [
        RegistryKey("root_001", KeyType.ROOT, "reg_alpha", now - 86400*120, now + 86400*245,
                    witnesses=["op_a/w1", "op_b/w2", "op_c/w3", "op_d/w4"]),
        RegistryKey("op_001", KeyType.OPERATIONAL, "reg_alpha", now - 86400*60, now + 86400*30)
    ]
    
    audit = audit_registry_keys(keys, RiskTier.HIGH)
    print(f"  Health: {audit['registry_health']}")
    for r in audit['key_rotations']:
        print(f"  {r['key_type']}: age={r['age_days']}d, remaining={r['remaining_days']}d, urgency={r['urgency']}")
    if audit['issues']:
        for i in audit['issues']:
            print(f"  ⚠ {i}")
    print()


def scenario_overdue_rotation():
    """Operational key past rotation date — DEGRADED."""
    print("=== Scenario: Overdue Rotation (HIGH risk) ===")
    now = time.time()
    
    keys = [
        RegistryKey("root_002", KeyType.ROOT, "reg_beta", now - 86400*300, now + 86400*65,
                    witnesses=["op_a/w1", "op_b/w2", "op_c/w3", "op_d/w4"]),
        RegistryKey("op_002", KeyType.OPERATIONAL, "reg_beta", now - 86400*100, now - 86400*10)
    ]
    
    audit = audit_registry_keys(keys, RiskTier.HIGH)
    print(f"  Health: {audit['registry_health']}")
    for r in audit['key_rotations']:
        print(f"  {r['key_type']}: age={r['age_days']}d, remaining={r['remaining_days']}d, urgency={r['urgency']}")
    for i in audit['issues']:
        print(f"  ⚠ {i}")
    
    # Plan rollover
    stale_key = keys[1]
    rollover = plan_rollover(stale_key, RiskTier.HIGH)
    print(f"  Planned rollover: {rollover.old_key_id} → {rollover.new_key_id}")
    print(f"  Pre-publish: now, Activation: +{PRE_PUBLISH_DAYS}d, Revocation: +{PRE_PUBLISH_DAYS + OVERLAP_PERIOD_DAYS}d")
    print()


def scenario_ceremony_validation():
    """Root key ceremony — witness quorum check."""
    print("=== Scenario: Root Key Ceremony Validation ===")
    
    # Valid ceremony
    valid = validate_ceremony(["op_a/w1", "op_b/w2", "op_c/w3", "op_d/w4"])
    print(f"  4 witnesses, 4 operators: valid={valid['ceremony_valid']}, BFT f={valid['bft_tolerance']}")
    
    # Insufficient witnesses
    insufficient = validate_ceremony(["op_a/w1", "op_b/w2"])
    print(f"  2 witnesses: valid={insufficient['ceremony_valid']} (need {MIN_CEREMONY_WITNESSES})")
    
    # Same operator sybil
    sybil = validate_ceremony(["op_a/w1", "op_a/w2", "op_a/w3", "op_a/w4"])
    print(f"  4 witnesses, 1 operator: valid={sybil['ceremony_valid']} (diversity={sybil['has_diversity']})")
    print()


def scenario_risk_tiering():
    """Different risk tiers get different rotation cadences."""
    print("=== Scenario: Risk-Tiered Rotation Cadences ===")
    now = time.time()
    
    for tier in RiskTier:
        key = RegistryKey(f"op_{tier.value}", KeyType.OPERATIONAL, "reg_multi",
                         now - 86400*100, now + 86400*100)
        rotation = compute_next_rotation(key, tier)
        print(f"  {tier.value}: max_age={rotation['max_age_days']}d, "
              f"remaining={rotation['remaining_days']}d, urgency={rotation['urgency']}")
    
    print(f"\n  DNSSEC comparison:")
    print(f"    ZSK rotation: 90 days (Verisign)")
    print(f"    KSK rotation: ~7 years (only twice: 2017, 2025)")
    print(f"    ATF HIGH:     90d operational, 365d root (7x faster than DNSSEC)")
    print()


if __name__ == "__main__":
    print("Registry Rekey Scheduler — Split-Key Re-Attestation for ATF")
    print("Per santaclawd + Verisign KSK-2024 (Jan 2025)")
    print("=" * 70)
    print()
    print("Key hierarchy:")
    print(f"  ROOT:        {ROOT_CEREMONY_INTERVAL_DAYS}d ceremony, {MIN_CEREMONY_WITNESSES} witnesses")
    print(f"  OPERATIONAL: {OPERATIONAL_ROTATION_DAYS[RiskTier.HIGH]}d/{OPERATIONAL_ROTATION_DAYS[RiskTier.MEDIUM]}d/{OPERATIONAL_ROTATION_DAYS[RiskTier.LOW]}d (H/M/L)")
    print(f"  EMERGENCY:   {EMERGENCY_ROTATION_DAYS}d forced")
    print(f"  Overlap:     {OVERLAP_PERIOD_DAYS}d, Pre-publish: {PRE_PUBLISH_DAYS}d")
    print()
    
    scenario_healthy_registry()
    scenario_overdue_rotation()
    scenario_ceremony_validation()
    scenario_risk_tiering()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. DNSSEC split KSK/ZSK = ATF split ROOT/OPERATIONAL.")
    print("2. Verisign rolled KSK twice in 7 years. ATF does it annually — 7x faster.")
    print("3. Overlap period prevents hard cutover failures (DS propagation window).")
    print("4. Risk tiering: HIGH (payment) gets 90d rotation, LOW gets 365d.")
    print("5. Ceremony validation: quorum + operator diversity. Same-operator sybil = invalid.")
