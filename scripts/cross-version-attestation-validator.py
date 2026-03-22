#!/usr/bin/env python3
"""
cross-version-attestation-validator.py — TECH-GAP-29 fix.

Per sighter: "cross-version attestation comparison fails silently —
version mismatch has no compliance meaning."

Validates that attestations from different schema versions are not
silently compared. Forces explicit version negotiation.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Optional


@dataclass  
class SchemaVersion:
    major: int
    minor: int
    patch: int
    registry_hash: str  # hash of field registry at this version
    
    @property
    def semver(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def compatible_with(self, other: 'SchemaVersion') -> tuple[bool, str]:
        """Check if two versions can be compared."""
        if self.major != other.major:
            return False, f"INCOMPATIBLE: major version mismatch ({self.semver} vs {other.semver})"
        if self.registry_hash != other.registry_hash:
            return False, f"REGISTRY_DRIFT: same semver but different field registries"
        if self.minor != other.minor:
            return True, f"MINOR_DIFF: backward compatible but fields may differ"
        return True, f"COMPATIBLE: identical schema"


@dataclass
class Attestation:
    agent_id: str
    schema_version: Optional[SchemaVersion]
    fields: dict
    receipt_hash: str
    
    @property
    def has_version(self) -> bool:
        return self.schema_version is not None


def validate_cross_version(a: Attestation, b: Attestation) -> dict:
    """Validate whether two attestations can be meaningfully compared."""
    issues = []
    
    # 1. Version presence check
    if not a.has_version:
        issues.append({
            "type": "MISSING_VERSION",
            "agent": a.agent_id,
            "severity": "CRITICAL",
            "detail": "No schema_version — cannot validate field semantics"
        })
    if not b.has_version:
        issues.append({
            "type": "MISSING_VERSION", 
            "agent": b.agent_id,
            "severity": "CRITICAL",
            "detail": "No schema_version — cannot validate field semantics"
        })
    
    if not a.has_version or not b.has_version:
        return {
            "verdict": "UNVERSIONED",
            "comparable": False,
            "issues": issues,
            "detail": "Cannot compare attestations without schema versions (TECH-GAP-29)"
        }
    
    # 2. Version compatibility
    compatible, reason = a.schema_version.compatible_with(b.schema_version)
    
    if not compatible:
        issues.append({
            "type": "VERSION_INCOMPATIBLE",
            "versions": [a.schema_version.semver, b.schema_version.semver],
            "severity": "CRITICAL",
            "detail": reason
        })
        return {
            "verdict": "INCOMPATIBLE",
            "comparable": False,
            "version_a": a.schema_version.semver,
            "version_b": b.schema_version.semver,
            "issues": issues
        }
    
    # 3. Field overlap check — what fields exist in both?
    shared = set(a.fields.keys()) & set(b.fields.keys())
    a_only = set(a.fields.keys()) - set(b.fields.keys())
    b_only = set(b.fields.keys()) - set(a.fields.keys())
    
    if a_only or b_only:
        issues.append({
            "type": "FIELD_ASYMMETRY",
            "severity": "WARNING",
            "a_only": sorted(a_only),
            "b_only": sorted(b_only),
            "shared": len(shared),
            "detail": f"{len(a_only)} fields in A only, {len(b_only)} in B only"
        })
    
    # 4. Type consistency on shared fields
    type_mismatches = []
    for field in shared:
        if type(a.fields[field]) != type(b.fields[field]):
            type_mismatches.append(field)
    
    if type_mismatches:
        issues.append({
            "type": "TYPE_MISMATCH",
            "severity": "CRITICAL",
            "fields": type_mismatches,
            "detail": f"{len(type_mismatches)} fields have different types across versions"
        })
    
    # Verdict
    critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    
    if critical > 0:
        verdict = "UNSAFE_COMPARISON"
    elif warnings > 0:
        verdict = "PARTIAL_COMPARISON"
    else:
        verdict = "SAFE_COMPARISON"
    
    return {
        "verdict": verdict,
        "comparable": critical == 0,
        "version_a": a.schema_version.semver,
        "version_b": b.schema_version.semver,
        "shared_fields": len(shared),
        "issues": issues
    }


def demo():
    v1 = SchemaVersion(1, 2, 0, "0d730e47c61ac763")
    v1_1 = SchemaVersion(1, 3, 0, "0d730e47c61ac763")  # minor bump, same registry
    v2 = SchemaVersion(2, 0, 0, "ab12cd34ef567890")  # major bump
    v1_drift = SchemaVersion(1, 2, 0, "ffffff0000000000")  # same semver, different registry
    
    # Scenario 1: Compatible versions
    a1 = Attestation("kit_fox", v1, {"soul_hash": "abc", "model_hash": "def", "corrections": 12}, "r1")
    a2 = Attestation("bro_agent", v1_1, {"soul_hash": "xyz", "model_hash": "uvw", "corrections": 8, "fork_prob": 0.1}, "r2")
    
    result = validate_cross_version(a1, a2)
    print(f"Compatible versions: {result['verdict']} (shared: {result['shared_fields']})")
    for i in result['issues']:
        print(f"  [{i['severity']}] {i['type']}: {i['detail']}")
    
    # Scenario 2: Major version mismatch
    a3 = Attestation("old_agent", v1, {"soul_hash": "old"}, "r3")
    a4 = Attestation("new_agent", v2, {"soul_hash": "new", "schema_version": "2.0.0"}, "r4")
    
    result = validate_cross_version(a3, a4)
    print(f"\nMajor mismatch: {result['verdict']}")
    for i in result['issues']:
        print(f"  [{i['severity']}] {i['type']}: {i['detail']}")
    
    # Scenario 3: Missing version (TECH-GAP-29)
    a5 = Attestation("legacy_agent", None, {"soul_hash": "leg"}, "r5")
    a6 = Attestation("modern_agent", v1, {"soul_hash": "mod"}, "r6")
    
    result = validate_cross_version(a5, a6)
    print(f"\nMissing version: {result['verdict']}")
    for i in result['issues']:
        print(f"  [{i['severity']}] {i['type']}: {i['detail']}")
    
    # Scenario 4: Registry drift (same semver, different hash)
    a7 = Attestation("agent_a", v1, {"soul_hash": "a"}, "r7")
    a8 = Attestation("agent_b", v1_drift, {"soul_hash": "b"}, "r8")
    
    result = validate_cross_version(a7, a8)
    print(f"\nRegistry drift: {result['verdict']}")
    for i in result['issues']:
        print(f"  [{i['severity']}] {i['type']}: {i['detail']}")


if __name__ == "__main__":
    demo()
