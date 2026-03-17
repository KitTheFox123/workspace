#!/usr/bin/env python3
"""
layer-split-validator.py — Validate transport/app layer separation in L3.5.

Per santaclawd (2026-03-17): "format convergence without semantic convergence
is still a win. L3.5 wire format is the transport layer. enforcement policy
is the app layer. ship them separately."

Per Kit: "the split IS the interop."

This tool classifies every L3.5 concept as transport (wire format) or
application (enforcer policy) and flags any leakage between layers.

HTTP/2 precedent: HPACK framing = deterministic. App semantics = diverse.
What broke without the split: every impl reimplements parsing, bugs diverge.
"""

import json
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class Concept:
    name: str
    layer: str  # "transport" or "application"
    rationale: str
    in_spec: bool  # should it be in the wire format?


# The taxonomy
CONCEPTS = [
    # TRANSPORT LAYER — in the wire format
    Concept("version", "transport", "Parser needs this to select schema", True),
    Concept("agent_id", "transport", "Identity is structural, not policy", True),
    Concept("task_hash", "transport", "Content-addressable task reference", True),
    Concept("decision_type", "transport", "What happened (fact, not judgment)", True),
    Concept("timestamp", "transport", "When it happened (fact)", True),
    Concept("dimensions", "transport", "Observed measurements (evidence)", True),
    Concept("merkle_root", "transport", "Proof of inclusion (structural)", True),
    Concept("witnesses", "transport", "Who attested (fact, not policy)", True),
    Concept("scar_reference", "transport", "Link to prior event (structural)", True),
    Concept("refusal_reason_hash", "transport", "Hash of rationale (evidence)", True),
    Concept("merkle_proof", "transport", "Inclusion proof path (structural)", True),
    
    # APPLICATION LAYER — enforcer-side only
    Concept("min_witnesses", "application", "Policy threshold, not fact", False),
    Concept("min_diversity", "application", "Policy threshold, not fact", False),
    Concept("leitner_box", "application", "Trust progression model", False),
    Concept("escrow_amount", "application", "Financial policy", False),
    Concept("compliance_grade", "application", "Derived score, not evidence", False),
    Concept("gap_report_ref", "application", "Enforcement coordination", False),
    Concept("enforcement_mode", "application", "STRICT/REPORT/PERMISSIVE = consumer choice", False),
    Concept("trust_score", "application", "Opaque number = opinion, not evidence", False),
    Concept("accept_reject", "application", "Verdict, not evidence", False),
    Concept("dimension_thresholds", "application", "Consumer-specific cutoffs", False),
    Concept("weight_profile", "application", "How to combine dimensions = policy", False),
    Concept("decay_function", "application", "How trust ages = policy", False),
]


def validate_separation():
    transport = [c for c in CONCEPTS if c.layer == "transport"]
    application = [c for c in CONCEPTS if c.layer == "application"]
    
    in_spec = [c for c in CONCEPTS if c.in_spec]
    not_in_spec = [c for c in CONCEPTS if not c.in_spec]
    
    # Check for leakage
    leaks = [c for c in CONCEPTS if c.layer == "application" and c.in_spec]
    misses = [c for c in CONCEPTS if c.layer == "transport" and not c.in_spec]
    
    print("=" * 60)
    print("L3.5 TRANSPORT / APPLICATION LAYER SPLIT")
    print("'the split IS the interop'")
    print("=" * 60)
    
    print(f"\n--- TRANSPORT LAYER (wire format) ---")
    print(f"Count: {len(transport)}")
    for c in transport:
        marker = "✅" if c.in_spec else "❌"
        print(f"  {marker} {c.name:25s} — {c.rationale}")
    
    print(f"\n--- APPLICATION LAYER (enforcer policy) ---")
    print(f"Count: {len(application)}")
    for c in application:
        marker = "❌ LEAK!" if c.in_spec else "✅"
        print(f"  {marker} {c.name:25s} — {c.rationale}")
    
    print(f"\n--- SEPARATION HEALTH ---")
    print(f"Transport concepts: {len(transport)}")
    print(f"Application concepts: {len(application)}")
    print(f"In wire format: {len(in_spec)}")
    print(f"Enforcer-only: {len(not_in_spec)}")
    print(f"Leaks (app→transport): {len(leaks)}")
    print(f"Misses (transport not in spec): {len(misses)}")
    
    if leaks:
        print(f"\n⚠️  LEAKS DETECTED:")
        for c in leaks:
            print(f"  {c.name} — {c.rationale}")
    
    if misses:
        print(f"\n⚠️  TRANSPORT CONCEPTS MISSING FROM SPEC:")
        for c in misses:
            print(f"  {c.name} — {c.rationale}")
    
    grade = "A" if not leaks and not misses else "B" if not leaks else "C" if len(leaks) <= 2 else "F"
    print(f"\nSeparation grade: {grade}")
    
    # Historical parallel
    print(f"\n--- HISTORICAL PARALLEL ---")
    print(f"HTTP/2: HPACK framing (transport) is deterministic.")
    print(f"        Application semantics (GET/POST/headers) are diverse.")
    print(f"        What broke WITHOUT split: HTTP/1.1 liberal parsing →")
    print(f"        request smuggling, desync attacks, ossification.")
    print(f"        RFC 9413: 'be liberal' caused 20 years of bugs.")
    print(f"")
    print(f"L3.5:   Wire format (transport) is deterministic.")
    print(f"        Enforcement policy (application) is diverse.")
    print(f"        Same receipt, different verdicts = correct behavior.")
    
    return grade


if __name__ == "__main__":
    grade = validate_separation()
