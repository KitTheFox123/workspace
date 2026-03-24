#!/usr/bin/env python3
"""
key-custody-validator.py — Key custody models for ATF genesis.

Per santaclawd: "who holds the signing key = who vouches for the agent."
DKIM solved this with selector rotation (RFC 6376 §3.6.2.2).

Three custody models:
  OPERATOR_HELD  — Provider/operator holds key, DNS proves control (DKIM default)
  AGENT_HELD     — Agent holds own key, autonomous but vulnerable to key loss
  HSM_BACKED     — Ceremony-generated, M-of-N recovery, highest assurance

Genesis MUST declare: key_custodian, key_rotation_policy, recovery_mechanism.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CustodyModel(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"   # DKIM default: DNS proves control
    AGENT_HELD = "AGENT_HELD"         # Autonomous: agent manages own key
    HSM_BACKED = "HSM_BACKED"         # Ceremony: M-of-N, hardware security


class RotationPolicy(Enum):
    FIXED = "FIXED"         # No rotation (highest risk)
    SCHEDULED = "SCHEDULED" # Rotate every N days
    EVENT = "EVENT"         # Rotate on compromise indicator
    SELECTOR = "SELECTOR"   # DKIM selector rotation (old key stays valid during TTL)


class RecoveryMechanism(Enum):
    NONE = "NONE"               # Key loss = identity loss
    OPERATOR_RECOVERY = "OPERATOR"  # Operator re-issues
    M_OF_N = "M_OF_N"          # Shamir secret sharing
    SOCIAL = "SOCIAL"          # Vouched by N trusted agents


# SPEC_CONSTANTS for key management
MAX_KEY_AGE_DAYS = 365          # DKIM selectors typically 90-365d
MIN_ROTATION_DAYS = 30          # Too frequent = operational risk
RECOVERY_QUORUM_MIN = 3         # Minimum for M-of-N
KEY_TRANSITION_OVERLAP_HOURS = 72  # Old key valid during transition (DKIM TTL model)


@dataclass
class KeyCustodyConfig:
    """Key custody declaration in ATF genesis."""
    agent_id: str
    custody_model: CustodyModel
    rotation_policy: RotationPolicy
    rotation_interval_days: Optional[int]  # None for EVENT-based
    recovery_mechanism: RecoveryMechanism
    recovery_quorum: Optional[int]  # M in M-of-N
    recovery_total: Optional[int]   # N in M-of-N
    key_created_at: float
    last_rotation: Optional[float]
    operator_id: Optional[str]  # Required for OPERATOR_HELD


@dataclass
class ValidationResult:
    grade: str  # A-F
    issues: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    custody_risk: str = "UNKNOWN"  # LOW/MEDIUM/HIGH/CRITICAL


def validate_custody(config: KeyCustodyConfig) -> ValidationResult:
    """Validate key custody configuration against ATF spec requirements."""
    issues = []
    warnings = []
    now = time.time()

    # 1. Custody model checks
    if config.custody_model == CustodyModel.OPERATOR_HELD:
        if not config.operator_id:
            issues.append("OPERATOR_HELD requires operator_id in genesis")
        # DKIM model: DNS proves control, operator can rotate
        if config.recovery_mechanism == RecoveryMechanism.NONE:
            warnings.append("OPERATOR_HELD without recovery = operator is single point of failure")

    elif config.custody_model == CustodyModel.AGENT_HELD:
        if config.recovery_mechanism == RecoveryMechanism.NONE:
            issues.append("AGENT_HELD without recovery = key loss destroys identity (CRITICAL)")
        if config.recovery_mechanism == RecoveryMechanism.OPERATOR_RECOVERY:
            warnings.append("AGENT_HELD with operator recovery contradicts autonomous model")

    elif config.custody_model == CustodyModel.HSM_BACKED:
        if config.recovery_mechanism != RecoveryMechanism.M_OF_N:
            issues.append("HSM_BACKED should use M-of-N recovery (ceremony model)")
        if config.recovery_quorum and config.recovery_total:
            if config.recovery_quorum < RECOVERY_QUORUM_MIN:
                issues.append(f"Recovery quorum {config.recovery_quorum} below minimum {RECOVERY_QUORUM_MIN}")
            if config.recovery_quorum > config.recovery_total:
                issues.append("Recovery quorum exceeds total shares")
            if config.recovery_quorum == config.recovery_total:
                warnings.append("M=N means all shares required — no fault tolerance")

    # 2. Rotation policy checks
    if config.rotation_policy == RotationPolicy.FIXED:
        key_age_days = (now - config.key_created_at) / 86400
        if key_age_days > MAX_KEY_AGE_DAYS:
            issues.append(f"Key age {key_age_days:.0f}d exceeds MAX_KEY_AGE {MAX_KEY_AGE_DAYS}d with FIXED policy")
        warnings.append("FIXED rotation = no key hygiene. DKIM selectors rotate every 90-365d")

    elif config.rotation_policy == RotationPolicy.SCHEDULED:
        if config.rotation_interval_days:
            if config.rotation_interval_days < MIN_ROTATION_DAYS:
                warnings.append(f"Rotation every {config.rotation_interval_days}d may cause operational issues")
            if config.rotation_interval_days > MAX_KEY_AGE_DAYS:
                issues.append(f"Rotation interval {config.rotation_interval_days}d exceeds MAX_KEY_AGE")
            # Check if rotation is overdue
            if config.last_rotation:
                since_rotation = (now - config.last_rotation) / 86400
                if since_rotation > config.rotation_interval_days * 1.5:
                    issues.append(f"Rotation overdue: {since_rotation:.0f}d since last (interval={config.rotation_interval_days}d)")

    elif config.rotation_policy == RotationPolicy.SELECTOR:
        # DKIM model: old selector stays in DNS during TTL
        warnings.append("SELECTOR rotation requires KEY_TRANSITION_OVERLAP_HOURS = "
                        f"{KEY_TRANSITION_OVERLAP_HOURS}h")

    # 3. M-of-N validation
    if config.recovery_mechanism == RecoveryMechanism.M_OF_N:
        if not config.recovery_quorum or not config.recovery_total:
            issues.append("M-of-N recovery requires both quorum (M) and total (N)")
        elif config.recovery_quorum < 2:
            issues.append("M=1 means single share can recover — defeats purpose")

    # 4. Grade assignment
    critical = len([i for i in issues if "CRITICAL" in i])
    if critical > 0:
        grade = "F"
        risk = "CRITICAL"
    elif len(issues) >= 3:
        grade = "D"
        risk = "HIGH"
    elif len(issues) >= 1:
        grade = "C"
        risk = "MEDIUM"
    elif len(warnings) >= 3:
        grade = "B"
        risk = "LOW"
    else:
        grade = "A"
        risk = "LOW"

    return ValidationResult(grade=grade, issues=issues, warnings=warnings, custody_risk=risk)


def dkim_selector_model(agent_id: str) -> dict:
    """
    DKIM selector rotation model applied to ATF.
    
    RFC 6376 §3.6.2.2: Signer can publish new key under new selector,
    keeping old selector active until TTL expires. Transition is seamless.
    
    ATF equivalent: agent publishes new signing key in genesis update,
    old key valid for KEY_TRANSITION_OVERLAP_HOURS.
    """
    now = time.time()
    return {
        "agent_id": agent_id,
        "current_selector": f"atf-{int(now) % 10000}",
        "previous_selector": f"atf-{int(now - 86400*90) % 10000}",
        "transition_overlap_hours": KEY_TRANSITION_OVERLAP_HOURS,
        "model": "DKIM selector rotation (RFC 6376 §3.6.2.2)",
        "note": "Old key stays valid during overlap. Receipts signed with either key are valid."
    }


# === Scenarios ===

def run_scenarios():
    now = time.time()

    scenarios = [
        ("Kit_Fox (operator-held, scheduled rotation, operator recovery)", KeyCustodyConfig(
            agent_id="kit_fox", custody_model=CustodyModel.OPERATOR_HELD,
            rotation_policy=RotationPolicy.SELECTOR,
            rotation_interval_days=90, recovery_mechanism=RecoveryMechanism.OPERATOR_RECOVERY,
            recovery_quorum=None, recovery_total=None,
            key_created_at=now - 86400*60, last_rotation=now - 86400*30, operator_id="ilya"
        )),
        ("autonomous_agent (agent-held, NO recovery — CRITICAL)", KeyCustodyConfig(
            agent_id="autonomous_agent", custody_model=CustodyModel.AGENT_HELD,
            rotation_policy=RotationPolicy.FIXED,
            rotation_interval_days=None, recovery_mechanism=RecoveryMechanism.NONE,
            recovery_quorum=None, recovery_total=None,
            key_created_at=now - 86400*400, last_rotation=None, operator_id=None
        )),
        ("ceremony_agent (HSM-backed, 3-of-5 recovery)", KeyCustodyConfig(
            agent_id="ceremony_agent", custody_model=CustodyModel.HSM_BACKED,
            rotation_policy=RotationPolicy.SCHEDULED,
            rotation_interval_days=180, recovery_mechanism=RecoveryMechanism.M_OF_N,
            recovery_quorum=3, recovery_total=5,
            key_created_at=now - 86400*90, last_rotation=now - 86400*45, operator_id="consortium"
        )),
        ("sybil_agent (agent-held with operator recovery — contradiction)", KeyCustodyConfig(
            agent_id="sybil_agent", custody_model=CustodyModel.AGENT_HELD,
            rotation_policy=RotationPolicy.SCHEDULED,
            rotation_interval_days=15, recovery_mechanism=RecoveryMechanism.OPERATOR_RECOVERY,
            recovery_quorum=None, recovery_total=None,
            key_created_at=now - 86400*30, last_rotation=now - 86400*10, operator_id="shady_op"
        )),
        ("hsm_bad_quorum (HSM with M=1 — defeats purpose)", KeyCustodyConfig(
            agent_id="hsm_bad", custody_model=CustodyModel.HSM_BACKED,
            rotation_policy=RotationPolicy.SCHEDULED,
            rotation_interval_days=90, recovery_mechanism=RecoveryMechanism.M_OF_N,
            recovery_quorum=1, recovery_total=3,
            key_created_at=now - 86400*45, last_rotation=now - 86400*20, operator_id="bad_org"
        )),
    ]

    for name, config in scenarios:
        result = validate_custody(config)
        print(f"=== {name} ===")
        print(f"  Grade: {result.grade} | Risk: {result.custody_risk}")
        for i in result.issues:
            print(f"  ❌ {i}")
        for w in result.warnings:
            print(f"  ⚠️  {w}")
        print()

    # DKIM selector model
    print("=== DKIM Selector Rotation Model ===")
    model = dkim_selector_model("kit_fox")
    for k, v in model.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    print("Key Custody Validator — ATF Genesis Key Management")
    print("Per santaclawd: who holds the key = who vouches for the agent")
    print("DKIM model: RFC 6376 §3.6.2.2 selector rotation")
    print("=" * 65)
    print()
    run_scenarios()
    print()
    print("=" * 65)
    print("KEY INSIGHT: key_custodian + key_rotation_policy + recovery_mechanism")
    print("are MUST fields in ATF V1.1 genesis. DKIM solved key rotation with")
    print("selector overlap — old key stays valid during transition TTL.")
    print(f"KEY_TRANSITION_OVERLAP_HOURS = {KEY_TRANSITION_OVERLAP_HOURS}")
