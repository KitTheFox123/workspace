#!/usr/bin/env python3
"""
atf-constants-v1.1.py — ATF V1.1 normative constants registry.

Per santaclawd: impl-defined constants = silent fragmentation.
V1.1 pins ALL spec-critical values as SPEC_CONSTANT.

Design principle: agents can be STRICTER, never LOOSER.
Like TLS: minimum version is spec-defined, implementation
can require higher.

Three tiers:
  SPEC_CONSTANT — normative, MUST match across implementations
  SPEC_DEFAULT  — normative default, MAY override STRICTER only
  IMPL_DEFINED  — implementation choice (minimized in V1.1)

Usage:
    python3 atf-constants-v1.1.py
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum


class ConstantTier(str, Enum):
    SPEC_CONSTANT = "SPEC_CONSTANT"  # Normative, immutable
    SPEC_DEFAULT = "SPEC_DEFAULT"    # Normative default, override stricter only
    IMPL_DEFINED = "IMPL_DEFINED"    # Implementation choice


class ConstantDomain(str, Enum):
    TIMING = "timing"
    STATISTICAL = "statistical"
    QUORUM = "quorum"
    GOVERNANCE = "governance"
    BOOTSTRAP = "bootstrap"
    DRIFT = "drift"
    MIGRATION = "migration"
    CHAIN = "chain"


@dataclass
class ATFConstant:
    name: str
    value: Any
    tier: ConstantTier
    domain: ConstantDomain
    unit: str
    rationale: str
    stricter_direction: str  # "lower" or "higher" — which way is stricter
    min_bound: Optional[Any] = None  # absolute minimum (even for impl overrides)
    max_bound: Optional[Any] = None  # absolute maximum


# V1.1 Normative Constants
ATF_V1_1_CONSTANTS = [
    # === TIMING ===
    ATFConstant(
        name="MIGRATION_WINDOW_DEFAULT",
        value=72,  # hours
        tier=ConstantTier.SPEC_DEFAULT,
        domain=ConstantDomain.MIGRATION,
        unit="hours",
        rationale="Key migration overlap window. DNS TTL parallel. 72h = 3 days for counterparty discovery.",
        stricter_direction="lower",
        min_bound=24,
        max_bound=168,
    ),
    ATFConstant(
        name="MIGRATION_WINDOW_FLOOR",
        value=24,  # hours
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.MIGRATION,
        unit="hours",
        rationale="Absolute minimum migration window. Below this, counterparties can't discover the change.",
        stricter_direction="lower",
    ),
    ATFConstant(
        name="DEGRADED_QUORUM_REEMIT_INTERVAL",
        value=12,  # hours
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.QUORUM,
        unit="hours",
        rationale="DEGRADED_QUORUM state re-emits at this interval. Liveness proof.",
        stricter_direction="lower",
        min_bound=1,
    ),
    ATFConstant(
        name="CONTESTED_REEMIT_INTERVAL",
        value=6,  # hours
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.QUORUM,
        unit="hours",
        rationale="CONTESTED state re-emits more frequently. Urgency signal.",
        stricter_direction="lower",
        min_bound=1,
    ),
    ATFConstant(
        name="BOOTSTRAP_TIMEOUT",
        value=168,  # hours (7 days)
        tier=ConstantTier.SPEC_DEFAULT,
        domain=ConstantDomain.BOOTSTRAP,
        unit="hours",
        rationale="Max time in BOOTSTRAP state before fallback to MANUAL. 7 days.",
        stricter_direction="lower",
        min_bound=24,
        max_bound=720,
    ),
    ATFConstant(
        name="DECAY_HALFLIFE",
        value=30,  # days
        tier=ConstantTier.SPEC_DEFAULT,
        domain=ConstantDomain.DRIFT,
        unit="days",
        rationale="Trust score exponential decay half-life. 30 days = monthly recalibration.",
        stricter_direction="lower",
        min_bound=7,
        max_bound=90,
    ),

    # === STATISTICAL ===
    ATFConstant(
        name="KS_REJECT_THRESHOLD",
        value=0.05,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.STATISTICAL,
        unit="p-value",
        rationale="KS test: p < 0.05 = REJECT (receipt pattern is non-random). Standard significance.",
        stricter_direction="lower",
    ),
    ATFConstant(
        name="KS_PASS_THRESHOLD",
        value=0.30,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.STATISTICAL,
        unit="p-value",
        rationale="KS test: p > 0.30 = PASS. Gap between 0.05-0.30 = INCONCLUSIVE.",
        stricter_direction="higher",
    ),
    ATFConstant(
        name="KS_MIN_SAMPLE_SIZE",
        value=10,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.STATISTICAL,
        unit="receipts",
        rationale="Minimum receipts before KS test applies. Below this, low-n noise > gaming signal. Use Wilson CI instead.",
        stricter_direction="higher",
    ),
    ATFConstant(
        name="JS_DIVERGENCE_FLOOR",
        value=0.30,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.DRIFT,
        unit="JS divergence",
        rationale="Jensen-Shannon divergence floor for OP_DRIFT detection. ≥0.30 = RECOMMENDED minimum.",
        stricter_direction="lower",
    ),
    ATFConstant(
        name="CORRECTION_RANGE_MIN",
        value=0.05,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.DRIFT,
        unit="ratio",
        rationale="Healthy correction frequency minimum. Below = never self-correcting.",
        stricter_direction="higher",
    ),
    ATFConstant(
        name="CORRECTION_RANGE_MAX",
        value=0.40,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.DRIFT,
        unit="ratio",
        rationale="Healthy correction frequency maximum. Above = chronically unreliable.",
        stricter_direction="lower",
    ),

    # === QUORUM ===
    ATFConstant(
        name="MIN_COUNTERPARTIES",
        value=3,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.QUORUM,
        unit="agents",
        rationale="Minimum counterparties for meaningful trust aggregation. Below = MIN() only.",
        stricter_direction="higher",
    ),
    ATFConstant(
        name="BFT_FAULT_FRACTION",
        value=1/3,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.QUORUM,
        unit="fraction",
        rationale="Byzantine fault tolerance: f < n/3. Standard BFT bound.",
        stricter_direction="lower",
    ),
    ATFConstant(
        name="SYBIL_OPERATOR_DISCOUNT",
        value=1,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.QUORUM,
        unit="effective_count",
        rationale="Multiple agents from same operator count as 1 effective witness.",
        stricter_direction="lower",
    ),

    # === GOVERNANCE ===
    ATFConstant(
        name="ATF_MUST_FIELDS",
        value=14,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.GOVERNANCE,
        unit="fields",
        rationale="Number of MUST fields in ATF-core. 14 including anchor_type.",
        stricter_direction="higher",
    ),
    ATFConstant(
        name="BASE_ERROR_TYPES",
        value=7,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.GOVERNANCE,
        unit="types",
        rationale="Core error type enum. Frozen. Extensions via ext: prefix.",
        stricter_direction="higher",
    ),
    ATFConstant(
        name="CEREMONY_HASH_REQUIRED",
        value=True,
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.BOOTSTRAP,
        unit="boolean",
        rationale="Per santaclawd: ceremony_hash MUST be in genesis record. Transparent bootstrap.",
        stricter_direction="higher",
    ),

    # === CHAIN ===
    ATFConstant(
        name="MAX_CHAIN_LENGTH",
        value=10,
        tier=ConstantTier.SPEC_DEFAULT,
        domain=ConstantDomain.CHAIN,
        unit="hops",
        rationale="Maximum delegation chain length. ARC parallel: chains > 10 = suspicious.",
        stricter_direction="lower",
        min_bound=3,
        max_bound=20,
    ),
    ATFConstant(
        name="CHAIN_GRADE_FUNCTION",
        value="MIN",
        tier=ConstantTier.SPEC_CONSTANT,
        domain=ConstantDomain.CHAIN,
        unit="function",
        rationale="Chain trust grade = MIN(all hops). Like ARC cv=fail propagation.",
        stricter_direction="lower",
    ),
]


def validate_override(constant: ATFConstant, proposed_value: Any) -> dict:
    """Check if an implementation's proposed override is valid."""
    if constant.tier == ConstantTier.SPEC_CONSTANT:
        return {
            "valid": proposed_value == constant.value,
            "reason": "SPEC_CONSTANT: cannot override" if proposed_value != constant.value else "matches spec",
            "severity": "REJECT" if proposed_value != constant.value else "OK",
        }

    if constant.tier == ConstantTier.IMPL_DEFINED:
        return {"valid": True, "reason": "IMPL_DEFINED: any value accepted", "severity": "OK"}

    # SPEC_DEFAULT: check stricter direction
    if constant.stricter_direction == "lower":
        is_stricter = proposed_value <= constant.value
    else:
        is_stricter = proposed_value >= constant.value

    # Check bounds
    if constant.min_bound is not None and proposed_value < constant.min_bound:
        return {"valid": False, "reason": f"below absolute minimum {constant.min_bound}", "severity": "REJECT"}
    if constant.max_bound is not None and proposed_value > constant.max_bound:
        return {"valid": False, "reason": f"above absolute maximum {constant.max_bound}", "severity": "REJECT"}

    if not is_stricter:
        return {
            "valid": False,
            "reason": f"SPEC_DEFAULT: override must be stricter ({constant.stricter_direction}). Got {proposed_value}, spec={constant.value}",
            "severity": "REJECT",
        }

    return {"valid": True, "reason": f"stricter override accepted ({proposed_value} vs spec {constant.value})", "severity": "OK"}


def registry_hash(constants: list[ATFConstant]) -> str:
    """Deterministic hash of all constants for versioning."""
    canonical = "|".join(
        f"{c.name}={c.value}:{c.tier.value}"
        for c in sorted(constants, key=lambda x: x.name)
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def demo():
    print("=" * 60)
    print("ATF V1.1 Constants Registry")
    print("=" * 60)

    reg_hash = registry_hash(ATF_V1_1_CONSTANTS)
    print(f"\nRegistry hash: {reg_hash}")
    print(f"Total constants: {len(ATF_V1_1_CONSTANTS)}")

    # Tier breakdown
    by_tier = {}
    for c in ATF_V1_1_CONSTANTS:
        by_tier.setdefault(c.tier.value, []).append(c.name)
    print("\nBy tier:")
    for tier, names in sorted(by_tier.items()):
        print(f"  {tier}: {len(names)}")

    # Domain breakdown
    by_domain = {}
    for c in ATF_V1_1_CONSTANTS:
        by_domain.setdefault(c.domain.value, []).append(c.name)
    print("\nBy domain:")
    for domain, names in sorted(by_domain.items()):
        print(f"  {domain}: {len(names)}")

    # Override validation scenarios
    print("\n--- Override Validation ---")
    scenarios = [
        ("MIGRATION_WINDOW_DEFAULT", 48, "stricter (48h < 72h)"),
        ("MIGRATION_WINDOW_DEFAULT", 96, "looser (96h > 72h)"),
        ("MIGRATION_WINDOW_DEFAULT", 12, "below floor (12h < 24h)"),
        ("KS_REJECT_THRESHOLD", 0.01, "attempt to change SPEC_CONSTANT"),
        ("KS_MIN_SAMPLE_SIZE", 15, "stricter (15 > 10)"),
        ("KS_MIN_SAMPLE_SIZE", 5, "looser (5 < 10)"),
        ("DECAY_HALFLIFE", 14, "stricter (14d < 30d)"),
        ("DECAY_HALFLIFE", 5, "below min bound (5d < 7d)"),
    ]

    const_map = {c.name: c for c in ATF_V1_1_CONSTANTS}
    for name, value, desc in scenarios:
        result = validate_override(const_map[name], value)
        status = "✅" if result["valid"] else "❌"
        print(f"  {status} {name}={value} ({desc}): {result['reason']}")

    # Fragmentation check
    print("\n--- Fragmentation Analysis ---")
    spec_const = len([c for c in ATF_V1_1_CONSTANTS if c.tier == ConstantTier.SPEC_CONSTANT])
    spec_default = len([c for c in ATF_V1_1_CONSTANTS if c.tier == ConstantTier.SPEC_DEFAULT])
    impl_defined = len([c for c in ATF_V1_1_CONSTANTS if c.tier == ConstantTier.IMPL_DEFINED])
    total = len(ATF_V1_1_CONSTANTS)

    interop_score = (spec_const + spec_default * 0.8) / total
    print(f"  SPEC_CONSTANT: {spec_const}/{total} ({spec_const/total:.0%})")
    print(f"  SPEC_DEFAULT:  {spec_default}/{total} ({spec_default/total:.0%})")
    print(f"  IMPL_DEFINED:  {impl_defined}/{total} ({impl_defined/total:.0%})")
    print(f"  Interop score: {interop_score:.2f}")
    print(f"  Fragmentation risk: {'LOW' if interop_score > 0.8 else 'MEDIUM' if interop_score > 0.6 else 'HIGH'}")

    print(f"\n{'=' * 60}")
    print("V1.1: {impl_defined} impl-defined constants (down from V1.0).")
    print("Agents can be STRICTER, never LOOSER. TLS minimum version model.")
    print(f"Registry hash: {reg_hash}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
