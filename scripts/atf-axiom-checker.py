#!/usr/bin/env python3
"""atf-axiom-checker.py — ATF axiom compliance checker.

Two axioms define the ATF trust model (per santaclawd thread, Mar 22):

Axiom 1: VERIFIER-INDEPENDENCE
  A verifier MUST be checkable by counterparty without asking the
  originating agent. The architecture property IS the independence.
  CT logs are verifiable without asking Google. DKIM is verifiable
  without asking the sender.

Axiom 2: WRITE-PROTECTION
  The verification surface MUST be write-locked from the verified
  principal. An agent cannot modify its own trust score. A grader
  cannot modify the evidence it grades. Separation of concerns
  at the data layer.

Every ATF field must satisfy both axioms or fail ATF-core compliance.

Also: error_type taxonomy (option 3 from thread):
  Base enum ossifies. Extension points via X- prefix.
  HTTP status codes model: 4xx/5xx frozen, custom codes allowed.

Vocabulary cadence vs verifier cadence (IETF lesson):
  Field names freeze at registry_hash.
  Verifier logic evolves per schema_version.
  Two clocks, one protocol.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AxiomResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"  # One axiom passes, one fails


class ErrorType(Enum):
    """ATF-core base error enum (option 3: versioned + extensible)."""
    TIMEOUT = "TIMEOUT"
    REFUSAL = "REFUSAL"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    TRUST_FAILURE = "TRUST_FAILURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if error type is valid (base enum or X- extension)."""
        if value.startswith("X-"):
            return True  # Extension point
        return value in cls._value2member_map_


@dataclass
class FieldAxiomCheck:
    """Check a single ATF field against both axioms."""
    field_name: str
    layer: str  # genesis, attestation, drift, revocation, composition, transport, policy, dispute

    # Axiom 1: Verifier-independence
    counterparty_verifiable: bool = False  # Can counterparty verify without asking agent?
    verification_method: str = ""  # How: hash_compare, signature_check, log_lookup, receipt_chain
    requires_agent_cooperation: bool = True  # If True, fails axiom 1

    # Axiom 2: Write-protection
    write_locked: bool = False  # Is field write-locked from verified principal?
    writer: str = ""  # Who writes: agent, counterparty, oracle, system
    verified_by: str = ""  # Who verifies: counterparty, oracle, auditor
    writer_is_verifier: bool = False  # If True, fails axiom 2

    @property
    def axiom1_result(self) -> AxiomResult:
        """Verifier-independence: counterparty checks without asking."""
        if self.counterparty_verifiable and not self.requires_agent_cooperation:
            return AxiomResult.PASS
        return AxiomResult.FAIL

    @property
    def axiom2_result(self) -> AxiomResult:
        """Write-protection: verified principal cannot modify verification surface."""
        if self.write_locked and not self.writer_is_verifier:
            return AxiomResult.PASS
        return AxiomResult.FAIL

    @property
    def overall(self) -> AxiomResult:
        a1 = self.axiom1_result
        a2 = self.axiom2_result
        if a1 == AxiomResult.PASS and a2 == AxiomResult.PASS:
            return AxiomResult.PASS
        if a1 == AxiomResult.FAIL and a2 == AxiomResult.FAIL:
            return AxiomResult.FAIL
        return AxiomResult.PARTIAL

    def report(self) -> dict:
        return {
            "field": self.field_name,
            "layer": self.layer,
            "axiom1_verifier_independence": self.axiom1_result.value,
            "axiom2_write_protection": self.axiom2_result.value,
            "overall": self.overall.value,
            "details": {
                "verification_method": self.verification_method,
                "writer": self.writer,
                "verified_by": self.verified_by,
            },
        }


@dataclass
class CadenceCheck:
    """Vocabulary cadence vs verifier cadence distinction."""
    vocabulary_version: str  # registry_hash — frozen
    verifier_version: str  # schema_version — evolves
    vocabulary_fields_changed: bool = False  # Should be False after freeze
    verifier_logic_changed: bool = False  # Can be True

    @property
    def compliant(self) -> bool:
        """Vocabulary frozen, verifier can evolve."""
        return not self.vocabulary_fields_changed

    def report(self) -> dict:
        return {
            "vocabulary_version": self.vocabulary_version,
            "verifier_version": self.verifier_version,
            "vocabulary_frozen": not self.vocabulary_fields_changed,
            "verifier_evolved": self.verifier_logic_changed,
            "compliant": self.compliant,
            "note": "Two clocks, one protocol. IETF lesson: SMTP fields frozen since RFC 822, DKIM methods evolve.",
        }


def check_atf_core_fields() -> list[FieldAxiomCheck]:
    """Define all ATF-core MUST fields with axiom checks."""
    return [
        # Genesis layer
        FieldAxiomCheck(
            field_name="soul_hash",
            layer="genesis",
            counterparty_verifiable=True,
            verification_method="hash_compare",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="agent",
            verified_by="counterparty",
        ),
        FieldAxiomCheck(
            field_name="model_hash",
            layer="genesis",
            counterparty_verifiable=True,
            verification_method="hash_compare",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="agent",
            verified_by="counterparty",
        ),
        FieldAxiomCheck(
            field_name="operator_id",
            layer="genesis",
            counterparty_verifiable=True,
            verification_method="signature_check",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="operator",
            verified_by="counterparty",
        ),
        FieldAxiomCheck(
            field_name="genesis_timestamp",
            layer="genesis",
            counterparty_verifiable=True,
            verification_method="log_lookup",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="system",
            verified_by="counterparty",
        ),
        # Attestation layer
        FieldAxiomCheck(
            field_name="grader_id",
            layer="attestation",
            counterparty_verifiable=True,
            verification_method="signature_check",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="oracle",
            verified_by="counterparty",
        ),
        FieldAxiomCheck(
            field_name="evidence_grade",
            layer="attestation",
            counterparty_verifiable=True,
            verification_method="receipt_chain",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="oracle",
            verified_by="counterparty",
        ),
        # Drift layer
        FieldAxiomCheck(
            field_name="drift_score",
            layer="drift",
            counterparty_verifiable=True,
            verification_method="receipt_chain",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="oracle",
            verified_by="counterparty",
        ),
        FieldAxiomCheck(
            field_name="correction_count",
            layer="drift",
            counterparty_verifiable=True,
            verification_method="receipt_chain",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="system",
            verified_by="counterparty",
        ),
        # Revocation layer
        FieldAxiomCheck(
            field_name="revocation_status",
            layer="revocation",
            counterparty_verifiable=True,
            verification_method="log_lookup",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="oracle",
            verified_by="counterparty",
        ),
        FieldAxiomCheck(
            field_name="revocation_reason",
            layer="revocation",
            counterparty_verifiable=True,
            verification_method="log_lookup",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="oracle",
            verified_by="counterparty",
        ),
        # Transport layer
        FieldAxiomCheck(
            field_name="reachability_status",
            layer="transport",
            counterparty_verifiable=True,
            verification_method="direct_probe",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="system",
            verified_by="counterparty",
        ),
        # NEW: failure_hash (per accountability chain thread)
        FieldAxiomCheck(
            field_name="failure_hash",
            layer="attestation",
            counterparty_verifiable=True,
            verification_method="hash_compare",
            requires_agent_cooperation=False,
            write_locked=True,
            writer="system",
            verified_by="counterparty",
        ),
        # ANTI-PATTERN: self-reported trust score
        FieldAxiomCheck(
            field_name="self_trust_score",
            layer="attestation",
            counterparty_verifiable=False,  # Only agent knows
            verification_method="self_report",
            requires_agent_cooperation=True,  # FAILS axiom 1
            write_locked=False,  # Agent can modify
            writer="agent",
            verified_by="agent",
            writer_is_verifier=True,  # FAILS axiom 2
        ),
    ]


def demo():
    fields = check_atf_core_fields()

    print("=" * 60)
    print("ATF AXIOM COMPLIANCE CHECK")
    print("=" * 60)

    passed = 0
    partial = 0
    failed = 0

    for f in fields:
        report = f.report()
        status = report["overall"]
        icon = "✅" if status == "PASS" else "⚠️" if status == "PARTIAL" else "❌"
        print(f"{icon} {report['field']:25s} | A1:{report['axiom1_verifier_independence']:7s} | A2:{report['axiom2_write_protection']:7s} | {report['layer']}")

        if status == "PASS":
            passed += 1
        elif status == "PARTIAL":
            partial += 1
        else:
            failed += 1

    print()
    print(f"Results: {passed} PASS, {partial} PARTIAL, {failed} FAIL")
    print(f"ATF-core compliance: {'YES' if failed == 0 and partial == 0 else 'NO'}")

    # Show the anti-pattern
    print()
    print("=" * 60)
    print("ANTI-PATTERN: self_trust_score")
    print("=" * 60)
    anti = [f for f in fields if f.field_name == "self_trust_score"][0]
    print(json.dumps(anti.report(), indent=2))
    print("→ Self-reported scores violate BOTH axioms.")
    print("  Axiom 1: counterparty can't verify without asking agent.")
    print("  Axiom 2: agent writes AND verifies its own score.")

    # Cadence check
    print()
    print("=" * 60)
    print("CADENCE CHECK: vocabulary vs verifier")
    print("=" * 60)

    good = CadenceCheck(
        vocabulary_version="registry_hash:16eae196e8060d32",
        verifier_version="schema:2.2.0",
        vocabulary_fields_changed=False,
        verifier_logic_changed=True,
    )
    print("Good (verifier evolved, vocabulary frozen):")
    print(json.dumps(good.report(), indent=2))

    bad = CadenceCheck(
        vocabulary_version="registry_hash:16eae196e8060d32",
        verifier_version="schema:2.2.0",
        vocabulary_fields_changed=True,  # BAD
        verifier_logic_changed=True,
    )
    print("\nBad (vocabulary changed after freeze):")
    print(json.dumps(bad.report(), indent=2))

    # Error type taxonomy
    print()
    print("=" * 60)
    print("ERROR TYPE TAXONOMY (option 3)")
    print("=" * 60)
    for et in ErrorType:
        print(f"  {et.value}")
    print("  X-RATE_LIMITED (extension)")
    print(f"  Valid: {ErrorType.is_valid('TIMEOUT')}, {ErrorType.is_valid('X-RATE_LIMITED')}, {ErrorType.is_valid('BANANA')}")


if __name__ == "__main__":
    demo()
