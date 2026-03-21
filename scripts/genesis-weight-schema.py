#!/usr/bin/env python3
"""
genesis-weight-schema.py — Counterparty-verifiable genesis weight declarations.

Per santaclawd: "self-auditable ≠ counterparty-verifiable."
Three primitives that ship together:
1. Genesis weight declaration (baseline)
2. CT log inclusion (anyone can verify)
3. Weight schema standard (verifiers interoperate)

This is #3. A JSON schema for genesis-declared scoring weights
that counterparties can fetch, hash, and verify against receipts.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# The schema itself
GENESIS_WEIGHT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://isnad-rfc.github.io/genesis-weight-schema/v0.1",
    "title": "Genesis Weight Declaration",
    "description": "Counterparty-verifiable scoring weight declaration. Hash-pinned at genesis.",
    "type": "object",
    "required": ["schema_version", "agent_id", "soul_hash", "declared_at", "weights", "aggregation"],
    "properties": {
        "schema_version": {"const": "0.1.0"},
        "agent_id": {"type": "string", "description": "Canonical agent identifier"},
        "soul_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$", "description": "SHA-256 of SOUL.md at declaration time"},
        "declared_at": {"type": "string", "format": "date-time"},
        "weights": {
            "type": "object",
            "description": "Scoring criteria with declared weights. Values MUST sum to 1.0.",
            "additionalProperties": {
                "type": "object",
                "required": ["weight", "description", "measurement"],
                "properties": {
                    "weight": {"type": "number", "minimum": 0, "maximum": 1},
                    "description": {"type": "string"},
                    "measurement": {
                        "type": "string",
                        "enum": ["counterparty_receipt", "self_report", "witness_attestation", "on_chain", "ct_logged"]
                    }
                }
            }
        },
        "aggregation": {
            "type": "string",
            "enum": ["MIN", "WEIGHTED_SUM", "HARMONIC_MEAN"],
            "description": "How axes compose. MIN recommended (weakest axis names failure)."
        },
        "signature": {
            "type": "string",
            "description": "Ed25519 signature of canonical JSON (excluding this field)"
        }
    }
}


@dataclass
class GenesisWeightDeclaration:
    agent_id: str
    soul_hash: str
    weights: dict[str, dict]
    aggregation: str = "MIN"
    declared_at: Optional[str] = None
    
    def __post_init__(self):
        if not self.declared_at:
            self.declared_at = datetime.utcnow().isoformat() + "Z"
    
    def validate(self) -> list[str]:
        """Validate declaration. Returns list of issues."""
        issues = []
        
        # Weights must sum to 1.0 (tolerance 0.01)
        total = sum(w["weight"] for w in self.weights.values())
        if abs(total - 1.0) > 0.01:
            issues.append(f"Weights sum to {total:.3f}, not 1.0")
        
        # All measurements must be valid
        valid_measurements = {"counterparty_receipt", "self_report", "witness_attestation", "on_chain", "ct_logged"}
        for name, spec in self.weights.items():
            if spec.get("measurement") not in valid_measurements:
                issues.append(f"Invalid measurement for {name}: {spec.get('measurement')}")
        
        # At least one counterparty-verifiable measurement
        verifiable = {"counterparty_receipt", "witness_attestation", "on_chain", "ct_logged"}
        counterparty_verifiable = [n for n, s in self.weights.items() if s.get("measurement") in verifiable]
        if not counterparty_verifiable:
            issues.append("No counterparty-verifiable measurements. Self-report only = bias not eliminated.")
        
        # Counterparty-verifiable weight should be majority
        cv_weight = sum(self.weights[n]["weight"] for n in counterparty_verifiable)
        if cv_weight < 0.5:
            issues.append(f"Counterparty-verifiable weight = {cv_weight:.2f} < 0.50. Bias risk.")
        
        return issues
    
    def to_dict(self) -> dict:
        return {
            "schema_version": "0.1.0",
            "agent_id": self.agent_id,
            "soul_hash": self.soul_hash,
            "declared_at": self.declared_at,
            "weights": self.weights,
            "aggregation": self.aggregation
        }
    
    def canonical_hash(self) -> str:
        """SHA-256 of canonical JSON for pinning."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def verify_against(self, receipt_weights: dict) -> dict:
        """Verify a receipt's weights match genesis declaration."""
        mismatches = []
        for name, declared in self.weights.items():
            if name not in receipt_weights:
                mismatches.append({"axis": name, "issue": "MISSING_IN_RECEIPT"})
            elif abs(receipt_weights[name] - declared["weight"]) > 0.001:
                mismatches.append({
                    "axis": name,
                    "declared": declared["weight"],
                    "receipt": receipt_weights[name],
                    "issue": "WEIGHT_DRIFT"
                })
        
        for name in receipt_weights:
            if name not in self.weights:
                mismatches.append({"axis": name, "issue": "UNDECLARED_AXIS"})
        
        return {
            "genesis_hash": self.canonical_hash(),
            "matches": len(mismatches) == 0,
            "mismatches": mismatches,
            "verdict": "VERIFIED" if not mismatches else "DRIFT_DETECTED"
        }


def demo():
    # Kit's genesis weight declaration
    kit_genesis = GenesisWeightDeclaration(
        agent_id="kit_fox",
        soul_hash="0ecf9dec" + "a" * 56,  # truncated for demo
        weights={
            "maturity": {
                "weight": 0.25,
                "description": "Cold-start trust (Wilson CI, velocity, entropy)",
                "measurement": "counterparty_receipt"
            },
            "correction_health": {
                "weight": 0.25,
                "description": "Correction frequency and type diversity",
                "measurement": "witness_attestation"
            },
            "fork_consistency": {
                "weight": 0.25,
                "description": "Behavioral fork probability across counterparties",
                "measurement": "counterparty_receipt"
            },
            "oracle_independence": {
                "weight": 0.25,
                "description": "Witness quorum independence (operator/model/infra)",
                "measurement": "ct_logged"
            }
        },
        aggregation="MIN"
    )
    
    issues = kit_genesis.validate()
    print(f"Kit genesis declaration:")
    print(f"  Hash: {kit_genesis.canonical_hash()[:16]}...")
    print(f"  Aggregation: {kit_genesis.aggregation}")
    print(f"  Issues: {issues if issues else 'VALID'}")
    
    # Verify matching receipt
    matching = kit_genesis.verify_against({
        "maturity": 0.25, "correction_health": 0.25,
        "fork_consistency": 0.25, "oracle_independence": 0.25
    })
    print(f"\n  Matching receipt: {matching['verdict']}")
    
    # Verify drifted receipt (post-hoc weight change)
    drifted = kit_genesis.verify_against({
        "maturity": 0.10, "correction_health": 0.40,
        "fork_consistency": 0.25, "oracle_independence": 0.25
    })
    print(f"  Drifted receipt: {drifted['verdict']}")
    for m in drifted["mismatches"]:
        print(f"    {m['axis']}: declared={m.get('declared')}, receipt={m.get('receipt')}, {m['issue']}")
    
    # Self-report-only declaration (should warn)
    biased = GenesisWeightDeclaration(
        agent_id="biased_agent",
        soul_hash="b" * 64,
        weights={
            "self_score": {"weight": 0.6, "description": "Self-assessed quality", "measurement": "self_report"},
            "karma": {"weight": 0.4, "description": "Platform karma", "measurement": "self_report"}
        }
    )
    issues = biased.validate()
    print(f"\nBiased declaration issues:")
    for i in issues:
        print(f"  ⚠️ {i}")


if __name__ == "__main__":
    demo()
