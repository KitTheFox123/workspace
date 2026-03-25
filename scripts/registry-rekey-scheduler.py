#!/usr/bin/env python3
"""
registry-rekey-scheduler.py — Split-key re-attestation for ATF registries.

Per santaclawd: "registries age. operators change. trust anchors should have
expiry + re-attestation windows, not just genesis."
Per Verisign (Jan 2025): DNSSEC root KSK rolled only twice (2017, 2024).
Seven years is too slow for agent time.

Split-key model (DNSSEC parallel):
  REGISTRY_ROOT_KEY  — Annual ceremony, multi-witness (= KSK)
  OPERATIONAL_KEY    — Quarterly automated renewal (= ZSK)

Risk-tiered ceremony frequency:
  HIGH   — 180d root, 30d operational
  MEDIUM — 365d root, 90d operational  
  LOW    — 730d root, 180d operational
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class KeyType(Enum):
    REGISTRY_ROOT = "REGISTRY_ROOT"    # Ceremony key (KSK equivalent)
    OPERATIONAL = "OPERATIONAL"         # Automated key (ZSK equivalent)


class RiskTier(Enum):
    HIGH = "HIGH"       # Financial, identity-critical
    MEDIUM = "MEDIUM"   # General purpose
    LOW = "LOW"         # Experimental, low-value


class CeremonyStatus(Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    EMERGENCY = "EMERGENCY"


# SPEC_CONSTANTS per risk tier
REKEY_SCHEDULE = {
    RiskTier.HIGH: {
        KeyType.REGISTRY_ROOT: 180,   # days
        KeyType.OPERATIONAL: 30,
    },
    RiskTier.MEDIUM: {
        KeyType.REGISTRY_ROOT: 365,
        KeyType.OPERATIONAL: 90,
    },
    RiskTier.LOW: {
        KeyType.REGISTRY_ROOT: 730,
        KeyType.OPERATIONAL: 180,
    },
}

# Ceremony requirements per key type
CEREMONY_REQUIREMENTS = {
    KeyType.REGISTRY_ROOT: {
        "min_witnesses": 4,          # BFT 3f+1, f=1
        "min_operator_classes": 3,    # Diversity
        "signed_transcript": True,
        "advance_notice_days": 30,
        "overlap_period_days": 14,   # Old key still valid during transition
    },
    KeyType.OPERATIONAL: {
        "min_witnesses": 2,
        "min_operator_classes": 1,
        "signed_transcript": False,  # Automated
        "advance_notice_days": 7,
        "overlap_period_days": 7,
    },
}

OVERDUE_GRACE_DAYS = 30  # Grace period before EMERGENCY
DNSSEC_KSK_INTERVAL_YEARS = 7  # For comparison


@dataclass
class Key:
    key_id: str
    key_type: KeyType
    created_at: float
    expires_at: float
    ceremony_hash: str  # Links to ceremony transcript
    operator_id: str
    active: bool = True


@dataclass
class Registry:
    registry_id: str
    risk_tier: RiskTier
    operator_id: str
    root_key: Optional[Key] = None
    operational_key: Optional[Key] = None
    ceremony_history: list = field(default_factory=list)


@dataclass
class CeremonyRecord:
    ceremony_id: str
    key_type: KeyType
    timestamp: float
    witnesses: list[str]
    witness_operators: list[str]
    old_key_id: Optional[str]
    new_key_id: str
    transcript_hash: str
    status: CeremonyStatus


def compute_next_rekey(registry: Registry, key_type: KeyType) -> dict:
    """Compute when next re-attestation is due."""
    schedule = REKEY_SCHEDULE[registry.risk_tier]
    interval_days = schedule[key_type]
    
    key = registry.root_key if key_type == KeyType.REGISTRY_ROOT else registry.operational_key
    now = time.time()
    
    if key is None:
        return {
            "status": "NO_KEY",
            "action": "GENESIS_CEREMONY_REQUIRED",
            "urgency": "CRITICAL"
        }
    
    days_since_creation = (now - key.created_at) / 86400
    days_until_expiry = (key.expires_at - now) / 86400
    
    requirements = CEREMONY_REQUIREMENTS[key_type]
    advance_notice = requirements["advance_notice_days"]
    
    if days_until_expiry < 0:
        overdue_days = abs(days_until_expiry)
        if overdue_days > OVERDUE_GRACE_DAYS:
            status = CeremonyStatus.EMERGENCY
        else:
            status = CeremonyStatus.OVERDUE
    elif days_until_expiry < advance_notice:
        status = CeremonyStatus.SCHEDULED
    else:
        status = CeremonyStatus.COMPLETED  # Current key still valid
    
    return {
        "key_type": key_type.value,
        "risk_tier": registry.risk_tier.value,
        "interval_days": interval_days,
        "key_age_days": round(days_since_creation, 1),
        "days_until_expiry": round(days_until_expiry, 1),
        "status": status.value,
        "next_ceremony_window": f"in {max(0, days_until_expiry - advance_notice):.0f} days",
        "overlap_period_days": requirements["overlap_period_days"],
        "requirements": requirements
    }


def validate_ceremony(ceremony: CeremonyRecord, registry: Registry) -> dict:
    """Validate a re-attestation ceremony meets requirements."""
    requirements = CEREMONY_REQUIREMENTS[ceremony.key_type]
    issues = []
    
    if len(ceremony.witnesses) < requirements["min_witnesses"]:
        issues.append(f"Need {requirements['min_witnesses']} witnesses, got {len(ceremony.witnesses)}")
    
    unique_operators = len(set(ceremony.witness_operators))
    if unique_operators < requirements["min_operator_classes"]:
        issues.append(f"Need {requirements['min_operator_classes']} operator classes, got {unique_operators}")
    
    if requirements["signed_transcript"] and not ceremony.transcript_hash:
        issues.append("Signed transcript required for REGISTRY_ROOT ceremony")
    
    # Check overlap: old key should still be valid
    if ceremony.old_key_id and registry.root_key:
        old_key = registry.root_key
        overlap_remaining = (old_key.expires_at - ceremony.timestamp) / 86400
        if overlap_remaining < 0:
            issues.append(f"Old key expired {abs(overlap_remaining):.0f} days before ceremony — gap in trust chain")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "witnesses": len(ceremony.witnesses),
        "operator_diversity": unique_operators,
        "ceremony_type": ceremony.key_type.value
    }


def compare_with_dnssec() -> dict:
    """Compare ATF rekey schedule with DNSSEC."""
    return {
        "dnssec_ksk_interval_years": DNSSEC_KSK_INTERVAL_YEARS,
        "dnssec_zsk_interval_days": 90,
        "atf_high_root_days": REKEY_SCHEDULE[RiskTier.HIGH][KeyType.REGISTRY_ROOT],
        "atf_high_operational_days": REKEY_SCHEDULE[RiskTier.HIGH][KeyType.OPERATIONAL],
        "atf_medium_root_days": REKEY_SCHEDULE[RiskTier.MEDIUM][KeyType.REGISTRY_ROOT],
        "speedup_vs_dnssec": f"{DNSSEC_KSK_INTERVAL_YEARS * 365 / REKEY_SCHEDULE[RiskTier.MEDIUM][KeyType.REGISTRY_ROOT]:.0f}x faster",
        "rationale": "Agent time moves faster than DNS time. 7-year KSK rollover = unacceptable for ATF."
    }


# === Scenarios ===

def scenario_medium_risk_lifecycle():
    """Normal medium-risk registry through full rekey cycle."""
    print("=== Scenario: Medium-Risk Registry Lifecycle ===")
    now = time.time()
    
    registry = Registry("reg_001", RiskTier.MEDIUM, "op_main")
    
    # Genesis key created 300 days ago
    registry.root_key = Key("root_001", KeyType.REGISTRY_ROOT,
                           now - 86400*300, now + 86400*65,  # Expires in 65 days
                           "genesis_hash", "op_main")
    registry.operational_key = Key("op_001", KeyType.OPERATIONAL,
                                  now - 86400*80, now + 86400*10,  # Expires in 10 days
                                  "op_hash", "op_main")
    
    root_status = compute_next_rekey(registry, KeyType.REGISTRY_ROOT)
    op_status = compute_next_rekey(registry, KeyType.OPERATIONAL)
    
    print(f"  Root key: {root_status['status']} (expires in {root_status['days_until_expiry']}d)")
    print(f"  Operational key: {op_status['status']} (expires in {op_status['days_until_expiry']}d)")
    print(f"  Root ceremony window: {root_status['next_ceremony_window']}")
    print(f"  Op ceremony window: {op_status['next_ceremony_window']}")
    print()


def scenario_overdue_root():
    """Root key expired — escalating urgency."""
    print("=== Scenario: Overdue Root Key ===")
    now = time.time()
    
    registry = Registry("reg_002", RiskTier.HIGH, "op_slow")
    
    # Root key expired 20 days ago (within grace)
    registry.root_key = Key("root_old", KeyType.REGISTRY_ROOT,
                           now - 86400*200, now - 86400*20,
                           "old_hash", "op_slow")
    
    status = compute_next_rekey(registry, KeyType.REGISTRY_ROOT)
    print(f"  Status: {status['status']}")
    print(f"  Days overdue: {abs(status['days_until_expiry']):.0f}")
    print(f"  Grace period: {OVERDUE_GRACE_DAYS}d")
    print(f"  Within grace: {abs(status['days_until_expiry']) <= OVERDUE_GRACE_DAYS}")
    print()
    
    # Now 45 days overdue (past grace)
    registry.root_key.expires_at = now - 86400*45
    status2 = compute_next_rekey(registry, KeyType.REGISTRY_ROOT)
    print(f"  After 45 days overdue: {status2['status']}")
    print(f"  EMERGENCY = all trust from this registry degrades to STALE")
    print()


def scenario_valid_ceremony():
    """Proper re-attestation ceremony."""
    print("=== Scenario: Valid Re-Attestation Ceremony ===")
    now = time.time()
    
    registry = Registry("reg_003", RiskTier.MEDIUM, "op_good")
    registry.root_key = Key("root_old", KeyType.REGISTRY_ROOT,
                           now - 86400*350, now + 86400*15,  # Expiring soon
                           "old_hash", "op_good")
    
    ceremony = CeremonyRecord(
        ceremony_id="ceremony_001",
        key_type=KeyType.REGISTRY_ROOT,
        timestamp=now,
        witnesses=["w1", "w2", "w3", "w4", "w5"],
        witness_operators=["op_a", "op_b", "op_c", "op_d"],
        old_key_id="root_old",
        new_key_id="root_new",
        transcript_hash=hashlib.sha256(b"ceremony_transcript").hexdigest()[:16],
        status=CeremonyStatus.COMPLETED
    )
    
    validation = validate_ceremony(ceremony, registry)
    print(f"  Valid: {validation['valid']}")
    print(f"  Witnesses: {validation['witnesses']} (need {CEREMONY_REQUIREMENTS[KeyType.REGISTRY_ROOT]['min_witnesses']})")
    print(f"  Operator diversity: {validation['operator_diversity']} (need {CEREMONY_REQUIREMENTS[KeyType.REGISTRY_ROOT]['min_operator_classes']})")
    print(f"  Overlap: old key still valid for 15 days — clean transition")
    print()


def scenario_gap_in_trust_chain():
    """Old key expired before ceremony — trust chain gap."""
    print("=== Scenario: Trust Chain Gap ===")
    now = time.time()
    
    registry = Registry("reg_004", RiskTier.HIGH, "op_late")
    registry.root_key = Key("root_expired", KeyType.REGISTRY_ROOT,
                           now - 86400*200, now - 86400*5,  # Expired 5 days ago
                           "old_hash", "op_late")
    
    ceremony = CeremonyRecord(
        ceremony_id="ceremony_002",
        key_type=KeyType.REGISTRY_ROOT,
        timestamp=now,  # Ceremony happening NOW, after expiry
        witnesses=["w1", "w2", "w3", "w4"],
        witness_operators=["op_a", "op_b", "op_c"],
        old_key_id="root_expired",
        new_key_id="root_new",
        transcript_hash=hashlib.sha256(b"late_ceremony").hexdigest()[:16],
        status=CeremonyStatus.COMPLETED
    )
    
    validation = validate_ceremony(ceremony, registry)
    print(f"  Valid: {validation['valid']}")
    for issue in validation['issues']:
        print(f"  Issue: {issue}")
    print(f"  KEY: Gap in trust chain = all receipts during gap have no root anchor")
    print()


def scenario_dnssec_comparison():
    """Compare ATF and DNSSEC rekey schedules."""
    print("=== Scenario: ATF vs DNSSEC Rekey Schedule ===")
    comparison = compare_with_dnssec()
    print(f"  DNSSEC KSK interval: {comparison['dnssec_ksk_interval_years']} years")
    print(f"  DNSSEC ZSK interval: {comparison['dnssec_zsk_interval_days']} days")
    print(f"  ATF HIGH root: {comparison['atf_high_root_days']} days")
    print(f"  ATF HIGH operational: {comparison['atf_high_operational_days']} days")
    print(f"  ATF MEDIUM root: {comparison['atf_medium_root_days']} days")
    print(f"  Speedup: {comparison['speedup_vs_dnssec']}")
    print(f"  Rationale: {comparison['rationale']}")
    print()


if __name__ == "__main__":
    print("Registry Rekey Scheduler — Split-Key Re-Attestation for ATF")
    print("Per santaclawd + Verisign (Jan 2025) DNSSEC KSK Rollover")
    print("=" * 70)
    print()
    print("Split-key model:")
    for tier in RiskTier:
        sched = REKEY_SCHEDULE[tier]
        print(f"  {tier.value}: root={sched[KeyType.REGISTRY_ROOT]}d, operational={sched[KeyType.OPERATIONAL]}d")
    print()
    
    scenario_medium_risk_lifecycle()
    scenario_overdue_root()
    scenario_valid_ceremony()
    scenario_gap_in_trust_chain()
    scenario_dnssec_comparison()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Split-key: ceremony key (infrequent) + operational key (automated).")
    print("2. DNSSEC rolled KSK twice in 7 years. ATF: annual or 180d for HIGH risk.")
    print("3. Overlap period prevents trust chain gaps during transition.")
    print("4. Overdue grace → EMERGENCY escalation after 30 days.")
    print("5. Risk-tiered: HIGH registries rotate faster than LOW.")
