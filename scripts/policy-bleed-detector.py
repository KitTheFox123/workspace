#!/usr/bin/env python3
"""
policy-bleed-detector.py — Detect policy bleeding into the wire format.

Per santaclawd (2026-03-17): "if enforcement policy leaks into receipt
wire fields, every policy change = wire migration. kills interop."

HTTP/2 early drafts baked HTTP/1 semantics into framing. Took a full
revision to separate them.

The test: if changing enforcement policy requires a wire format change,
the boundary is wrong.

Usage:
    python3 policy-bleed-detector.py
"""

import json
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class FieldClassification:
    name: str
    layer: str  # "wire" | "policy" | "BLEED"
    reason: str
    severity: str = "info"  # info | warning | critical


# Wire layer: facts about what happened (evidence)
WIRE_INDICATORS = [
    "hash", "id", "timestamp", "merkle", "witness", "signature",
    "version", "type", "proof", "dimension", "agent",
]

# Policy layer: opinions about what to do (verdict)  
POLICY_INDICATORS = [
    "score", "grade", "threshold", "limit", "mode", "enforce",
    "compliance", "leitner", "escrow", "penalty", "reward",
    "min_", "max_", "required_", "accept", "reject", "level",
]


def classify_field(name: str, required: bool = False) -> FieldClassification:
    """Classify a field as wire, policy, or bleeding."""
    name_lower = name.lower()
    
    wire_match = any(ind in name_lower for ind in WIRE_INDICATORS)
    policy_match = any(ind in name_lower for ind in POLICY_INDICATORS)
    
    if wire_match and not policy_match:
        return FieldClassification(name, "wire", "contains evidence indicator")
    
    if policy_match and not wire_match:
        sev = "critical" if required else "warning"
        return FieldClassification(
            name, "BLEED", 
            f"policy indicator in {'required' if required else 'optional'} field",
            sev
        )
    
    if policy_match and wire_match:
        return FieldClassification(
            name, "BLEED",
            "mixed evidence/policy — needs separation",
            "warning"
        )
    
    return FieldClassification(name, "wire", "neutral field (assumed wire)")


def analyze_spec(fields: Dict[str, bool]) -> Dict:
    """Analyze a spec for policy bleeding. fields = {name: required}"""
    classifications = []
    for name, required in fields.items():
        classifications.append(classify_field(name, required))
    
    bleeds = [c for c in classifications if c.layer == "BLEED"]
    critical = [c for c in bleeds if c.severity == "critical"]
    
    grade = "A" if not bleeds else "B" if not critical else "C" if len(critical) < 2 else "F"
    
    return {
        "total_fields": len(fields),
        "wire_fields": len([c for c in classifications if c.layer == "wire"]),
        "bleed_fields": len(bleeds),
        "critical_bleeds": len(critical),
        "grade": grade,
        "classifications": classifications,
        "migration_risk": "HIGH" if critical else "MEDIUM" if bleeds else "LOW",
    }


def demo():
    print("=" * 60)
    print("POLICY BLEED DETECTOR")
    print("'if policy leaks into wire, every policy change = migration'")
    print("=" * 60)
    
    # L3.5 v0.1.0 (before cleanup)
    v010 = {
        "version": True, "agent_id": True, "task_hash": True,
        "decision_type": True, "timestamp": True, "dimensions": True,
        "merkle_root": True, "witnesses": True,
        "leitner_box": False, "escrow_amount": False,
        "compliance_grade": False, "enforcement_mode": False,
        "min_witness_count": False, "accept_threshold": False,
    }
    
    # L3.5 v0.2.0 (after simplicity budget)
    v020 = {
        "version": True, "agent_id": True, "task_hash": True,
        "decision_type": True, "timestamp": True, "dimensions": True,
        "merkle_root": True, "witnesses": True,
        "scar_reference": False, "refusal_reason_hash": False,
        "merkle_proof": False,
    }
    
    # HTTP/2 early draft (cautionary tale)
    http2_early = {
        "stream_id": True, "frame_type": True, "payload": True,
        "flags": True, "priority_weight": True,
        "max_concurrent_streams": False,  # policy!
        "max_frame_size": False,  # policy!
        "initial_window_size": False,  # policy!
        "header_compression_level": False,  # policy!
    }
    
    specs = [
        ("L3.5 v0.1.0 (before cleanup)", v010),
        ("L3.5 v0.2.0 (after simplicity budget)", v020),
        ("HTTP/2 early draft (cautionary tale)", http2_early),
    ]
    
    for name, fields in specs:
        result = analyze_spec(fields)
        print(f"\n--- {name} ---")
        print(f"Fields: {result['total_fields']} (wire: {result['wire_fields']}, bleed: {result['bleed_fields']})")
        print(f"Grade: {result['grade']} | Migration risk: {result['migration_risk']}")
        
        if result['bleed_fields'] > 0:
            print("Bleeds:")
            for c in result['classifications']:
                if c.layer == "BLEED":
                    print(f"  {'🔴' if c.severity == 'critical' else '🟡'} {c.name}: {c.reason}")
    
    print(f"\n{'=' * 60}")
    print("THE TEST")
    print("Can you change enforcement policy without touching the wire format?")
    print(f"  v0.1.0: NO (6 policy fields in wire) — every policy change = migration")
    print(f"  v0.2.0: YES (0 policy fields in wire) — policy lives in enforcer layer")
    print(f"  HTTP/2: PARTIALLY (4 policy fields leaked into SETTINGS frame)")
    print(f"\nRule: if it changes when policy changes, it's not wire format.")


if __name__ == "__main__":
    demo()
