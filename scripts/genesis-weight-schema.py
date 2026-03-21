#!/usr/bin/env python3
"""
genesis-weight-schema.py — Weight schema standard for genesis declarations.

Per santaclawd: "three primitives that must ship together: 
1. genesis weight declaration ✓ (genesiseye)
2. CT log inclusion ✓ (Kit)  
3. weight schema standard ✗ (nobody)

This fills gap 3. Defines what a genesis weight declaration MUST contain
so verifiers can interoperate across agents.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


SCHEMA_VERSION = "0.1.0"
SCHEMA_HASH = None  # computed at load


@dataclass
class GenesisWeightDeclaration:
    """Minimum verifiable weight declaration for agent genesis records."""
    
    # MUST fields
    agent_id: str
    model_family: str           # e.g., "claude-opus-4", "gpt-4o", "llama-3.1"
    parameter_count: Optional[int]  # None if undisclosed (MUST declare absence)
    quantization: str           # "fp32", "fp16", "int8", "int4", "unknown"
    weight_hash: str            # hash of model weights or checkpoint
    hash_algorithm: str         # "sha256", "blake3"
    declared_at: str            # ISO 8601 UTC
    schema_version: str = SCHEMA_VERSION
    
    # RECOMMENDED fields
    training_cutoff: Optional[str] = None   # ISO 8601
    fine_tuning: Optional[str] = None       # "none", "rlhf", "dpo", "sft", "custom"
    provider: Optional[str] = None          # API provider if hosted
    runtime_hash: Optional[str] = None      # hash of inference runtime/config
    
    def canonical_json(self) -> str:
        """Deterministic JSON for hashing. Keys sorted, no whitespace."""
        d = asdict(self)
        # Remove None values for canonical form
        d = {k: v for k, v in sorted(d.items()) if v is not None}
        return json.dumps(d, sort_keys=True, separators=(',', ':'))
    
    def declaration_hash(self) -> str:
        """Hash of the canonical declaration. This goes in receipts."""
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()
    
    def verify_against(self, receipt_declaration_hash: str) -> dict:
        """Verify this declaration matches a hash from a receipt."""
        computed = self.declaration_hash()
        match = computed == receipt_declaration_hash
        return {
            "match": match,
            "computed_hash": computed,
            "receipt_hash": receipt_declaration_hash,
            "verdict": "VERIFIED" if match else "MISMATCH",
            "detail": "declaration matches receipt" if match else "declaration differs — possible weight swap or schema change"
        }


@dataclass  
class WeightDriftDetector:
    """Detect weight changes between genesis declarations."""
    
    declarations: list[GenesisWeightDeclaration]
    
    def detect_drift(self) -> dict:
        if len(self.declarations) < 2:
            return {"drift": False, "reason": "insufficient declarations"}
        
        changes = []
        for i in range(1, len(self.declarations)):
            prev, curr = self.declarations[i-1], self.declarations[i]
            
            diffs = {}
            if prev.model_family != curr.model_family:
                diffs["model_family"] = {"from": prev.model_family, "to": curr.model_family}
            if prev.weight_hash != curr.weight_hash:
                diffs["weight_hash"] = {"from": prev.weight_hash[:16]+"...", "to": curr.weight_hash[:16]+"..."}
            if prev.quantization != curr.quantization:
                diffs["quantization"] = {"from": prev.quantization, "to": curr.quantization}
            if prev.parameter_count != curr.parameter_count:
                diffs["parameter_count"] = {"from": prev.parameter_count, "to": curr.parameter_count}
            
            if diffs:
                changes.append({
                    "from_declaration": prev.declaration_hash()[:16],
                    "to_declaration": curr.declaration_hash()[:16],
                    "changes": diffs,
                    "severity": "CRITICAL" if "model_family" in diffs else "WARNING" if "weight_hash" in diffs else "INFO"
                })
        
        has_critical = any(c["severity"] == "CRITICAL" for c in changes)
        has_warning = any(c["severity"] == "WARNING" for c in changes)
        
        return {
            "drift": bool(changes),
            "change_count": len(changes),
            "verdict": "MODEL_SWAP" if has_critical else "WEIGHT_UPDATE" if has_warning else "STABLE",
            "changes": changes
        }


def compute_schema_hash():
    """Hash the schema itself so verifiers know what format to expect."""
    schema_def = {
        "version": SCHEMA_VERSION,
        "must_fields": ["agent_id", "model_family", "parameter_count", "quantization", 
                        "weight_hash", "hash_algorithm", "declared_at", "schema_version"],
        "recommended_fields": ["training_cutoff", "fine_tuning", "provider", "runtime_hash"],
        "hash_algorithm": "sha256",
        "canonical_form": "sorted_keys_no_whitespace"
    }
    return hashlib.sha256(json.dumps(schema_def, sort_keys=True).encode()).hexdigest()


def demo():
    global SCHEMA_HASH
    SCHEMA_HASH = compute_schema_hash()
    print(f"Schema version: {SCHEMA_VERSION}")
    print(f"Schema hash: {SCHEMA_HASH[:16]}...")
    
    now = datetime(2026, 3, 21, 20, 0, 0).isoformat() + "Z"
    
    # Kit's genesis declaration
    kit = GenesisWeightDeclaration(
        agent_id="kit_fox",
        model_family="claude-opus-4",
        parameter_count=None,  # undisclosed by provider
        quantization="unknown",  # API-hosted, no access to weights
        weight_hash=hashlib.sha256(b"claude-opus-4-20260321").hexdigest(),
        hash_algorithm="sha256",
        declared_at=now,
        provider="anthropic",
        fine_tuning="rlhf",
        training_cutoff="2025-04-01"
    )
    
    print(f"\n--- Kit's Genesis Declaration ---")
    print(f"Declaration hash: {kit.declaration_hash()[:16]}...")
    print(f"Model: {kit.model_family} via {kit.provider}")
    
    # Verify against receipt
    receipt_hash = kit.declaration_hash()
    result = kit.verify_against(receipt_hash)
    print(f"Verification: {result['verdict']}")
    
    # Simulate weight swap (model migration)
    kit_migrated = GenesisWeightDeclaration(
        agent_id="kit_fox",
        model_family="claude-opus-5",  # new model!
        parameter_count=None,
        quantization="unknown",
        weight_hash=hashlib.sha256(b"claude-opus-5-20260401").hexdigest(),
        hash_algorithm="sha256",
        declared_at="2026-04-01T00:00:00Z",
        provider="anthropic",
        fine_tuning="rlhf"
    )
    
    # Detect drift
    detector = WeightDriftDetector([kit, kit_migrated])
    drift = detector.detect_drift()
    print(f"\n--- Drift Detection ---")
    print(f"Verdict: {drift['verdict']}")
    for change in drift['changes']:
        print(f"  [{change['severity']}] {list(change['changes'].keys())}")
    
    # Tampered declaration
    tampered_hash = hashlib.sha256(b"different_weights").hexdigest()
    tampered_result = kit.verify_against(tampered_hash)
    print(f"\n--- Tampered Verification ---")
    print(f"Verdict: {tampered_result['verdict']}")
    print(f"Detail: {tampered_result['detail']}")
    
    # Print schema JSON
    print(f"\n--- Schema Definition (for interop) ---")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "schema_hash": SCHEMA_HASH[:16] + "...",
        "must_fields": ["agent_id", "model_family", "parameter_count", "quantization",
                        "weight_hash", "hash_algorithm", "declared_at"],
        "typed_hashes": {"weight_hash": "TypedHash<weights>", "runtime_hash": "TypedHash<runtime>"},
        "canonical_form": "JSON, sorted keys, no whitespace, nulls excluded"
    }, indent=2))


if __name__ == "__main__":
    demo()
