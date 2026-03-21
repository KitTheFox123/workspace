#!/usr/bin/env python3
"""
atf-schema-registry.py — Agent Trust Framework schema registry with semver+hash pairs.

Per santaclawd: "semver + content hash = best of both."
- Semver: human-auditable, easy to compare
- Content hash: tamper-evident, immutable
- Both: "ATF:1.2.0:sha256:7f3a..." as canonical ref

Features:
1. Schema version declaration at genesis
2. Silent patch detection (semver same, hash different)
3. Version compatibility matrix
4. Threshold floor enforcement (JS divergence >= 0.3 RECOMMENDED)
5. Migration path validation
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ATFSchema:
    """A specific ATF version with its content hash."""
    version: str  # semver e.g. "1.2.0"
    spec: dict    # the actual schema content
    
    @property
    def content_hash(self) -> str:
        canonical = json.dumps(self.spec, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    @property
    def canonical_ref(self) -> str:
        return f"ATF:{self.version}:sha256:{self.content_hash}"
    
    def is_compatible(self, other: 'ATFSchema') -> dict:
        """Check compatibility between two schema versions."""
        sv = self.version.split('.')
        ov = other.version.split('.')
        
        if sv[0] != ov[0]:
            return {"compatible": False, "reason": "MAJOR_MISMATCH", "migration_required": True}
        if sv[1] != ov[1]:
            return {"compatible": True, "reason": "MINOR_DIFF", "migration_required": False,
                    "note": "New features available but backward compatible"}
        if sv[2] != ov[2]:
            return {"compatible": True, "reason": "PATCH_DIFF", "migration_required": False}
        
        # Same version — check hash
        if self.content_hash != other.content_hash:
            return {"compatible": False, "reason": "SILENT_PATCH", 
                    "severity": "CRITICAL",
                    "detail": f"Same version {self.version} but different hash: {self.content_hash} vs {other.content_hash}"}
        
        return {"compatible": True, "reason": "IDENTICAL"}


@dataclass 
class GenesisDeclaration:
    """What an agent declares at spawn time."""
    agent_id: str
    atf_ref: str  # canonical ref
    thresholds: dict  # agent's declared thresholds
    declared_at: float  # epoch
    
    def validate_floors(self, floors: dict) -> list:
        """Check that declared thresholds meet RECOMMENDED floors."""
        violations = []
        for key, floor in floors.items():
            declared = self.thresholds.get(key)
            if declared is None:
                violations.append({"field": key, "issue": "MISSING", "floor": floor})
            elif declared < floor:
                violations.append({"field": key, "declared": declared, "floor": floor,
                                   "issue": "BELOW_FLOOR"})
        return violations


class ATFRegistry:
    """Registry of ATF schema versions."""
    
    # RECOMMENDED threshold floors per santaclawd
    THRESHOLD_FLOORS = {
        "js_divergence": 0.3,
        "latency_drift_sigma": 2.0,
        "grade_downgrade_threshold": 0.5,
        "witness_disagreement_threshold": 0.4,
        "counterparty_drop_threshold": 0.3,
    }
    
    def __init__(self):
        self.schemas: dict[str, ATFSchema] = {}
        self.declarations: dict[str, GenesisDeclaration] = {}
    
    def register_schema(self, schema: ATFSchema):
        self.schemas[schema.canonical_ref] = schema
    
    def declare_genesis(self, decl: GenesisDeclaration) -> dict:
        # Validate ATF ref exists
        if decl.atf_ref not in self.schemas:
            return {"valid": False, "error": f"Unknown ATF ref: {decl.atf_ref}"}
        
        # Validate threshold floors
        violations = decl.validate_floors(self.THRESHOLD_FLOORS)
        
        self.declarations[decl.agent_id] = decl
        
        return {
            "valid": len(violations) == 0,
            "agent_id": decl.agent_id,
            "atf_ref": decl.atf_ref,
            "floor_violations": violations,
            "grade": "A" if not violations else "C" if len(violations) <= 2 else "F"
        }
    
    def check_drift(self, agent_id: str, current_atf_ref: str) -> dict:
        """Check if agent's current ATF ref matches genesis declaration."""
        decl = self.declarations.get(agent_id)
        if not decl:
            return {"status": "NO_GENESIS", "detail": "Agent has no genesis declaration"}
        
        if decl.atf_ref == current_atf_ref:
            return {"status": "STABLE", "declared": decl.atf_ref}
        
        # Different ref — check compatibility
        declared_schema = self.schemas.get(decl.atf_ref)
        current_schema = self.schemas.get(current_atf_ref)
        
        if not current_schema:
            return {"status": "UNKNOWN_VERSION", "declared": decl.atf_ref, "current": current_atf_ref}
        
        compat = declared_schema.is_compatible(current_schema)
        
        if compat.get("reason") == "SILENT_PATCH":
            return {"status": "SILENT_PATCH", "severity": "CRITICAL", **compat}
        elif not compat["compatible"]:
            return {"status": "MAJOR_DRIFT", "requires_regenesis": True, **compat}
        else:
            return {"status": "MINOR_DRIFT", "ok": True, **compat}


def demo():
    registry = ATFRegistry()
    
    # Register schema versions
    v1_2 = ATFSchema("1.2.0", {
        "js_divergence_floor": 0.3,
        "triggers": ["action_distribution", "latency", "grade", "witness", "counterparty_drop"],
        "quorum_bft": "f<n/3"
    })
    
    v1_2_patched = ATFSchema("1.2.0", {
        "js_divergence_floor": 0.3,
        "triggers": ["action_distribution", "latency", "grade", "witness", "counterparty_drop"],
        "quorum_bft": "f<n/3",
        "silent_addition": True  # sneaky patch
    })
    
    v2_0 = ATFSchema("2.0.0", {
        "js_divergence_floor": 0.3,
        "triggers": ["action_distribution", "latency", "grade", "witness", "counterparty_drop", "schema_drift"],
        "quorum_bft": "f<n/3",
        "typed_hashes": True
    })
    
    registry.register_schema(v1_2)
    registry.register_schema(v1_2_patched)
    registry.register_schema(v2_0)
    
    print(f"v1.2.0 ref: {v1_2.canonical_ref}")
    print(f"v1.2.0 (patched) ref: {v1_2_patched.canonical_ref}")
    print(f"v2.0.0 ref: {v2_0.canonical_ref}")
    
    # Declare genesis with good thresholds
    good = GenesisDeclaration("kit_fox", v1_2.canonical_ref, {
        "js_divergence": 0.35, "latency_drift_sigma": 2.5,
        "grade_downgrade_threshold": 0.6, "witness_disagreement_threshold": 0.5,
        "counterparty_drop_threshold": 0.4
    }, 1711065600)
    
    # Declare genesis with weak thresholds
    weak = GenesisDeclaration("lazy_agent", v1_2.canonical_ref, {
        "js_divergence": 0.1,  # below floor!
        "latency_drift_sigma": 1.0,  # below floor!
    }, 1711065600)
    
    print(f"\n{'='*50}")
    print("Genesis declarations:")
    print(json.dumps(registry.declare_genesis(good), indent=2))
    print(json.dumps(registry.declare_genesis(weak), indent=2))
    
    # Drift checks
    print(f"\n{'='*50}")
    print("Drift checks:")
    print(f"kit_fox stable: {json.dumps(registry.check_drift('kit_fox', v1_2.canonical_ref))}")
    print(f"kit_fox silent patch: {json.dumps(registry.check_drift('kit_fox', v1_2_patched.canonical_ref))}")
    print(f"kit_fox major: {json.dumps(registry.check_drift('kit_fox', v2_0.canonical_ref))}")


if __name__ == "__main__":
    demo()
