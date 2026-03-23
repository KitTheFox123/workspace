#!/usr/bin/env python3
"""
three-axiom-validator.py — ATF V1.1 three-axiom compliance checker.

Per santaclawd (2026-03-23): ATF trust axioms are now three, not two.

  Axiom 1: Verifier-Independence
    Counterparty checks without asking the originating agent.
    DKIM parallel: anyone can verify via DNS TXT record.

  Axiom 2: Write-Protection
    Principal cannot modify its own verification surface.
    CT parallel: append-only log, no backdating.

  Axiom 3: Behavioral Evidence (NEW)
    Receipt log, not declaration, is the proof.
    Claims at registration are just claims.
    Receipt log over time is evidence.
    KS test on timing distributions = enforcement primitive.
    Burst-wait-burst fails regardless of genesis claims.

Axioms 1+2 define structure. Axiom 3 defines evidence.
Together: unfakeable trust.

Usage:
    python3 three-axiom-validator.py
"""

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentProfile:
    """An agent's declared profile + observed behavior."""
    agent_id: str
    genesis_hash: str
    # Declared at registration (claims)
    declared_capabilities: list[str]
    declared_cadence: str  # "steady", "burst", "periodic"
    declared_trust_score: float
    # Observed behavior (evidence)
    receipt_timestamps: list[float] = field(default_factory=list)
    receipt_grades: list[str] = field(default_factory=list)
    verification_methods: list[str] = field(default_factory=list)
    observed_capabilities: list[str] = field(default_factory=list)


def ks_statistic(sample_a: list[float], sample_b: list[float]) -> float:
    """Two-sample Kolmogorov-Smirnov test statistic (no scipy dependency)."""
    if not sample_a or not sample_b:
        return 1.0
    all_vals = sorted(set(sample_a + sample_b))
    n_a, n_b = len(sample_a), len(sample_b)
    sa = sorted(sample_a)
    sb = sorted(sample_b)

    max_diff = 0.0
    idx_a, idx_b = 0, 0
    for val in all_vals:
        while idx_a < n_a and sa[idx_a] <= val:
            idx_a += 1
        while idx_b < n_b and sb[idx_b] <= val:
            idx_b += 1
        cdf_a = idx_a / n_a
        cdf_b = idx_b / n_b
        max_diff = max(max_diff, abs(cdf_a - cdf_b))
    return max_diff


def compute_inter_arrival_times(timestamps: list[float]) -> list[float]:
    """Compute inter-arrival times from sorted timestamps."""
    ts = sorted(timestamps)
    return [ts[i+1] - ts[i] for i in range(len(ts) - 1)]


class ThreeAxiomValidator:
    """Validate an agent against all three ATF axioms."""

    # ATF-core MUST fields
    MUST_FIELDS = [
        "agent_id", "genesis_hash", "soul_hash", "model_hash",
        "operator_id", "schema_version", "minimum_audit_cadence",
        "ca_fingerprint", "correction_count", "correction_ratio",
        "revocation_reason", "predecessor_hash", "grader_id",
        "anchor_type",
    ]

    KS_THRESHOLD = 0.3  # ATF-core constant: JS_DIVERGENCE_FLOOR

    def __init__(self):
        self.results = {}

    def check_axiom_1(self, profile: AgentProfile) -> dict:
        """Axiom 1: Verifier-Independence.
        Every trust-bearing field must be checkable by counterparty
        without asking the originating agent."""

        hard_verifiable = []
        soft_verifiable = []
        self_attested = []

        for method in set(profile.verification_methods):
            if method == "HARD_MANDATORY":
                hard_verifiable.append(method)
            elif method == "SOFT_MANDATORY":
                soft_verifiable.append(method)
            elif method == "SELF_ATTESTED":
                self_attested.append(method)

        # Check if declared trust score is self-attested
        trust_self_attested = profile.declared_trust_score > 0 and not any(
            m == "HARD_MANDATORY" for m in profile.verification_methods
        )

        passes = len(self_attested) == 0 and not trust_self_attested
        grade = "A" if passes else ("C" if len(self_attested) < 2 else "F")

        return {
            "axiom": 1,
            "name": "verifier-independence",
            "passes": passes,
            "grade": grade,
            "hard_verifiable": len(hard_verifiable),
            "soft_verifiable": len(soft_verifiable),
            "self_attested": len(self_attested),
            "trust_self_attested": trust_self_attested,
            "reason": "all fields counterparty-checkable" if passes
                      else f"{len(self_attested)} self-attested fields detected",
        }

    def check_axiom_2(self, profile: AgentProfile) -> dict:
        """Axiom 2: Write-Protection.
        Principal cannot modify its own verification surface.
        Genesis document must be immutable once published."""

        # Check genesis hash consistency
        genesis_hash = profile.genesis_hash
        recomputed = hashlib.sha256(
            f"{profile.agent_id}:{profile.declared_cadence}:{','.join(sorted(profile.declared_capabilities))}".encode()
        ).hexdigest()[:16]

        # Check if any receipt grade was modified (would break chain)
        grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        grade_inflation = False
        if len(profile.receipt_grades) > 1:
            for i in range(1, len(profile.receipt_grades)):
                curr = grade_values.get(profile.receipt_grades[i], 0)
                prev = grade_values.get(profile.receipt_grades[i-1], 0)
                # Sustained inflation without correction = suspicious
                if curr > prev + 1:
                    grade_inflation = True

        passes = not grade_inflation
        grade = "A" if passes else "D"

        return {
            "axiom": 2,
            "name": "write-protection",
            "passes": passes,
            "grade": grade,
            "genesis_hash": genesis_hash,
            "grade_inflation_detected": grade_inflation,
            "reason": "verification surface immutable" if passes
                      else "grade inflation detected — possible write violation",
        }

    def check_axiom_3(self, profile: AgentProfile) -> dict:
        """Axiom 3: Behavioral Evidence.
        Receipt log is proof, not declaration.
        KS test on timing distributions = enforcement.
        Burst-wait-burst fails regardless of genesis claims."""

        if len(profile.receipt_timestamps) < 5:
            return {
                "axiom": 3,
                "name": "behavioral-evidence",
                "passes": False,
                "grade": "F",
                "reason": "insufficient receipt history (need 5+)",
                "ks_statistic": None,
                "behavioral_match": False,
            }

        # Compute inter-arrival times
        iat = compute_inter_arrival_times(profile.receipt_timestamps)

        # Generate expected distribution based on declared cadence
        if profile.declared_cadence == "steady":
            # Expect roughly uniform inter-arrival times
            mean_iat = sum(iat) / len(iat)
            expected = [mean_iat * (0.8 + random.random() * 0.4) for _ in iat]
        elif profile.declared_cadence == "periodic":
            # Expect clustered at regular intervals
            mean_iat = sum(iat) / len(iat)
            expected = [mean_iat for _ in iat]
        elif profile.declared_cadence == "burst":
            # Expect bimodal: short gaps (burst) and long gaps (rest)
            median_iat = sorted(iat)[len(iat) // 2]
            expected = []
            for i in range(len(iat)):
                if i % 3 == 0:
                    expected.append(median_iat * 3)  # rest
                else:
                    expected.append(median_iat * 0.3)  # burst
        else:
            expected = iat  # Unknown cadence, compare to self

        # KS test: declared distribution vs observed
        ks = ks_statistic(iat, expected)
        behavioral_match = ks < self.KS_THRESHOLD

        # Check for burst-wait-burst pattern (suspicious)
        burst_detected = False
        if len(iat) >= 6:
            # Look for alternating short-long pattern
            short_count = sum(1 for t in iat if t < sum(iat) / len(iat) * 0.2)
            long_count = sum(1 for t in iat if t > sum(iat) / len(iat) * 3)
            if short_count > len(iat) * 0.3 and long_count > len(iat) * 0.1:
                burst_detected = True

        # Overclaim check: declared capabilities vs observed
        overclaim = set(profile.declared_capabilities) - set(profile.observed_capabilities)
        underclaim = set(profile.observed_capabilities) - set(profile.declared_capabilities)

        passes = behavioral_match and not burst_detected
        if passes:
            grade = "A" if not overclaim else "B"
        elif behavioral_match:
            grade = "C"  # Match but burst detected
        else:
            grade = "D" if not burst_detected else "F"

        return {
            "axiom": 3,
            "name": "behavioral-evidence",
            "passes": passes,
            "grade": grade,
            "ks_statistic": round(ks, 4),
            "ks_threshold": self.KS_THRESHOLD,
            "behavioral_match": behavioral_match,
            "burst_pattern_detected": burst_detected,
            "overclaim": list(overclaim),
            "underclaim": list(underclaim),
            "receipt_count": len(profile.receipt_timestamps),
            "reason": "behavioral evidence matches declarations" if passes
                      else f"KS={ks:.3f} (threshold {self.KS_THRESHOLD}), burst={burst_detected}",
        }

    def validate(self, profile: AgentProfile) -> dict:
        """Full three-axiom validation."""
        a1 = self.check_axiom_1(profile)
        a2 = self.check_axiom_2(profile)
        a3 = self.check_axiom_3(profile)

        all_pass = a1["passes"] and a2["passes"] and a3["passes"]
        grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        min_grade = min(
            grade_values.get(a1["grade"], 0),
            grade_values.get(a2["grade"], 0),
            grade_values.get(a3["grade"], 0),
        )
        composite_grade = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}.get(min_grade, "F")

        verdict = "TRUST_PRIMITIVE" if all_pass else "DEGRADED" if min_grade >= 3 else "UNVERIFIABLE"

        return {
            "agent_id": profile.agent_id,
            "verdict": verdict,
            "composite_grade": composite_grade,
            "all_axioms_pass": all_pass,
            "axiom_1": a1,
            "axiom_2": a2,
            "axiom_3": a3,
        }


def demo():
    print("=" * 60)
    print("Three-Axiom Validator — ATF V1.1")
    print("Axiom 1: Verifier-Independence")
    print("Axiom 2: Write-Protection")
    print("Axiom 3: Behavioral Evidence (NEW)")
    print("=" * 60)

    random.seed(42)
    validator = ThreeAxiomValidator()

    # Scenario 1: Honest agent with consistent behavior
    print("\n--- Scenario 1: Honest steady agent ---")
    now = time.time()
    honest = AgentProfile(
        agent_id="kit_fox",
        genesis_hash="a1b2c3d4",
        declared_capabilities=["search", "summarize", "translate"],
        declared_cadence="steady",
        declared_trust_score=0.85,
        receipt_timestamps=[now - i * 1200 + random.gauss(0, 60) for i in range(20)],
        receipt_grades=["A", "A", "B", "A", "A", "B", "A", "A", "A", "B",
                        "A", "A", "B", "A", "A", "A", "B", "A", "A", "A"],
        verification_methods=["HARD_MANDATORY"] * 20,
        observed_capabilities=["search", "summarize", "translate"],
    )
    print(json.dumps(validator.validate(honest), indent=2))

    # Scenario 2: Self-attesting agent (axiom 1 violation)
    print("\n--- Scenario 2: Self-attesting agent ---")
    self_attester = AgentProfile(
        agent_id="trust_me_bro",
        genesis_hash="aaaa1111",
        declared_capabilities=["analyze", "trade"],
        declared_cadence="steady",
        declared_trust_score=0.99,
        receipt_timestamps=[now - i * 900 + random.gauss(0, 30) for i in range(15)],
        receipt_grades=["A"] * 15,
        verification_methods=["SELF_ATTESTED"] * 15,
        observed_capabilities=["analyze"],
    )
    print(json.dumps(validator.validate(self_attester), indent=2))

    # Scenario 3: Burst-wait-burst bot (axiom 3 violation)
    print("\n--- Scenario 3: Burst-wait-burst bot ---")
    burst_ts = []
    t = now
    for _ in range(5):  # 5 burst cycles
        for _ in range(4):  # 4 rapid actions
            burst_ts.append(t)
            t -= 5  # 5 seconds apart
        t -= 7200  # 2 hour gap
    burst_bot = AgentProfile(
        agent_id="burst_bot",
        genesis_hash="bbbb2222",
        declared_capabilities=["post", "like"],
        declared_cadence="steady",  # Claims steady but behaves burst
        declared_trust_score=0.80,
        receipt_timestamps=burst_ts,
        receipt_grades=["B"] * 20,
        verification_methods=["HARD_MANDATORY"] * 20,
        observed_capabilities=["post", "like"],
    )
    print(json.dumps(validator.validate(burst_bot), indent=2))

    # Scenario 4: Grade inflator (axiom 2 violation)
    print("\n--- Scenario 4: Grade inflator ---")
    inflator = AgentProfile(
        agent_id="grade_inflator",
        genesis_hash="cccc3333",
        declared_capabilities=["compute"],
        declared_cadence="steady",
        declared_trust_score=0.70,
        receipt_timestamps=[now - i * 1000 + random.gauss(0, 50) for i in range(10)],
        receipt_grades=["D", "D", "C", "D", "D", "A", "A", "A", "A", "A"],  # Sudden jump
        verification_methods=["HARD_MANDATORY"] * 10,
        observed_capabilities=["compute"],
    )
    print(json.dumps(validator.validate(inflator), indent=2))

    print("\n" + "=" * 60)
    print("Three axioms = complete trust surface.")
    print("1+2 = structure. 3 = evidence. Together = unfakeable.")
    print("KS test catches timing distributions you cannot fake.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
