#!/usr/bin/env python3
"""
cross-registry-federator.py — FBCA-style cross-registry federation for ATF.

Per santaclawd: ATF-A trusts agent X, ATF-B trusts agent X.
Does ATF-A trust ATF-B's verified agents?

X.509 answer: Federal Bridge CA (FBCA). Peer-to-peer cross-certification.
Each CA independently decides if the other meets its requirements.
No automatic trust inheritance. Mutual recognition, not union.

ATF equivalent: cross-attestation receipts.
Registry A signs "I verified agent X under MY registry."
Registry B decides if A's MUST fields meet B's minimum.

Email parallel: Gmail trusts Outlook's DKIM because both publish to DNS.
No bilateral agreement needed. The standard IS the agreement.

Usage:
    python3 cross-registry-federator.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RegistryPolicy:
    """A registry's MUST field requirements."""
    registry_id: str
    registry_hash: str
    must_fields: set[str]
    min_evidence_grade: str  # A-F
    min_verifier_count: int
    require_must_staple: bool
    
    def grade_value(self, grade: str) -> int:
        return {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}.get(grade, 0)


@dataclass
class AgentAttestation:
    """An attestation from a specific registry about an agent."""
    agent_id: str
    registry_id: str
    evidence_grade: str
    fields_verified: set[str]
    verifier_count: int
    has_must_staple: bool
    genesis_hash: str
    attestation_hash: str = ""
    
    def __post_init__(self):
        if not self.attestation_hash:
            h = hashlib.sha256(
                f"{self.agent_id}:{self.registry_id}:{self.evidence_grade}:{self.genesis_hash}".encode()
            ).hexdigest()[:16]
            self.attestation_hash = h


@dataclass 
class CrossAttestationReceipt:
    """Receipt from Registry B recognizing Registry A's attestation."""
    source_registry: str
    target_registry: str
    agent_id: str
    source_attestation_hash: str
    recognition_level: str  # FULL, PARTIAL, REJECTED
    field_coverage: float   # % of target MUST fields covered by source
    missing_fields: set[str]
    grade_sufficient: bool
    receipt_hash: str = ""

    def __post_init__(self):
        if not self.receipt_hash:
            h = hashlib.sha256(
                f"{self.source_registry}:{self.target_registry}:{self.agent_id}:{self.recognition_level}".encode()
            ).hexdigest()[:16]
            self.receipt_hash = h


class CrossRegistryFederator:
    """FBCA-style peer-to-peer registry federation."""

    def __init__(self):
        self.registries: dict[str, RegistryPolicy] = {}
        self.attestations: dict[str, list[AgentAttestation]] = {}  # agent_id -> attestations

    def add_registry(self, policy: RegistryPolicy):
        self.registries[policy.registry_id] = policy

    def add_attestation(self, att: AgentAttestation):
        if att.agent_id not in self.attestations:
            self.attestations[att.agent_id] = []
        self.attestations[att.agent_id].append(att)

    def evaluate_cross_recognition(
        self,
        agent_id: str,
        source_registry_id: str,
        target_registry_id: str,
    ) -> CrossAttestationReceipt:
        """Can target_registry recognize source_registry's attestation of agent?"""
        
        target = self.registries.get(target_registry_id)
        source = self.registries.get(source_registry_id)
        
        if not target or not source:
            return CrossAttestationReceipt(
                source_registry=source_registry_id,
                target_registry=target_registry_id,
                agent_id=agent_id,
                source_attestation_hash="",
                recognition_level="REJECTED",
                field_coverage=0.0,
                missing_fields=set(),
                grade_sufficient=False,
            )

        # Find source's attestation of this agent
        agent_atts = self.attestations.get(agent_id, [])
        source_att = next(
            (a for a in agent_atts if a.registry_id == source_registry_id), None
        )
        
        if not source_att:
            return CrossAttestationReceipt(
                source_registry=source_registry_id,
                target_registry=target_registry_id,
                agent_id=agent_id,
                source_attestation_hash="",
                recognition_level="REJECTED",
                field_coverage=0.0,
                missing_fields=target.must_fields,
                grade_sufficient=False,
            )

        # Check field coverage
        covered = source_att.fields_verified & target.must_fields
        missing = target.must_fields - source_att.fields_verified
        coverage = len(covered) / len(target.must_fields) if target.must_fields else 1.0

        # Check grade
        grade_ok = target.grade_value(source_att.evidence_grade) >= target.grade_value(target.min_evidence_grade)

        # Check verifier count
        verifiers_ok = source_att.verifier_count >= target.min_verifier_count

        # Check must-staple
        staple_ok = source_att.has_must_staple if target.require_must_staple else True

        # Determine recognition level
        if coverage >= 1.0 and grade_ok and verifiers_ok and staple_ok:
            level = "FULL"
        elif coverage >= 0.7 and grade_ok:
            level = "PARTIAL"
        else:
            level = "REJECTED"

        return CrossAttestationReceipt(
            source_registry=source_registry_id,
            target_registry=target_registry_id,
            agent_id=agent_id,
            source_attestation_hash=source_att.attestation_hash,
            recognition_level=level,
            field_coverage=coverage,
            missing_fields=missing,
            grade_sufficient=grade_ok,
        )

    def federation_matrix(self, agent_id: str) -> dict:
        """Show cross-recognition status across all registry pairs for an agent."""
        results = {}
        registry_ids = list(self.registries.keys())
        
        for source in registry_ids:
            for target in registry_ids:
                if source == target:
                    continue
                receipt = self.evaluate_cross_recognition(agent_id, source, target)
                key = f"{source}->{target}"
                results[key] = {
                    "level": receipt.recognition_level,
                    "coverage": f"{receipt.field_coverage:.0%}",
                    "missing": sorted(receipt.missing_fields) if receipt.missing_fields else [],
                    "grade_ok": receipt.grade_sufficient,
                }
        
        return results


def demo():
    print("=" * 60)
    print("Cross-Registry Federator — FBCA model for ATF")
    print("=" * 60)

    fed = CrossRegistryFederator()

    # Registry A: strict (like a government CA)
    fed.add_registry(RegistryPolicy(
        registry_id="atf-strict",
        registry_hash="strict001",
        must_fields={"soul_hash", "genesis_hash", "model_hash", "operator_id", 
                     "grader_id", "evidence_grade", "schema_version", "anchor_type",
                     "failure_hash", "correction_rate", "verifier_table_hash",
                     "receipt_max_age", "hot_swap_max_age"},
        min_evidence_grade="A",
        min_verifier_count=3,
        require_must_staple=True,
    ))

    # Registry B: moderate (like a commercial CA)
    fed.add_registry(RegistryPolicy(
        registry_id="atf-moderate",
        registry_hash="moderate001",
        must_fields={"soul_hash", "genesis_hash", "model_hash", "operator_id",
                     "evidence_grade", "schema_version"},
        min_evidence_grade="B",
        min_verifier_count=2,
        require_must_staple=False,
    ))

    # Registry C: minimal (like Let's Encrypt DV)
    fed.add_registry(RegistryPolicy(
        registry_id="atf-minimal",
        registry_hash="minimal001",
        must_fields={"soul_hash", "genesis_hash", "evidence_grade"},
        min_evidence_grade="C",
        min_verifier_count=1,
        require_must_staple=False,
    ))

    # Agent X: well-attested across registries
    fed.add_attestation(AgentAttestation(
        agent_id="agent_x",
        registry_id="atf-strict",
        evidence_grade="A",
        fields_verified={"soul_hash", "genesis_hash", "model_hash", "operator_id",
                        "grader_id", "evidence_grade", "schema_version", "anchor_type",
                        "failure_hash", "correction_rate", "verifier_table_hash",
                        "receipt_max_age", "hot_swap_max_age"},
        verifier_count=5,
        has_must_staple=True,
        genesis_hash="agentx_gen001",
    ))

    fed.add_attestation(AgentAttestation(
        agent_id="agent_x",
        registry_id="atf-moderate",
        evidence_grade="B",
        fields_verified={"soul_hash", "genesis_hash", "model_hash", "operator_id",
                        "evidence_grade", "schema_version"},
        verifier_count=3,
        has_must_staple=False,
        genesis_hash="agentx_gen001",
    ))

    # Agent Y: only minimally attested
    fed.add_attestation(AgentAttestation(
        agent_id="agent_y",
        registry_id="atf-minimal",
        evidence_grade="C",
        fields_verified={"soul_hash", "genesis_hash", "evidence_grade"},
        verifier_count=1,
        has_must_staple=False,
        genesis_hash="agenty_gen001",
    ))

    # Scenario 1: Well-attested agent across registries
    print("\n--- Agent X: Federation matrix ---")
    matrix = fed.federation_matrix("agent_x")
    print(json.dumps(matrix, indent=2))

    # Scenario 2: Minimally attested agent
    print("\n--- Agent Y: Federation matrix ---")
    matrix_y = fed.federation_matrix("agent_y")
    print(json.dumps(matrix_y, indent=2))

    # Scenario 3: Specific cross-recognition
    print("\n--- Can atf-strict recognize atf-moderate's attestation of agent_x? ---")
    receipt = fed.evaluate_cross_recognition("agent_x", "atf-moderate", "atf-strict")
    print(json.dumps({
        "level": receipt.recognition_level,
        "coverage": f"{receipt.field_coverage:.0%}",
        "missing": sorted(receipt.missing_fields),
        "grade_ok": receipt.grade_sufficient,
        "receipt_hash": receipt.receipt_hash,
    }, indent=2))

    print("\n" + "=" * 60)
    print("FBCA model: peer-to-peer, not hierarchical.")
    print("Each registry decides if the other meets its MUST fields.")
    print("No automatic trust inheritance. The standard IS the agreement.")
    print("strict->moderate: REJECTED (grade B < required A)")
    print("moderate->strict: FULL (strict exceeds moderate's requirements)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
