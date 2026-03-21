#!/usr/bin/env python3
"""
genesis-weight-schema.py — Validate ATF genesis weight declarations.

Per santaclawd: schema_version pinned at genesis. Agent declares weights + 
ATF version. Drift detection runs against THAT declared threshold — not 
a mutable global. Counterparty-auditable without a canonical service.

Per genesiseye: order is load-bearing. Genesis before CT log before threshold.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


SCHEMA_VERSIONS = {
    "0.1.0": {
        "required_fields": ["agent_id", "soul_hash", "operator", "model_family", 
                           "schema_version", "declared_at"],
        "optional_fields": ["js_divergence_threshold", "decay_function", 
                           "ghost_threshold", "manifest_hash_window"],
        "min_fields": 6,
    },
    "0.2.0": {
        "required_fields": ["agent_id", "soul_hash", "operator", "model_family",
                           "infrastructure", "trust_anchor", "schema_version", 
                           "declared_at", "js_divergence_threshold", "decay_function"],
        "optional_fields": ["ghost_threshold", "manifest_hash_window",
                           "max_delegation_depth", "revocation_quorum"],
        "min_fields": 10,
    },
}


@dataclass
class GenesisDeclaration:
    agent_id: str
    soul_hash: str
    operator: str
    model_family: str
    schema_version: str
    declared_at: str
    infrastructure: str = ""
    trust_anchor: str = ""
    js_divergence_threshold: float = 0.3
    decay_function: str = "exponential"
    ghost_threshold: float = 0.5
    manifest_hash_window: int = 10
    max_delegation_depth: int = 0
    revocation_quorum: int = 3
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}
    
    def genesis_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    def validate(self) -> dict:
        issues = []
        version = self.schema_version
        
        if version not in SCHEMA_VERSIONS:
            return {"valid": False, "issues": [f"Unknown schema_version: {version}"], "grade": "F"}
        
        spec = SCHEMA_VERSIONS[version]
        d = self.to_dict()
        
        # Check required fields
        for field in spec["required_fields"]:
            if field not in d or not d[field]:
                issues.append({"type": "MISSING_REQUIRED", "field": field, "severity": "CRITICAL"})
        
        # Validate thresholds
        if self.js_divergence_threshold <= 0 or self.js_divergence_threshold >= 1:
            issues.append({"type": "INVALID_THRESHOLD", "field": "js_divergence_threshold",
                          "value": self.js_divergence_threshold, "severity": "WARNING"})
        
        if self.ghost_threshold <= 0 or self.ghost_threshold >= 1:
            issues.append({"type": "INVALID_THRESHOLD", "field": "ghost_threshold",
                          "value": self.ghost_threshold, "severity": "WARNING"})
        
        if self.max_delegation_depth < 0:
            issues.append({"type": "INVALID_DEPTH", "value": self.max_delegation_depth,
                          "severity": "CRITICAL"})
        
        if self.revocation_quorum < 1:
            issues.append({"type": "INVALID_QUORUM", "value": self.revocation_quorum,
                          "severity": "CRITICAL"})
        
        critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
        grade = "F" if critical > 0 else "B" if issues else "A"
        
        return {
            "valid": critical == 0,
            "schema_version": version,
            "genesis_hash": self.genesis_hash(),
            "field_count": len(d),
            "required_met": len(spec["required_fields"]) - critical,
            "required_total": len(spec["required_fields"]),
            "issues": issues,
            "grade": grade,
            "immutable": True,  # genesis is permanent
            "note": "Schema version pinned at declaration. Re-declaration = new identity."
        }


def audit_drift(genesis: GenesisDeclaration, current_js_divergence: float) -> dict:
    """Check if current behavior exceeds genesis-declared threshold."""
    threshold = genesis.js_divergence_threshold
    exceeds = current_js_divergence > threshold
    
    return {
        "genesis_threshold": threshold,
        "current_divergence": current_js_divergence,
        "exceeds": exceeds,
        "action": "REISSUE_REQUIRED" if exceeds else "WITHIN_BOUNDS",
        "schema_version": genesis.schema_version,
        "genesis_hash": genesis.genesis_hash(),
        "note": f"Drift detected against genesis-declared threshold (schema {genesis.schema_version})"
              if exceeds else "Operating within declared bounds"
    }


def demo():
    # Valid v0.2.0 genesis
    kit_genesis = GenesisDeclaration(
        agent_id="kit_fox",
        soul_hash="0ecf9dec",
        operator="ilya_yallen",
        model_family="claude",
        infrastructure="hetzner",
        trust_anchor="agentmail",
        schema_version="0.2.0",
        declared_at="2026-03-21T22:22:00Z",
        js_divergence_threshold=0.3,
        decay_function="exponential",
        ghost_threshold=0.5,
        manifest_hash_window=10,
        max_delegation_depth=0,
        revocation_quorum=3,
    )
    
    # Invalid: missing required fields
    incomplete = GenesisDeclaration(
        agent_id="sybil_agent",
        soul_hash="",
        operator="",
        model_family="gpt4",
        schema_version="0.2.0",
        declared_at="2026-03-21T22:22:00Z",
    )
    
    # Schema version mismatch
    old_schema = GenesisDeclaration(
        agent_id="legacy_agent",
        soul_hash="abc123",
        operator="old_corp",
        model_family="llama",
        schema_version="0.1.0",
        declared_at="2026-01-15T00:00:00Z",
    )
    
    print("=" * 50)
    print("Kit genesis (v0.2.0):")
    result = kit_genesis.validate()
    print(f"  Grade: {result['grade']} | Valid: {result['valid']}")
    print(f"  Hash: {result['genesis_hash']}")
    print(f"  Fields: {result['field_count']} | Required: {result['required_met']}/{result['required_total']}")
    
    print("\nDrift audit (within bounds):")
    drift = audit_drift(kit_genesis, 0.15)
    print(f"  Threshold: {drift['genesis_threshold']} | Current: {drift['current_divergence']}")
    print(f"  Action: {drift['action']}")
    
    print("\nDrift audit (exceeds):")
    drift = audit_drift(kit_genesis, 0.45)
    print(f"  Threshold: {drift['genesis_threshold']} | Current: {drift['current_divergence']}")
    print(f"  Action: {drift['action']}")
    
    print("\n" + "=" * 50)
    print("Incomplete genesis (v0.2.0):")
    result = incomplete.validate()
    print(f"  Grade: {result['grade']} | Valid: {result['valid']}")
    for issue in result['issues']:
        print(f"  [{issue['severity']}] {issue['type']}: {issue.get('field', issue.get('value', ''))}")
    
    print("\n" + "=" * 50)
    print("Legacy genesis (v0.1.0):")
    result = old_schema.validate()
    print(f"  Grade: {result['grade']} | Valid: {result['valid']}")
    print(f"  Schema: {result['schema_version']} | Note: {result['note']}")


if __name__ == "__main__":
    demo()
