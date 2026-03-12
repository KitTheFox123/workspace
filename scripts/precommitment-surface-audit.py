#!/usr/bin/env python3
"""
precommitment-surface-audit.py — Audits unhashed inputs as retroactive rationalization surfaces.

Based on:
- santaclawd: "every unhashed input = retroactive rationalization slot = mirage attack surface"
- santaclawd: "commit-reveal-intent is not a pattern. it is the substrate."
- funwolf: email threads = accidental pre-commitment stores

Scans a contract/protocol for inputs that SHOULD be pre-committed but aren't.
Each unhashed input = potential mirage attack vector.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommitStatus(Enum):
    COMMITTED = "committed"       # Hashed before use
    UNCOMMITTED = "uncommitted"   # Used raw — attack surface
    PARTIAL = "partial"           # Some fields hashed, some not
    IMPLICIT = "implicit"         # Committed via reference (e.g., email Message-ID)


class InputCategory(Enum):
    RULE = "rule"                 # Scoring/evaluation rule
    DATA = "data"                 # Input data to be scored
    ENVIRONMENT = "environment"   # Runtime, VM, arch
    CANARY = "canary"             # Recovery probe spec
    SCOPE = "scope"               # What agent can/should do
    CALIBRATION = "calibration"   # Reference dataset
    INTENT = "intent"             # Why action was taken
    ABSENCE = "absence"           # Why action was NOT taken


@dataclass
class ProtocolInput:
    name: str
    category: InputCategory
    status: CommitStatus
    hash_field: Optional[str] = None  # Name of hash field if committed
    mirage_risk: str = ""             # What happens if retroactively changed


def audit_paylock_v21() -> list[ProtocolInput]:
    """Audit PayLock ABI v2.1 inputs."""
    return [
        ProtocolInput("scoring_rule", InputCategory.RULE, CommitStatus.COMMITTED,
                       "rule_hash", "Swap friendly rule for punitive post-delivery"),
        ProtocolInput("scope_manifest", InputCategory.SCOPE, CommitStatus.COMMITTED,
                       "scope_hash", "Retroactively expand/contract deliverables"),
        ProtocolInput("canary_spec", InputCategory.CANARY, CommitStatus.COMMITTED,
                       "canary_spec_hash", "Make recovery trivial or impossible"),
        ProtocolInput("calibration_data", InputCategory.CALIBRATION, CommitStatus.COMMITTED,
                       "dataset_hash", "Shift baseline to fail/pass anything"),
        ProtocolInput("environment", InputCategory.ENVIRONMENT, CommitStatus.COMMITTED,
                       "env_hash", "Run on different VM → different float results"),
        ProtocolInput("execution_trace", InputCategory.DATA, CommitStatus.COMMITTED,
                       "trace_hash", "Claim different execution path post-hoc"),
        ProtocolInput("params_negotiation", InputCategory.RULE, CommitStatus.COMMITTED,
                       "params_hash", "Change α/β after seeing results"),
        # THE GAPS
        ProtocolInput("intent_declaration", InputCategory.INTENT, CommitStatus.UNCOMMITTED,
                       None, "Retroactively claim different motivation"),
        ProtocolInput("null_receipt_context", InputCategory.ABSENCE, CommitStatus.PARTIAL,
                       None, "Claim absence was chosen when it was imposed"),
        ProtocolInput("attestor_selection", InputCategory.RULE, CommitStatus.UNCOMMITTED,
                       None, "Cherry-pick favorable attestor after delivery"),
    ]


def audit_email_protocol() -> list[ProtocolInput]:
    """Audit email as accidental pre-commitment (funwolf insight)."""
    return [
        ProtocolInput("message_content", InputCategory.DATA, CommitStatus.IMPLICIT,
                       "Message-ID", "Message-ID = content-derived, immutable after send"),
        ProtocolInput("ordering", InputCategory.DATA, CommitStatus.IMPLICIT,
                       "References", "References header = hash-equivalent chain"),
        ProtocolInput("origin", InputCategory.RULE, CommitStatus.IMPLICIT,
                       "DKIM-Signature", "DKIM proves sender domain"),
        ProtocolInput("timestamp", InputCategory.ENVIRONMENT, CommitStatus.IMPLICIT,
                       "Date", "Received headers add independent timestamps"),
        # EMAIL GAPS
        ProtocolInput("recipient_intent", InputCategory.INTENT, CommitStatus.UNCOMMITTED,
                       None, "No proof recipient read vs ignored"),
        ProtocolInput("delivery_proof", InputCategory.ABSENCE, CommitStatus.UNCOMMITTED,
                       None, "No proof of non-delivery (silent drop)"),
    ]


def grade_surface(inputs: list[ProtocolInput]) -> tuple[str, dict]:
    """Grade pre-commitment surface coverage."""
    total = len(inputs)
    committed = sum(1 for i in inputs if i.status in (CommitStatus.COMMITTED, CommitStatus.IMPLICIT))
    uncommitted = sum(1 for i in inputs if i.status == CommitStatus.UNCOMMITTED)
    partial = sum(1 for i in inputs if i.status == CommitStatus.PARTIAL)
    
    ratio = committed / total if total else 0
    
    if ratio >= 0.9:
        grade = "A"
    elif ratio >= 0.7:
        grade = "B"
    elif ratio >= 0.5:
        grade = "C"
    else:
        grade = "F"
    
    return grade, {
        "total": total,
        "committed": committed,
        "uncommitted": uncommitted,
        "partial": partial,
        "coverage": ratio,
        "attack_surfaces": uncommitted + partial,
    }


def main():
    print("=" * 70)
    print("PRE-COMMITMENT SURFACE AUDIT")
    print("santaclawd: 'every unhashed input = mirage attack surface'")
    print("=" * 70)

    # PayLock v2.1
    print("\n--- PayLock ABI v2.1 ---")
    paylock = audit_paylock_v21()
    print(f"{'Input':<25} {'Category':<15} {'Status':<15} {'Hash Field':<20} {'Mirage Risk'}")
    print("-" * 95)
    for inp in paylock:
        hf = inp.hash_field or "NONE"
        risk = inp.mirage_risk[:35] if inp.mirage_risk else ""
        marker = "⚠️" if inp.status == CommitStatus.UNCOMMITTED else "  "
        print(f"{marker}{inp.name:<23} {inp.category.value:<15} {inp.status.value:<15} {hf:<20} {risk}")
    
    grade, stats = grade_surface(paylock)
    print(f"\nGrade: {grade} | Coverage: {stats['coverage']:.0%} | Attack surfaces: {stats['attack_surfaces']}")

    # Email protocol
    print("\n--- Email Protocol (funwolf: accidental pre-commitment) ---")
    email = audit_email_protocol()
    for inp in email:
        hf = inp.hash_field or "NONE"
        marker = "⚠️" if inp.status == CommitStatus.UNCOMMITTED else "  "
        print(f"{marker}{inp.name:<23} {inp.category.value:<15} {inp.status.value:<15} {hf:<20}")
    
    grade_e, stats_e = grade_surface(email)
    print(f"\nGrade: {grade_e} | Coverage: {stats_e['coverage']:.0%} | Attack surfaces: {stats_e['attack_surfaces']}")

    # The unified model
    print("\n--- Unified Attack Model ---")
    print("Every protocol input falls into one of:")
    print("  COMMITTED:   Hashed before use → retroactive change detectable")
    print("  UNCOMMITTED: Raw input → retroactive rationalization possible")
    print("  IMPLICIT:    Committed by infrastructure (email headers, git)")
    print("  PARTIAL:     Some fields hashed → attack surface in unhashed fields")
    print()
    print("The audit question for ANY protocol:")
    print("  For each input: is it hashed before it influences output?")
    print("  If no: that's a mirage attack surface.")
    print()
    print("santaclawd: 'commit-reveal-intent is not a pattern. it is the substrate.'")
    print("funwolf: 'email built it accidentally in the 70s. we keep reinventing worse.'")


if __name__ == "__main__":
    main()
