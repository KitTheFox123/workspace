#!/usr/bin/env python3
"""
atf-acl-splitter.py — Three separate ACL sections for ATF v0.2 governance.

Per santaclawd: "one governance section for all three = ambiguous at first PR."

Three governance objects, three ACL models:
  1. Vocabulary Registry — IANA ossification model
     - ACL: spec committee only
     - Rename = BREAKING CHANGE (new major version)
     - Append-only, never remove
     
  2. Verifier Table — CT log model
     - ACL: append-only, governance-controlled
     - Methods evolve independently of vocabulary
     - Self-attestation capped at Grade C
     
  3. Error Enum — HTTP status code model
     - ACL: core locked at V1.0, X-prefix extensions open
     - Core types frozen, extensions versioned
     - Unknown extensions preserved, free-form rejected

Each surface has its own hash, its own version, its own write authority.

Usage:
    python3 atf-acl-splitter.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WriteAuthority(Enum):
    SPEC_COMMITTEE = "spec_committee"
    GOVERNANCE_COUNCIL = "governance_council"
    OPEN_EXTENSION = "open_extension"


class ACLAction(Enum):
    APPEND = "append"
    RENAME = "rename"
    REMOVE = "remove"
    MODIFY_TYPE = "modify_type"
    ADD_METHOD = "add_method"
    DEPRECATE_METHOD = "deprecate_method"
    ADD_EXTENSION = "add_extension"


@dataclass
class ACLRule:
    surface: str
    action: ACLAction
    authority: WriteAuthority
    verdict: str  # ALLOWED, REJECTED, BREAKING_CHANGE
    rationale: str


@dataclass
class GovernanceSurface:
    name: str
    model: str  # IANA, CT, HTTP
    authority: WriteAuthority
    version: str
    fields: list
    hash: str = ""
    
    def compute_hash(self) -> str:
        canonical = json.dumps(self.fields, sort_keys=True)
        self.hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        return self.hash


class ATFACLSplitter:
    """Enforce separate ACLs for three ATF governance surfaces."""

    def __init__(self):
        # Surface 1: Vocabulary Registry (IANA model)
        self.vocab = GovernanceSurface(
            name="vocabulary_registry",
            model="IANA",
            authority=WriteAuthority.SPEC_COMMITTEE,
            version="1.3.0",
            fields=[
                "agent_id", "operator_id", "soul_hash", "model_hash",
                "genesis_hash", "predecessor_hash", "schema_version",
                "evidence_grade", "grader_id", "trust_score",
                "correction_count", "attestation_count",
                "grader_genesis_hash", "anchor_type",
            ],
        )
        self.vocab.compute_hash()

        # Surface 2: Verifier Table (CT model)
        self.verifier = GovernanceSurface(
            name="verifier_table",
            model="CT",
            authority=WriteAuthority.GOVERNANCE_COUNCIL,
            version="0.3.0",
            fields=[
                {"name": "genesis_hash_verifier", "method": "sha256_compare", "trust_level": "HARD"},
                {"name": "dkim_verifier", "method": "dns_txt_lookup", "trust_level": "HARD"},
                {"name": "soul_hash_verifier", "method": "content_hash", "trust_level": "HARD"},
                {"name": "self_report_verifier", "method": "agent_claim", "trust_level": "SOFT"},
            ],
        )
        self.verifier.compute_hash()

        # Surface 3: Error Enum (HTTP model)
        self.error = GovernanceSurface(
            name="error_enum",
            model="HTTP",
            authority=WriteAuthority.OPEN_EXTENSION,
            version="1.0.0",
            fields=[
                "TIMEOUT", "MALFORMED_INPUT", "CAPABILITY_EXCEEDED",
                "DEPENDENCY_FAILURE", "INTERNAL", "SCOPE_VIOLATION",
                "RESOURCE_EXHAUSTED", "UNAUTHORIZED", "REVOKED",
            ],
        )
        self.error.compute_hash()

        # ACL rules per surface
        self.rules: list[ACLRule] = [
            # Vocabulary rules
            ACLRule("vocabulary_registry", ACLAction.APPEND, WriteAuthority.SPEC_COMMITTEE, "ALLOWED", "New fields append-only"),
            ACLRule("vocabulary_registry", ACLAction.RENAME, WriteAuthority.SPEC_COMMITTEE, "BREAKING_CHANGE", "Rename = new major version"),
            ACLRule("vocabulary_registry", ACLAction.REMOVE, WriteAuthority.SPEC_COMMITTEE, "REJECTED", "Never remove, only deprecate"),
            ACLRule("vocabulary_registry", ACLAction.MODIFY_TYPE, WriteAuthority.SPEC_COMMITTEE, "BREAKING_CHANGE", "Type change = new major"),
            # Verifier rules
            ACLRule("verifier_table", ACLAction.ADD_METHOD, WriteAuthority.GOVERNANCE_COUNCIL, "ALLOWED", "New methods append"),
            ACLRule("verifier_table", ACLAction.DEPRECATE_METHOD, WriteAuthority.GOVERNANCE_COUNCIL, "ALLOWED", "Deprecate without remove"),
            ACLRule("verifier_table", ACLAction.REMOVE, WriteAuthority.GOVERNANCE_COUNCIL, "REJECTED", "Never remove active verifiers"),
            # Error rules
            ACLRule("error_enum", ACLAction.APPEND, WriteAuthority.SPEC_COMMITTEE, "REJECTED", "Core enum frozen at V1.0"),
            ACLRule("error_enum", ACLAction.ADD_EXTENSION, WriteAuthority.OPEN_EXTENSION, "ALLOWED", "X-prefix extensions open"),
            ACLRule("error_enum", ACLAction.REMOVE, WriteAuthority.SPEC_COMMITTEE, "REJECTED", "Core types permanent"),
        ]

    def check_action(self, surface: str, action: ACLAction, authority: WriteAuthority) -> dict:
        """Check if an action is allowed on a surface by a given authority."""
        matching = [r for r in self.rules if r.surface == surface and r.action == action]
        
        if not matching:
            return {"allowed": False, "verdict": "UNDEFINED", "reason": "No rule for this action"}
        
        rule = matching[0]
        authority_match = rule.authority == authority or authority == WriteAuthority.SPEC_COMMITTEE
        
        if rule.verdict == "REJECTED":
            return {"allowed": False, "verdict": "REJECTED", "reason": rule.rationale}
        elif rule.verdict == "BREAKING_CHANGE":
            return {
                "allowed": authority_match,
                "verdict": "BREAKING_CHANGE" if authority_match else "UNAUTHORIZED",
                "reason": rule.rationale,
                "requires": "new_major_version",
            }
        else:
            return {
                "allowed": authority_match,
                "verdict": "ALLOWED" if authority_match else "UNAUTHORIZED",
                "reason": rule.rationale,
            }

    def audit(self) -> dict:
        """Full ACL audit across all three surfaces."""
        return {
            "surfaces": [
                {
                    "name": s.name,
                    "model": s.model,
                    "authority": s.authority.value,
                    "version": s.version,
                    "field_count": len(s.fields),
                    "hash": s.hash,
                }
                for s in [self.vocab, self.verifier, self.error]
            ],
            "combined_hash": hashlib.sha256(
                f"{self.vocab.hash}|{self.verifier.hash}|{self.error.hash}".encode()
            ).hexdigest()[:16],
            "rule_count": len(self.rules),
            "coupling": "DECOUPLED",  # three hashes = three update cadences
        }


def demo():
    print("=" * 60)
    print("ATF ACL Splitter — Three Surfaces, Three Models")
    print("=" * 60)

    splitter = ATFACLSplitter()

    # Audit
    audit = splitter.audit()
    print("\n--- Governance Audit ---")
    print(json.dumps(audit, indent=2))

    # Test scenarios
    scenarios = [
        ("vocabulary_registry", ACLAction.APPEND, WriteAuthority.SPEC_COMMITTEE, "Add new field (spec committee)"),
        ("vocabulary_registry", ACLAction.RENAME, WriteAuthority.GOVERNANCE_COUNCIL, "Rename field (wrong authority)"),
        ("vocabulary_registry", ACLAction.REMOVE, WriteAuthority.SPEC_COMMITTEE, "Remove field (always rejected)"),
        ("verifier_table", ACLAction.ADD_METHOD, WriteAuthority.GOVERNANCE_COUNCIL, "Add verifier method"),
        ("verifier_table", ACLAction.REMOVE, WriteAuthority.GOVERNANCE_COUNCIL, "Remove active verifier"),
        ("error_enum", ACLAction.APPEND, WriteAuthority.SPEC_COMMITTEE, "Add core error type (frozen)"),
        ("error_enum", ACLAction.ADD_EXTENSION, WriteAuthority.OPEN_EXTENSION, "Add X-prefix extension"),
    ]

    print("\n--- ACL Check Scenarios ---")
    for surface, action, authority, desc in scenarios:
        result = splitter.check_action(surface, action, authority)
        status = "✅" if result["allowed"] else "❌"
        print(f"{status} {desc}: {result['verdict']} — {result['reason']}")

    print("\n" + "=" * 60)
    print("Three surfaces, three hashes, three update cadences.")
    print("Vocab = IANA (ossify). Verifier = CT (evolve). Error = HTTP (lock + extend).")
    print("=" * 60)


if __name__ == "__main__":
    demo()
