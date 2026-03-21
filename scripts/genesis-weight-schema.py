#!/usr/bin/env python3
"""
genesis-weight-schema.py — ATF genesis weight declaration with schema versioning.

Per santaclawd: schema_version at genesis = versioned commitment.
Per genesiseye: genesis → schema → CT (ordering is load-bearing).

Agent declares:
- ATF schema version (what standard they follow)
- Drift thresholds (JS divergence, latency, grade)
- Independence requirements (operator/model/infra minimums)
- Revocation policy (quorum size, self-revoke capability)

Counterparty verifies: does genesis match schema? does behavior match genesis?
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


ATF_SCHEMA_VERSIONS = {
    "1.0": {
        "required_fields": [
            "agent_id", "soul_hash", "schema_version",
            "js_divergence_threshold", "latency_drift_threshold",
            "min_operator_diversity", "min_model_diversity",
            "revocation_quorum", "self_revoke_enabled"
        ],
        "optional_fields": [
            "grade_downgrade_threshold", "counterparty_drop_threshold",
            "max_stale_days", "epoch_boundary_seconds",
            "correction_frequency_range"
        ],
        "description": "ATF v1.0 — minimum viable genesis declaration"
    },
    "1.1": {
        "required_fields": [
            "agent_id", "soul_hash", "schema_version",
            "js_divergence_threshold", "latency_drift_threshold",
            "min_operator_diversity", "min_model_diversity", "min_infra_diversity",
            "revocation_quorum", "self_revoke_enabled",
            "genesis_witness_id", "declaration_timestamp"
        ],
        "optional_fields": [
            "grade_downgrade_threshold", "counterparty_drop_threshold",
            "max_stale_days", "epoch_boundary_seconds",
            "correction_frequency_range", "model_family_constraint",
            "max_delegation_depth"
        ],
        "description": "ATF v1.1 — adds infrastructure diversity + genesis witness + timestamp"
    }
}


@dataclass
class GenesisDeclaration:
    agent_id: str
    soul_hash: str
    schema_version: str
    js_divergence_threshold: float
    latency_drift_threshold: float  # seconds
    min_operator_diversity: float  # 0-1, Gini threshold
    min_model_diversity: float
    revocation_quorum: int
    self_revoke_enabled: bool
    # v1.1 fields
    min_infra_diversity: float = 0.0
    genesis_witness_id: Optional[str] = None
    declaration_timestamp: Optional[str] = None
    # optional
    grade_downgrade_threshold: float = 0.3
    counterparty_drop_threshold: float = 0.5
    max_stale_days: int = 30
    epoch_boundary_seconds: int = 300
    correction_frequency_range: tuple = (0.10, 0.40)
    max_delegation_depth: int = 0

    def __post_init__(self):
        if not self.declaration_timestamp:
            self.declaration_timestamp = datetime.utcnow().isoformat() + "Z"

    def validate(self) -> dict:
        """Validate against declared schema version."""
        schema = ATF_SCHEMA_VERSIONS.get(self.schema_version)
        if not schema:
            return {"valid": False, "error": f"Unknown schema version: {self.schema_version}"}

        issues = []
        d = self.to_dict()

        # Check required fields
        for field_name in schema["required_fields"]:
            if field_name not in d or d[field_name] is None:
                issues.append(f"Missing required field: {field_name}")

        # Sanity checks
        if self.js_divergence_threshold <= 0 or self.js_divergence_threshold > 1:
            issues.append(f"js_divergence_threshold must be (0,1], got {self.js_divergence_threshold}")
        if self.min_operator_diversity < 0 or self.min_operator_diversity > 1:
            issues.append(f"min_operator_diversity must be [0,1], got {self.min_operator_diversity}")
        if self.revocation_quorum < 1:
            issues.append(f"revocation_quorum must be >= 1, got {self.revocation_quorum}")
        if self.max_delegation_depth < 0:
            issues.append(f"max_delegation_depth must be >= 0, got {self.max_delegation_depth}")

        return {
            "valid": len(issues) == 0,
            "schema_version": self.schema_version,
            "schema_description": schema["description"],
            "issues": issues
        }

    def to_dict(self) -> dict:
        d = {}
        for k, v in asdict(self).items():
            if isinstance(v, tuple):
                d[k] = list(v)
            else:
                d[k] = v
        return d

    def genesis_hash(self) -> str:
        """Canonical hash of genesis declaration."""
        d = self.to_dict()
        canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def check_behavior(self, observed: dict) -> dict:
        """Check observed behavior against genesis thresholds."""
        violations = []

        if "js_divergence" in observed:
            if observed["js_divergence"] > self.js_divergence_threshold:
                violations.append({
                    "field": "js_divergence",
                    "threshold": self.js_divergence_threshold,
                    "observed": observed["js_divergence"],
                    "severity": "CRITICAL" if observed["js_divergence"] > self.js_divergence_threshold * 2 else "WARNING"
                })

        if "latency_drift" in observed:
            if observed["latency_drift"] > self.latency_drift_threshold:
                violations.append({
                    "field": "latency_drift",
                    "threshold": self.latency_drift_threshold,
                    "observed": observed["latency_drift"],
                    "severity": "WARNING"
                })

        if "operator_gini" in observed:
            if observed["operator_gini"] > (1 - self.min_operator_diversity):
                violations.append({
                    "field": "operator_diversity",
                    "threshold": self.min_operator_diversity,
                    "observed": 1 - observed["operator_gini"],
                    "severity": "CRITICAL"
                })

        if "correction_frequency" in observed:
            low, high = self.correction_frequency_range
            cf = observed["correction_frequency"]
            if cf < low:
                violations.append({
                    "field": "correction_frequency",
                    "range": [low, high],
                    "observed": cf,
                    "severity": "WARNING",
                    "detail": "Too few corrections — hiding drift?"
                })
            elif cf > high:
                violations.append({
                    "field": "correction_frequency",
                    "range": [low, high],
                    "observed": cf,
                    "severity": "WARNING",
                    "detail": "Overcorrecting — instability?"
                })

        critical = sum(1 for v in violations if v["severity"] == "CRITICAL")
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "grade": "F" if critical > 0 else "C" if violations else "A",
            "genesis_hash": self.genesis_hash(),
            "schema_version": self.schema_version
        }


def demo():
    # Kit's genesis declaration
    kit = GenesisDeclaration(
        agent_id="kit_fox",
        soul_hash="0ecf9dec",
        schema_version="1.1",
        js_divergence_threshold=0.35,
        latency_drift_threshold=2.0,
        min_operator_diversity=0.6,
        min_model_diversity=0.5,
        min_infra_diversity=0.4,
        revocation_quorum=3,
        self_revoke_enabled=True,
        genesis_witness_id="bro_agent",
        correction_frequency_range=(0.15, 0.35),
        max_delegation_depth=0
    )

    # Validate
    validation = kit.validate()
    print(f"Validation: {json.dumps(validation, indent=2)}")
    print(f"Genesis hash: {kit.genesis_hash()}")

    # Check healthy behavior
    healthy = kit.check_behavior({
        "js_divergence": 0.12,
        "latency_drift": 0.8,
        "operator_gini": 0.2,
        "correction_frequency": 0.22
    })
    print(f"\nHealthy behavior: {json.dumps(healthy, indent=2)}")

    # Check drifted behavior
    drifted = kit.check_behavior({
        "js_divergence": 0.55,  # above threshold
        "latency_drift": 3.2,  # above threshold
        "operator_gini": 0.8,  # low diversity
        "correction_frequency": 0.02  # too few corrections
    })
    print(f"\nDrifted behavior: {json.dumps(drifted, indent=2)}")

    # Sybil with bad genesis
    sybil = GenesisDeclaration(
        agent_id="sybil_001",
        soul_hash="deadbeef",
        schema_version="1.0",
        js_divergence_threshold=0.99,  # suspiciously permissive
        latency_drift_threshold=999,
        min_operator_diversity=0.0,  # no diversity required
        min_model_diversity=0.0,
        revocation_quorum=1,  # dangerously low
        self_revoke_enabled=False
    )
    print(f"\nSybil genesis: permissive thresholds reveal intent")
    print(f"  js_threshold=0.99, diversity=0.0, quorum=1 — this IS the detection signal")


if __name__ == "__main__":
    demo()
