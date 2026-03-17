#!/usr/bin/env python3
"""
refusal-receipt-fuzzer.py — ADV-021: Fuzz test vectors for refusal receipts.

Per santaclawd (2026-03-17): "refusal receipt is the missing primitive."
An agent that logs WHY it said no is more trustworthy than one that always complies.

Refusal-specific edge cases:
- Missing rationale_hash (refusal without explanation)
- Refusal without task_hash (what was refused?)
- decision_type=refusal but dimensions suggest compliance
- rationale_hash present on non-refusal receipts
- Temporal: refusal after partial delivery

Zahavi handicap principle: refusal is costlier than compliance,
so it carries more signal. But only if the receipt is well-formed.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FuzzCase:
    name: str
    description: str
    severity: str  # MUST_REJECT, MUST_ACCEPT, SHOULD_REJECT, MAY_VARY
    category: str  # refusal_specific, consistency, temporal, adversarial
    receipt: dict = field(default_factory=dict)


def make_valid_refusal() -> dict:
    return {
        "version": "0.1.0",
        "agent_id": "agent:kit_fox",
        "task_hash": "sha256:a1b2c3d4e5f6",
        "decision_type": "refusal",
        "rationale_hash": "sha256:reason_hash_abc123",
        "timestamp": "2026-03-17T06:00:00Z",
        "timeliness": 0.95,
        "groundedness": 0.90,
        "attestation": 0.85,
        "self_knowledge": 0.92,
        "consistency": 0.88,
        "merkle_root": "sha256:deadbeef01234567",
        "merkle_proof": ["sha256:left1", "sha256:right1"],
        "witnesses": [
            {"agent_id": "agent:bro", "operator_id": "org:braindiff", "score": 0.90},
            {"agent_id": "agent:momo", "operator_id": "org:attestnet", "score": 0.87},
        ],
    }


def generate_fuzz_cases() -> list[FuzzCase]:
    cases = []
    
    # === REFUSAL-SPECIFIC ===
    
    # ADV-021-01: Valid refusal receipt
    cases.append(FuzzCase(
        name="ADV-021-01",
        description="Well-formed refusal with rationale_hash",
        severity="MUST_ACCEPT",
        category="refusal_specific",
        receipt=make_valid_refusal(),
    ))
    
    # ADV-021-02: Refusal without rationale_hash
    r = make_valid_refusal()
    del r["rationale_hash"]
    cases.append(FuzzCase(
        name="ADV-021-02",
        description="Refusal missing rationale_hash — why did it refuse?",
        severity="SHOULD_REJECT",
        category="refusal_specific",
        receipt=r,
    ))
    
    # ADV-021-03: Refusal without task_hash
    r = make_valid_refusal()
    del r["task_hash"]
    cases.append(FuzzCase(
        name="ADV-021-03",
        description="Refusal missing task_hash — what was refused?",
        severity="MUST_REJECT",
        category="refusal_specific",
        receipt=r,
    ))
    
    # ADV-021-04: rationale_hash on delivery receipt (should be ignored or warned)
    r = make_valid_refusal()
    r["decision_type"] = "delivery"
    cases.append(FuzzCase(
        name="ADV-021-04",
        description="rationale_hash present on delivery — leak or mistake?",
        severity="MAY_VARY",
        category="consistency",
        receipt=r,
    ))
    
    # ADV-021-05: Refusal with all dimensions at 1.0 (suspicious)
    r = make_valid_refusal()
    for dim in ["timeliness", "groundedness", "attestation", "self_knowledge", "consistency"]:
        r[dim] = 1.0
    cases.append(FuzzCase(
        name="ADV-021-05",
        description="Perfect scores on a refusal — too good to be true?",
        severity="MAY_VARY",
        category="adversarial",
        receipt=r,
    ))
    
    # ADV-021-06: Refusal with 0.0 self_knowledge (refused but doesn't know why)
    r = make_valid_refusal()
    r["self_knowledge"] = 0.0
    cases.append(FuzzCase(
        name="ADV-021-06",
        description="Refusal with zero self_knowledge — refused but can't explain",
        severity="MAY_VARY",
        category="consistency",
        receipt=r,
    ))
    
    # === TEMPORAL ===
    
    # ADV-021-07: Refusal after partial delivery (scar_reference to delivery receipt)
    r = make_valid_refusal()
    r["scar_reference"] = "sha256:prior_delivery_abc"
    r["decision_type"] = "refusal"
    cases.append(FuzzCase(
        name="ADV-021-07",
        description="Refusal after partial delivery — scar references prior work",
        severity="MUST_ACCEPT",
        category="temporal",
        receipt=r,
    ))
    
    # ADV-021-08: Refusal with future timestamp
    r = make_valid_refusal()
    r["timestamp"] = "2030-01-01T00:00:00Z"
    cases.append(FuzzCase(
        name="ADV-021-08",
        description="Refusal with future timestamp",
        severity="MUST_REJECT",
        category="temporal",
        receipt=r,
    ))
    
    # ADV-021-09: Refusal with empty rationale_hash
    r = make_valid_refusal()
    r["rationale_hash"] = ""
    cases.append(FuzzCase(
        name="ADV-021-09",
        description="Refusal with empty string rationale_hash",
        severity="SHOULD_REJECT",
        category="refusal_specific",
        receipt=r,
    ))
    
    # === ADVERSARIAL ===
    
    # ADV-021-10: Refusal spam — same agent, same task, rapid refusals
    r = make_valid_refusal()
    r["agent_id"] = "agent:spammer"
    cases.append(FuzzCase(
        name="ADV-021-10",
        description="Rapid refusal spam — system must rate-limit, format can't prevent",
        severity="MAY_VARY",
        category="adversarial",
        receipt=r,
    ))
    
    # ADV-021-11: Refusal with rationale_hash = task_hash (circular reference)
    r = make_valid_refusal()
    r["rationale_hash"] = r["task_hash"]
    cases.append(FuzzCase(
        name="ADV-021-11",
        description="rationale_hash == task_hash — circular or lazy?",
        severity="SHOULD_REJECT",
        category="adversarial",
        receipt=r,
    ))
    
    # ADV-021-12: decision_type not in enum
    r = make_valid_refusal()
    r["decision_type"] = "maybe"
    cases.append(FuzzCase(
        name="ADV-021-12",
        description="Invalid decision_type 'maybe'",
        severity="MUST_REJECT",
        category="refusal_specific",
        receipt=r,
    ))
    
    return cases


def run_reference_parser(receipt: dict) -> dict:
    """Reference parser — validates refusal receipt."""
    errors = []
    warnings = []
    
    required = ["version", "agent_id", "task_hash", "decision_type", "timestamp", "merkle_root"]
    for f in required:
        if f not in receipt or not receipt[f]:
            errors.append(f"missing: {f}")
    
    valid_types = {"delivery", "refusal", "liveness", "slash", "inaction"}
    dt = receipt.get("decision_type", "")
    if dt and dt not in valid_types:
        errors.append(f"invalid_decision_type: {dt}")
    
    if dt == "refusal":
        rh = receipt.get("rationale_hash", None)
        if rh is None:
            warnings.append("refusal_without_rationale_hash")
        elif rh == "":
            warnings.append("empty_rationale_hash")
        if rh and rh == receipt.get("task_hash"):
            warnings.append("circular_rationale_reference")
    
    if dt != "refusal" and receipt.get("rationale_hash"):
        warnings.append("rationale_hash_on_non_refusal")
    
    ts = receipt.get("timestamp", "")
    if ts and ts > "2027":
        errors.append(f"future_timestamp: {ts}")
    
    witnesses = receipt.get("witnesses", [])
    if len(witnesses) < 2:
        errors.append(f"insufficient_witnesses: {len(witnesses)}")
    
    for dim in ["timeliness", "groundedness", "attestation", "self_knowledge", "consistency"]:
        v = receipt.get(dim)
        if v is not None and (v < 0 or v > 1):
            errors.append(f"out_of_bounds: {dim}={v}")
    
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def main():
    cases = generate_fuzz_cases()
    
    print("=" * 65)
    print("ADV-021: REFUSAL RECEIPT FUZZ SUITE")
    print(f"{len(cases)} test vectors")
    print("=" * 65)
    
    results = {"pass": 0, "fail": 0, "details": []}
    
    for case in cases:
        result = run_reference_parser(case.receipt)
        
        # Check if parser behavior matches expected severity
        if case.severity == "MUST_ACCEPT":
            passed = result["valid"]
        elif case.severity == "MUST_REJECT":
            passed = not result["valid"]
        else:  # SHOULD_REJECT, MAY_VARY
            passed = True  # informational
        
        status = "✅" if passed else "❌"
        results["pass" if passed else "fail"] += 1
        
        detail = f"{status} {case.name} [{case.severity}] {case.description}"
        if result["errors"]:
            detail += f"\n   Errors: {result['errors']}"
        if result["warnings"]:
            detail += f"\n   Warnings: {result['warnings']}"
        
        results["details"].append(detail)
        print(detail)
    
    print(f"\n{'=' * 65}")
    print(f"Results: {results['pass']} pass, {results['fail']} fail out of {len(cases)}")
    print(f"Reference parser pass rate: {results['pass']/len(cases)*100:.0f}%")
    
    # Export as JSON for cross-parser testing
    export = []
    for case in cases:
        export.append({
            "name": case.name,
            "description": case.description,
            "severity": case.severity,
            "category": case.category,
            "receipt": case.receipt,
        })
    
    with open("specs/refusal-fuzz-vectors.json", "w") as f:
        json.dump({"suite": "ADV-021", "version": "0.1.0", "vectors": export}, f, indent=2)
    
    print(f"\nExported to specs/refusal-fuzz-vectors.json")


if __name__ == "__main__":
    main()
