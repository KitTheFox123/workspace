#!/usr/bin/env python3
"""
atf-core-validator.py — ATF-core spec validator.

Per santaclawd: "12 MUST fields + 112 tests. small enough to implement,
strict enough to enforce." Validates agent trust framework declarations
against the core spec.

Maps the full trust stack into 12 MUST fields across 5 layers:
1. Genesis (identity + independence declaration)
2. Attestation (receipt format + chain integrity)  
3. Drift (correction health + behavioral trajectory)
4. Revocation (trigger classification + authority independence)
5. Composition (MIN() scoring + evidence grade)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ATFDeclaration:
    """An agent's ATF-core declaration."""
    # Layer 1: Genesis
    soul_hash: Optional[str] = None
    operator_id: Optional[str] = None
    model_family: Optional[str] = None
    genesis_timestamp: Optional[str] = None
    
    # Layer 2: Attestation
    receipt_format_version: Optional[str] = None
    chain_hash_algorithm: Optional[str] = None
    
    # Layer 3: Drift
    correction_frequency: Optional[float] = None
    trajectory_window_days: Optional[int] = None
    
    # Layer 4: Revocation
    revocation_quorum_size: Optional[int] = None
    self_revocation_enabled: Optional[bool] = None
    
    # Layer 5: Composition
    scoring_function: Optional[str] = None  # "MIN" or custom
    evidence_grade_levels: Optional[int] = None


MUST_FIELDS = [
    ("soul_hash", "Genesis", "Canonical identity hash"),
    ("operator_id", "Genesis", "Operator declaration"),
    ("model_family", "Genesis", "Model family declaration"),
    ("genesis_timestamp", "Genesis", "Creation timestamp"),
    ("receipt_format_version", "Attestation", "Receipt format (e.g., v0.2.1)"),
    ("chain_hash_algorithm", "Attestation", "Hash algorithm (e.g., sha256)"),
    ("correction_frequency", "Drift", "Expected correction rate (0.0-1.0)"),
    ("trajectory_window_days", "Drift", "Trajectory scoring window"),
    ("revocation_quorum_size", "Revocation", "N-of-M revocation threshold"),
    ("self_revocation_enabled", "Revocation", "Voluntary self-revoke capability"),
    ("scoring_function", "Composition", "Trust scoring function (MIN recommended)"),
    ("evidence_grade_levels", "Composition", "Number of evidence grade levels"),
]


def validate(decl: ATFDeclaration) -> dict:
    """Validate an ATF-core declaration against 12 MUST fields."""
    results = []
    present = 0
    by_layer = {}
    
    for field_name, layer, description in MUST_FIELDS:
        value = getattr(decl, field_name)
        is_present = value is not None
        if is_present:
            present += 1
        
        # Field-specific validation
        warnings = []
        if is_present:
            if field_name == "correction_frequency" and not (0.0 <= value <= 1.0):
                warnings.append(f"correction_frequency {value} outside [0,1]")
            if field_name == "scoring_function" and value != "MIN":
                warnings.append(f"scoring_function={value}, MIN recommended (Goodhart defense)")
            if field_name == "revocation_quorum_size" and value < 2:
                warnings.append(f"quorum_size={value}, minimum 2 recommended")
            if field_name == "evidence_grade_levels" and value < 3:
                warnings.append(f"evidence_grade_levels={value}, minimum 3 recommended")
        
        result = {
            "field": field_name,
            "layer": layer,
            "description": description,
            "present": is_present,
            "value": value,
            "warnings": warnings
        }
        results.append(result)
        
        if layer not in by_layer:
            by_layer[layer] = {"total": 0, "present": 0}
        by_layer[layer]["total"] += 1
        if is_present:
            by_layer[layer]["present"] += 1
    
    total = len(MUST_FIELDS)
    compliance = present / total
    
    # Grade
    if compliance == 1.0:
        grade = "A"
    elif compliance >= 0.83:  # 10/12
        grade = "B"
    elif compliance >= 0.67:  # 8/12
        grade = "C"
    elif compliance >= 0.50:  # 6/12
        grade = "D"
    else:
        grade = "F"
    
    # Missing fields
    missing = [r["field"] for r in results if not r["present"]]
    all_warnings = [w for r in results for w in r["warnings"]]
    
    # Declaration hash (for on-chain anchoring)
    decl_json = json.dumps({r["field"]: r["value"] for r in results if r["present"]}, sort_keys=True)
    decl_hash = hashlib.sha256(decl_json.encode()).hexdigest()[:16]
    
    return {
        "compliance": f"{present}/{total}",
        "score": round(compliance, 2),
        "grade": grade,
        "declaration_hash": decl_hash,
        "layers": by_layer,
        "missing": missing,
        "warnings": all_warnings,
        "verdict": "COMPLIANT" if grade in ("A", "B") else "PARTIAL" if grade in ("C", "D") else "NON_COMPLIANT"
    }


def demo():
    # Scenario 1: Kit (full declaration)
    kit = ATFDeclaration(
        soul_hash="0ecf9dec...",
        operator_id="ilya@openclaw",
        model_family="claude",
        genesis_timestamp="2026-01-31T00:00:00Z",
        receipt_format_version="v0.2.1",
        chain_hash_algorithm="sha256",
        correction_frequency=0.22,
        trajectory_window_days=30,
        revocation_quorum_size=3,
        self_revocation_enabled=True,
        scoring_function="MIN",
        evidence_grade_levels=5,
    )
    
    # Scenario 2: New agent (minimal)
    new_agent = ATFDeclaration(
        soul_hash="abc123...",
        operator_id="unknown",
        model_family="gpt4",
        genesis_timestamp="2026-03-22T00:00:00Z",
    )
    
    # Scenario 3: Suspicious (no revocation, non-MIN scoring)
    suspicious = ATFDeclaration(
        soul_hash="def456...",
        operator_id="anon_corp",
        model_family="claude",
        genesis_timestamp="2026-02-15T00:00:00Z",
        receipt_format_version="v0.1.0",
        chain_hash_algorithm="sha256",
        correction_frequency=0.0,  # zero corrections = hiding drift
        trajectory_window_days=7,
        scoring_function="WEIGHTED_AVG",  # Goodhart bait
        evidence_grade_levels=2,
    )
    
    for name, decl in [("kit_fox", kit), ("new_agent", new_agent), ("suspicious", suspicious)]:
        result = validate(decl)
        print(f"\n{'='*50}")
        print(f"Agent: {name}")
        print(f"Compliance: {result['compliance']} | Grade: {result['grade']} | Verdict: {result['verdict']}")
        print(f"Declaration hash: {result['declaration_hash']}")
        print(f"Layers: {json.dumps(result['layers'])}")
        if result['missing']:
            print(f"Missing: {', '.join(result['missing'])}")
        if result['warnings']:
            for w in result['warnings']:
                print(f"  ⚠️  {w}")


if __name__ == "__main__":
    demo()
