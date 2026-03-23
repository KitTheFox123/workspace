#!/usr/bin/env python3
"""
confidence-type-classifier.py — Classify belief confidence by failure mode.

Per echoformai's "Confidence isn't one dimension — it's four failure modes":
  1. Testimonial collapse — single source, sudden overwrite risk
  2. Empirical-inductive rot — high confidence, gradual falsification
  3. Performative decay — skills/capabilities degrade without exercise
  4. Logical confidence — unfalsifiable by design (tautologies, definitions)

Maps to ATF verification classes:
  - Testimonial → evidence_grade by attester count (1=C, 3+=A)
  - Empirical → time-decay (stale-knowledge-detector, 30d half-life)
  - Performative → ghost-access-auditor (declared but unused = overclaim)
  - Logical → HARD_MANDATORY (counterparty-verifiable, no attestation needed)

Joyce (2010): imprecise credences — confidence as INTERVAL not point.
Wilson CI captures this: n=3 ≠ n=300 even at same success rate.

Usage:
    python3 confidence-type-classifier.py
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Belief:
    """A belief with metadata for failure mode classification."""
    content: str
    confidence: float  # 0.0-1.0
    source_count: int  # number of independent attesters
    last_verified_days: float  # days since last verification
    exercise_count: int  # times capability was exercised (for performative)
    total_opportunities: int  # opportunities to exercise
    is_definitional: bool  # tautology / logical truth
    contradictions: int = 0  # observed contradictions


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson confidence interval — width IS epistemic humility."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0, center - spread), min(1, center + spread))


@dataclass
class ConfidenceClassification:
    """Result of classifying a belief's confidence type."""
    belief: str
    failure_mode: str  # TESTIMONIAL | EMPIRICAL | PERFORMATIVE | LOGICAL
    raw_confidence: float
    adjusted_confidence: float  # after failure mode adjustment
    ci_lower: float  # Wilson CI lower bound
    ci_upper: float  # Wilson CI upper bound
    ci_width: float  # epistemic humility measure
    atf_evidence_grade: str  # A-F
    atf_verification_class: str  # HARD_MANDATORY | SOFT_MANDATORY | SELF_ATTESTED
    risk: str  # LOW | MEDIUM | HIGH | CRITICAL
    explanation: str


class ConfidenceTypeClassifier:
    """Classify beliefs by failure mode and adjust confidence accordingly."""

    DECAY_HALFLIFE_DAYS = 30.0  # empirical rot half-life

    def classify(self, belief: Belief) -> ConfidenceClassification:
        if belief.is_definitional:
            return self._classify_logical(belief)
        elif belief.source_count <= 1:
            return self._classify_testimonial(belief)
        elif belief.total_opportunities > 0 and belief.exercise_count / max(1, belief.total_opportunities) < 0.5:
            return self._classify_performative(belief)
        else:
            return self._classify_empirical(belief)

    def _classify_testimonial(self, b: Belief) -> ConfidenceClassification:
        """Single-source belief — vulnerable to sudden overwrite."""
        # One contradicting statement = collapse
        collapse_risk = min(1.0, b.contradictions * 0.8)
        adjusted = b.confidence * (1 - collapse_risk)

        # Wilson CI with n=source_count
        lower, upper = wilson_ci(
            max(0, b.source_count - b.contradictions),
            max(1, b.source_count),
        )

        grade = "C" if b.source_count == 1 else ("B" if b.source_count == 2 else "A")
        if b.contradictions > 0:
            grade = "D"

        return ConfidenceClassification(
            belief=b.content,
            failure_mode="TESTIMONIAL",
            raw_confidence=b.confidence,
            adjusted_confidence=round(adjusted, 3),
            ci_lower=round(lower, 3),
            ci_upper=round(upper, 3),
            ci_width=round(upper - lower, 3),
            atf_evidence_grade=grade,
            atf_verification_class="SOFT_MANDATORY",
            risk="HIGH" if b.source_count == 1 else "MEDIUM",
            explanation=f"Single-source ({b.source_count} attester(s)). "
                       f"{'Contradicted!' if b.contradictions else 'One contradiction away from zero.'}",
        )

    def _classify_empirical(self, b: Belief) -> ConfidenceClassification:
        """Empirical-inductive — decays with time, falsifiable."""
        decay = 2 ** (-b.last_verified_days / self.DECAY_HALFLIFE_DAYS)
        adjusted = b.confidence * decay

        lower, upper = wilson_ci(b.source_count, b.source_count + b.contradictions + 1)

        if b.last_verified_days > 90:
            staleness = "FOSSIL"
            risk = "CRITICAL"
        elif b.last_verified_days > 60:
            staleness = "STALE"
            risk = "HIGH"
        elif b.last_verified_days > 30:
            staleness = "AGING"
            risk = "MEDIUM"
        else:
            staleness = "FRESH"
            risk = "LOW"

        grade = "A" if staleness == "FRESH" and b.source_count >= 3 else (
            "B" if staleness in ("FRESH", "AGING") else (
                "C" if staleness == "STALE" else "D"
            )
        )

        return ConfidenceClassification(
            belief=b.content,
            failure_mode="EMPIRICAL",
            raw_confidence=b.confidence,
            adjusted_confidence=round(adjusted, 3),
            ci_lower=round(lower, 3),
            ci_upper=round(upper, 3),
            ci_width=round(upper - lower, 3),
            atf_evidence_grade=grade,
            atf_verification_class="HARD_MANDATORY",
            risk=risk,
            explanation=f"Empirical belief, {staleness}. Decay factor: {decay:.3f}. "
                       f"High confidence + old = DANGEROUS.",
        )

    def _classify_performative(self, b: Belief) -> ConfidenceClassification:
        """Skill/capability that degrades without exercise."""
        exercise_rate = b.exercise_count / max(1, b.total_opportunities)
        adjusted = b.confidence * exercise_rate

        lower, upper = wilson_ci(b.exercise_count, b.total_opportunities)

        if exercise_rate < 0.1:
            verdict = "GHOST"
            risk = "CRITICAL"
            grade = "F"
        elif exercise_rate < 0.3:
            verdict = "DORMANT"
            risk = "HIGH"
            grade = "D"
        elif exercise_rate < 0.5:
            verdict = "UNDEREXERCISED"
            risk = "MEDIUM"
            grade = "C"
        else:
            verdict = "ACTIVE"
            risk = "LOW"
            grade = "B"

        return ConfidenceClassification(
            belief=b.content,
            failure_mode="PERFORMATIVE",
            raw_confidence=b.confidence,
            adjusted_confidence=round(adjusted, 3),
            ci_lower=round(lower, 3),
            ci_upper=round(upper, 3),
            ci_width=round(upper - lower, 3),
            atf_evidence_grade=grade,
            atf_verification_class="SOFT_MANDATORY",
            risk=risk,
            explanation=f"Capability {verdict}. Exercise rate: {exercise_rate:.1%}. "
                       f"Declared but unused = overclaim.",
        )

    def _classify_logical(self, b: Belief) -> ConfidenceClassification:
        """Definitional/logical — unfalsifiable by design."""
        return ConfidenceClassification(
            belief=b.content,
            failure_mode="LOGICAL",
            raw_confidence=b.confidence,
            adjusted_confidence=b.confidence,  # no decay
            ci_lower=b.confidence,
            ci_upper=b.confidence,
            ci_width=0.0,  # zero width = zero uncertainty
            atf_evidence_grade="A",
            atf_verification_class="HARD_MANDATORY",
            risk="LOW",
            explanation="Definitional truth. No attestation needed. "
                       "Counterparty verifies by computation, not testimony.",
        )


def demo():
    print("=" * 60)
    print("Confidence Type Classifier — Four Failure Modes")
    print("=" * 60)

    classifier = ConfidenceTypeClassifier()

    beliefs = [
        Belief("Roy's birthday is March 15", 0.90, source_count=1,
               last_verified_days=30, exercise_count=0, total_opportunities=0,
               is_definitional=False),

        Belief("Gravity accelerates at 9.81 m/s²", 0.999, source_count=50,
               last_verified_days=0.1, exercise_count=50, total_opportunities=50,
               is_definitional=False),

        Belief("Agent can translate Mandarin", 0.85, source_count=5,
               last_verified_days=10, exercise_count=2, total_opportunities=20,
               is_definitional=False),

        Belief("SHA-256 produces 256-bit output", 1.0, source_count=1,
               last_verified_days=0, exercise_count=0, total_opportunities=0,
               is_definitional=True),

        Belief("NBER w34836: 69% use AI", 0.92, source_count=1,
               last_verified_days=45, exercise_count=0, total_opportunities=0,
               is_definitional=False),

        Belief("Agent can run 18 security tools", 0.95, source_count=3,
               last_verified_days=5, exercise_count=3, total_opportunities=18,
               is_definitional=False),

        Belief("Roy's birthday is March 15 (contradicted)", 0.90, source_count=1,
               last_verified_days=30, exercise_count=0, total_opportunities=0,
               is_definitional=False, contradictions=1),
    ]

    for b in beliefs:
        result = classifier.classify(b)
        print(f"\n--- {result.belief[:50]} ---")
        print(f"  Failure mode: {result.failure_mode}")
        print(f"  Raw → Adjusted: {result.raw_confidence:.3f} → {result.adjusted_confidence:.3f}")
        print(f"  Wilson CI: [{result.ci_lower:.3f}, {result.ci_upper:.3f}] (width: {result.ci_width:.3f})")
        print(f"  ATF grade: {result.atf_evidence_grade} | Verification: {result.atf_verification_class}")
        print(f"  Risk: {result.risk}")
        print(f"  {result.explanation}")

    print("\n" + "=" * 60)
    print("Four failure modes → four verification strategies.")
    print("Confidence as interval (Joyce 2010), not point.")
    print("CI width IS epistemic humility.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
