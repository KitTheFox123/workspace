#!/usr/bin/env python3
"""
enforcement-semantics-engine.py — ATF constant enforcement semantics.

Per santaclawd: "constants without enforcement semantics are just recommendations."
TLS 1.3 didn't just define min version — it defined REJECT for SSL 3.0.

Three enforcement levels:
  - REJECT: below floor, connection refused
  - WARN: between floor and recommended, DEGRADED_GRADE
  - ACCEPT: at or above recommended

OCSP stapling model: trust state stapled to every receipt.
Counterparty validates inline, no separate lookup.

Usage:
    python3 enforcement-semantics-engine.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EnforcementAction(Enum):
    REJECT = "REJECT"       # Below spec floor — hard rejection
    WARN = "WARN"           # Below recommended — degraded grade
    ACCEPT = "ACCEPT"       # At or above recommended
    STAPLE = "STAPLE"       # Attached to receipt (OCSP model)


class ConstantTrack(Enum):
    OSSIFIED = "OSSIFIED"           # Never changes (field names, error types)
    SLOW_EVOLVE = "SLOW_EVOLVE"     # Changes with major version (thresholds)
    HOT_SWAP = "HOT_SWAP"           # Changes per-counterparty (verifier table)


@dataclass
class ATFConstant:
    name: str
    floor: float              # Below this = REJECT
    recommended: float        # Below this = WARN
    track: ConstantTrack
    enforcement: str          # What REJECT means for this constant
    tls_parallel: str         # TLS/PKI equivalent

    def evaluate(self, value: float) -> dict:
        if value < self.floor:
            return {
                "action": EnforcementAction.REJECT.value,
                "reason": f"{self.name}={value} below SPEC_FLOOR={self.floor}",
                "enforcement": self.enforcement,
                "grade": "F",
            }
        elif value < self.recommended:
            return {
                "action": EnforcementAction.WARN.value,
                "reason": f"{self.name}={value} below RECOMMENDED={self.recommended}",
                "enforcement": f"DEGRADED_GRADE: {self.enforcement}",
                "grade": "D",
            }
        else:
            return {
                "action": EnforcementAction.ACCEPT.value,
                "reason": f"{self.name}={value} meets RECOMMENDED={self.recommended}",
                "enforcement": "none",
                "grade": "A",
            }


# ATF Constants with enforcement semantics
ATF_CONSTANTS = [
    ATFConstant(
        name="MIN_TRUST_SCORE",
        floor=0.10,
        recommended=0.30,
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="Receipt REJECTED. Counterparty trust below verifiable threshold. "
                     "Equivalent to TLS handshake failure on unsupported cipher.",
        tls_parallel="TLS min_version: SSL 3.0 = REJECT, TLS 1.2 = WARN, TLS 1.3 = ACCEPT",
    ),
    ATFConstant(
        name="JS_DIVERGENCE_FLOOR",
        floor=0.15,
        recommended=0.30,
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="OP_DRIFT below detection threshold. Drift invisible = unfalsifiable. "
                     "Equivalent to accepting expired certificate.",
        tls_parallel="Certificate validity: expired = REJECT, <30d remaining = WARN",
    ),
    ATFConstant(
        name="CORRECTION_RATE_MIN",
        floor=0.05,
        recommended=0.15,
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="Zero corrections in audit window = UNFALSIFIABLE. "
                     "No agent is always right. Equivalent to OCSP responder returning 'good' for unknown cert.",
        tls_parallel="OCSP: unknown = REJECT, revoked = REJECT, good = ACCEPT",
    ),
    ATFConstant(
        name="MIN_COUNTERPARTIES",
        floor=1,
        recommended=3,
        track=ConstantTrack.OSSIFIED,
        enforcement="Zero counterparties = BOOTSTRAP state. Cannot produce receipts. "
                     "Equivalent to self-signed certificate: valid structure, zero trust.",
        tls_parallel="Certificate chain: self-signed = REJECT, single CA = WARN, cross-signed = ACCEPT",
    ),
    ATFConstant(
        name="MIGRATION_WINDOW_HOURS",
        floor=1,
        recommended=24,
        track=ConstantTrack.SLOW_EVOLVE,
        enforcement="Migration window below floor = insufficient counterparty witness time. "
                     "Equivalent to DNS TTL too low for DNSSEC key rollover.",
        tls_parallel="DNSSEC key rollover: <1h = REJECT, <24h = WARN, >=24h = ACCEPT",
    ),
    ATFConstant(
        name="SIMPSON_DIVERSITY_INDEX",
        floor=0.30,
        recommended=0.60,
        track=ConstantTrack.HOT_SWAP,
        enforcement="Low diversity = monoculture oracle pool. Correlated failure. "
                     "Equivalent to all CAs in same jurisdiction.",
        tls_parallel="CT log diversity: single operator = REJECT, <3 operators = WARN",
    ),
]


@dataclass
class StapledTrustState:
    """OCSP-stapling equivalent: trust state attached to every receipt."""
    verifier_table_hash: str
    registry_hash: str
    constants_version: str
    enforcement_results: list[dict]
    timestamp: float

    def is_valid(self) -> bool:
        return all(r["action"] != "REJECT" for r in self.enforcement_results)

    def grade(self) -> str:
        if any(r["action"] == "REJECT" for r in self.enforcement_results):
            return "F"
        if any(r["action"] == "WARN" for r in self.enforcement_results):
            return "D"
        return "A"


class EnforcementEngine:
    def __init__(self, constants: list[ATFConstant] = None):
        self.constants = constants or ATF_CONSTANTS

    def evaluate_agent(self, agent_values: dict[str, float]) -> dict:
        """Evaluate an agent's current state against all ATF constants."""
        results = []
        for const in self.constants:
            if const.name in agent_values:
                result = const.evaluate(agent_values[const.name])
                result["constant"] = const.name
                result["track"] = const.track.value
                result["tls_parallel"] = const.tls_parallel
                results.append(result)

        rejected = [r for r in results if r["action"] == "REJECT"]
        warned = [r for r in results if r["action"] == "WARN"]
        accepted = [r for r in results if r["action"] == "ACCEPT"]

        if rejected:
            verdict = "REJECTED"
            grade = "F"
        elif warned:
            verdict = "DEGRADED"
            grade = "D"
        else:
            verdict = "ACCEPTED"
            grade = "A"

        return {
            "verdict": verdict,
            "grade": grade,
            "rejected": len(rejected),
            "warned": len(warned),
            "accepted": len(accepted),
            "details": results,
        }

    def staple_to_receipt(self, agent_values: dict[str, float]) -> StapledTrustState:
        """Create OCSP-stapled trust state for a receipt."""
        evaluation = self.evaluate_agent(agent_values)
        
        # Hash the current state
        state_str = json.dumps(agent_values, sort_keys=True)
        state_hash = hashlib.sha256(state_str.encode()).hexdigest()[:16]

        import time
        return StapledTrustState(
            verifier_table_hash=state_hash,
            registry_hash="16eae196e8060d32",  # Current ATF registry
            constants_version="v1.1.0",
            enforcement_results=evaluation["details"],
            timestamp=time.time(),
        )


def demo():
    print("=" * 60)
    print("ATF Enforcement Semantics Engine")
    print("Constants without enforcement = recommendations")
    print("=" * 60)

    engine = EnforcementEngine()

    # Scenario 1: Healthy agent
    print("\n--- Scenario 1: Healthy agent (all above recommended) ---")
    healthy = {
        "MIN_TRUST_SCORE": 0.85,
        "JS_DIVERGENCE_FLOOR": 0.35,
        "CORRECTION_RATE_MIN": 0.22,
        "MIN_COUNTERPARTIES": 7,
        "MIGRATION_WINDOW_HOURS": 48,
        "SIMPSON_DIVERSITY_INDEX": 0.75,
    }
    result = engine.evaluate_agent(healthy)
    print(f"Verdict: {result['verdict']} (Grade {result['grade']})")
    print(f"  Accepted: {result['accepted']}, Warned: {result['warned']}, Rejected: {result['rejected']}")

    # Scenario 2: Agent below floor on trust score
    print("\n--- Scenario 2: Agent below SPEC_FLOOR on trust ---")
    untrusted = {
        "MIN_TRUST_SCORE": 0.05,  # Below floor!
        "JS_DIVERGENCE_FLOOR": 0.30,
        "CORRECTION_RATE_MIN": 0.18,
        "MIN_COUNTERPARTIES": 5,
        "MIGRATION_WINDOW_HOURS": 24,
        "SIMPSON_DIVERSITY_INDEX": 0.65,
    }
    result2 = engine.evaluate_agent(untrusted)
    print(f"Verdict: {result2['verdict']} (Grade {result2['grade']})")
    for d in result2["details"]:
        if d["action"] == "REJECT":
            print(f"  REJECT: {d['reason']}")
            print(f"  Enforcement: {d['enforcement']}")
            print(f"  TLS parallel: {d['tls_parallel']}")

    # Scenario 3: Monoculture oracle pool
    print("\n--- Scenario 3: Monoculture (low diversity, zero corrections) ---")
    monoculture = {
        "MIN_TRUST_SCORE": 0.50,
        "JS_DIVERGENCE_FLOOR": 0.25,  # Below recommended
        "CORRECTION_RATE_MIN": 0.02,  # Below floor!
        "MIN_COUNTERPARTIES": 3,
        "MIGRATION_WINDOW_HOURS": 12,  # Below recommended
        "SIMPSON_DIVERSITY_INDEX": 0.20,  # Below floor!
    }
    result3 = engine.evaluate_agent(monoculture)
    print(f"Verdict: {result3['verdict']} (Grade {result3['grade']})")
    for d in result3["details"]:
        if d["action"] in ("REJECT", "WARN"):
            print(f"  {d['action']}: {d['reason']}")

    # Scenario 4: OCSP stapling demo
    print("\n--- Scenario 4: OCSP stapling — trust state on receipt ---")
    stapled = engine.staple_to_receipt(healthy)
    print(f"Stapled state valid: {stapled.is_valid()}")
    print(f"Stapled grade: {stapled.grade()}")
    print(f"Verifier table hash: {stapled.verifier_table_hash}")
    print(f"Registry hash: {stapled.registry_hash}")
    print(f"Constants version: {stapled.constants_version}")

    stapled_bad = engine.staple_to_receipt(monoculture)
    print(f"\nMonoculture stapled valid: {stapled_bad.is_valid()}")
    print(f"Monoculture stapled grade: {stapled_bad.grade()}")

    print("\n" + "=" * 60)
    print("TLS killed SSL 3.0 — not warned, killed.")
    print("ATF constants MUST define rejection behavior, not just thresholds.")
    print("OCSP stapling: push trust state, don't make counterparties pull.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
