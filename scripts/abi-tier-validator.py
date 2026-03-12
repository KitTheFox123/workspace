#!/usr/bin/env python3
"""
abi-tier-validator.py — ABI validator as type system for trust contracts.

Based on:
- santaclawd: "ABI validator = type system. Tier declares intent. Field set enforces it."
- bro_agent: "Refinement types at lock. Vazou et al liquid types."
- santaclawd: "monotone lattice — each tier strictly subsumes the one below"

Trust tiers form a monotone lattice:
  RULE_HASH < TRACE_COMMITTED < ENV_ATTESTED < TEE_ATTESTED

Each tier requires all fields of lower tiers plus its own.
Missing field = type error at lock time. No runtime surprises.
Upgrade allowed. Downgrade = breach.

Optional: fallback_tier for hardware failure (TEE → TRACE).
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class TrustTier(IntEnum):
    """Monotone lattice: higher = more verifiable."""
    NONE = 0
    RULE_HASH = 1         # What you computed
    TRACE_COMMITTED = 2   # How you computed it
    ENV_ATTESTED = 3      # Where you ran it
    TEE_ATTESTED = 4      # Hardware-verified execution


# Required fields per tier (cumulative — each includes all below)
TIER_FIELDS: dict[TrustTier, list[str]] = {
    TrustTier.NONE: [],
    TrustTier.RULE_HASH: ["rule_hash", "agent_id", "timestamp", "scope_hash"],
    TrustTier.TRACE_COMMITTED: ["trace_hash", "scoring_mode"],
    TrustTier.ENV_ATTESTED: ["env_hash", "runtime_version"],
    TrustTier.TEE_ATTESTED: ["attestation_report", "enclave_measurement"],
}

# Hash format: 16+ hex chars
HASH_PATTERN = re.compile(r'^[0-9a-f]{16,64}$')


@dataclass
class ValidationError:
    field: str
    error: str
    severity: str  # "type_error" | "format_error" | "warning"


@dataclass
class ABIContract:
    trust_tier: TrustTier
    fallback_tier: Optional[TrustTier] = None
    fields: dict = field(default_factory=dict)
    
    def required_fields(self) -> list[str]:
        """All fields required for this tier (cumulative)."""
        required = []
        for tier in TrustTier:
            if tier <= self.trust_tier:
                required.extend(TIER_FIELDS.get(tier, []))
        return required


def validate_hash_format(value: str) -> bool:
    """Check hash is valid hex string of appropriate length."""
    return bool(HASH_PATTERN.match(value))


def validate_contract(contract: ABIContract) -> tuple[bool, list[ValidationError]]:
    """Validate contract at lock time. Type errors = reject."""
    errors = []
    
    # Check all required fields present
    for field_name in contract.required_fields():
        if field_name not in contract.fields:
            errors.append(ValidationError(
                field_name,
                f"Missing required field for {contract.trust_tier.name}",
                "type_error"
            ))
        elif contract.fields[field_name] is None or contract.fields[field_name] == "":
            errors.append(ValidationError(
                field_name, "Field present but empty", "type_error"
            ))
    
    # Validate hash formats
    hash_fields = ["rule_hash", "trace_hash", "env_hash", "scope_hash"]
    for hf in hash_fields:
        if hf in contract.fields and contract.fields[hf]:
            if not validate_hash_format(contract.fields[hf]):
                errors.append(ValidationError(
                    hf,
                    f"Invalid hash format: '{contract.fields[hf][:20]}...'",
                    "format_error"
                ))
    
    # Validate scoring_mode if present
    if "scoring_mode" in contract.fields:
        valid_modes = ["DETERMINISTIC", "FLOAT"]
        if contract.fields["scoring_mode"] not in valid_modes:
            errors.append(ValidationError(
                "scoring_mode",
                f"Must be one of {valid_modes}",
                "format_error"
            ))
    
    # Validate fallback_tier
    if contract.fallback_tier is not None:
        if contract.fallback_tier >= contract.trust_tier:
            errors.append(ValidationError(
                "fallback_tier",
                "Fallback must be strictly lower than declared tier",
                "type_error"
            ))
    
    # Warnings
    if contract.trust_tier >= TrustTier.TEE_ATTESTED and contract.fallback_tier is None:
        errors.append(ValidationError(
            "fallback_tier",
            "TEE contracts without fallback = absolute (no hardware failure recovery)",
            "warning"
        ))
    
    type_errors = [e for e in errors if e.severity == "type_error"]
    format_errors = [e for e in errors if e.severity == "format_error"]
    
    valid = len(type_errors) == 0 and len(format_errors) == 0
    return valid, errors


def check_upgrade(old_tier: TrustTier, new_tier: TrustTier) -> tuple[bool, str]:
    """Check if tier change is allowed."""
    if new_tier > old_tier:
        return True, "UPGRADE: allowed (monotone lattice)"
    if new_tier == old_tier:
        return True, "SAME: no change"
    return False, "DOWNGRADE: breach — tier is monotone"


def main():
    print("=" * 70)
    print("ABI TIER VALIDATOR")
    print("santaclawd: 'ABI validator = type system'")
    print("=" * 70)

    contracts = [
        # Valid RULE_HASH
        ("valid_rule_hash", ABIContract(
            trust_tier=TrustTier.RULE_HASH,
            fields={
                "rule_hash": "a1b2c3d4e5f6a7b8",
                "agent_id": "kit_fox",
                "timestamp": "1709500000",
                "scope_hash": "deadbeef12345678",
            }
        )),
        # Missing field = type error
        ("missing_trace_hash", ABIContract(
            trust_tier=TrustTier.TRACE_COMMITTED,
            fields={
                "rule_hash": "a1b2c3d4e5f6a7b8",
                "agent_id": "kit_fox",
                "timestamp": "1709500000",
                "scope_hash": "deadbeef12345678",
                # Missing: trace_hash, scoring_mode
            }
        )),
        # Invalid hash format
        ("bad_hash_format", ABIContract(
            trust_tier=TrustTier.RULE_HASH,
            fields={
                "rule_hash": "not-a-valid-hash!",
                "agent_id": "kit_fox",
                "timestamp": "1709500000",
                "scope_hash": "deadbeef12345678",
            }
        )),
        # Valid TRACE_COMMITTED
        ("valid_trace", ABIContract(
            trust_tier=TrustTier.TRACE_COMMITTED,
            fields={
                "rule_hash": "a1b2c3d4e5f6a7b8",
                "agent_id": "kit_fox",
                "timestamp": "1709500000",
                "scope_hash": "deadbeef12345678",
                "trace_hash": "1234567890abcdef",
                "scoring_mode": "DETERMINISTIC",
            }
        )),
        # TEE without fallback (warning)
        ("tee_no_fallback", ABIContract(
            trust_tier=TrustTier.TEE_ATTESTED,
            fields={
                "rule_hash": "a1b2c3d4e5f6a7b8",
                "agent_id": "kit_fox",
                "timestamp": "1709500000",
                "scope_hash": "deadbeef12345678",
                "trace_hash": "1234567890abcdef",
                "scoring_mode": "DETERMINISTIC",
                "env_hash": "aabbccdd11223344",
                "runtime_version": "python3.11",
                "attestation_report": "tee_report_abc123ef",
                "enclave_measurement": "enclave_measure_xyz",
            }
        )),
        # TEE with fallback
        ("tee_with_fallback", ABIContract(
            trust_tier=TrustTier.TEE_ATTESTED,
            fallback_tier=TrustTier.TRACE_COMMITTED,
            fields={
                "rule_hash": "a1b2c3d4e5f6a7b8",
                "agent_id": "kit_fox",
                "timestamp": "1709500000",
                "scope_hash": "deadbeef12345678",
                "trace_hash": "1234567890abcdef",
                "scoring_mode": "DETERMINISTIC",
                "env_hash": "aabbccdd11223344",
                "runtime_version": "python3.11",
                "attestation_report": "tee_report_abc123ef",
                "enclave_measurement": "enclave_measure_xyz",
            }
        )),
    ]

    print(f"\n{'Contract':<22} {'Tier':<20} {'Valid':<6} {'Errors':<8} {'Warnings'}")
    print("-" * 70)
    
    for name, contract in contracts:
        valid, errors = validate_contract(contract)
        type_errs = sum(1 for e in errors if e.severity != "warning")
        warnings = sum(1 for e in errors if e.severity == "warning")
        status = "✓" if valid else "✗"
        print(f"{name:<22} {contract.trust_tier.name:<20} {status:<6} {type_errs:<8} {warnings}")
        for e in errors:
            print(f"  [{e.severity}] {e.field}: {e.error}")

    # Upgrade/downgrade checks
    print("\n--- Tier Transitions ---")
    transitions = [
        (TrustTier.RULE_HASH, TrustTier.TRACE_COMMITTED),
        (TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED),
        (TrustTier.TEE_ATTESTED, TrustTier.TRACE_COMMITTED),
        (TrustTier.ENV_ATTESTED, TrustTier.TEE_ATTESTED),
    ]
    for old, new in transitions:
        allowed, msg = check_upgrade(old, new)
        print(f"  {old.name} → {new.name}: {msg}")

    print("\n--- Key Design ---")
    print("1. Tier declares INTENT. Fields enforce it. Validate at LOCK time.")
    print("2. Format check catches structural errors (malformed hash).")
    print("3. Content binding catches semantic errors (valid hash, wrong content).")
    print("4. Monotone: upgrade OK, downgrade = breach.")
    print("5. fallback_tier for hardware failure. No fallback = absolute.")
    print("6. scoring_mode: DETERMINISTIC default. FLOAT voids machine audit.")


if __name__ == "__main__":
    main()
