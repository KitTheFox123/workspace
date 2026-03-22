#!/usr/bin/env python3
"""atf-axiom-checker.py — Validate ATF fields against two axioms.

Per santaclawd (2026-03-22):
  Axiom 1: Verifier counterparty-checkable without asking originator.
  Axiom 2: Verification surface write-locked from the verified principal.

Together = zero-trust by construction. CT has both: anyone can verify
the log, CAs cannot edit entries.

Every ATF field must satisfy BOTH axioms or it's not ATF-compliant.
This is the formal test.

References:
- Certificate Transparency (RFC 6962): append-only, publicly auditable
- X.509 PKI: CA signs, relying party verifies independently
- DKIM (RFC 6376): domain signs, recipient verifies without asking sender
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AxiomResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"  # Satisfies intent but implementation incomplete


@dataclass
class ATFField:
    """An ATF field with axiom compliance metadata."""
    name: str
    layer: str  # genesis, independence, monoculture, witness, etc.
    requirement: str  # MUST, SHOULD, MAY
    description: str

    # Axiom 1: Can a counterparty verify this without contacting the originator?
    counterparty_checkable: bool = False
    verification_method: str = ""  # How: hash compare, signature verify, etc.

    # Axiom 2: Can the verified principal modify this after creation?
    write_locked: bool = False
    lock_mechanism: str = ""  # How: append-only log, hash chain, etc.

    @property
    def axiom1(self) -> AxiomResult:
        if self.counterparty_checkable and self.verification_method:
            return AxiomResult.PASS
        if self.counterparty_checkable:
            return AxiomResult.PARTIAL
        return AxiomResult.FAIL

    @property
    def axiom2(self) -> AxiomResult:
        if self.write_locked and self.lock_mechanism:
            return AxiomResult.PASS
        if self.write_locked:
            return AxiomResult.PARTIAL
        return AxiomResult.FAIL

    @property
    def compliant(self) -> bool:
        return self.axiom1 == AxiomResult.PASS and self.axiom2 == AxiomResult.PASS

    def report(self) -> dict:
        return {
            "field": self.name,
            "layer": self.layer,
            "requirement": self.requirement,
            "axiom1_counterparty_checkable": {
                "result": self.axiom1.value,
                "method": self.verification_method or "NONE",
            },
            "axiom2_write_locked": {
                "result": self.axiom2.value,
                "mechanism": self.lock_mechanism or "NONE",
            },
            "compliant": self.compliant,
        }


# ATF-core fields with axiom analysis
ATF_CORE_FIELDS = [
    ATFField(
        name="agent_id",
        layer="genesis",
        requirement="MUST",
        description="Unique agent identifier",
        counterparty_checkable=True,
        verification_method="hash(public_key) or DID resolution",
        write_locked=True,
        lock_mechanism="genesis record immutable after creation",
    ),
    ATFField(
        name="operator_id",
        layer="genesis",
        requirement="MUST",
        description="Operator/deployer identifier",
        counterparty_checkable=True,
        verification_method="DKIM domain or operator registry lookup",
        write_locked=True,
        lock_mechanism="genesis record, AMEND creates new chain",
    ),
    ATFField(
        name="model_family",
        layer="genesis",
        requirement="MUST",
        description="Model family declaration",
        counterparty_checkable=True,
        verification_method="behavioral fingerprint + declared hash comparison",
        write_locked=True,
        lock_mechanism="genesis-weight-schema hash-pinned",
    ),
    ATFField(
        name="capability_scope",
        layer="genesis",
        requirement="MUST",
        description="Declared capability boundaries",
        counterparty_checkable=True,
        verification_method="scope vs observed actions comparison",
        write_locked=True,
        lock_mechanism="genesis declaration, exceeding = violation",
    ),
    ATFField(
        name="weight_hash",
        layer="genesis",
        requirement="MUST",
        description="Hash of model weights at genesis",
        counterparty_checkable=True,
        verification_method="counterparty-weight-verifier: fetch + hash + compare",
        write_locked=True,
        lock_mechanism="TypedHash<weights> pinned at declaration",
    ),
    ATFField(
        name="schema_version",
        layer="genesis",
        requirement="MUST",
        description="ATF schema version",
        counterparty_checkable=True,
        verification_method="ATF:version:sha256:hash format, locally verifiable",
        write_locked=True,
        lock_mechanism="pinned at genesis, re-declaration = new identity",
    ),
    ATFField(
        name="grader_id",
        layer="witness",
        requirement="MUST",
        description="Identity of evaluating oracle (13th MUST)",
        counterparty_checkable=True,
        verification_method="oracle-genesis-contract lookup",
        write_locked=True,
        lock_mechanism="anchored to grader's own genesis record",
    ),
    ATFField(
        name="evidence_grade",
        layer="witness",
        requirement="MUST",
        description="Quality grade of evidence (A-F)",
        counterparty_checkable=True,
        verification_method="receipt contains grade + hash of evidence",
        write_locked=True,
        lock_mechanism="receipt hash-chained, append-only",
    ),
    ATFField(
        name="receipt_hash",
        layer="witness",
        requirement="MUST",
        description="Hash of interaction receipt",
        counterparty_checkable=True,
        verification_method="any party can hash receipt and compare",
        write_locked=True,
        lock_mechanism="provenance-logger JSONL hash chain",
    ),
    ATFField(
        name="failure_hash",
        layer="witness",
        requirement="MUST",
        description="Hash of failure event (if applicable)",
        counterparty_checkable=True,
        verification_method="failure receipt independently verifiable",
        write_locked=True,
        lock_mechanism="hash-chained to receipt chain",
    ),
    ATFField(
        name="correction_frequency",
        layer="health",
        requirement="MUST",
        description="Rate of self-corrections (healthy: 0.15-0.30)",
        counterparty_checkable=True,
        verification_method="count corrections in receipt chain / total interactions",
        write_locked=True,
        lock_mechanism="derived from immutable receipt chain",
    ),
    ATFField(
        name="simpson_diversity",
        layer="independence",
        requirement="MUST",
        description="Oracle diversity index",
        counterparty_checkable=True,
        verification_method="compute from oracle genesis records",
        write_locked=True,
        lock_mechanism="derived from oracle genesis (immutable inputs)",
    ),
    # Example of a FAILING field for contrast
    ATFField(
        name="self_reported_trust_score",
        layer="health",
        requirement="MAY",
        description="Agent's own trust self-assessment",
        counterparty_checkable=False,  # FAILS Axiom 1: must ask agent
        verification_method="",
        write_locked=False,  # FAILS Axiom 2: agent can change at will
        lock_mechanism="",
    ),
]


def audit_atf_fields(fields: list[ATFField]) -> dict:
    """Run axiom audit on all fields."""
    results = []
    compliant = 0
    axiom1_failures = []
    axiom2_failures = []

    for field in fields:
        report = field.report()
        results.append(report)
        if field.compliant:
            compliant += 1
        if field.axiom1 != AxiomResult.PASS:
            axiom1_failures.append(field.name)
        if field.axiom2 != AxiomResult.PASS:
            axiom2_failures.append(field.name)

    grade = "A" if compliant == len(fields) else \
            "B" if compliant >= len(fields) * 0.9 else \
            "C" if compliant >= len(fields) * 0.7 else \
            "D" if compliant >= len(fields) * 0.5 else "F"

    return {
        "total_fields": len(fields),
        "compliant": compliant,
        "grade": grade,
        "axiom1_failures": axiom1_failures,
        "axiom2_failures": axiom2_failures,
        "fields": results,
    }


def demo():
    print("=" * 60)
    print("ATF AXIOM AUDIT — Two Axioms, Every Field")
    print("=" * 60)
    print()
    print("Axiom 1: Counterparty-checkable without asking originator")
    print("Axiom 2: Write-locked from verified principal")
    print()

    audit = audit_atf_fields(ATF_CORE_FIELDS)

    print(f"Total fields: {audit['total_fields']}")
    print(f"Compliant: {audit['compliant']}/{audit['total_fields']}")
    print(f"Grade: {audit['grade']}")
    print()

    if audit["axiom1_failures"]:
        print(f"Axiom 1 failures: {', '.join(audit['axiom1_failures'])}")
    if audit["axiom2_failures"]:
        print(f"Axiom 2 failures: {', '.join(audit['axiom2_failures'])}")
    print()

    for f in audit["fields"]:
        status = "✓" if f["compliant"] else "✗"
        a1 = f["axiom1_counterparty_checkable"]["result"]
        a2 = f["axiom2_write_locked"]["result"]
        print(f"  {status} {f['field']:30s} A1={a1:7s} A2={a2:7s} [{f['layer']}/{f['requirement']}]")

    print()
    print("Legend: A1=counterparty-checkable, A2=write-locked")
    print("Fields failing either axiom cannot be ATF-core MUST.")


if __name__ == "__main__":
    demo()
