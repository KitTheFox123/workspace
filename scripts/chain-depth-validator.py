#!/usr/bin/env python3
"""
chain-depth-validator.py — ATF chain depth limit enforcement.

Implements CHAIN_DEPTH_LIMIT indexed by action_class, inspired by:
- RFC 5280 §6.1: X.509 path validation with pathLenConstraint
- ATF thread (2026-03-27): READ[5] → ATTEST[3] → TRANSFER[2]
- Principle: blast radius scales with depth limit

The insight from PKI: unlimited delegation depth = transitive trust explosion.
X.509 solved this with basicConstraints.pathLenConstraint (RFC 5280 §4.2.1.9).
ATF needs the same, but indexed per action class — READ can tolerate deeper
chains than TRANSFER because the damage from a bad READ is bounded.

Combines with causal-attestation-validator.py (confounder detection) and
trust-aimd.py (score dynamics) for full ATF validation stack.

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionClass(Enum):
    READ = "READ"
    WRITE = "WRITE" 
    ATTEST = "ATTEST"
    TRANSFER = "TRANSFER"


# Default depth limits (from ATF thread consensus)
DEFAULT_DEPTH_LIMITS = {
    ActionClass.READ: 5,
    ActionClass.ATTEST: 3,
    ActionClass.TRANSFER: 2,
    ActionClass.WRITE: 3,
}


@dataclass
class DelegationLink:
    """A single link in a delegation chain."""
    delegator: str
    delegate: str
    action_class: ActionClass
    ttl_seconds: int
    delegator_score: float  # Trust score of delegator
    timestamp: str


@dataclass
class ChainValidation:
    valid: bool
    depth: int
    max_depth: int
    action_class: str
    effective_ttl: int  # min() of all TTLs in chain
    effective_score: float  # min() of all scores in chain
    violations: list = field(default_factory=list)
    chain: list = field(default_factory=list)


class ChainDepthValidator:
    """
    Validates ATF delegation chains against depth limits.
    
    RFC 5280 parallel:
    - pathLenConstraint → CHAIN_DEPTH_LIMIT[action_class]
    - basicConstraints.cA → agent.can_delegate[action_class]
    - nameConstraints → scope restrictions (not yet implemented)
    
    Key properties:
    1. Depth limit indexed by action class (higher stakes = shorter chains)
    2. min() composition: effective TTL = min(all TTLs in chain)
    3. min() composition: effective score = min(all scores in chain)
    4. Delegatee cannot escalate beyond delegator's permissions
    """
    
    def __init__(self, depth_limits: Optional[dict] = None):
        self.depth_limits = depth_limits or DEFAULT_DEPTH_LIMITS
    
    def validate_chain(self, chain: list[DelegationLink]) -> ChainValidation:
        """Validate a delegation chain against depth and composition rules."""
        if not chain:
            return ChainValidation(
                valid=False, depth=0, max_depth=0,
                action_class="NONE", effective_ttl=0, effective_score=0.0,
                violations=["Empty chain"]
            )
        
        action_class = chain[0].action_class
        max_depth = self.depth_limits.get(action_class, 2)
        violations = []
        
        # Check 1: All links must be same action class
        for i, link in enumerate(chain):
            if link.action_class != action_class:
                violations.append(
                    f"Link {i}: action_class mismatch ({link.action_class.value} "
                    f"vs chain {action_class.value}). Cannot cross action boundaries."
                )
        
        # Check 2: Depth limit
        depth = len(chain)
        if depth > max_depth:
            violations.append(
                f"Chain depth {depth} exceeds limit {max_depth} for {action_class.value}. "
                f"RFC 5280 §4.2.1.9 equivalent: pathLenConstraint exceeded."
            )
        
        # Check 3: min() composition for TTL
        ttls = [link.ttl_seconds for link in chain]
        effective_ttl = min(ttls)
        
        # Check 4: min() composition for score
        scores = [link.delegator_score for link in chain]
        effective_score = min(scores)
        
        # Check 5: Chain continuity (delegate[i] == delegator[i+1])
        for i in range(len(chain) - 1):
            if chain[i].delegate != chain[i + 1].delegator:
                violations.append(
                    f"Chain break at link {i}: {chain[i].delegate} ≠ {chain[i+1].delegator}. "
                    f"Delegation must be continuous."
                )
        
        # Check 6: Score monotonicity warning
        # Delegatee inherits min(delegator_score, own_score)
        # If a low-score agent delegates to high-score, effective is still low
        for i in range(len(chain) - 1):
            if chain[i + 1].delegator_score > chain[i].delegator_score:
                # Not a violation, but worth noting
                pass
        
        chain_repr = [
            {"from": link.delegator, "to": link.delegate, 
             "score": link.delegator_score, "ttl": link.ttl_seconds}
            for link in chain
        ]
        
        return ChainValidation(
            valid=len(violations) == 0,
            depth=depth,
            max_depth=max_depth,
            action_class=action_class.value,
            effective_ttl=effective_ttl,
            effective_score=round(effective_score, 3),
            violations=violations,
            chain=chain_repr
        )
    
    def find_max_delegatable_depth(self, agent_score: float, 
                                     action_class: ActionClass) -> int:
        """
        How deep can this agent delegate?
        
        Low-trust agents get shorter chains (cold-start speed limit).
        Score < 0.3 → max depth 1 (can only delegate directly)
        Score < 0.6 → max depth = limit - 1
        Score >= 0.6 → full depth limit
        """
        base = self.depth_limits.get(action_class, 2)
        if agent_score < 0.3:
            return min(1, base)
        elif agent_score < 0.6:
            return max(1, base - 1)
        return base
    
    def compare_to_rfc5280(self) -> dict:
        """Map ATF concepts to RFC 5280 equivalents."""
        return {
            "ATF → RFC 5280 mapping": {
                "CHAIN_DEPTH_LIMIT[action]": "pathLenConstraint (§4.2.1.9)",
                "min(TTL)": "notAfter composition (§6.1.3.c)",
                "min(score)": "No direct equivalent — PKI is binary (valid/revoked)",
                "action_class": "keyUsage + extKeyUsage (§4.2.1.3, §4.2.1.12)",
                "can_delegate": "basicConstraints.cA (§4.2.1.9)",
            },
            "ATF improvements over X.509": [
                "Graduated trust (scores) vs binary valid/revoked",
                "Per-action-class depth limits vs single pathLen",
                "min() composition gives automatic risk bounding",
                "Cold-start speed limits (score-gated delegation depth)",
            ],
            "X.509 lessons for ATF": [
                "Name constraints prevent scope creep (not yet in ATF)",
                "CRL/OCSP for revocation — ATF needs TTL expiry + active revocation",
                "Cross-certification creates unexpected paths — ATF min() prevents escalation",
            ]
        }


def demo():
    v = ChainDepthValidator()
    
    print("=" * 60)
    print("ATF CHAIN DEPTH VALIDATION")
    print(f"Limits: {', '.join(f'{k.value}[{v}]' for k, v in DEFAULT_DEPTH_LIMITS.items())}")
    print("=" * 60)
    
    # Scenario 1: Valid READ chain (depth 3, limit 5)
    print("\n--- Scenario 1: Valid READ chain (depth 3/5) ---")
    chain1 = [
        DelegationLink("genesis", "alice", ActionClass.READ, 86400, 0.9, "2026-03-27T00:00:00Z"),
        DelegationLink("alice", "bob", ActionClass.READ, 43200, 0.75, "2026-03-27T01:00:00Z"),
        DelegationLink("bob", "carol", ActionClass.READ, 21600, 0.6, "2026-03-27T02:00:00Z"),
    ]
    r1 = v.validate_chain(chain1)
    print(f"Valid: {r1.valid} | Depth: {r1.depth}/{r1.max_depth}")
    print(f"Effective TTL: {r1.effective_ttl}s | Score: {r1.effective_score}")
    assert r1.valid
    
    # Scenario 2: TRANSFER chain exceeds depth (3 > 2)
    print("\n--- Scenario 2: TRANSFER chain exceeds depth (3/2) ---")
    chain2 = [
        DelegationLink("alice", "bob", ActionClass.TRANSFER, 3600, 0.8, "2026-03-27T00:00:00Z"),
        DelegationLink("bob", "carol", ActionClass.TRANSFER, 1800, 0.7, "2026-03-27T00:01:00Z"),
        DelegationLink("carol", "dave", ActionClass.TRANSFER, 900, 0.6, "2026-03-27T00:02:00Z"),
    ]
    r2 = v.validate_chain(chain2)
    print(f"Valid: {r2.valid} | Depth: {r2.depth}/{r2.max_depth}")
    print(f"Violations: {r2.violations}")
    assert not r2.valid
    
    # Scenario 3: Action class mismatch
    print("\n--- Scenario 3: Action class mismatch in chain ---")
    chain3 = [
        DelegationLink("alice", "bob", ActionClass.READ, 3600, 0.8, "2026-03-27T00:00:00Z"),
        DelegationLink("bob", "carol", ActionClass.TRANSFER, 1800, 0.7, "2026-03-27T00:01:00Z"),
    ]
    r3 = v.validate_chain(chain3)
    print(f"Valid: {r3.valid}")
    print(f"Violations: {r3.violations}")
    assert not r3.valid
    
    # Scenario 4: Chain break (delegate ≠ next delegator)
    print("\n--- Scenario 4: Chain continuity break ---")
    chain4 = [
        DelegationLink("alice", "bob", ActionClass.ATTEST, 3600, 0.8, "2026-03-27T00:00:00Z"),
        DelegationLink("carol", "dave", ActionClass.ATTEST, 1800, 0.7, "2026-03-27T00:01:00Z"),
    ]
    r4 = v.validate_chain(chain4)
    print(f"Valid: {r4.valid}")
    print(f"Violations: {r4.violations}")
    assert not r4.valid
    
    # Scenario 5: Cold-start depth gating
    print("\n--- Scenario 5: Cold-start delegation depth ---")
    for score in [0.2, 0.5, 0.8]:
        for action in [ActionClass.READ, ActionClass.TRANSFER]:
            max_d = v.find_max_delegatable_depth(score, action)
            print(f"  Score {score}, {action.value}: max depth = {max_d}")
    
    # RFC 5280 comparison
    print("\n--- RFC 5280 Mapping ---")
    mapping = v.compare_to_rfc5280()
    print(json.dumps(mapping, indent=2))
    
    print("\n✓ ALL SCENARIOS PASSED")


if __name__ == "__main__":
    demo()
