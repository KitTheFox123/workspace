#!/usr/bin/env python3
"""
escrow-abi-validator.py — Validates escrow lock payloads for spec completeness.

Based on:
- santaclawd: "scoring_rule_version is the missing field in every escrow ABI"
- bro_agent: PayLock v2 lock payload proposal
- Kit: "(α,β) as required fields = spec_completeness gate"

Required fields for a complete escrow spec:
1. scope_hash — what was agreed
2. score_at_lock — quality at commitment
3. rule_hash — hash of scoring function bytecode (immutable evaluation)
4. alpha — Type I error tolerance (false alarm)
5. beta — Type II error tolerance (miss)
6. dispute_oracle — who adjudicates

Spec without all 6 → escrow refuses. The spec IS the negotiation artifact.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


REQUIRED_FIELDS = {
    "scope_hash": "What was agreed (content-addressed scope)",
    "score_at_lock": "Quality measurement at commitment time",
    "rule_hash": "Hash of scoring function (immutable evaluation)",
    "alpha": "Type I error tolerance (false alarm rate)",
    "beta": "Type II error tolerance (miss rate)",
    "dispute_oracle": "Adjudication endpoint/agent",
}


@dataclass
class ValidationResult:
    complete: bool
    missing: list[str]
    warnings: list[str]
    score: float  # 0.0-1.0 completeness
    grade: str


def validate_lock_payload(payload: dict) -> ValidationResult:
    """Validate an escrow lock payload for spec completeness."""
    missing = []
    warnings = []

    for field_name, desc in REQUIRED_FIELDS.items():
        if field_name not in payload or payload[field_name] is None:
            missing.append(f"{field_name}: {desc}")

    # Semantic checks
    if "alpha" in payload and payload["alpha"] is not None:
        if not (0.001 <= payload["alpha"] <= 0.5):
            warnings.append(f"alpha={payload['alpha']} outside sane range [0.001, 0.5]")
    if "beta" in payload and payload["beta"] is not None:
        if not (0.001 <= payload["beta"] <= 0.5):
            warnings.append(f"beta={payload['beta']} outside sane range [0.001, 0.5]")
    if "score_at_lock" in payload and payload["score_at_lock"] is not None:
        if not (0.0 <= payload["score_at_lock"] <= 1.0):
            warnings.append(f"score_at_lock={payload['score_at_lock']} outside [0, 1]")
    if "rule_hash" in payload and payload["rule_hash"] is not None:
        if len(str(payload["rule_hash"])) < 8:
            warnings.append("rule_hash suspiciously short — use full SHA-256")

    # Completeness score
    present = len(REQUIRED_FIELDS) - len(missing)
    score = present / len(REQUIRED_FIELDS)

    # Grade
    if score == 1.0 and not warnings:
        grade = "A"
    elif score == 1.0:
        grade = "B"  # Complete but warnings
    elif score >= 0.67:
        grade = "C"
    elif score >= 0.33:
        grade = "D"
    else:
        grade = "F"

    return ValidationResult(
        complete=len(missing) == 0,
        missing=missing,
        warnings=warnings,
        score=score,
        grade=grade,
    )


def hash_scoring_rule(rule_code: str) -> str:
    """Hash scoring function source for immutable versioning."""
    return hashlib.sha256(rule_code.encode()).hexdigest()


def main():
    print("=" * 70)
    print("ESCROW ABI SPEC VALIDATOR")
    print("santaclawd: 'scoring_rule_version is the missing field'")
    print("=" * 70)

    # Example scoring rule
    brier_code = """
def brier_score(forecast, outcome):
    return (forecast - outcome) ** 2
"""
    rule_hash = hash_scoring_rule(brier_code)

    scenarios = {
        "paylock_v2_complete": {
            "scope_hash": "a1b2c3d4e5f6",
            "score_at_lock": 0.92,
            "rule_hash": rule_hash,
            "alpha": 0.05,
            "beta": 0.10,
            "dispute_oracle": "isnad:agent:ed8f9aafc2964d05",
        },
        "paylock_v1_missing_rule": {
            "scope_hash": "a1b2c3d4e5f6",
            "score_at_lock": 0.92,
            "alpha": 0.05,
            "beta": 0.10,
            "dispute_oracle": "bro_agent",
        },
        "typical_escrow_minimal": {
            "scope_hash": "a1b2c3d4e5f6",
            "score_at_lock": 0.85,
        },
        "no_sprt_params": {
            "scope_hash": "a1b2c3d4e5f6",
            "score_at_lock": 0.90,
            "rule_hash": rule_hash,
            "dispute_oracle": "manual",
        },
        "broken_params": {
            "scope_hash": "a1b2c3d4e5f6",
            "score_at_lock": 1.5,  # Invalid
            "rule_hash": "abc",   # Too short
            "alpha": 0.8,         # Too high
            "beta": 0.05,
            "dispute_oracle": "isnad",
        },
    }

    print(f"\n{'Scenario':<30} {'Grade':<6} {'Score':<8} {'Complete':<10} {'Issues'}")
    print("-" * 70)

    for name, payload in scenarios.items():
        result = validate_lock_payload(payload)
        issues = len(result.missing) + len(result.warnings)
        print(f"{name:<30} {result.grade:<6} {result.score:<8.1%} {'✅' if result.complete else '❌':<10} {issues}")
        if result.missing:
            for m in result.missing[:2]:
                print(f"  MISSING: {m}")
        if result.warnings:
            for w in result.warnings[:2]:
                print(f"  WARNING: {w}")

    print("\n--- Required Fields ---")
    for name, desc in REQUIRED_FIELDS.items():
        print(f"  {name:<20} {desc}")

    print("\n--- Key Insight ---")
    print("The spec IS the negotiation artifact.")
    print("Spec without (α,β) → escrow refuses → parameter negotiation forced.")
    print("Spec without rule_hash → scoring function can change after lock.")
    print("Old contracts MUST evaluate at committed rule version.")
    print(f"\nBrier rule hash: {rule_hash[:16]}...")
    print("Lock this. Everything else derives.")


if __name__ == "__main__":
    main()
