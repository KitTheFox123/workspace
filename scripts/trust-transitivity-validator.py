#!/usr/bin/env python3
"""
trust-transitivity-validator.py — Trust transitivity policy for ATF delegation chains.

The next open question after stapling: A trusts B, B delegates to C.
Does A trust C? Under what conditions?

Three models:
  1. NO_TRANSITIVITY: A must independently verify C (most secure)
  2. SCOPED_TRANSITIVITY: C gets narrower scope than B (confused deputy prevention)
  3. FULL_TRANSITIVITY: A trusts anyone B trusts (most dangerous)

ATF answer: SCOPED_TRANSITIVITY with:
  - Scope narrowing: each hop MUST have equal or narrower scope
  - Chain hash: C proves B authorized the delegation
  - Depth limit: genesis constant (default: 3)
  - Grade decay: trust grade drops 1 per hop (A→B=A, B→C=B, C→D=C)

Inspired by:
  - Hardy (1988): Confused Deputy — authority without verification
  - X.509 path length constraints: basicConstraints pathLenConstraint
  - OAuth2 token exchange (RFC 8693): scope narrowing on delegation
  - Kerberos: ticket-granting with constrained delegation

Usage:
    python3 trust-transitivity-validator.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class TransitivityPolicy(Enum):
    NONE = "NO_TRANSITIVITY"
    SCOPED = "SCOPED_TRANSITIVITY"
    FULL = "FULL_TRANSITIVITY"


class DelegationVerdict(Enum):
    ACCEPTED = "ACCEPTED"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    DEPTH_EXCEEDED = "DEPTH_EXCEEDED"
    GRADE_TOO_LOW = "GRADE_TOO_LOW"
    CHAIN_BROKEN = "CHAIN_BROKEN"
    NO_TRANSITIVITY = "NO_TRANSITIVITY"


@dataclass
class DelegationGrant:
    """One hop in a delegation chain."""
    delegator: str          # who grants
    delegate: str           # who receives
    scope: set[str]         # allowed actions
    evidence_grade: str     # A-F at this hop
    chain_hash: str         # hash linking to previous grant
    depth: int              # current depth (0 = original principal)

    def canonical(self) -> str:
        scope_str = ",".join(sorted(self.scope))
        return f"{self.delegator}>{self.delegate}:{scope_str}:{self.evidence_grade}:{self.depth}"


class TrustTransitivityValidator:
    """Validate trust transitivity in delegation chains."""

    GRADE_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

    def __init__(
        self,
        policy: TransitivityPolicy = TransitivityPolicy.SCOPED,
        max_depth: int = 3,
        min_grade: str = "C",
    ):
        self.policy = policy
        self.max_depth = max_depth
        self.min_grade_value = self.GRADE_ORDER.get(min_grade, 3)

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def _grade_value(self, grade: str) -> int:
        return self.GRADE_ORDER.get(grade, 0)

    def _decay_grade(self, grade: str, hops: int) -> str:
        """Grade decays by 1 per hop."""
        val = self._grade_value(grade) - hops
        reverse = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}
        return reverse.get(max(1, val), "F")

    def validate_delegation(
        self,
        chain: list[DelegationGrant],
    ) -> dict:
        """Validate an entire delegation chain."""

        if self.policy == TransitivityPolicy.NONE:
            return {
                "verdict": DelegationVerdict.NO_TRANSITIVITY.value,
                "reason": "policy forbids trust transitivity",
                "chain_length": len(chain),
                "action": "REJECT" if len(chain) > 1 else "ACCEPT",
            }

        issues = []
        hops = []

        for i, grant in enumerate(chain):
            hop_result = {"depth": grant.depth, "delegator": grant.delegator,
                         "delegate": grant.delegate, "scope_size": len(grant.scope),
                         "grade": grant.evidence_grade}

            # Check depth limit
            if grant.depth > self.max_depth:
                issues.append({
                    "type": "DEPTH_EXCEEDED",
                    "hop": i,
                    "depth": grant.depth,
                    "max": self.max_depth,
                })
                hop_result["issue"] = "DEPTH_EXCEEDED"

            # Check scope narrowing (each hop must be subset of previous)
            if i > 0:
                prev_scope = chain[i - 1].scope
                if not grant.scope.issubset(prev_scope):
                    extra = grant.scope - prev_scope
                    issues.append({
                        "type": "SCOPE_VIOLATION",
                        "hop": i,
                        "extra_scope": list(extra),
                        "confused_deputy": True,
                    })
                    hop_result["issue"] = "SCOPE_VIOLATION"

            # Check grade decay
            if self.policy == TransitivityPolicy.SCOPED:
                decayed = self._decay_grade(chain[0].evidence_grade, i)
                actual = grant.evidence_grade
                if self._grade_value(actual) > self._grade_value(decayed):
                    issues.append({
                        "type": "GRADE_INFLATION",
                        "hop": i,
                        "expected_max": decayed,
                        "actual": actual,
                    })
                    hop_result["issue"] = "GRADE_INFLATION"

                if self._grade_value(actual) < self.min_grade_value:
                    issues.append({
                        "type": "GRADE_TOO_LOW",
                        "hop": i,
                        "grade": actual,
                        "minimum": {v: k for k, v in self.GRADE_ORDER.items()}[self.min_grade_value],
                    })
                    hop_result["issue"] = "GRADE_TOO_LOW"

            # Check chain hash continuity
            if i > 0:
                expected_hash = self._hash(chain[i - 1].canonical())
                if grant.chain_hash != expected_hash:
                    issues.append({
                        "type": "CHAIN_BROKEN",
                        "hop": i,
                        "expected": expected_hash,
                        "actual": grant.chain_hash,
                    })
                    hop_result["issue"] = "CHAIN_BROKEN"

            hops.append(hop_result)

        # Determine verdict
        if not issues:
            verdict = DelegationVerdict.ACCEPTED.value
            action = "ACCEPT"
        else:
            issue_types = {i["type"] for i in issues}
            if "CHAIN_BROKEN" in issue_types:
                verdict = DelegationVerdict.CHAIN_BROKEN.value
            elif "SCOPE_VIOLATION" in issue_types:
                verdict = DelegationVerdict.SCOPE_VIOLATION.value
            elif "DEPTH_EXCEEDED" in issue_types:
                verdict = DelegationVerdict.DEPTH_EXCEEDED.value
            else:
                verdict = DelegationVerdict.GRADE_TOO_LOW.value
            action = "REJECT"

        # Effective scope at end of chain
        effective_scope = chain[0].scope
        for grant in chain[1:]:
            effective_scope = effective_scope & grant.scope

        # Effective grade
        effective_grade = self._decay_grade(chain[0].evidence_grade, len(chain) - 1)

        return {
            "verdict": verdict,
            "action": action,
            "policy": self.policy.value,
            "chain_length": len(chain),
            "max_depth": self.max_depth,
            "original_scope": sorted(chain[0].scope),
            "effective_scope": sorted(effective_scope),
            "scope_narrowing": len(chain[0].scope) - len(effective_scope),
            "original_grade": chain[0].evidence_grade,
            "effective_grade": effective_grade,
            "issues": issues,
            "hops": hops,
            "hardy_1988": "confused deputy prevented" if not any(
                i["type"] == "SCOPE_VIOLATION" for i in issues
            ) else "CONFUSED DEPUTY DETECTED",
        }

    def build_chain(self, specs: list[dict]) -> list[DelegationGrant]:
        """Helper to build a chain from specs."""
        chain = []
        for i, spec in enumerate(specs):
            prev_hash = self._hash(chain[-1].canonical()) if chain else "genesis"
            grant = DelegationGrant(
                delegator=spec["delegator"],
                delegate=spec["delegate"],
                scope=set(spec["scope"]),
                evidence_grade=spec.get("grade", self._decay_grade("A", i)),
                chain_hash=spec.get("chain_hash", prev_hash),
                depth=i,
            )
            chain.append(grant)
        return chain


def demo():
    print("=" * 60)
    print("Trust Transitivity Validator — Confused Deputy Prevention")
    print("=" * 60)

    validator = TrustTransitivityValidator(
        policy=TransitivityPolicy.SCOPED,
        max_depth=3,
        min_grade="C",
    )

    # Scenario 1: Clean delegation with scope narrowing
    print("\n--- Scenario 1: Clean 3-hop with scope narrowing ---")
    chain1 = validator.build_chain([
        {"delegator": "alice", "delegate": "bob",
         "scope": ["read", "write", "execute", "admin"], "grade": "A"},
        {"delegator": "bob", "delegate": "carol",
         "scope": ["read", "write", "execute"], "grade": "B"},
        {"delegator": "carol", "delegate": "dave",
         "scope": ["read", "write"], "grade": "C"},
    ])
    print(json.dumps(validator.validate_delegation(chain1), indent=2))

    # Scenario 2: Confused deputy — scope WIDENS
    print("\n--- Scenario 2: Confused Deputy — scope widens at hop 2 ---")
    chain2 = validator.build_chain([
        {"delegator": "alice", "delegate": "bob",
         "scope": ["read", "write"], "grade": "A"},
        {"delegator": "bob", "delegate": "mallory",
         "scope": ["read", "write", "admin"], "grade": "B"},  # admin not in original!
    ])
    print(json.dumps(validator.validate_delegation(chain2), indent=2))

    # Scenario 3: Depth exceeded
    print("\n--- Scenario 3: Depth limit exceeded (4 hops, max 3) ---")
    chain3 = validator.build_chain([
        {"delegator": "a", "delegate": "b", "scope": ["read", "write"], "grade": "A"},
        {"delegator": "b", "delegate": "c", "scope": ["read", "write"], "grade": "B"},
        {"delegator": "c", "delegate": "d", "scope": ["read"], "grade": "C"},
        {"delegator": "d", "delegate": "e", "scope": ["read"], "grade": "D"},
    ])
    print(json.dumps(validator.validate_delegation(chain3), indent=2))

    # Scenario 4: NO_TRANSITIVITY policy
    print("\n--- Scenario 4: NO_TRANSITIVITY policy ---")
    strict = TrustTransitivityValidator(policy=TransitivityPolicy.NONE)
    chain4 = validator.build_chain([
        {"delegator": "alice", "delegate": "bob", "scope": ["read"], "grade": "A"},
        {"delegator": "bob", "delegate": "carol", "scope": ["read"], "grade": "B"},
    ])
    print(json.dumps(strict.validate_delegation(chain4), indent=2))

    # Scenario 5: Grade inflation attack
    print("\n--- Scenario 5: Grade inflation (hop 2 claims A, should be B) ---")
    chain5_specs = [
        {"delegator": "origin", "delegate": "mid", "scope": ["read", "write"], "grade": "A"},
        {"delegator": "mid", "delegate": "inflator", "scope": ["read"], "grade": "A"},  # should decay to B
    ]
    chain5 = validator.build_chain(chain5_specs)
    # Override grade to show inflation
    chain5[1].evidence_grade = "A"
    print(json.dumps(validator.validate_delegation(chain5), indent=2))

    print("\n" + "=" * 60)
    print("Three invariants for safe delegation:")
    print("  1. Scope MUST narrow or stay equal (never widen)")
    print("  2. Grade MUST decay by 1 per hop (never inflate)")
    print("  3. Depth MUST respect genesis constant (default: 3)")
    print("Hardy (1988): confused deputy = authority without verification.")
    print("X.509 pathLenConstraint: same problem, same solution.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
