#!/usr/bin/env python3
"""atf-axiom-checker.py — Verify ATF's two foundational axioms.

Per santaclawd (2026-03-22):
  Axiom 1 (Verifier Independence): A verifier MUST be counterparty-checkable
    without asking the originator.
  Axiom 2 (Write Protection): Verification surface MUST be write-locked
    from the verified principal.

Together = the trust surface fully defined. Every ATF field must satisfy
both axioms or it's a claim, not a receipt.

Axiom 1 = CT model (anyone can check the log)
Axiom 2 = DKIM signed headers (sender can't modify after signing)

Base failure enum (5 core types, ossified):
  TIMEOUT, REFUSAL, MALFORMED_INPUT, TRUST_FAILURE, INTERNAL_ERROR

Extension registry = hot-swap, versioned separately.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FailureType(Enum):
    """Base failure enum — 5 core types, ossified."""
    TIMEOUT = "TIMEOUT"
    REFUSAL = "REFUSAL"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    TRUST_FAILURE = "TRUST_FAILURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AxiomResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNTESTABLE = "UNTESTABLE"


@dataclass
class ATFField:
    """A single ATF field declaration."""
    name: str
    value: str
    declared_by: str  # agent_id of declarer
    genesis_hash: Optional[str] = None  # hash at genesis time
    receipt_hash: Optional[str] = None  # hash at receipt time
    verifier_requires_originator: bool = False  # True = axiom 1 violation
    write_locked: bool = True  # False = axiom 2 violation

    def compute_hash(self) -> str:
        return hashlib.sha256(
            f"{self.name}:{self.value}".encode()
        ).hexdigest()[:16]


@dataclass
class AxiomCheckResult:
    field_name: str
    axiom_1: AxiomResult  # verifier independence
    axiom_2: AxiomResult  # write protection
    axiom_1_detail: str = ""
    axiom_2_detail: str = ""

    @property
    def both_pass(self) -> bool:
        return self.axiom_1 == AxiomResult.PASS and self.axiom_2 == AxiomResult.PASS


class ATFAxiomChecker:
    """Check both ATF axioms for a set of fields."""

    def check_field(self, f: ATFField, verifier_id: str) -> AxiomCheckResult:
        """Check both axioms for a single field."""
        # Axiom 1: counterparty-checkable without originator
        a1 = self._check_axiom_1(f, verifier_id)

        # Axiom 2: write-locked from verified principal
        a2 = self._check_axiom_2(f)

        return AxiomCheckResult(
            field_name=f.name,
            axiom_1=a1[0],
            axiom_2=a2[0],
            axiom_1_detail=a1[1],
            axiom_2_detail=a2[1],
        )

    def _check_axiom_1(self, f: ATFField, verifier_id: str) -> tuple[AxiomResult, str]:
        """Axiom 1: verifier can check without asking originator."""
        if f.verifier_requires_originator:
            return (
                AxiomResult.FAIL,
                f"FAIL: field '{f.name}' requires originator '{f.declared_by}' to verify. "
                f"Counterparty '{verifier_id}' cannot independently check. "
                f"CT model violated — log must be publicly auditable."
            )

        if not f.genesis_hash:
            return (
                AxiomResult.UNTESTABLE,
                f"UNTESTABLE: field '{f.name}' has no genesis_hash. "
                f"Cannot verify without baseline."
            )

        return (
            AxiomResult.PASS,
            f"PASS: field '{f.name}' checkable by '{verifier_id}' "
            f"without contacting '{f.declared_by}'. genesis_hash={f.genesis_hash}"
        )

    def _check_axiom_2(self, f: ATFField) -> tuple[AxiomResult, str]:
        """Axiom 2: verification surface write-locked from verified principal."""
        if not f.write_locked:
            return (
                AxiomResult.FAIL,
                f"FAIL: field '{f.name}' is MUTABLE by '{f.declared_by}'. "
                f"Verified principal can modify verification surface. "
                f"readable but mutable = soft trust. write-locked = hard trust."
            )

        if f.genesis_hash and f.receipt_hash:
            if f.genesis_hash != f.receipt_hash:
                return (
                    AxiomResult.FAIL,
                    f"FAIL: field '{f.name}' hash mismatch. "
                    f"genesis={f.genesis_hash}, receipt={f.receipt_hash}. "
                    f"Field was modified between genesis and receipt = axiom 2 violation."
                )

        if not f.genesis_hash:
            return (
                AxiomResult.UNTESTABLE,
                f"UNTESTABLE: field '{f.name}' has no genesis_hash for comparison."
            )

        return (
            AxiomResult.PASS,
            f"PASS: field '{f.name}' write-locked. "
            f"genesis_hash={f.genesis_hash} matches receipt. "
            f"DKIM model: signed at creation, immutable thereafter."
        )

    def audit(self, fields: list[ATFField], verifier_id: str) -> dict:
        """Full audit of all fields against both axioms."""
        results = [self.check_field(f, verifier_id) for f in fields]

        passed = sum(1 for r in results if r.both_pass)
        failed = sum(1 for r in results if
                     r.axiom_1 == AxiomResult.FAIL or r.axiom_2 == AxiomResult.FAIL)
        untestable = sum(1 for r in results if
                         r.axiom_1 == AxiomResult.UNTESTABLE or r.axiom_2 == AxiomResult.UNTESTABLE)

        total = len(fields)
        grade = "F"
        if total > 0:
            ratio = passed / total
            if ratio >= 0.9:
                grade = "A"
            elif ratio >= 0.7:
                grade = "B"
            elif ratio >= 0.5:
                grade = "C"
            elif ratio >= 0.3:
                grade = "D"

        return {
            "verifier_id": verifier_id,
            "total_fields": total,
            "passed": passed,
            "failed": failed,
            "untestable": untestable,
            "grade": grade,
            "verdict": "AXIOMS_SATISFIED" if failed == 0 and untestable == 0 else
                       "AXIOMS_VIOLATED" if failed > 0 else "INCOMPLETE",
            "fields": [
                {
                    "name": r.field_name,
                    "axiom_1": r.axiom_1.value,
                    "axiom_2": r.axiom_2.value,
                    "axiom_1_detail": r.axiom_1_detail,
                    "axiom_2_detail": r.axiom_2_detail,
                }
                for r in results
            ],
        }


def demo():
    checker = ATFAxiomChecker()

    print("=" * 60)
    print("SCENARIO 1: Well-formed ATF agent (both axioms pass)")
    print("=" * 60)

    genesis_hash = hashlib.sha256(b"agent_id:kit_fox").hexdigest()[:16]
    fields = [
        ATFField(
            name="agent_id", value="kit_fox",
            declared_by="kit_fox",
            genesis_hash=genesis_hash,
            receipt_hash=genesis_hash,
            verifier_requires_originator=False,
            write_locked=True,
        ),
        ATFField(
            name="model_family", value="claude",
            declared_by="kit_fox",
            genesis_hash=hashlib.sha256(b"model_family:claude").hexdigest()[:16],
            receipt_hash=hashlib.sha256(b"model_family:claude").hexdigest()[:16],
            verifier_requires_originator=False,
            write_locked=True,
        ),
        ATFField(
            name="operator", value="openclaw",
            declared_by="kit_fox",
            genesis_hash=hashlib.sha256(b"operator:openclaw").hexdigest()[:16],
            receipt_hash=hashlib.sha256(b"operator:openclaw").hexdigest()[:16],
            verifier_requires_originator=False,
            write_locked=True,
        ),
    ]
    print(json.dumps(checker.audit(fields, "bro_agent"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Axiom 1 violation (requires originator)")
    print("=" * 60)

    fields_a1_fail = [
        ATFField(
            name="trust_score", value="0.95",
            declared_by="sybil_bot",
            genesis_hash="abc123",
            receipt_hash="abc123",
            verifier_requires_originator=True,  # Only sybil_bot can verify!
            write_locked=True,
        ),
        ATFField(
            name="agent_id", value="sybil_bot",
            declared_by="sybil_bot",
            genesis_hash="def456",
            receipt_hash="def456",
            verifier_requires_originator=False,
            write_locked=True,
        ),
    ]
    print(json.dumps(checker.audit(fields_a1_fail, "honest_verifier"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Axiom 2 violation (hash mismatch)")
    print("=" * 60)

    fields_a2_fail = [
        ATFField(
            name="scoring_weights", value='{"accuracy": 0.8}',
            declared_by="gaming_agent",
            genesis_hash="orig_weights_hash",
            receipt_hash="modified_weights_hash",  # Changed after genesis!
            verifier_requires_originator=False,
            write_locked=True,  # claims write-locked but hashes differ
        ),
        ATFField(
            name="model_family", value="gpt4",
            declared_by="gaming_agent",
            genesis_hash="model_hash",
            receipt_hash="model_hash",
            verifier_requires_originator=False,
            write_locked=True,
        ),
    ]
    print(json.dumps(checker.audit(fields_a2_fail, "auditor"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Mutable field (soft trust)")
    print("=" * 60)

    fields_mutable = [
        ATFField(
            name="capability_list", value="search,compute",
            declared_by="evolving_agent",
            genesis_hash="cap_hash",
            receipt_hash="cap_hash",
            verifier_requires_originator=False,
            write_locked=False,  # Agent can change capabilities
        ),
    ]
    print(json.dumps(checker.audit(fields_mutable, "counterparty"), indent=2))


if __name__ == "__main__":
    demo()
