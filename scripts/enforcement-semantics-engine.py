#!/usr/bin/env python3
"""
enforcement-semantics-engine.py — ATF enforcement semantics per santaclawd.

TLS 1.3 didn't just define min version — it defined what REJECT means.
ATF needs the same: constants without enforcement semantics are recommendations.

Three enforcement tiers:
  - REJECT: below SPEC_FLOOR. Hard kill. No fallback. (TLS 1.3 removing SSLv3)
  - WARN + DEGRADED_GRADE: between FLOOR and RECOMMENDED. (TLS deprecation warnings)
  - ACCEPT: at or above RECOMMENDED.

OCSP lesson (Feisty Duck, Jan 2025): soft-fail = no security. An attacker blocks
the check and proceeds. Chrome disabled OCSP in 2012 because soft-fail is pointless.
ATF must hard-fail on SPEC_FLOOR violations.

DigiNotar lesson (2011): CAA as MUST was 8 years after SHOULD. Don't wait for the breach.

Usage:
    python3 enforcement-semantics-engine.py
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EnforcementAction(Enum):
    REJECT = "REJECT"           # Hard kill, no fallback
    DEGRADED = "DEGRADED"       # Warn + grade reduction
    ACCEPT = "ACCEPT"           # Within spec
    OVERRIDE = "OVERRIDE"       # Counterparty policy stricter than spec


class ConstantTrack(Enum):
    OSSIFIED = "OSSIFIED"       # Never changes (field names, hash algorithms)
    SLOW_EVOLVE = "SLOW_EVOLVE" # Changes via formal process (30d+ window)
    HOT_SWAP = "HOT_SWAP"       # Can change per-receipt (verifier table)


@dataclass
class ATFConstant:
    name: str
    value: float | int | str
    track: ConstantTrack
    enforcement: str  # What happens on violation
    spec_floor: Optional[float] = None  # Hard kill threshold
    recommended: Optional[float] = None  # Target threshold
    description: str = ""


# ATF Constants Registry with enforcement semantics
ATF_CONSTANTS = [
    ATFConstant(
        name="MIN_WITNESSES",
        value=3,
        track=ConstantTrack.OSSIFIED,
        enforcement="REJECT if witnesses < 3. No quorum = no verification.",
        spec_floor=3,
        recommended=5,
        description="Minimum independent witnesses for key ceremony / migration",
    ),
    ATFConstant(
        name="SPEC_MINIMUM_WINDOW",
        value=86400,  # 24h in seconds
        track=ConstantTrack.OSSIFIED,
        enforcement="REJECT migration if window < 24h. Rushed migration = attack vector.",
        spec_floor=86400,
        recommended=259200,  # 72h
        description="Minimum key migration window in seconds",
    ),
    ATFConstant(
        name="JS_DIVERGENCE_FLOOR",
        value=0.3,
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="REJECT if JS divergence >= floor. Behavioral drift = identity compromise.",
        spec_floor=0.3,
        recommended=0.15,
        description="Jensen-Shannon divergence threshold for OP_DRIFT",
    ),
    ATFConstant(
        name="CORRECTION_RANGE_MIN",
        value=0.05,
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="DEGRADED if correction rate < 0.05. Zero corrections = unfalsifiable.",
        spec_floor=0.0,
        recommended=0.05,
        description="Minimum healthy correction frequency",
    ),
    ATFConstant(
        name="CORRECTION_RANGE_MAX",
        value=0.40,
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="DEGRADED if correction rate > 0.40. Too many corrections = unreliable.",
        spec_floor=None,
        recommended=0.40,
        description="Maximum healthy correction frequency",
    ),
    ATFConstant(
        name="DECAY_HALFLIFE",
        value=2592000,  # 30d in seconds
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="DEGRADED if trust not refreshed within 2 half-lives. Stale trust = fossil.",
        spec_floor=None,
        recommended=2592000,
        description="Trust score decay half-life in seconds",
    ),
    ATFConstant(
        name="HASH_ALGORITHM",
        value="sha256",
        track=ConstantTrack.OSSIFIED,
        enforcement="REJECT if hash != sha256. No algorithm negotiation. DigiNotar lesson.",
        spec_floor=None,
        recommended=None,
        description="Canonical hash algorithm for all ATF hashes",
    ),
    ATFConstant(
        name="TRANSCRIPT_HASH_ALGORITHM",
        value="sha256",
        track=ConstantTrack.OSSIFIED,
        enforcement="REJECT if ceremony transcript uses different hash. Impl-defined = unchecked.",
        spec_floor=None,
        recommended=None,
        description="Hash algorithm for ceremony transcripts",
    ),
    ATFConstant(
        name="MAX_CHAIN_LENGTH",
        value=5,
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="DEGRADED at length > 5. REJECT at > 10. Delegation cascade = intent dilution.",
        spec_floor=10,
        recommended=5,
        description="Maximum delegation chain length before degradation",
    ),
    ATFConstant(
        name="SELF_GRADE_CAP",
        value="C",
        track=ConstantTrack.OSSIFIED,
        enforcement="REJECT if self-graded above C. Self-attestation = axiom 1 violation.",
        spec_floor=None,
        recommended=None,
        description="Maximum grade for self-attested evidence",
    ),
]


@dataclass
class EnforcementResult:
    constant_name: str
    presented_value: float | int | str
    action: EnforcementAction
    reason: str
    grade_impact: str  # How this affects overall grade


class EnforcementEngine:
    """Evaluate ATF constant compliance with enforcement semantics."""

    def __init__(self):
        self.constants = {c.name: c for c in ATF_CONSTANTS}

    def evaluate(self, name: str, value) -> EnforcementResult:
        """Evaluate a presented value against ATF constant."""
        if name not in self.constants:
            return EnforcementResult(
                constant_name=name,
                presented_value=value,
                action=EnforcementAction.REJECT,
                reason=f"Unknown constant: {name}",
                grade_impact="F — unknown constant = untrusted",
            )

        c = self.constants[name]

        # String constants: exact match required
        if isinstance(c.value, str):
            if str(value) != c.value:
                return EnforcementResult(
                    constant_name=name,
                    presented_value=value,
                    action=EnforcementAction.REJECT,
                    reason=f"Expected {c.value}, got {value}. {c.enforcement}",
                    grade_impact="F — spec violation",
                )
            return EnforcementResult(
                constant_name=name,
                presented_value=value,
                action=EnforcementAction.ACCEPT,
                reason="Matches spec constant",
                grade_impact="No impact",
            )

        # Numeric constants with floor/recommended
        value = float(value)

        # Check if this is a "minimum" or "maximum" type constant
        is_minimum = name in {"MIN_WITNESSES", "SPEC_MINIMUM_WINDOW", "CORRECTION_RANGE_MIN"}
        is_maximum = name in {"JS_DIVERGENCE_FLOOR", "CORRECTION_RANGE_MAX", "MAX_CHAIN_LENGTH"}

        if c.spec_floor is not None:
            if is_minimum and value < c.spec_floor:
                return EnforcementResult(
                    constant_name=name,
                    presented_value=value,
                    action=EnforcementAction.REJECT,
                    reason=f"Below SPEC_FLOOR ({c.spec_floor}). {c.enforcement}",
                    grade_impact="F — hard rejection",
                )
            if is_maximum and value >= c.spec_floor:
                return EnforcementResult(
                    constant_name=name,
                    presented_value=value,
                    action=EnforcementAction.REJECT,
                    reason=f"At/above SPEC_FLOOR ({c.spec_floor}). {c.enforcement}",
                    grade_impact="F — hard rejection",
                )

        if c.recommended is not None:
            if is_minimum and value < c.recommended:
                return EnforcementResult(
                    constant_name=name,
                    presented_value=value,
                    action=EnforcementAction.DEGRADED,
                    reason=f"Below RECOMMENDED ({c.recommended}). Above FLOOR.",
                    grade_impact="Grade capped at B",
                )
            if is_maximum and value > c.recommended:
                return EnforcementResult(
                    constant_name=name,
                    presented_value=value,
                    action=EnforcementAction.DEGRADED,
                    reason=f"Above RECOMMENDED ({c.recommended}). Below FLOOR.",
                    grade_impact="Grade capped at B",
                )

        return EnforcementResult(
            constant_name=name,
            presented_value=value,
            action=EnforcementAction.ACCEPT,
            reason="Within spec",
            grade_impact="No impact",
        )

    def audit_agent(self, agent_values: dict) -> dict:
        """Full audit of an agent's constant compliance."""
        results = []
        rejections = 0
        degradations = 0

        for name, value in agent_values.items():
            r = self.evaluate(name, value)
            results.append(r)
            if r.action == EnforcementAction.REJECT:
                rejections += 1
            elif r.action == EnforcementAction.DEGRADED:
                degradations += 1

        # Overall grade
        if rejections > 0:
            grade = "F"
            verdict = "REJECTED"
        elif degradations > 2:
            grade = "D"
            verdict = "HEAVILY_DEGRADED"
        elif degradations > 0:
            grade = "B"
            verdict = "DEGRADED"
        else:
            grade = "A"
            verdict = "COMPLIANT"

        return {
            "verdict": verdict,
            "grade": grade,
            "rejections": rejections,
            "degradations": degradations,
            "total_checked": len(results),
            "results": [
                {
                    "constant": r.constant_name,
                    "value": r.presented_value,
                    "action": r.action.value,
                    "reason": r.reason,
                }
                for r in results
            ],
        }


def demo():
    print("=" * 60)
    print("ATF Enforcement Semantics Engine")
    print("TLS 1.3 model: REJECT not WARN")
    print("=" * 60)

    engine = EnforcementEngine()

    # Scenario 1: Compliant agent
    print("\n--- Scenario 1: Fully compliant agent ---")
    result = engine.audit_agent({
        "MIN_WITNESSES": 5,
        "SPEC_MINIMUM_WINDOW": 259200,
        "JS_DIVERGENCE_FLOOR": 0.10,
        "HASH_ALGORITHM": "sha256",
        "CORRECTION_RANGE_MIN": 0.15,
        "MAX_CHAIN_LENGTH": 3,
    })
    print(json.dumps(result, indent=2))

    # Scenario 2: Agent with soft-fail violations (OCSP pattern)
    print("\n--- Scenario 2: Below RECOMMENDED but above FLOOR ---")
    result2 = engine.audit_agent({
        "MIN_WITNESSES": 3,  # At floor, not recommended
        "SPEC_MINIMUM_WINDOW": 86400,  # At floor
        "JS_DIVERGENCE_FLOOR": 0.20,  # Between floor and recommended
        "HASH_ALGORITHM": "sha256",
    })
    print(json.dumps(result2, indent=2))

    # Scenario 3: Hard rejection (DigiNotar pattern)
    print("\n--- Scenario 3: Below SPEC_FLOOR — hard REJECT ---")
    result3 = engine.audit_agent({
        "MIN_WITNESSES": 1,  # Below floor!
        "SPEC_MINIMUM_WINDOW": 3600,  # 1 hour — way below 24h floor
        "HASH_ALGORITHM": "md5",  # Wrong algorithm!
    })
    print(json.dumps(result3, indent=2))

    # Scenario 4: Delegation cascade
    print("\n--- Scenario 4: Delegation cascade (chain too long) ---")
    result4 = engine.audit_agent({
        "MAX_CHAIN_LENGTH": 7,  # Above recommended, below hard reject
        "MIN_WITNESSES": 5,
        "HASH_ALGORITHM": "sha256",
    })
    print(json.dumps(result4, indent=2))

    # Scenario 5: Self-grading above cap
    print("\n--- Scenario 5: Self-grade above cap ---")
    r = engine.evaluate("SELF_GRADE_CAP", "A")  # Claiming A when cap is C
    print(f"Self-grade 'A': {r.action.value} — {r.reason}")

    print("\n" + "=" * 60)
    print("OCSP lesson: soft-fail = no security.")
    print("Chrome disabled OCSP in 2012. ATF must hard-fail on FLOOR.")
    print("DigiNotar lesson: SHOULD became MUST 8 years too late.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
