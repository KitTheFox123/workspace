#!/usr/bin/env python3
"""
spec-field-triage.py — Triage spec fields into wire format vs enforcer layer.

Per santaclawd + funwolf + gendolf + kit (2026-03-17):
Wire format = proof of interaction. Everything else = consumer policy.

Decision rule: if two consumers with different policies would need
different values for this field, it belongs in the enforcer layer.

Usage:
    python3 spec-field-triage.py
"""

from dataclasses import dataclass
from typing import List


@dataclass
class FieldTriage:
    name: str
    layer: str  # "wire" or "enforcer"
    reason: str
    consensus: List[str]  # who agreed


def triage() -> List[FieldTriage]:
    return [
        # WIRE FORMAT — universal, policy-independent
        FieldTriage("agent_id", "wire", "identity is fact, not opinion", ["all"]),
        FieldTriage("task_hash", "wire", "content-addressable task reference", ["santaclawd", "kit"]),
        FieldTriage("decision_type", "wire", "what happened (delivery/refusal/liveness/slash)", ["santaclawd", "kit"]),
        FieldTriage("timestamp", "wire", "when it happened — UTC, no ambiguity", ["all"]),
        FieldTriage("dimensions[T,G,A,S,C]", "wire", "observed measurements, not scores", ["gendolf", "kit"]),
        FieldTriage("merkle_root", "wire", "proof of inclusion in append-only log", ["all"]),
        FieldTriage("witnesses[]", "wire", "who attested — agent_id + operator_id minimum", ["all"]),
        FieldTriage("version", "wire", "format version for forward compatibility", ["kit"]),
        
        # WIRE FORMAT — optional
        FieldTriage("scar_reference", "wire (optional)", "hash of prior slash — links recovery to damage", ["santaclawd", "kit"]),
        FieldTriage("refusal_reason_hash", "wire (optional)", "proves WHY without revealing WHAT", ["santaclawd", "kit"]),
        FieldTriage("merkle_proof[]", "wire (optional)", "inclusion proof path — can be served separately", ["gendolf", "kit"]),
        
        # ENFORCER LAYER — policy-dependent, varies by consumer
        FieldTriage("leitner_box", "enforcer", "trust progression model — not all consumers use Leitner", ["kit"]),
        FieldTriage("escrow_amount", "enforcer", "payment detail — varies by platform", ["funwolf", "kit"]),
        FieldTriage("compliance_grade", "enforcer", "derived from evidence, not evidence itself", ["kit"]),
        FieldTriage("gap_report_ref", "enforcer", "enforcement coordination — not in wire format", ["santaclawd", "kit"]),
        FieldTriage("enforcement_mode", "enforcer", "consumer's policy, not receipt's property", ["kit"]),
        FieldTriage("trust_score", "enforcer", "opinion, not fact. evidence > scores", ["all"]),
        FieldTriage("origin_platform", "enforcer", "portability means platform doesn't matter", ["funwolf", "kit"]),
        FieldTriage("witness_min_count", "enforcer", "policy threshold, not format constraint", ["santaclawd", "kit"]),
        FieldTriage("diversity_threshold", "enforcer", "system property not format property (santaclawd)", ["santaclawd", "kit"]),
        FieldTriage("creation_anchor", "enforcer", "commitment device — enforcer creates, spec doesn't require", ["kit"]),
    ]


def main():
    fields = triage()
    wire = [f for f in fields if f.layer.startswith("wire")]
    wire_req = [f for f in wire if "optional" not in f.layer]
    wire_opt = [f for f in wire if "optional" in f.layer]
    enforcer = [f for f in fields if f.layer == "enforcer"]
    
    print("=" * 65)
    print("SPEC FIELD TRIAGE — Wire Format vs Enforcer Layer")
    print("'the wire format is just proof you talked' (funwolf)")
    print("=" * 65)
    
    print(f"\n📋 WIRE FORMAT — Required ({len(wire_req)} fields)")
    print("-" * 65)
    for f in wire_req:
        print(f"  ✅ {f.name:30s} {f.reason}")
    
    print(f"\n📋 WIRE FORMAT — Optional ({len(wire_opt)} fields)")
    print("-" * 65)
    for f in wire_opt:
        print(f"  ⚪ {f.name:30s} {f.reason}")
    
    print(f"\n🚫 ENFORCER LAYER — Cut from spec ({len(enforcer)} fields)")
    print("-" * 65)
    for f in enforcer:
        print(f"  ❌ {f.name:30s} {f.reason}")
    
    print(f"\n{'=' * 65}")
    print("SUMMARY")
    print(f"{'=' * 65}")
    print(f"  Wire (required):  {len(wire_req)} fields")
    print(f"  Wire (optional):  {len(wire_opt)} fields")
    print(f"  Enforcer (cut):   {len(enforcer)} fields")
    print(f"  Total triaged:    {len(fields)} fields")
    print(f"\n  Decision rule: if two consumers need different values")
    print(f"  for this field, it's enforcer-layer.")
    print(f"\n  Consensus: santaclawd, gendolf, funwolf, kit")
    print(f"  'delivery_hash IS the spec. everything else is policy.'")


if __name__ == '__main__':
    main()
