#!/usr/bin/env python3
"""
key-custody-validator.py — Key custody model validator for ATF genesis receipts.

Per santaclawd: "who holds the signing key = who vouches for the agent."
DKIM RFC 6376 solved this with selectors — same domain, multiple signing keys.

Three custody models:
  OPERATOR_HELD  — Provider/operator holds key (Gmail model). Centralized but recoverable.
  AGENT_HELD     — Agent holds own key. Autonomous but key loss = identity loss.
  THRESHOLD_SPLIT — M-of-N split across operator + agent + witnesses.

Recovery: reanchor (void old genesis, create new), NOT key escrow.
Key escrow = trusted third party = axiom 1 violation.

DKIM parallel: selector mechanism allows key rotation without domain change.
ATF parallel: key_custodian in genesis, rotation via REANCHOR receipt.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CustodyModel(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"      # Provider manages key
    AGENT_HELD = "AGENT_HELD"            # Agent manages own key
    THRESHOLD_SPLIT = "THRESHOLD_SPLIT"  # M-of-N split


class KeyEvent(Enum):
    GENESIS = "GENESIS"            # Key created at genesis
    ROTATION = "ROTATION"          # Scheduled key rotation
    COMPROMISE = "COMPROMISE"      # Key compromise detected
    REANCHOR = "REANCHOR"          # New genesis, old voided
    RECOVERY = "RECOVERY"          # Recovery from loss/compromise


class CustodyRisk(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class KeyCustodyConfig:
    """Genesis key custody configuration."""
    model: CustodyModel
    custodian_id: str           # Who holds the key
    agent_id: str
    operator_id: str
    # Threshold split params
    threshold_m: int = 0        # M signatures required
    threshold_n: int = 0        # N total key holders
    key_holders: list = field(default_factory=list)
    # Rotation policy
    rotation_interval_days: int = 90   # DKIM: rotate every 90 days
    max_key_age_days: int = 365
    # Recovery
    recovery_method: str = "REANCHOR"  # REANCHOR | ESCROW (escrow = axiom 1 violation)
    # DKIM selector equivalent
    selector: str = "default"


@dataclass
class KeyEvent:
    event_type: str
    timestamp: float
    old_key_hash: Optional[str] = None
    new_key_hash: Optional[str] = None
    authorized_by: list = field(default_factory=list)
    reason: str = ""


def validate_custody_config(config: KeyCustodyConfig) -> dict:
    """Validate key custody configuration against ATF requirements."""
    issues = []
    warnings = []
    risk = CustodyRisk.LOW
    
    # Rule 1: custodian must be identified
    if not config.custodian_id:
        issues.append("MISSING: custodian_id required in genesis")
        risk = CustodyRisk.CRITICAL
    
    # Rule 2: model-specific validation
    if config.model == CustodyModel.OPERATOR_HELD:
        if config.custodian_id == config.agent_id:
            issues.append("OPERATOR_HELD but custodian = agent (self-custody)")
            risk = CustodyRisk.HIGH
        if config.operator_id and config.custodian_id != config.operator_id:
            warnings.append("custodian ≠ operator in OPERATOR_HELD model")
    
    elif config.model == CustodyModel.AGENT_HELD:
        if config.custodian_id != config.agent_id:
            issues.append("AGENT_HELD but custodian ≠ agent")
        warnings.append("AGENT_HELD: key loss = identity loss (no recovery without reanchor)")
        risk = CustodyRisk.MEDIUM
    
    elif config.model == CustodyModel.THRESHOLD_SPLIT:
        if config.threshold_m < 2:
            issues.append(f"threshold_m={config.threshold_m} < 2 (no split)")
            risk = CustodyRisk.HIGH
        if config.threshold_n < config.threshold_m:
            issues.append(f"threshold_n={config.threshold_n} < threshold_m={config.threshold_m}")
            risk = CustodyRisk.CRITICAL
        if config.threshold_n < 3:
            warnings.append("threshold_n < 3: limited fault tolerance")
        if len(config.key_holders) != config.threshold_n:
            issues.append(f"key_holders count ({len(config.key_holders)}) ≠ threshold_n ({config.threshold_n})")
        # Check for operator monoculture in key holders
        unique_holders = set(config.key_holders)
        if len(unique_holders) < config.threshold_m:
            issues.append("MONOCULTURE: fewer unique holders than threshold")
            risk = CustodyRisk.CRITICAL
        # BFT check: can tolerate f < n/3 compromised holders
        max_compromised = (config.threshold_n - 1) // 3
        if max_compromised < 1:
            warnings.append(f"BFT tolerance: 0 compromised holders (n={config.threshold_n})")
    
    # Rule 3: recovery method
    if config.recovery_method == "ESCROW":
        issues.append("ESCROW = trusted third party = axiom 1 violation. Use REANCHOR.")
        risk = CustodyRisk.CRITICAL
    
    # Rule 4: rotation policy
    if config.rotation_interval_days > 365:
        warnings.append(f"rotation interval {config.rotation_interval_days}d > 365d (DKIM best practice: 90d)")
    if config.rotation_interval_days < 7:
        warnings.append(f"rotation interval {config.rotation_interval_days}d < 7d (too frequent)")
    
    # Rule 5: max key age
    if config.max_key_age_days > 730:
        issues.append(f"max key age {config.max_key_age_days}d > 730d (2 year maximum)")
    
    # Grade
    if issues:
        grade = "F" if risk == CustodyRisk.CRITICAL else "D"
    elif warnings:
        grade = "B" if len(warnings) <= 2 else "C"
    else:
        grade = "A"
    
    return {
        "model": config.model.value,
        "custodian": config.custodian_id,
        "grade": grade,
        "risk": risk.value,
        "issues": issues,
        "warnings": warnings,
        "dkim_parallel": _dkim_parallel(config),
    }


def _dkim_parallel(config: KeyCustodyConfig) -> str:
    """Map ATF custody model to DKIM equivalent."""
    parallels = {
        CustodyModel.OPERATOR_HELD: "Gmail/provider DKIM: domain operator holds signing key, manages rotation",
        CustodyModel.AGENT_HELD: "Self-hosted DKIM: domain owner manages own keys via DNS TXT",
        CustodyModel.THRESHOLD_SPLIT: "No DKIM equivalent — DKIM is single-signer. Closest: DNSSEC multi-signer (RFC 8901)",
    }
    return parallels.get(config.model, "unknown")


def validate_key_rotation(events: list, config: KeyCustodyConfig) -> dict:
    """Validate key rotation history against policy."""
    if not events:
        return {"status": "NO_HISTORY", "grade": "C"}
    
    rotations = [e for e in events if e.event_type == "ROTATION"]
    compromises = [e for e in events if e.event_type == "COMPROMISE"]
    reanchors = [e for e in events if e.event_type == "REANCHOR"]
    
    issues = []
    
    # Check rotation frequency
    if len(rotations) >= 2:
        intervals = []
        for i in range(1, len(rotations)):
            gap_days = (rotations[i].timestamp - rotations[i-1].timestamp) / 86400
            intervals.append(gap_days)
            if gap_days > config.max_key_age_days:
                issues.append(f"key age exceeded: {gap_days:.0f}d > {config.max_key_age_days}d")
    
    # Check compromise response time
    for c in compromises:
        next_rotation = None
        for r in rotations + reanchors:
            if r.timestamp > c.timestamp:
                next_rotation = r
                break
        if next_rotation:
            response_hours = (next_rotation.timestamp - c.timestamp) / 3600
            if response_hours > 24:
                issues.append(f"compromise response: {response_hours:.0f}h > 24h")
        else:
            issues.append("COMPROMISE without subsequent rotation/reanchor")
    
    return {
        "total_events": len(events),
        "rotations": len(rotations),
        "compromises": len(compromises),
        "reanchors": len(reanchors),
        "issues": issues,
        "grade": "A" if not issues else ("C" if len(issues) <= 1 else "F"),
    }


# === Scenarios ===

def run_scenarios():
    now = time.time()
    
    # Scenario 1: Operator-held (Gmail model)
    print("=== Scenario 1: Operator-Held (Gmail DKIM model) ===")
    config = KeyCustodyConfig(
        model=CustodyModel.OPERATOR_HELD,
        custodian_id="operator_acme",
        agent_id="kit_fox",
        operator_id="operator_acme",
        rotation_interval_days=90,
        max_key_age_days=365,
    )
    result = validate_custody_config(config)
    print(f"  Grade: {result['grade']} | Risk: {result['risk']}")
    print(f"  DKIM parallel: {result['dkim_parallel']}")
    print(f"  Issues: {result['issues'] or 'none'}")
    print(f"  Warnings: {result['warnings'] or 'none'}")
    print()
    
    # Scenario 2: Agent-held (autonomous)
    print("=== Scenario 2: Agent-Held (Self-hosted DKIM) ===")
    config = KeyCustodyConfig(
        model=CustodyModel.AGENT_HELD,
        custodian_id="kit_fox",
        agent_id="kit_fox",
        operator_id="operator_acme",
        rotation_interval_days=90,
    )
    result = validate_custody_config(config)
    print(f"  Grade: {result['grade']} | Risk: {result['risk']}")
    print(f"  DKIM parallel: {result['dkim_parallel']}")
    print(f"  Warnings: {result['warnings']}")
    print()
    
    # Scenario 3: Threshold split (2-of-3)
    print("=== Scenario 3: Threshold Split 2-of-3 ===")
    config = KeyCustodyConfig(
        model=CustodyModel.THRESHOLD_SPLIT,
        custodian_id="threshold_group",
        agent_id="kit_fox",
        operator_id="operator_acme",
        threshold_m=2,
        threshold_n=3,
        key_holders=["operator_acme", "kit_fox", "witness_1"],
    )
    result = validate_custody_config(config)
    print(f"  Grade: {result['grade']} | Risk: {result['risk']}")
    print(f"  DKIM parallel: {result['dkim_parallel']}")
    print(f"  Warnings: {result['warnings']}")
    print()
    
    # Scenario 4: Escrow (axiom 1 violation)
    print("=== Scenario 4: Key Escrow (AXIOM 1 VIOLATION) ===")
    config = KeyCustodyConfig(
        model=CustodyModel.OPERATOR_HELD,
        custodian_id="escrow_service",
        agent_id="kit_fox",
        operator_id="operator_acme",
        recovery_method="ESCROW",
    )
    result = validate_custody_config(config)
    print(f"  Grade: {result['grade']} | Risk: {result['risk']}")
    print(f"  Issues: {result['issues']}")
    print()
    
    # Scenario 5: Monoculture threshold (fake split)
    print("=== Scenario 5: Monoculture Threshold (Fake Split) ===")
    config = KeyCustodyConfig(
        model=CustodyModel.THRESHOLD_SPLIT,
        custodian_id="threshold_group",
        agent_id="sybil_agent",
        operator_id="operator_shady",
        threshold_m=2,
        threshold_n=3,
        key_holders=["operator_shady", "operator_shady", "sybil_agent"],
    )
    result = validate_custody_config(config)
    print(f"  Grade: {result['grade']} | Risk: {result['risk']}")
    print(f"  Issues: {result['issues']}")
    print()
    
    # Scenario 6: Key rotation history
    print("=== Scenario 6: Key Rotation History ===")
    config = KeyCustodyConfig(
        model=CustodyModel.OPERATOR_HELD,
        custodian_id="operator_acme",
        agent_id="kit_fox",
        operator_id="operator_acme",
        max_key_age_days=365,
    )
    events = [
        KeyEvent("GENESIS", now - 86400*400),
        KeyEvent("ROTATION", now - 86400*300, "old1", "new1", ["operator_acme"]),
        KeyEvent("COMPROMISE", now - 86400*100, reason="key_leak"),
        KeyEvent("REANCHOR", now - 86400*99.5, "new1", "new2", ["operator_acme", "witness_1"]),
        KeyEvent("ROTATION", now - 86400*10, "new2", "new3", ["operator_acme"]),
    ]
    result = validate_key_rotation(events, config)
    print(f"  Grade: {result['grade']}")
    print(f"  Rotations: {result['rotations']}, Compromises: {result['compromises']}, Reanchors: {result['reanchors']}")
    print(f"  Issues: {result['issues'] or 'none'}")
    print()


if __name__ == "__main__":
    print("Key Custody Validator — DKIM Key Management Model for ATF")
    print("Per santaclawd: 'who holds the signing key = who vouches for the agent'")
    print("=" * 70)
    print()
    run_scenarios()
    print("=" * 70)
    print("KEY INSIGHT: key_custodian in genesis = DKIM selector mechanism.")
    print("Three models: OPERATOR_HELD (Gmail), AGENT_HELD (self-hosted), THRESHOLD_SPLIT.")
    print("Recovery = REANCHOR (void + new genesis), NOT escrow (axiom 1 violation).")
    print("Rotation policy: 90d recommended (DKIM best practice), 365d max.")
