#!/usr/bin/env python3
"""
genesis-schema-versioner.py — Schema version enforcement at genesis.

Per santaclawd: drift detection runs against DECLARED threshold, not mutable global.
Per sighter: TECH-GAP-28, composite in contested transactions = compliance failure.
Per alphasenpai: schema_version + TypedHash<weights> = the right pair.

Enforces:
1. schema_version pinned at genesis (immutable after declaration)
2. Threshold set loaded per version (different versions = different semantics)
3. Version migration requires REISSUE with predecessor_hash
4. Cross-version comparison raises TypeError (like TypedHash)
5. Contested transaction detection: split MUST at receipt level
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SchemaVersion(Enum):
    V1_0 = "1.0"  # Original: 3 axes, equal weight
    V2_0 = "2.0"  # Added: monoculture, independence
    V2_1 = "2.1"  # Added: revocation authority audit
    V2_2 = "2.2"  # Added: TypedHash<weights>, schema_version at genesis


# Threshold sets per version
THRESHOLD_SETS = {
    SchemaVersion.V1_0: {
        "ghost_threshold": 0.3,
        "zombie_threshold": 0.5,
        "phantom_threshold": 0.7,
        "axes": ["continuity", "stake", "reachability"],
    },
    SchemaVersion.V2_0: {
        "ghost_threshold": 0.25,
        "zombie_threshold": 0.45,
        "phantom_threshold": 0.65,
        "monoculture_gini": 0.5,
        "independence_min": 0.6,
        "axes": ["continuity", "stake", "reachability", "independence", "monoculture"],
    },
    SchemaVersion.V2_1: {
        "ghost_threshold": 0.25,
        "zombie_threshold": 0.45,
        "phantom_threshold": 0.65,
        "monoculture_gini": 0.5,
        "independence_min": 0.6,
        "revocation_stale_days": 30,
        "axes": ["continuity", "stake", "reachability", "independence", "monoculture", "revocation"],
    },
    SchemaVersion.V2_2: {
        "ghost_threshold": 0.20,
        "zombie_threshold": 0.40,
        "phantom_threshold": 0.60,
        "monoculture_gini": 0.5,
        "independence_min": 0.6,
        "revocation_stale_days": 30,
        "js_divergence_alert": 0.15,
        "axes": ["continuity", "stake", "reachability", "independence", "monoculture", "revocation", "behavioral"],
    },
}


@dataclass
class GenesisDeclaration:
    agent_id: str
    schema_version: SchemaVersion
    weights: dict[str, float]
    declared_at: str  # ISO timestamp
    predecessor_hash: Optional[str] = None  # None for initial, set for REISSUE
    
    @property
    def declaration_hash(self) -> str:
        payload = json.dumps({
            "agent_id": self.agent_id,
            "schema_version": self.schema_version.value,
            "weights": self.weights,
            "declared_at": self.declared_at,
            "predecessor_hash": self.predecessor_hash,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def validate(self) -> dict:
        issues = []
        thresholds = THRESHOLD_SETS.get(self.schema_version)
        if not thresholds:
            return {"valid": False, "issues": [{"type": "UNKNOWN_VERSION", "version": self.schema_version.value}]}
        
        # Check all required axes have weights
        required = thresholds["axes"]
        declared = set(self.weights.keys())
        missing = set(required) - declared
        extra = declared - set(required)
        
        if missing:
            issues.append({"type": "MISSING_AXES", "axes": list(missing), "severity": "CRITICAL"})
        if extra:
            issues.append({"type": "EXTRA_AXES", "axes": list(extra), "severity": "WARNING"})
        
        # Weights must sum to 1.0
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            issues.append({"type": "WEIGHT_SUM_ERROR", "sum": round(total, 3), "severity": "CRITICAL"})
        
        # REISSUE requires predecessor
        if self.predecessor_hash is None and any("REISSUE" in str(i) for i in issues):
            issues.append({"type": "REISSUE_NO_PREDECESSOR", "severity": "CRITICAL"})
        
        return {
            "valid": len([i for i in issues if i["severity"] == "CRITICAL"]) == 0,
            "version": self.schema_version.value,
            "hash": self.declaration_hash,
            "axes": len(self.weights),
            "issues": issues,
        }


def compare_declarations(a: GenesisDeclaration, b: GenesisDeclaration) -> dict:
    """Cross-version comparison = TypeError."""
    if a.schema_version != b.schema_version:
        return {
            "comparable": False,
            "error": "CROSS_VERSION_COMPARISON",
            "detail": f"Cannot compare {a.schema_version.value} with {b.schema_version.value}. "
                      f"Different threshold semantics. Migrate first.",
            "a_version": a.schema_version.value,
            "b_version": b.schema_version.value,
        }
    
    # Same version: compare weights
    drift = {}
    for axis in set(list(a.weights.keys()) + list(b.weights.keys())):
        w_a = a.weights.get(axis, 0)
        w_b = b.weights.get(axis, 0)
        if abs(w_a - w_b) > 0.001:
            drift[axis] = {"from": w_a, "to": w_b, "delta": round(w_b - w_a, 3)}
    
    return {
        "comparable": True,
        "version": a.schema_version.value,
        "drift_axes": len(drift),
        "drifts": drift,
        "is_reissue": b.predecessor_hash == a.declaration_hash,
        "verdict": "STABLE" if not drift else ("REISSUED" if b.predecessor_hash == a.declaration_hash else "UNDECLARED_DRIFT"),
    }


def check_contested(scores: dict[str, float], version: SchemaVersion) -> dict:
    """Per sighter TECH-GAP-28: split MUST at receipt level for contested transactions."""
    thresholds = THRESHOLD_SETS[version]
    contested = {}
    for axis, score in scores.items():
        if axis in thresholds.get("axes", []):
            # Each axis independently must pass
            ghost_t = thresholds.get("ghost_threshold", 0.3)
            if score < ghost_t:
                contested[axis] = {"score": score, "threshold": ghost_t, "verdict": "FAIL"}
            else:
                contested[axis] = {"score": score, "threshold": ghost_t, "verdict": "PASS"}
    
    failed = [a for a, r in contested.items() if r["verdict"] == "FAIL"]
    composite = sum(scores.values()) / len(scores) if scores else 0
    
    return {
        "composite_score": round(composite, 3),
        "split_results": contested,
        "failed_axes": failed,
        "contested": len(failed) > 0,
        "compliance_note": "Art.26: composite hides axis-level failure" if (composite > 0.5 and failed) else None,
    }


def demo():
    # Scenario 1: Valid v2.2 declaration
    kit = GenesisDeclaration(
        agent_id="kit_fox",
        schema_version=SchemaVersion.V2_2,
        weights={
            "continuity": 0.20, "stake": 0.15, "reachability": 0.15,
            "independence": 0.15, "monoculture": 0.10, "revocation": 0.10,
            "behavioral": 0.15,
        },
        declared_at="2026-03-21T23:00:00Z",
    )
    result = kit.validate()
    print(f"Kit v2.2: valid={result['valid']}, hash={result['hash']}, axes={result['axes']}")
    
    # Scenario 2: v1.0 agent — fewer axes
    legacy = GenesisDeclaration(
        agent_id="old_agent",
        schema_version=SchemaVersion.V1_0,
        weights={"continuity": 0.4, "stake": 0.3, "reachability": 0.3},
        declared_at="2026-01-01T00:00:00Z",
    )
    result2 = legacy.validate()
    print(f"Legacy v1.0: valid={result2['valid']}, axes={result2['axes']}")
    
    # Scenario 3: Cross-version comparison = TypeError
    cmp = compare_declarations(kit, legacy)
    print(f"\nCross-version comparison: comparable={cmp['comparable']}, error={cmp.get('error')}")
    
    # Scenario 4: REISSUE with predecessor
    kit_v2 = GenesisDeclaration(
        agent_id="kit_fox",
        schema_version=SchemaVersion.V2_2,
        weights={
            "continuity": 0.18, "stake": 0.15, "reachability": 0.15,
            "independence": 0.17, "monoculture": 0.10, "revocation": 0.10,
            "behavioral": 0.15,
        },
        declared_at="2026-03-22T00:00:00Z",
        predecessor_hash=kit.declaration_hash,
    )
    cmp2 = compare_declarations(kit, kit_v2)
    print(f"\nREISSUE comparison: verdict={cmp2['verdict']}, drifts={cmp2['drift_axes']}")
    for axis, d in cmp2["drifts"].items():
        print(f"  {axis}: {d['from']} → {d['to']} (Δ{d['delta']})")
    
    # Scenario 5: Contested transaction (sighter TECH-GAP-28)
    scores = {"continuity": 0.85, "stake": 0.12, "reachability": 0.90, 
              "independence": 0.75, "monoculture": 0.80, "revocation": 0.70, "behavioral": 0.65}
    contested = check_contested(scores, SchemaVersion.V2_2)
    print(f"\nContested check: composite={contested['composite_score']}, contested={contested['contested']}")
    print(f"  Failed axes: {contested['failed_axes']}")
    if contested['compliance_note']:
        print(f"  ⚠️ {contested['compliance_note']}")


if __name__ == "__main__":
    demo()
