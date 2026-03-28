#!/usr/bin/env python3
"""
trust-layer-validator.py — Validates agent trust claims against the 3-layer model.

The trust stack has 3 layers that must be satisfied IN ORDER:
1. ADDRESSING — Can you reach me? (inbox exists, endpoint reachable)
2. IDENTITY — Consistent behavior over time (DKIM chain, behavioral fingerprint)
3. TRUST — Earned reputation (attestation chains, scored by independent evaluators)

Layer violations:
- Trust without identity = reputation laundering
- Identity without addressing = ghost agent
- Skipping layers = sybil shortcut

Inspired by Clawk thread (2026-03-28): "the agent trust stack has 3 layers
that keep getting conflated." Also: percolation threshold research (IEEE 2018)
shows sybils trivially get addressing but fail at identity (no history to fake).

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class Layer(Enum):
    ADDRESSING = 1
    IDENTITY = 2
    TRUST = 3


class Violation(Enum):
    MISSING_ADDRESSING = "Trust/Identity claimed without addressing"
    MISSING_IDENTITY = "Trust claimed without identity"
    STALE_IDENTITY = "Identity evidence expired (DKIM chain gap)"
    TTL_LAUNDERING = "Re-attestation on stale evidence (TTL laundering)"
    SYBIL_PATTERN = "Addressing-only with trust claims (sybil shortcut)"
    LAYER_SKIP = "Layer dependency violated"


@dataclass
class AddressingEvidence:
    """Layer 1: Can you reach me?"""
    endpoint: str              # e.g., "kit_fox@agentmail.to"
    endpoint_type: str         # "email", "api", "did"
    created_at: str            # ISO 8601
    reachable: bool = True
    dns_verified: bool = False  # MX record exists


@dataclass
class IdentityEvidence:
    """Layer 2: Consistent behavior over time."""
    dkim_chain_days: int = 0       # Days of verified DKIM signatures
    behavioral_samples: int = 0    # Distinct interactions observed
    fingerprint_consistency: float = 0.0  # 0-1, stylometric/behavioral
    oldest_evidence: Optional[str] = None  # ISO 8601
    newest_evidence: Optional[str] = None


@dataclass
class TrustEvidence:
    """Layer 3: Earned reputation."""
    attestation_count: int = 0
    unique_attesters: int = 0
    avg_score: float = 0.0
    attester_diversity: float = 0.0  # 0-1, how diverse are attesters
    oldest_attestation: Optional[str] = None
    newest_attestation: Optional[str] = None
    ttl_remaining: Optional[int] = None  # seconds


@dataclass
class AgentTrustProfile:
    agent_id: str
    addressing: Optional[AddressingEvidence] = None
    identity: Optional[IdentityEvidence] = None
    trust: Optional[TrustEvidence] = None


@dataclass
class ValidationResult:
    agent_id: str
    valid: bool
    highest_valid_layer: Optional[Layer] = None
    violations: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    layer_scores: dict = field(default_factory=dict)


class TrustLayerValidator:
    """Validates agent trust profiles against the 3-layer model."""
    
    # Thresholds
    MIN_DKIM_DAYS = 30       # Minimum for identity layer
    MIN_BEHAVIORAL_SAMPLES = 10
    MIN_FINGERPRINT_CONSISTENCY = 0.6
    MIN_ATTESTERS = 2        # At least 2 independent attesters for trust
    MIN_ATTESTER_DIVERSITY = 0.3
    IDENTITY_STALENESS_DAYS = 90  # Identity evidence older than this = stale
    
    def validate(self, profile: AgentTrustProfile) -> ValidationResult:
        result = ValidationResult(agent_id=profile.agent_id, valid=True)
        
        # Layer 1: Addressing
        addr_score = self._validate_addressing(profile, result)
        result.layer_scores["addressing"] = addr_score
        
        # Layer 2: Identity (requires addressing)
        id_score = self._validate_identity(profile, result)
        result.layer_scores["identity"] = id_score
        
        # Layer 3: Trust (requires identity)
        trust_score = self._validate_trust(profile, result)
        result.layer_scores["trust"] = trust_score
        
        # Determine highest valid layer
        if trust_score >= 0.5 and not any(v["violation"] in [
            Violation.MISSING_IDENTITY.value, 
            Violation.MISSING_ADDRESSING.value,
            Violation.LAYER_SKIP.value
        ] for v in result.violations):
            result.highest_valid_layer = Layer.TRUST
        elif id_score >= 0.5 and addr_score >= 0.5:
            result.highest_valid_layer = Layer.IDENTITY
        elif addr_score >= 0.5:
            result.highest_valid_layer = Layer.ADDRESSING
        
        result.valid = len(result.violations) == 0
        return result
    
    def _validate_addressing(self, profile: AgentTrustProfile, result: ValidationResult) -> float:
        if not profile.addressing:
            if profile.identity or profile.trust:
                result.violations.append({
                    "violation": Violation.MISSING_ADDRESSING.value,
                    "layer": "addressing",
                    "detail": "Higher layers claimed without addressing. Ghost agent pattern."
                })
            result.recommendations.append("Register an endpoint (email inbox, API, DID)")
            return 0.0
        
        score = 0.0
        addr = profile.addressing
        if addr.reachable:
            score += 0.5
        if addr.dns_verified:
            score += 0.3
        if addr.endpoint_type == "email":
            score += 0.2  # Email = strongest addressing (SMTP routing)
        elif addr.endpoint_type == "did":
            score += 0.15
        else:
            score += 0.1
        
        return min(1.0, score)
    
    def _validate_identity(self, profile: AgentTrustProfile, result: ValidationResult) -> float:
        if not profile.identity:
            if profile.trust:
                result.violations.append({
                    "violation": Violation.MISSING_IDENTITY.value,
                    "layer": "identity",
                    "detail": "Trust claimed without identity evidence. Reputation laundering pattern."
                })
            return 0.0
        
        if not profile.addressing:
            result.violations.append({
                "violation": Violation.LAYER_SKIP.value,
                "layer": "identity",
                "detail": "Identity without addressing = unverifiable."
            })
            return 0.0
        
        ident = profile.identity
        score = 0.0
        
        # DKIM chain duration
        if ident.dkim_chain_days >= self.MIN_DKIM_DAYS:
            score += 0.3 * min(1.0, ident.dkim_chain_days / 90)
        
        # Behavioral samples
        if ident.behavioral_samples >= self.MIN_BEHAVIORAL_SAMPLES:
            score += 0.3 * min(1.0, ident.behavioral_samples / 50)
        
        # Fingerprint consistency
        if ident.fingerprint_consistency >= self.MIN_FINGERPRINT_CONSISTENCY:
            score += 0.4 * ident.fingerprint_consistency
        
        # Staleness check
        if ident.newest_evidence:
            try:
                newest = datetime.fromisoformat(ident.newest_evidence.replace('Z', '+00:00'))
                age = datetime.now(timezone.utc) - newest
                if age.days > self.IDENTITY_STALENESS_DAYS:
                    result.violations.append({
                        "violation": Violation.STALE_IDENTITY.value,
                        "layer": "identity",
                        "detail": f"Last identity evidence {age.days}d old (threshold: {self.IDENTITY_STALENESS_DAYS}d)"
                    })
                    score *= 0.5
            except (ValueError, TypeError):
                pass
        
        return min(1.0, score)
    
    def _validate_trust(self, profile: AgentTrustProfile, result: ValidationResult) -> float:
        if not profile.trust:
            return 0.0
        
        # Check layer dependencies
        if not profile.identity:
            result.violations.append({
                "violation": Violation.SYBIL_PATTERN.value,
                "layer": "trust",
                "detail": "Trust claims without identity = sybil shortcut. "
                         "Trivial to get addressing; identity requires history."
            })
            return 0.0
        
        trust = profile.trust
        score = 0.0
        
        # Attestation count
        if trust.attestation_count > 0:
            score += 0.2 * min(1.0, trust.attestation_count / 10)
        
        # Attester diversity (critical — correlated attesters = confounded)
        if trust.unique_attesters >= self.MIN_ATTESTERS:
            score += 0.3 * trust.attester_diversity
        else:
            result.recommendations.append(
                f"Need {self.MIN_ATTESTERS}+ independent attesters (have {trust.unique_attesters})"
            )
        
        # Average score
        score += 0.3 * trust.avg_score
        
        # TTL check
        if trust.ttl_remaining is not None and trust.ttl_remaining <= 0:
            result.violations.append({
                "violation": Violation.TTL_LAUNDERING.value,
                "layer": "trust",
                "detail": "Attestation TTL expired. Re-attestation required."
            })
            score *= 0.3
        
        # Freshness
        if trust.newest_attestation:
            try:
                newest = datetime.fromisoformat(trust.newest_attestation.replace('Z', '+00:00'))
                age = datetime.now(timezone.utc) - newest
                freshness = max(0, 1.0 - (age.days / 365))
                score += 0.2 * freshness
            except (ValueError, TypeError):
                pass
        
        return min(1.0, score)


def demo():
    v = TrustLayerValidator()
    
    now = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    
    scenarios = [
        ("Kit (full stack)", AgentTrustProfile(
            agent_id="kit_fox",
            addressing=AddressingEvidence(
                endpoint="kit_fox@agentmail.to", endpoint_type="email",
                created_at="2026-02-01T00:00:00Z", reachable=True, dns_verified=True
            ),
            identity=IdentityEvidence(
                dkim_chain_days=55, behavioral_samples=200,
                fingerprint_consistency=0.85,
                oldest_evidence="2026-02-01T00:00:00Z", newest_evidence=now
            ),
            trust=TrustEvidence(
                attestation_count=8, unique_attesters=5,
                avg_score=0.82, attester_diversity=0.75,
                oldest_attestation="2026-02-14T00:00:00Z", newest_attestation=now,
                ttl_remaining=86400
            )
        )),
        ("Sybil (addressing + trust, no identity)", AgentTrustProfile(
            agent_id="sybil_001",
            addressing=AddressingEvidence(
                endpoint="sybil@agentmail.to", endpoint_type="email",
                created_at=now, reachable=True, dns_verified=True
            ),
            trust=TrustEvidence(
                attestation_count=5, unique_attesters=3,
                avg_score=0.9, attester_diversity=0.2,
                newest_attestation=now, ttl_remaining=3600
            )
        )),
        ("Ghost (identity + trust, no addressing)", AgentTrustProfile(
            agent_id="ghost_agent",
            identity=IdentityEvidence(
                dkim_chain_days=90, behavioral_samples=50,
                fingerprint_consistency=0.9
            ),
            trust=TrustEvidence(
                attestation_count=10, unique_attesters=4,
                avg_score=0.85, attester_diversity=0.6
            )
        )),
        ("Cold-start (addressing only)", AgentTrustProfile(
            agent_id="newbie",
            addressing=AddressingEvidence(
                endpoint="newbie@agentmail.to", endpoint_type="email",
                created_at=now, reachable=True, dns_verified=True
            )
        )),
        ("Stale (expired identity)", AgentTrustProfile(
            agent_id="stale_agent",
            addressing=AddressingEvidence(
                endpoint="stale@agentmail.to", endpoint_type="email",
                created_at="2025-06-01T00:00:00Z", reachable=True, dns_verified=True
            ),
            identity=IdentityEvidence(
                dkim_chain_days=45, behavioral_samples=30,
                fingerprint_consistency=0.7,
                oldest_evidence="2025-06-01T00:00:00Z", newest_evidence=old
            ),
            trust=TrustEvidence(
                attestation_count=3, unique_attesters=2,
                avg_score=0.7, attester_diversity=0.4,
                newest_attestation=old, ttl_remaining=0
            )
        )),
    ]
    
    for name, profile in scenarios:
        print("=" * 60)
        print(f"SCENARIO: {name}")
        print("=" * 60)
        result = v.validate(profile)
        print(f"  Valid: {result.valid}")
        print(f"  Highest layer: {result.highest_valid_layer.name if result.highest_valid_layer else 'NONE'}")
        print(f"  Scores: {json.dumps(result.layer_scores, indent=4)}")
        if result.violations:
            print(f"  Violations:")
            for viol in result.violations:
                print(f"    ⚠ [{viol['layer']}] {viol['violation']}")
                print(f"      {viol['detail']}")
        if result.recommendations:
            print(f"  Recommendations:")
            for rec in result.recommendations:
                print(f"    → {rec}")
        print()
    
    # Verify assertions
    results = {name: v.validate(profile) for name, profile in scenarios}
    assert results["Kit (full stack)"].valid == True
    assert results["Kit (full stack)"].highest_valid_layer == Layer.TRUST
    assert results["Sybil (addressing + trust, no identity)"].valid == False
    assert results["Ghost (identity + trust, no addressing)"].valid == False
    assert results["Cold-start (addressing only)"].valid == True
    assert results["Cold-start (addressing only)"].highest_valid_layer == Layer.ADDRESSING
    assert results["Stale (expired identity)"].valid == False
    
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
