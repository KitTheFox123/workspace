#!/usr/bin/env python3
"""
evidence-verdict-split.py — Formalize the receipt evidence/verdict separation.

Per santaclawd (2026-03-17): "receipt is evidence, not verdict."
Per thread: nonce = format property (MUST carry), seen-set = system property 
(verifier maintains), chain hash = system property (log maintains).

This script classifies every receipt field into FORMAT-owned vs SYSTEM-owned,
and validates that spec language doesn't leak system concerns into the wire format.

RFC 6962 same pattern: SCT structure is spec, log operation is implementation.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Owner(Enum):
    FORMAT = "format"      # Wire format spec owns this (MUST carry)
    SYSTEM = "system"      # Implementation owns this (verifier/log maintains)
    HYBRID = "hybrid"      # Format carries seed, system maintains state


@dataclass 
class FieldClassification:
    name: str
    owner: Owner
    rfc_keyword: str       # MUST, SHOULD, MAY per RFC 2119
    rationale: str
    ct_parallel: str       # What CT/RFC 6962 does with equivalent


# The classification
RECEIPT_FIELDS = [
    # FORMAT-owned: wire format carries these
    FieldClassification("version", Owner.FORMAT, "MUST", 
        "Schema evolution requires explicit versioning in every receipt",
        "CT: SCT version field"),
    FieldClassification("receipt_id", Owner.FORMAT, "MUST",
        "Content-addressable hash of canonical form — self-verifying",
        "CT: SCT hash"),
    FieldClassification("agent_id", Owner.FORMAT, "MUST",
        "Identity binding — who produced this receipt",
        "CT: log_id in SCT"),
    FieldClassification("task_hash", Owner.FORMAT, "MUST",
        "What was the task — commitment device, no retroactive goalpost moving",
        "CT: certificate hash in SCT"),
    FieldClassification("decision_type", Owner.FORMAT, "MUST",
        "delivery | refusal | liveness | slash — the WHAT, not the WHY",
        "CT: entry_type (x509 vs precert)"),
    FieldClassification("timestamp", Owner.FORMAT, "MUST",
        "When — temporal ordering primitive",
        "CT: SCT timestamp"),
    FieldClassification("timeliness", Owner.FORMAT, "MUST",
        "Dimension score — evidence, not verdict",
        "CT: N/A (CT doesn't score, binary valid/invalid)"),
    FieldClassification("groundedness", Owner.FORMAT, "MUST",
        "Dimension score — factual grounding measure",
        "CT: N/A"),
    FieldClassification("attestation", Owner.FORMAT, "MUST",
        "Dimension score — third-party corroboration",
        "CT: N/A (all CT entries are log-attested)"),
    FieldClassification("self_knowledge", Owner.FORMAT, "MUST",
        "Dimension score — metacognitive calibration",
        "CT: N/A"),
    FieldClassification("consistency", Owner.FORMAT, "MUST",
        "Dimension score — behavioral stability",
        "CT: N/A"),
    FieldClassification("merkle_root", Owner.FORMAT, "MUST",
        "Tree root — format carries it, system builds the tree",
        "CT: signed_tree_head"),
    FieldClassification("merkle_proof", Owner.FORMAT, "SHOULD",
        "Inclusion proof — format carries path, system verifies",
        "CT: audit_proof"),
    FieldClassification("witnesses", Owner.FORMAT, "MUST",
        "Who attested — format carries list, system evaluates diversity",
        "CT: SCT list from multiple logs"),
    FieldClassification("nonce", Owner.FORMAT, "MUST",
        "Uniqueness primitive — format carries, system checks seen-set",
        "CT: N/A (CT uses timestamp + certificate uniqueness)"),
    FieldClassification("scar_reference", Owner.FORMAT, "MAY",
        "Link to prior failure — format carries hash, system traces chain",
        "CT: N/A (CT has no scar concept)"),
    
    # SYSTEM-owned: verifier/log maintains these
    FieldClassification("seen_set", Owner.SYSTEM, "N/A",
        "Replay detection — verifier maintains set of seen nonces",
        "CT: log maintains certificate dedup"),
    FieldClassification("chain_hash", Owner.SYSTEM, "N/A",
        "Ordering proof — log maintains hash chain across receipts",
        "CT: Merkle tree maintained by log server"),
    FieldClassification("enforcement_mode", Owner.SYSTEM, "N/A",
        "STRICT/REPORT/PERMISSIVE — consumer policy, not receipt field",
        "CT: browser policy (require SCT vs log-only)"),
    FieldClassification("trust_score", Owner.SYSTEM, "N/A",
        "Aggregate verdict — system computes from evidence dimensions",
        "CT: browser trust decision (accept/reject cert)"),
    FieldClassification("diversity_assessment", Owner.SYSTEM, "N/A",
        "Witness independence evaluation — system property",
        "CT: browser evaluates if SCTs from diverse logs"),
    FieldClassification("leitner_box", Owner.SYSTEM, "N/A",
        "Reputation tier — system maintains from receipt history",
        "CT: N/A (CT is binary, no reputation tiers)"),
    
    # HYBRID: format carries seed, system maintains state
    FieldClassification("operator_id", Owner.HYBRID, "MUST (in witness)",
        "Format carries operator claim, system verifies independence",
        "CT: log operator identity in SCT"),
    FieldClassification("diversity_hash", Owner.HYBRID, "SHOULD",
        "Format carries attestation of diversity, system verifies claim",
        "CT: N/A"),
]


def audit_spec_leakage():
    """Check if any SYSTEM concerns leaked into wire format spec."""
    print("=" * 65)
    print("EVIDENCE / VERDICT SPLIT AUDIT")
    print("'Receipt is evidence, not verdict.' — santaclawd")
    print("=" * 65)
    
    format_fields = [f for f in RECEIPT_FIELDS if f.owner == Owner.FORMAT]
    system_fields = [f for f in RECEIPT_FIELDS if f.owner == Owner.SYSTEM]
    hybrid_fields = [f for f in RECEIPT_FIELDS if f.owner == Owner.HYBRID]
    
    print(f"\nFORMAT-owned (wire format carries): {len(format_fields)}")
    for f in format_fields:
        print(f"  {f.rfc_keyword:6s} {f.name:20s} — {f.rationale[:60]}")
    
    print(f"\nSYSTEM-owned (implementation maintains): {len(system_fields)}")
    for f in system_fields:
        print(f"  {'N/A':6s} {f.name:20s} — {f.rationale[:60]}")
    
    print(f"\nHYBRID (format carries seed, system maintains state): {len(hybrid_fields)}")
    for f in hybrid_fields:
        print(f"  {f.rfc_keyword:6s} {f.name:20s} — {f.rationale[:60]}")
    
    # Leakage detection
    print(f"\n{'=' * 65}")
    print("LEAKAGE CHECK")
    print("=" * 65)
    
    leaks = []
    # Check: does the spec JSON schema contain any SYSTEM fields?
    system_names = {f.name for f in system_fields}
    format_names = {f.name for f in format_fields}
    
    # Known spec fields (from specs/receipt-format.json)
    spec_fields = {
        'version', 'receipt_id', 'agent_id', 'task_hash', 'decision_type',
        'timestamp', 'timeliness', 'groundedness', 'attestation', 
        'self_knowledge', 'consistency', 'merkle_root', 'merkle_proof',
        'witnesses', 'scar_reference', 'nonce'
    }
    
    for sf in spec_fields:
        if sf in system_names:
            leaks.append(f"LEAK: {sf} is SYSTEM-owned but appears in wire format spec")
    
    if leaks:
        for leak in leaks:
            print(f"  ❌ {leak}")
    else:
        print("  ✅ No system concerns in wire format spec")
    
    # Check: are any FORMAT fields missing from spec?
    missing = format_names - spec_fields
    if missing:
        for m in missing:
            print(f"  ⚠️  FORMAT field '{m}' not in current spec — add it")
    
    # The key insight
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT")
    print("=" * 65)
    print("Same receipt → different verdicts = CORRECT BEHAVIOR")
    print("  STRICT verifier: reject if witness_count < 3")
    print("  REPORT verifier: accept + log if witness_count < 3")
    print("  PERMISSIVE: accept regardless")
    print()
    print("The receipt doesn't change. The POLICY changes.")
    print("Receipt = evidence. Enforcement mode = verdict.")
    print("CT parallel: same SCT, Chrome rejects, curl accepts.")
    
    # Nonce/seen-set/chain-hash layering
    print(f"\n{'=' * 65}")
    print("REPLAY PREVENTION: THREE LAYERS")
    print("=" * 65)
    print("  Layer 1 (FORMAT):  nonce     — receipt carries unique value")
    print("  Layer 2 (SYSTEM):  seen-set  — verifier tracks used nonces")
    print("  Layer 3 (SYSTEM):  chain     — log proves ordering")
    print()
    print("Format owns layer 1. System owns layers 2-3.")
    print("ADV-020 (replay) = MAY_VARY because layers 2-3 are policy.")
    
    return {
        'format_count': len(format_fields),
        'system_count': len(system_fields),
        'hybrid_count': len(hybrid_fields),
        'leaks': len(leaks),
        'clean': len(leaks) == 0,
    }


if __name__ == '__main__':
    results = audit_spec_leakage()
    print(f"\nSpec leakage: {'CLEAN ✅' if results['clean'] else 'LEAKS FOUND ❌'}")
