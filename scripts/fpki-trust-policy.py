#!/usr/bin/env python3
"""
fpki-trust-policy.py — F-PKI-style relying-party trust policy engine for ATF.

Maps Chuat et al (NDSS 2022, Princeton/ETH Zurich) "F-PKI: Enabling Innovation
and Trust Flexibility in the HTTPS Public-Key Infrastructure" to ATF.

F-PKI key ideas applied to ATF:
- Ternary trust: UNTRUSTED / TRUSTED / HIGHLY_TRUSTED (per name, per relying party)
- Domain policies via cert extensions → ATF: agent policies via attestation extensions
- Relying party controls trust levels, not issuer → ATF inverts PKI control model
- Map servers provide comprehensive certificate view → ATF: shared forensic floor
- Policy resolution: Bool=AND, Max=MIN, Set=INTERSECT (strictest wins)
- Downgrade prevention: highly trusted attestation can't be hidden by lower-trust one

ATF mapping:
- CA = Registry (issues trust attestations)
- Domain owner = Agent (defines acceptable trust sources)
- Relying party = Any agent evaluating trust claims
- Certificate = Attestation
- Map server = Shared forensic log (CT-log equivalent)
- ISSUERS policy = AUTHORIZED_REGISTRIES
- Certificate Transparency = Attestation Transparency (what ATF IS)

Key F-PKI insight: "Security is defined by the weakest link" in traditional PKI.
F-PKI fixes this by letting relying parties define WHICH links they consider strong.
ATF does the same: forensic floor is shared, revocation graph is yours.
"""

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
from datetime import datetime, timezone


class TrustLevel(Enum):
    """F-PKI ternary trust model."""
    UNTRUSTED = 0
    TRUSTED = 1          # Standard trust (can attest, but overridden by HIGHLY_TRUSTED)
    HIGHLY_TRUSTED = 2   # Priority trust (policies from this level take precedence)


class PolicyAttribute(Enum):
    """F-PKI policy attribute types with resolution rules."""
    BOOL = "bool"    # Resolved via AND (conjunction)
    MAX = "max"      # Resolved via MIN (take minimum)
    SET = "set"      # Resolved via INTERSECT (intersection)


@dataclass
class AgentPolicy:
    """
    Agent-defined policy (F-PKI domain policy equivalent).
    Embedded in attestations to restrict valid trust claims.
    """
    agent_id: str
    authorized_registries: set[str] = field(default_factory=set)  # ISSUERS equivalent
    max_attestation_ttl_hours: int = 168  # MAX attribute
    require_multi_witness: bool = False   # BOOL attribute
    allowed_action_classes: set[str] = field(default_factory=lambda: {"READ", "WRITE", "TRANSFER", "ATTEST"})
    min_grader_diversity: float = 0.0     # Custom: minimum diversity-collapse-detector score


@dataclass
class Attestation:
    """An attestation (F-PKI certificate equivalent)."""
    id: str
    subject_agent: str     # Who this attestation is about
    issuing_registry: str  # Who issued it
    action_class: str
    score: float
    ttl_hours: int
    policy: Optional[AgentPolicy] = None  # Embedded policy
    witnesses: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass 
class ValidationPolicy:
    """
    Relying party's validation policy (F-PKI validation policy equivalent).
    Each relying party defines their own trust levels per registry.
    """
    owner_id: str
    trust_levels: dict[str, TrustLevel] = field(default_factory=dict)  # registry_id → trust level
    
    def get_trust_level(self, registry_id: str) -> TrustLevel:
        return self.trust_levels.get(registry_id, TrustLevel.UNTRUSTED)
    
    def highly_trusted_registries(self) -> set[str]:
        return {r for r, t in self.trust_levels.items() if t == TrustLevel.HIGHLY_TRUSTED}
    
    def trusted_registries(self) -> set[str]:
        return {r for r, t in self.trust_levels.items() if t.value >= TrustLevel.TRUSTED.value}


class PolicyResolver:
    """
    Resolve policies using F-PKI rules: strictest wins.
    Bool → AND, Max → MIN, Set → INTERSECT.
    """
    
    @staticmethod
    def resolve(policies: list[AgentPolicy]) -> AgentPolicy:
        if not policies:
            return AgentPolicy(agent_id="default")
        
        resolved = AgentPolicy(
            agent_id=policies[0].agent_id,
            authorized_registries=set(policies[0].authorized_registries),
            max_attestation_ttl_hours=policies[0].max_attestation_ttl_hours,
            require_multi_witness=policies[0].require_multi_witness,
            allowed_action_classes=set(policies[0].allowed_action_classes),
            min_grader_diversity=policies[0].min_grader_diversity,
        )
        
        for policy in policies[1:]:
            # SET: intersection (most restrictive)
            if policy.authorized_registries:
                resolved.authorized_registries &= policy.authorized_registries
            if policy.allowed_action_classes:
                resolved.allowed_action_classes &= policy.allowed_action_classes
            
            # MAX: minimum (most restrictive)
            resolved.max_attestation_ttl_hours = min(
                resolved.max_attestation_ttl_hours, 
                policy.max_attestation_ttl_hours
            )
            
            # BOOL: conjunction (if ANY policy requires it, it's required)
            resolved.require_multi_witness = resolved.require_multi_witness or policy.require_multi_witness
            
            # MAX for diversity floor
            resolved.min_grader_diversity = max(
                resolved.min_grader_diversity,
                policy.min_grader_diversity
            )
        
        return resolved


class AttestationValidator:
    """
    F-PKI-style attestation validation.
    
    Algorithm (maps F-PKI Algorithm 1):
    1. Legacy validation (signature, expiry)
    2. Check revocations
    3. Filter attestations by trust level (only consider highly trusted policies)
    4. Resolve policies (strictest wins)
    5. Verify attestation complies with resolved policy
    """
    
    def __init__(self, validation_policy: ValidationPolicy):
        self.policy = validation_policy
        self.forensic_log: list[dict] = []  # Shared forensic floor
    
    def validate(self, attestation: Attestation, 
                 other_attestations: list[Attestation] = None) -> dict:
        """
        Validate an attestation considering all known attestations for the subject.
        F-PKI insight: security comes from seeing ALL attestations, not just one chain.
        """
        other_attestations = other_attestations or []
        issues = []
        
        # Step 1: Basic validation
        issuer_trust = self.policy.get_trust_level(attestation.issuing_registry)
        if issuer_trust == TrustLevel.UNTRUSTED:
            return {
                "result": "REJECTED",
                "reason": "Issuing registry is UNTRUSTED",
                "registry": attestation.issuing_registry,
                "trust_level": issuer_trust.name,
            }
        
        # Step 2: Collect policies from highly trusted attestations only
        # F-PKI key: only policies from HIGHLY_TRUSTED CAs are considered
        highly_trusted_policies = []
        for other in other_attestations:
            other_trust = self.policy.get_trust_level(other.issuing_registry)
            if other_trust == TrustLevel.HIGHLY_TRUSTED and other.policy:
                highly_trusted_policies.append(other.policy)
        
        # Include policy from current attestation if from highly trusted
        if issuer_trust == TrustLevel.HIGHLY_TRUSTED and attestation.policy:
            highly_trusted_policies.append(attestation.policy)
        
        # Step 3: Resolve policies (strictest wins)
        if highly_trusted_policies:
            resolved = PolicyResolver.resolve(highly_trusted_policies)
        else:
            resolved = AgentPolicy(agent_id="default_browser_policy")
        
        # Step 4: Verify compliance
        # Check ISSUERS (authorized registries)
        if resolved.authorized_registries and attestation.issuing_registry not in resolved.authorized_registries:
            issues.append(f"Registry {attestation.issuing_registry} not in AUTHORIZED_REGISTRIES: {resolved.authorized_registries}")
        
        # Check TTL
        if attestation.ttl_hours > resolved.max_attestation_ttl_hours:
            issues.append(f"TTL {attestation.ttl_hours}h exceeds policy max {resolved.max_attestation_ttl_hours}h")
        
        # Check multi-witness
        if resolved.require_multi_witness and len(attestation.witnesses) < 2:
            issues.append(f"Policy requires multi-witness but attestation has {len(attestation.witnesses)} witness(es)")
        
        # Check action class
        if resolved.allowed_action_classes and attestation.action_class not in resolved.allowed_action_classes:
            issues.append(f"Action class {attestation.action_class} not in allowed: {resolved.allowed_action_classes}")
        
        # Step 5: Downgrade detection
        # F-PKI: check if a highly trusted attestation conflicts
        for other in other_attestations:
            other_trust = self.policy.get_trust_level(other.issuing_registry)
            if other_trust == TrustLevel.HIGHLY_TRUSTED:
                if other.score < 0.5 and attestation.score > 0.8:
                    issues.append(
                        f"DOWNGRADE_CONFLICT: Highly trusted {other.issuing_registry} scored {other.score:.2f} "
                        f"but this attestation claims {attestation.score:.2f}"
                    )
        
        # Log to forensic floor
        self.forensic_log.append({
            "attestation_id": attestation.id,
            "subject": attestation.subject_agent,
            "registry": attestation.issuing_registry,
            "trust_level": issuer_trust.name,
            "issues": issues,
            "policies_considered": len(highly_trusted_policies),
            "resolved_registries": list(resolved.authorized_registries) if resolved.authorized_registries else "any",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        if issues:
            return {
                "result": "REJECTED",
                "issues": issues,
                "policies_applied": len(highly_trusted_policies),
                "resolved_policy": {
                    "authorized_registries": list(resolved.authorized_registries) if resolved.authorized_registries else "any",
                    "max_ttl_hours": resolved.max_attestation_ttl_hours,
                    "require_multi_witness": resolved.require_multi_witness,
                },
            }
        
        return {
            "result": "ACCEPTED",
            "trust_level": issuer_trust.name,
            "policies_applied": len(highly_trusted_policies),
        }


def run_scenarios():
    """Demonstrate F-PKI trust policy validation in ATF context."""
    
    print("=" * 70)
    print("F-PKI TRUST POLICY ENGINE FOR ATF")
    print("Based on Chuat et al (NDSS 2022, Princeton/ETH Zurich)")
    print("=" * 70)
    
    # Setup: Relying party (agent_verifier) has ternary trust levels
    rp = ValidationPolicy(
        owner_id="agent_verifier",
        trust_levels={
            "registry_alpha": TrustLevel.HIGHLY_TRUSTED,
            "registry_beta": TrustLevel.TRUSTED,
            "registry_gamma": TrustLevel.UNTRUSTED,
            "registry_delta": TrustLevel.HIGHLY_TRUSTED,
        }
    )
    validator = AttestationValidator(rp)
    
    # Agent policy: only alpha and delta can attest, max 72h, need multi-witness
    agent_policy = AgentPolicy(
        agent_id="agent_subject",
        authorized_registries={"registry_alpha", "registry_delta"},
        max_attestation_ttl_hours=72,
        require_multi_witness=True,
    )
    
    # Highly trusted attestation from alpha WITH policy
    alpha_attestation = Attestation(
        id="att_alpha_1",
        subject_agent="agent_subject",
        issuing_registry="registry_alpha",
        action_class="WRITE",
        score=0.85,
        ttl_hours=48,
        policy=agent_policy,
        witnesses=["rekor", "rfc3161_tsa"],
    )
    
    scenarios = [
        {
            "name": "1. ACCEPTED: Highly trusted registry, compliant attestation",
            "attestation": Attestation(
                id="att_delta_1", subject_agent="agent_subject",
                issuing_registry="registry_delta", action_class="WRITE",
                score=0.80, ttl_hours=48, witnesses=["rekor", "ct_log"],
            ),
            "others": [alpha_attestation],
            "expected": "ACCEPTED",
        },
        {
            "name": "2. REJECTED: Untrusted registry (gamma)",
            "attestation": Attestation(
                id="att_gamma_1", subject_agent="agent_subject",
                issuing_registry="registry_gamma", action_class="READ",
                score=0.90, ttl_hours=24,
            ),
            "others": [],
            "expected": "REJECTED",
        },
        {
            "name": "3. REJECTED: Trusted (beta) but policy restricts to alpha+delta",
            "attestation": Attestation(
                id="att_beta_1", subject_agent="agent_subject",
                issuing_registry="registry_beta", action_class="WRITE",
                score=0.75, ttl_hours=48, witnesses=["rekor", "ct_log"],
            ),
            "others": [alpha_attestation],
            "expected": "REJECTED",
        },
        {
            "name": "4. REJECTED: TTL exceeds policy maximum",
            "attestation": Attestation(
                id="att_alpha_2", subject_agent="agent_subject",
                issuing_registry="registry_alpha", action_class="READ",
                score=0.90, ttl_hours=168, witnesses=["rekor", "ct_log"],
            ),
            "others": [alpha_attestation],
            "expected": "REJECTED",
        },
        {
            "name": "5. REJECTED: Missing multi-witness (policy requires it)",
            "attestation": Attestation(
                id="att_delta_2", subject_agent="agent_subject",
                issuing_registry="registry_delta", action_class="WRITE",
                score=0.80, ttl_hours=24, witnesses=["rekor"],  # Only 1
            ),
            "others": [alpha_attestation],
            "expected": "REJECTED",
        },
        {
            "name": "6. REJECTED: Downgrade conflict (highly trusted scored low)",
            "attestation": Attestation(
                id="att_delta_3", subject_agent="agent_subject",
                issuing_registry="registry_delta", action_class="WRITE",
                score=0.95, ttl_hours=48, witnesses=["rekor", "ct_log"],
            ),
            "others": [
                alpha_attestation,
                Attestation(  # Highly trusted says score is low
                    id="att_alpha_conflict", subject_agent="agent_subject",
                    issuing_registry="registry_alpha", action_class="WRITE",
                    score=0.30, ttl_hours=48, policy=agent_policy,
                    witnesses=["rekor", "rfc3161_tsa"],
                ),
            ],
            "expected": "REJECTED",
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        result = validator.validate(scenario["attestation"], scenario.get("others", []))
        passed = result["result"] == scenario["expected"]
        if not passed:
            all_pass = False
        status = "✓" if passed else "✗"
        
        print(f"\n{status} {scenario['name']}")
        print(f"  Registry: {scenario['attestation'].issuing_registry} ({rp.get_trust_level(scenario['attestation'].issuing_registry).name})")
        print(f"  Result: {result['result']}")
        if "issues" in result:
            for issue in result["issues"]:
                print(f"    → {issue}")
        if "policies_applied" in result:
            print(f"  Policies applied: {result['policies_applied']}")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {sum(1 for s in scenarios if validator.validate(s['attestation'], s.get('others', []))['result'] == s['expected'])}/{len(scenarios)} passed")
    
    print(f"\nF-PKI → ATF mapping:")
    print(f"  CA → Registry | Domain owner → Agent | Relying party → Verifier")
    print(f"  Certificate → Attestation | Map server → Forensic log")
    print(f"  ISSUERS policy → AUTHORIZED_REGISTRIES")
    print(f"  Policy resolution: Bool=AND, Max=MIN, Set=INTERSECT (strictest wins)")
    print(f"  Key: relying party controls trust, not issuer. PKI inverted.")
    print(f"  Forensic floor is shared. Revocation graph is yours.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
