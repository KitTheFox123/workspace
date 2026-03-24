#!/usr/bin/env python3
"""
cross-registry-vc-bridge.py — W3C VC 2.0 bridge for ATF cross-registry federation.

Per santaclawd: ATF V1.1 complete (5 primitives). Next frontier: cross-registry federation.
Per W3C VC 2.0 (Recommendation May 2025): issuer/holder/verifier triangle.

Maps ATF to VC 2.0:
  - Operator → Issuer (issues genesis credentials)
  - Agent → Holder (presents trust receipts)
  - Counterparty → Verifier (checks receipt validity)

Key VC 2.0 features for ATF:
  - Selective disclosure (show grade without revealing counterparty)
  - JSON-LD extensibility (ATF vocabulary as linked data)
  - Zero-knowledge proofs (prove trust_score > threshold without revealing score)
  - Decentralized identifiers (DID) for cross-registry agent identity
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RegistryId(Enum):
    ATF_ALPHA = "did:atf:alpha"
    ATF_BETA = "did:atf:beta"
    ATF_GAMMA = "did:atf:gamma"


class CredentialType(Enum):
    GENESIS = "ATFGenesisCredential"
    RECEIPT = "ATFReceiptCredential"
    TRUST_SCORE = "ATFTrustScoreCredential"
    DELEGATION = "ATFDelegationCredential"
    FEDERATION_BRIDGE = "ATFFederationBridgeCredential"


class BridgeDirection(Enum):
    UNIDIRECTIONAL = "unidirectional"  # A trusts B, B doesn't trust A
    BIDIRECTIONAL = "bidirectional"    # Mutual trust (rare, requires both sides)


class VerificationResult(Enum):
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    UNKNOWN_REGISTRY = "UNKNOWN_REGISTRY"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    DEPTH_EXCEEDED = "DEPTH_EXCEEDED"


@dataclass
class VerifiableCredential:
    """W3C VC 2.0 compatible credential structure."""
    context: list = field(default_factory=lambda: [
        "https://www.w3.org/ns/credentials/v2",
        "https://atf.registry/ns/v1.1"
    ])
    type: list = field(default_factory=lambda: ["VerifiableCredential"])
    issuer: str = ""           # DID of issuing registry/operator
    holder: str = ""           # DID of agent
    issuance_date: str = ""
    expiration_date: str = ""
    credential_subject: dict = field(default_factory=dict)
    proof: dict = field(default_factory=dict)
    
    def to_json(self) -> dict:
        return {
            "@context": self.context,
            "type": self.type,
            "issuer": self.issuer,
            "credentialSubject": self.credential_subject,
            "issuanceDate": self.issuance_date,
            "expirationDate": self.expiration_date,
            "proof": self.proof
        }
    
    def hash(self) -> str:
        canonical = json.dumps(self.to_json(), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class FederationBridge:
    """Cross-registry trust bridge using VC 2.0."""
    source_registry: RegistryId
    target_registry: RegistryId
    direction: BridgeDirection
    scope: list  # Which credential types are bridged
    max_depth: int = 2  # Maximum delegation chain across bridge
    grade_ceiling: str = "B"  # Max grade transferable across bridge
    expires_at: float = 0.0
    bridge_credential: Optional[VerifiableCredential] = None
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at if self.expires_at > 0 else False


@dataclass
class CrossRegistryVerification:
    """Result of verifying a credential across registries."""
    credential_hash: str
    source_registry: str
    target_registry: str
    bridge_used: Optional[str]
    result: VerificationResult
    original_grade: str
    bridged_grade: str  # May be lower due to grade_ceiling
    depth: int
    details: dict = field(default_factory=dict)


def create_genesis_vc(agent_id: str, operator_id: str, registry: RegistryId,
                      trust_score: float, grade: str) -> VerifiableCredential:
    """Create a W3C VC 2.0 genesis credential for an ATF agent."""
    now = time.time()
    vc = VerifiableCredential(
        type=["VerifiableCredential", CredentialType.GENESIS.value],
        issuer=f"{registry.value}:operator:{operator_id}",
        holder=f"{registry.value}:agent:{agent_id}",
        issuance_date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        expiration_date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 86400*90)),
        credential_subject={
            "id": f"{registry.value}:agent:{agent_id}",
            "type": "ATFAgent",
            "trustScore": trust_score,
            "evidenceGrade": grade,
            "registry": registry.value,
            "operator": operator_id,
            "primitives": {
                "probe_timeout": "jacobson_karels_srtt",
                "alleged_decay": "0.5*exp(-0.1*T)",
                "co_grader": "inherits_decay",
                "delegation_depth": 3,
                "soft_cascade_grace": "72h"
            }
        },
        proof={
            "type": "Ed25519Signature2020",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "proofPurpose": "assertionMethod",
            "verificationMethod": f"{registry.value}:operator:{operator_id}#key-1"
        }
    )
    return vc


def create_bridge_credential(source: RegistryId, target: RegistryId,
                             direction: BridgeDirection, scope: list,
                             max_depth: int = 2, grade_ceiling: str = "B") -> FederationBridge:
    """Create a cross-registry federation bridge."""
    now = time.time()
    bridge_vc = VerifiableCredential(
        type=["VerifiableCredential", CredentialType.FEDERATION_BRIDGE.value],
        issuer=source.value,
        holder=target.value,
        issuance_date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        expiration_date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 86400*30)),
        credential_subject={
            "type": "ATFFederationBridge",
            "sourceRegistry": source.value,
            "targetRegistry": target.value,
            "direction": direction.value,
            "scope": scope,
            "maxDepth": max_depth,
            "gradeCeiling": grade_ceiling,
            "bridgeHash": hashlib.sha256(
                f"{source.value}:{target.value}:{now}".encode()
            ).hexdigest()[:16]
        }
    )
    
    return FederationBridge(
        source_registry=source,
        target_registry=target,
        direction=direction,
        scope=scope,
        max_depth=max_depth,
        grade_ceiling=grade_ceiling,
        expires_at=now + 86400*30,
        bridge_credential=bridge_vc
    )


def verify_across_registry(credential: VerifiableCredential,
                           bridges: list[FederationBridge],
                           verifier_registry: RegistryId) -> CrossRegistryVerification:
    """Verify a credential from one registry in another."""
    subject = credential.credential_subject
    cred_registry = subject.get("registry", "")
    grade = subject.get("evidenceGrade", "F")
    
    # Same registry — no bridge needed
    if cred_registry == verifier_registry.value:
        return CrossRegistryVerification(
            credential_hash=credential.hash(),
            source_registry=cred_registry,
            target_registry=verifier_registry.value,
            bridge_used=None,
            result=VerificationResult.VALID,
            original_grade=grade,
            bridged_grade=grade,
            depth=0,
            details={"note": "Same registry, no bridge needed"}
        )
    
    # Find applicable bridge
    applicable = [b for b in bridges
                  if b.source_registry.value == cred_registry
                  and b.target_registry == verifier_registry
                  and not b.is_expired()]
    
    if not applicable:
        # Check reverse direction for bidirectional bridges
        applicable = [b for b in bridges
                      if b.target_registry.value == cred_registry
                      and b.source_registry == verifier_registry
                      and b.direction == BridgeDirection.BIDIRECTIONAL
                      and not b.is_expired()]
    
    if not applicable:
        return CrossRegistryVerification(
            credential_hash=credential.hash(),
            source_registry=cred_registry,
            target_registry=verifier_registry.value,
            bridge_used=None,
            result=VerificationResult.UNKNOWN_REGISTRY,
            original_grade=grade,
            bridged_grade="F",
            depth=0,
            details={"note": "No bridge between registries"}
        )
    
    bridge = applicable[0]
    
    # Check scope
    cred_type = credential.type[-1] if credential.type else ""
    if cred_type not in bridge.scope:
        return CrossRegistryVerification(
            credential_hash=credential.hash(),
            source_registry=cred_registry,
            target_registry=verifier_registry.value,
            bridge_used=bridge.bridge_credential.hash() if bridge.bridge_credential else None,
            result=VerificationResult.SCOPE_VIOLATION,
            original_grade=grade,
            bridged_grade="F",
            depth=0,
            details={"note": f"Credential type {cred_type} not in bridge scope {bridge.scope}"}
        )
    
    # Apply grade ceiling
    grade_order = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    ceiling_num = grade_order.get(bridge.grade_ceiling, 0)
    original_num = grade_order.get(grade, 0)
    bridged_grade = grade if original_num <= ceiling_num else bridge.grade_ceiling
    
    return CrossRegistryVerification(
        credential_hash=credential.hash(),
        source_registry=cred_registry,
        target_registry=verifier_registry.value,
        bridge_used=bridge.bridge_credential.hash() if bridge.bridge_credential else None,
        result=VerificationResult.VALID,
        original_grade=grade,
        bridged_grade=bridged_grade,
        depth=1,
        details={
            "bridge_direction": bridge.direction.value,
            "grade_ceiling_applied": grade != bridged_grade,
            "scope_matched": True
        }
    )


def selective_disclosure(credential: VerifiableCredential, 
                         reveal_fields: list[str]) -> dict:
    """
    Selective disclosure: reveal only specified fields.
    W3C VC 2.0 supports this via Data Integrity proofs.
    """
    full_subject = credential.credential_subject
    disclosed = {k: v for k, v in full_subject.items() if k in reveal_fields or k == "id"}
    redacted = [k for k in full_subject if k not in reveal_fields and k != "id"]
    
    return {
        "disclosed": disclosed,
        "redacted_fields": redacted,
        "proof_of_redaction": hashlib.sha256(
            json.dumps(full_subject, sort_keys=True).encode()
        ).hexdigest()[:16],
        "selective_disclosure": True
    }


# === Scenarios ===

def scenario_cross_registry_verification():
    """Agent from registry Alpha verified in registry Beta."""
    print("=== Scenario: Cross-Registry Verification ===")
    
    # Create agent credential in Alpha
    vc = create_genesis_vc("kit_fox", "ilya_ops", RegistryId.ATF_ALPHA, 0.92, "A")
    
    # Create bridge Alpha→Beta
    bridge = create_bridge_credential(
        RegistryId.ATF_ALPHA, RegistryId.ATF_BETA,
        BridgeDirection.UNIDIRECTIONAL,
        scope=[CredentialType.GENESIS.value, CredentialType.RECEIPT.value],
        grade_ceiling="B"
    )
    
    # Verify in Beta
    result = verify_across_registry(vc, [bridge], RegistryId.ATF_BETA)
    
    print(f"  Agent: kit_fox (Alpha)")
    print(f"  Verifier: Beta")
    print(f"  Result: {result.result.value}")
    print(f"  Original grade: {result.original_grade} → Bridged: {result.bridged_grade}")
    print(f"  Grade ceiling applied: {result.original_grade != result.bridged_grade}")
    print(f"  Bridge: {result.bridge_used}")
    print()


def scenario_no_bridge():
    """Agent from Alpha tries to verify in Gamma — no bridge exists."""
    print("=== Scenario: No Bridge Available ===")
    
    vc = create_genesis_vc("rogue_agent", "unknown_op", RegistryId.ATF_ALPHA, 0.5, "C")
    result = verify_across_registry(vc, [], RegistryId.ATF_GAMMA)
    
    print(f"  Agent: rogue_agent (Alpha)")
    print(f"  Verifier: Gamma")
    print(f"  Result: {result.result.value}")
    print(f"  Grade: {result.bridged_grade}")
    print()


def scenario_scope_violation():
    """Bridge exists but doesn't cover this credential type."""
    print("=== Scenario: Scope Violation ===")
    
    vc = create_genesis_vc("delegator", "op_x", RegistryId.ATF_ALPHA, 0.8, "B")
    vc.type = ["VerifiableCredential", CredentialType.DELEGATION.value]
    
    bridge = create_bridge_credential(
        RegistryId.ATF_ALPHA, RegistryId.ATF_BETA,
        BridgeDirection.UNIDIRECTIONAL,
        scope=[CredentialType.GENESIS.value],  # Only genesis, not delegation
        grade_ceiling="B"
    )
    
    result = verify_across_registry(vc, [bridge], RegistryId.ATF_BETA)
    
    print(f"  Credential type: {CredentialType.DELEGATION.value}")
    print(f"  Bridge scope: {bridge.scope}")
    print(f"  Result: {result.result.value}")
    print()


def scenario_selective_disclosure():
    """Agent reveals trust score but not counterparty details."""
    print("=== Scenario: Selective Disclosure ===")
    
    vc = create_genesis_vc("kit_fox", "ilya_ops", RegistryId.ATF_ALPHA, 0.92, "A")
    
    # Reveal only grade and trust score, hide operator and primitives
    disclosed = selective_disclosure(vc, ["trustScore", "evidenceGrade", "registry"])
    
    print(f"  Disclosed fields: {list(disclosed['disclosed'].keys())}")
    print(f"  Redacted fields: {disclosed['redacted_fields']}")
    print(f"  Proof of redaction: {disclosed['proof_of_redaction']}")
    print(f"  Key: verifier sees grade=A, score=0.92 but NOT operator or primitives")
    print()


def scenario_bidirectional_federation():
    """Mutual trust between Alpha and Beta."""
    print("=== Scenario: Bidirectional Federation ===")
    
    bridge = create_bridge_credential(
        RegistryId.ATF_ALPHA, RegistryId.ATF_BETA,
        BridgeDirection.BIDIRECTIONAL,
        scope=[CredentialType.GENESIS.value, CredentialType.RECEIPT.value],
        grade_ceiling="B"
    )
    
    # Alpha agent verified in Beta
    vc_alpha = create_genesis_vc("alpha_agent", "op_a", RegistryId.ATF_ALPHA, 0.88, "A")
    result_ab = verify_across_registry(vc_alpha, [bridge], RegistryId.ATF_BETA)
    
    # Beta agent verified in Alpha (reverse direction)
    vc_beta = create_genesis_vc("beta_agent", "op_b", RegistryId.ATF_BETA, 0.75, "B")
    result_ba = verify_across_registry(vc_beta, [bridge], RegistryId.ATF_ALPHA)
    
    print(f"  Alpha→Beta: {result_ab.result.value} (grade {result_ab.original_grade}→{result_ab.bridged_grade})")
    print(f"  Beta→Alpha: {result_ba.result.value} (grade {result_ba.original_grade}→{result_ba.bridged_grade})")
    print(f"  Bidirectional: both directions verified through same bridge")
    print()


if __name__ == "__main__":
    print("Cross-Registry VC Bridge — W3C VC 2.0 Federation for ATF")
    print("Per santaclawd: ATF V1.1 complete. Next: cross-registry federation.")
    print("W3C Verifiable Credentials 2.0 (Recommendation May 2025)")
    print("=" * 70)
    print()
    print("ATF → VC 2.0 mapping:")
    print("  Operator → Issuer (issues genesis credentials)")
    print("  Agent    → Holder (presents trust receipts)")  
    print("  Counter  → Verifier (checks receipt validity)")
    print()
    
    scenario_cross_registry_verification()
    scenario_no_bridge()
    scenario_scope_violation()
    scenario_selective_disclosure()
    scenario_bidirectional_federation()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Grade ceiling prevents trust inflation across registries")
    print("2. Scope filtering prevents credential type leakage")
    print("3. Selective disclosure = show grade without revealing operator")
    print("4. Unidirectional bridges = A trusts B ≠ B trusts A")
    print("5. W3C VC 2.0 gives ATF: interop, ZKP, selective disclosure, DIDs")
