#!/usr/bin/env python3
"""
paylock-v2-abi-validator.py — Validates PayLock v2 ABI contracts.

Based on santaclawd's locked spec (2026-03-03):
{scope_hash, score_at_lock, rule_hash, rule_label, alpha, beta, dispute_oracle}

Seven fields. Six load-bearing + rule_label as metadata.
- rule_hash = CID(multihash(JCS(bytecode))) — RFC 8785 canonical serialization
- commit-reveal for (α,β): hash(α,β,nonce) → reveal → Nash product → lock
- Post-lock: frozen. No renegotiation.

Validates: field presence, type constraints, PAC bounds, oracle independence.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class PayLockV2Contract:
    scope_hash: str          # SHA-256 of scope definition
    score_at_lock: float     # Score when contract locked
    rule_hash: str           # CID(multihash(JCS(bytecode)))
    rule_label: str          # Human-readable annotation (NOT load-bearing)
    alpha: float             # Type I error (false alarm)
    beta: float              # Type II error (miss)
    dispute_oracle: str      # Oracle identifier or set


@dataclass
class ValidationResult:
    field: str
    valid: bool
    severity: str  # "error", "warning", "info"
    message: str


def validate_contract(contract: PayLockV2Contract) -> list[ValidationResult]:
    results = []

    # 1. scope_hash: must be valid hex, 64 chars (SHA-256)
    if len(contract.scope_hash) == 64 and all(c in '0123456789abcdef' for c in contract.scope_hash):
        results.append(ValidationResult("scope_hash", True, "info", "Valid SHA-256"))
    else:
        results.append(ValidationResult("scope_hash", False, "error", "Invalid SHA-256 hash"))

    # 2. score_at_lock: must be in [0, 1]
    if 0.0 <= contract.score_at_lock <= 1.0:
        results.append(ValidationResult("score_at_lock", True, "info", f"Score {contract.score_at_lock:.3f}"))
    else:
        results.append(ValidationResult("score_at_lock", False, "error", f"Score {contract.score_at_lock} out of [0,1]"))

    # 3. rule_hash: should look like a CID or multihash
    if len(contract.rule_hash) >= 16:
        results.append(ValidationResult("rule_hash", True, "info", "Rule hash present"))
    else:
        results.append(ValidationResult("rule_hash", False, "error", "Rule hash too short"))

    # 4. rule_label: informational only, warn if empty
    if contract.rule_label:
        results.append(ValidationResult("rule_label", True, "info", f"Label: {contract.rule_label}"))
    else:
        results.append(ValidationResult("rule_label", True, "warning", "No human-readable label"))

    # 5. alpha: Type I error rate
    if 0.001 <= contract.alpha <= 0.20:
        results.append(ValidationResult("alpha", True, "info", f"α={contract.alpha}"))
    elif contract.alpha > 0.20:
        results.append(ValidationResult("alpha", False, "warning", f"α={contract.alpha} very lenient (>0.20)"))
    else:
        results.append(ValidationResult("alpha", False, "error", f"α={contract.alpha} invalid"))

    # 6. beta: Type II error rate
    if 0.001 <= contract.beta <= 0.30:
        results.append(ValidationResult("beta", True, "info", f"β={contract.beta}"))
    elif contract.beta > 0.30:
        results.append(ValidationResult("beta", False, "warning", f"β={contract.beta} very lenient (>0.30)"))
    else:
        results.append(ValidationResult("beta", False, "error", f"β={contract.beta} invalid"))

    # 7. PAC bound check: expected samples at these (α,β)
    try:
        n_samples = math.ceil((1 / (2 * contract.alpha**2)) * math.log(2 / contract.beta))
        if n_samples > 10000:
            results.append(ValidationResult("pac_bound", True, "warning",
                f"E[N]={n_samples} — very tight bounds, slow detection"))
        else:
            results.append(ValidationResult("pac_bound", True, "info", f"E[N]≈{n_samples} samples"))
    except (ValueError, ZeroDivisionError):
        results.append(ValidationResult("pac_bound", False, "error", "Cannot compute PAC bound"))

    # 8. SPRT boundaries
    try:
        A = math.log((1 - contract.beta) / contract.alpha)
        B = math.log(contract.beta / (1 - contract.alpha))
        width = A - B
        if width < 1.0:
            results.append(ValidationResult("sprt_bounds", True, "warning",
                f"SPRT width={width:.2f} — narrow, fast but noisy"))
        else:
            results.append(ValidationResult("sprt_bounds", True, "info",
                f"SPRT bounds=[{B:.2f}, {A:.2f}], width={width:.2f}"))
    except (ValueError, ZeroDivisionError):
        results.append(ValidationResult("sprt_bounds", False, "error", "Invalid SPRT boundaries"))

    # 9. dispute_oracle: warn if single oracle
    if "," in contract.dispute_oracle or "+" in contract.dispute_oracle:
        results.append(ValidationResult("dispute_oracle", True, "info", "Multiple oracles specified"))
    else:
        results.append(ValidationResult("dispute_oracle", True, "warning",
            "Single oracle — effective_N=1. TC4 showed N_eff=1.14 for same-substrate"))

    return results


def grade_contract(results: list[ValidationResult]) -> str:
    errors = sum(1 for r in results if not r.valid and r.severity == "error")
    warnings = sum(1 for r in results if r.severity == "warning")
    if errors > 0: return "F"
    if warnings >= 3: return "C"
    if warnings >= 1: return "B"
    return "A"


def main():
    print("=" * 70)
    print("PAYLOCK V2 ABI VALIDATOR")
    print("santaclawd spec (2026-03-03): 7 fields, 6 load-bearing")
    print("=" * 70)

    # Example contracts
    contracts = {
        "tc4_kit_bro": PayLockV2Contract(
            scope_hash=hashlib.sha256(b"What Does the Agent Economy Need at Scale?").hexdigest(),
            score_at_lock=0.92,
            rule_hash="bafkreigh7c2f5e8d1a3b6c9d0e2f4a5b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1",
            rule_label="brier_decomposition_v1",
            alpha=0.05,
            beta=0.10,
            dispute_oracle="bro_agent+kit_fox",
        ),
        "lenient_seller": PayLockV2Contract(
            scope_hash=hashlib.sha256(b"Quick delivery task").hexdigest(),
            score_at_lock=0.75,
            rule_hash="bafkreigh7c2f5e8d1a3b6c9",
            rule_label="",
            alpha=0.15,
            beta=0.25,
            dispute_oracle="single_llm",
        ),
        "tight_buyer": PayLockV2Contract(
            scope_hash=hashlib.sha256(b"High-stakes NIST submission").hexdigest(),
            score_at_lock=0.95,
            rule_hash="bafkreigh7c2f5e8d1a3b6c9d0e2f4a5b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2",
            rule_label="nist_caisi_scoring",
            alpha=0.01,
            beta=0.05,
            dispute_oracle="kit_fox+gerundium+isnad",
        ),
        "invalid_contract": PayLockV2Contract(
            scope_hash="not_a_hash",
            score_at_lock=1.5,
            rule_hash="short",
            rule_label="broken",
            alpha=0.0,
            beta=-0.1,
            dispute_oracle="self",
        ),
    }

    for name, contract in contracts.items():
        results = validate_contract(contract)
        grade = grade_contract(results)
        errors = [r for r in results if not r.valid or r.severity == "warning"]
        print(f"\n--- {name} (Grade: {grade}) ---")
        for r in results:
            icon = "✅" if r.valid and r.severity != "warning" else "⚠️" if r.severity == "warning" else "❌"
            print(f"  {icon} {r.field}: {r.message}")

    print("\n--- ABI Spec Summary ---")
    print("Field           Load-bearing  Type")
    print("-" * 45)
    fields = [
        ("scope_hash", True, "SHA-256 hex"),
        ("score_at_lock", True, "float [0,1]"),
        ("rule_hash", True, "CID(JCS(bytecode))"),
        ("rule_label", False, "string (metadata)"),
        ("alpha", True, "float (0,0.5)"),
        ("beta", True, "float (0,0.5)"),
        ("dispute_oracle", True, "oracle_id or set"),
    ]
    for name, lb, typ in fields:
        print(f"  {name:<16} {'YES' if lb else 'no':<14} {typ}")

    print("\n--- Lock Sequence ---")
    print("1. Negotiate offline (scope, scoring rule)")
    print("2. Commit-reveal (α,β): hash(α,β,nonce) → reveal → Nash product")
    print("3. Lock ABI: all 7 fields frozen")
    print("4. Execute: work performed within scope")
    print("5. Score: rule_hash bytecode evaluates delivery")
    print("6. Settle or dispute: oracle(s) adjudicate if score < threshold")


if __name__ == "__main__":
    main()
