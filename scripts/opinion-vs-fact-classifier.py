#!/usr/bin/env python3
"""
opinion-vs-fact-classifier.py — Classify receipt fields as opinion or fact.

Per santaclawd + gendolf (2026-03-17): "scores are opinions, attestations are facts."
Per Watson & Morgan: testimony = 1x weight, observation = 2x weight.

This tool audits a receipt schema and classifies every field as:
- FACT: cryptographically verifiable, platform-independent
- OPINION: interpretation-dependent, policy-specific
- DERIVED: computed from facts (verifiable but not primary)

Fields classified as OPINION must NOT be in the wire format.
They belong in the verdict/enforcer layer.

Usage:
    python3 opinion-vs-fact-classifier.py
"""

import json
from dataclasses import dataclass
from typing import List, Dict
from enum import Enum


class FieldClass(Enum):
    FACT = "FACT"           # Cryptographically verifiable
    OPINION = "OPINION"     # Interpretation-dependent
    DERIVED = "DERIVED"     # Computed from facts
    METADATA = "METADATA"   # Structural, neither fact nor opinion


@dataclass
class FieldAudit:
    name: str
    classification: FieldClass
    verifiable_by: str  # who/what can verify this
    weight: float       # Watson & Morgan epistemic weight
    in_wire_format: bool  # SHOULD it be in the spec?
    reason: str


def audit_l35_receipt() -> List[FieldAudit]:
    """Classify every L3.5 receipt field."""
    return [
        # FACTS — belong in wire format
        FieldAudit("agent_id", FieldClass.FACT,
                   "public key / DID resolution", 2.0, True,
                   "Cryptographic identity. Verifiable by anyone."),
        FieldAudit("task_hash", FieldClass.FACT,
                   "SHA-256 of task description", 2.0, True,
                   "Content-addressable. Hash is the proof."),
        FieldAudit("decision_type", FieldClass.FACT,
                   "agent action log", 2.0, True,
                   "What happened: delivery/refusal/liveness/slash. Observable."),
        FieldAudit("timestamp", FieldClass.FACT,
                   "witness co-signatures", 2.0, True,
                   "When it happened. Witnesses attest to temporal claims."),
        FieldAudit("merkle_root", FieldClass.FACT,
                   "independent tree reconstruction", 2.0, True,
                   "Cryptographic commitment. Anyone can verify inclusion."),
        FieldAudit("merkle_proof", FieldClass.FACT,
                   "hash chain verification", 2.0, True,
                   "Inclusion proof. Math, not trust."),
        FieldAudit("witnesses[]", FieldClass.FACT,
                   "witness public keys + signatures", 2.0, True,
                   "Who attested. Signatures are facts."),
        FieldAudit("witness.operator_id", FieldClass.FACT,
                   "operator registry / DID", 2.0, True,
                   "Organizational independence. Verifiable."),
        FieldAudit("refusal_reason", FieldClass.FACT,
                   "hash of rationale document", 2.0, True,
                   "What was refused and why. Hash proves existence without revealing content."),
        FieldAudit("scar_reference", FieldClass.FACT,
                   "previous receipt hash", 2.0, True,
                   "Link to prior failure. Content-addressable pointer."),
        
        # DERIVED — computed from facts, verifiable
        FieldAudit("receipt_id", FieldClass.DERIVED,
                   "SHA-256 of canonical JSON", 1.5, True,
                   "Content-addressable ID. Derived from all facts."),
        FieldAudit("witness_count", FieldClass.DERIVED,
                   "count of witnesses array", 1.5, False,
                   "Trivially derived. Don't duplicate data."),
        FieldAudit("diversity_score", FieldClass.DERIVED,
                   "unique operator_ids / total witnesses", 1.5, False,
                   "Computable from witness array. Enforcer-layer."),
        
        # DIMENSIONS — the tricky middle ground
        FieldAudit("timeliness", FieldClass.FACT,
                   "timestamp delta vs deadline", 2.0, True,
                   "Measurable: did it arrive on time? Binary underneath."),
        FieldAudit("groundedness", FieldClass.OPINION,
                   "evaluator judgment", 1.0, False,
                   "Quality assessment. Different evaluators, different scores."),
        FieldAudit("attestation", FieldClass.DERIVED,
                   "witness signatures present", 1.5, False,
                   "Derived from witness array. Don't score what you can count."),
        FieldAudit("self_knowledge", FieldClass.OPINION,
                   "evaluator judgment", 1.0, False,
                   "Did the agent know its limits? Interpretation-dependent."),
        FieldAudit("consistency", FieldClass.DERIVED,
                   "comparison with prior receipts", 1.5, False,
                   "Derived from receipt history. Not a single-receipt property."),
        
        # OPINIONS — must NOT be in wire format
        FieldAudit("trust_score", FieldClass.OPINION,
                   "consumer policy", 1.0, False,
                   "Aggregate score. Policy-dependent. THE classic opinion."),
        FieldAudit("compliance_grade", FieldClass.OPINION,
                   "enforcement policy", 1.0, False,
                   "A-F grading. Different enforcers, different grades."),
        FieldAudit("enforcement_mode", FieldClass.OPINION,
                   "consumer configuration", 1.0, False,
                   "STRICT/REPORT/PERMISSIVE. Consumer choice, not fact."),
        FieldAudit("leitner_box", FieldClass.OPINION,
                   "consumer trust model", 1.0, False,
                   "Where in the trust ladder. Consumer-specific progression."),
        FieldAudit("escrow_amount", FieldClass.OPINION,
                   "platform pricing", 1.0, False,
                   "How much to escrow. Platform-specific economics."),
        FieldAudit("risk_level", FieldClass.OPINION,
                   "consumer risk model", 1.0, False,
                   "HIGH/MEDIUM/LOW. Consumer's risk appetite decides."),
    ]


def main():
    fields = audit_l35_receipt()
    
    facts = [f for f in fields if f.classification == FieldClass.FACT]
    derived = [f for f in fields if f.classification == FieldClass.DERIVED]
    opinions = [f for f in fields if f.classification == FieldClass.OPINION]
    
    print("=" * 65)
    print("OPINION vs FACT CLASSIFIER — L3.5 Receipt Schema Audit")
    print("'scores are opinions, attestations are facts' (santaclawd)")
    print("=" * 65)
    
    print(f"\n── FACTS ({len(facts)}) — wire format ──")
    print(f"{'Field':<25} {'Weight':>6} {'Wire':>5}  Verified by")
    print("-" * 65)
    for f in facts:
        wire = "✓" if f.in_wire_format else "✗"
        print(f"{f.name:<25} {f.weight:>5.1f}x {wire:>5}  {f.verifiable_by}")
    
    print(f"\n── DERIVED ({len(derived)}) — computable from facts ──")
    for f in derived:
        wire = "✓" if f.in_wire_format else "✗"
        print(f"{f.name:<25} {f.weight:>5.1f}x {wire:>5}  {f.reason}")
    
    print(f"\n── OPINIONS ({len(opinions)}) — enforcer layer ONLY ──")
    for f in opinions:
        wire = "✓" if f.in_wire_format else "✗"
        print(f"{f.name:<25} {f.weight:>5.1f}x {wire:>5}  ⚠️  {f.reason}")
    
    # The hard finding
    print(f"\n{'=' * 65}")
    print("KEY FINDING: dimensions are mixed")
    print("-" * 65)
    dims = [f for f in fields if f.name in ('timeliness', 'groundedness', 'attestation', 'self_knowledge', 'consistency')]
    for d in dims:
        print(f"  {d.name:<20} → {d.classification.value:<8} ({d.reason[:60]})")
    
    print(f"\nOf 5 dimensions:")
    dim_facts = sum(1 for d in dims if d.classification == FieldClass.FACT)
    dim_derived = sum(1 for d in dims if d.classification == FieldClass.DERIVED)
    dim_opinions = sum(1 for d in dims if d.classification == FieldClass.OPINION)
    print(f"  {dim_facts} FACT (timeliness)")
    print(f"  {dim_derived} DERIVED (attestation, consistency)")  
    print(f"  {dim_opinions} OPINION (groundedness, self_knowledge)")
    
    print(f"\nIMPLICATION: Only timeliness belongs in the wire format as-is.")
    print(f"groundedness and self_knowledge are evaluator judgments = opinions.")
    print(f"The wire format should carry RAW OBSERVATIONS, not scores.")
    print(f"Let consumers score. Receipt carries evidence.")
    
    # Summary stats
    wire_facts = sum(1 for f in fields if f.in_wire_format and f.classification == FieldClass.FACT)
    wire_opinions = sum(1 for f in fields if f.in_wire_format and f.classification == FieldClass.OPINION)
    
    print(f"\n{'=' * 65}")
    print(f"WIRE FORMAT HEALTH")
    print(f"  Facts in wire: {wire_facts}")
    print(f"  Opinions in wire: {wire_opinions} {'✓ clean' if wire_opinions == 0 else '⚠️ CONTAMINATED'}")
    print(f"  Avg epistemic weight: {sum(f.weight for f in fields if f.in_wire_format) / max(sum(1 for f in fields if f.in_wire_format), 1):.2f}x")
    print(f"{'=' * 65}")


if __name__ == '__main__':
    main()
