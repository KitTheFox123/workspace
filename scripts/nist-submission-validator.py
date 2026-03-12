#!/usr/bin/env python3
"""
nist-submission-validator.py — Validates NIST CAISI RFI submission package.

NIST-2025-0035: Security Considerations for AI Agent Systems
Deadline: March 9, 2026
Docket: NIST-2025-0035

5 topics, 16 questions. Checks:
1. Coverage: which questions have evidence?
2. Evidence quality: empirical > theoretical > anecdotal
3. Uniqueness: what do we have that nobody else does?
4. Gaps: what's missing?
"""

import os
import json
from dataclasses import dataclass, field
from pathlib import Path


NIST_QUESTIONS = {
    "1a": "What are the primary threats and risks?",
    "1b": "How do agents introduce NEW security challenges?",
    "1c": "What are adoption barriers?",
    "1d": "Attack vectors unique to agent systems?",
    "2a": "Best practices for secure development?",
    "2b": "Identity and access management for agents?",
    "2c": "Secure communication protocols?",
    "2d": "Monitoring and logging practices?",
    "3a": "Metrics for measuring agent security?",
    "3b": "Benchmarks and evaluation frameworks?",
    "3c": "Testing methodologies?",
    "3d": "User-facing security documentation?",
    "4a": "Oversight and governance for deployed agents?",
    "4b": "Incident response for agent failures?",
    "4c": "Continuous monitoring approaches?",
    "4d": "Cross-organizational trust?",
}

PRIORITY_QUESTIONS = {"1a", "1d", "2a", "3a", "4a"}


@dataclass
class Evidence:
    name: str
    question_ids: list[str]
    evidence_type: str  # "empirical", "theoretical", "tool", "anecdotal"
    unique: bool = False  # Do we have something nobody else does?
    description: str = ""


def build_evidence_inventory() -> list[Evidence]:
    """Our actual evidence for NIST CAISI RFI."""
    return [
        # Empirical
        Evidence("TC4 PayLock", ["1d", "2a", "3a", "4a", "4d"],
                 "empirical", True, "Live verify-then-pay. 0.92 score. 5.9% dispute rate. Clove Δ50."),
        Evidence("TC3 PayLock", ["2a", "3a"],
                 "empirical", True, "First cross-agent escrow. Score 0.92."),
        Evidence("130 PayLock contracts", ["3a", "3b", "4a"],
                 "empirical", True, "bro_agent dataset. 91 pending, 6 abandoned, 2 disputed."),
        Evidence("Moltbook suspension x3", ["1d", "2d"],
                 "empirical", True, "Captcha failures = silent API drift. Real-world silent failure."),
        
        # Tools (299+ scripts)
        Evidence("integer-brier-scorer.py", ["2a", "3a", "3c"],
                 "tool", True, "Deterministic cross-VM scoring. Basis points, no floats."),
        Evidence("execution-trace-commit.py", ["2a", "2d", "3a"],
                 "tool", True, "4-level attestation: rule/trace/env/semantic."),
        Evidence("canary-spec-commit.py", ["2a", "4c"],
                 "tool", True, "Pre-committed probes for circuit breaker recovery."),
        Evidence("pac-heartbeat-audit.py", ["3a", "3c", "4c"],
                 "tool", True, "PAC bounds for monitoring cadence. ε-δ tradeoff."),
        Evidence("feed-injection-detector.py", ["1a", "1d"],
                 "tool", True, "14 patterns for indirect prompt injection in feeds."),
        Evidence("trust-jerk-detector.py", ["4c", "3a"],
                 "tool", True, "Third-derivative early warning. Nature Comms 2025."),
        Evidence("silent-failure-classifier.py", ["1a", "1d", "2d"],
                 "tool", True, "Abyrint 4 archetypes. Absence of alarm ≠ correctness."),
        Evidence("stochastic-audit-sampler.py", ["4c", "3c"],
                 "tool", True, "Poisson vs fixed: 22.8% vs 0% detection."),
        Evidence("attestation-signer.py", ["2b", "2c", "4d"],
                 "tool", True, "Ed25519 JWS + envelope for isnad."),
        
        # Infrastructure
        Evidence("isnad sandbox", ["2b", "4d"],
                 "tool", True, "Live trust registry. Ed25519 attestation. agent_id binding."),
        Evidence("isnad RFC", ["2b", "2c", "4d"],
                 "theoretical", True, "Universal trust pattern. Identity→attestation→corroboration."),
        
        # Research-backed
        Evidence("Kim et al ICML 2025", ["1a", "3a"],
                 "theoretical", False, "60% correlated errors across LLMs. Attester diversity."),
        Evidence("Kirchhof ICLR 2025", ["3a", "3b"],
                 "theoretical", False, "8 uncertainty definitions contradict. Source-wise > dichotomy."),
        Evidence("Kaya et al IEEE S&P 2026", ["1a", "1d"],
                 "theoretical", False, "13% e-commerce exposed to indirect prompt injection."),
        Evidence("Lancashire arXiv 2602.01790", ["2a", "4a"],
                 "theoretical", False, "Beyond Hurwicz. Mechanism design without revelation."),
        Evidence("Abyrint/Strand 2025", ["1a", "1d", "2d"],
                 "theoretical", False, "4 silent failure archetypes in financial technology."),
    ]


def validate_submission(evidence: list[Evidence]) -> dict:
    """Validate coverage and quality."""
    coverage = {}
    for q_id in NIST_QUESTIONS:
        items = [e for e in evidence if q_id in e.question_ids]
        empirical = [e for e in items if e.evidence_type == "empirical"]
        unique = [e for e in items if e.unique]
        coverage[q_id] = {
            "total": len(items),
            "empirical": len(empirical),
            "unique": len(unique),
            "priority": q_id in PRIORITY_QUESTIONS,
        }
    
    covered = sum(1 for v in coverage.values() if v["total"] > 0)
    priority_covered = sum(1 for q_id in PRIORITY_QUESTIONS 
                          if coverage[q_id]["total"] > 0)
    empirical_count = sum(1 for e in evidence if e.evidence_type == "empirical")
    unique_count = sum(1 for e in evidence if e.unique)
    
    # Grade
    score = (covered / len(NIST_QUESTIONS)) * 0.4 + \
            (priority_covered / len(PRIORITY_QUESTIONS)) * 0.3 + \
            (min(empirical_count, 5) / 5) * 0.15 + \
            (min(unique_count, 10) / 10) * 0.15
    
    if score >= 0.85: grade = "A"
    elif score >= 0.70: grade = "B"
    elif score >= 0.55: grade = "C"
    else: grade = "D"
    
    return {
        "coverage": coverage,
        "total_questions": len(NIST_QUESTIONS),
        "covered": covered,
        "priority_covered": priority_covered,
        "priority_total": len(PRIORITY_QUESTIONS),
        "empirical": empirical_count,
        "unique": unique_count,
        "total_evidence": len(evidence),
        "grade": grade,
        "score": round(score, 3),
    }


def main():
    print("=" * 70)
    print("NIST CAISI RFI SUBMISSION VALIDATOR")
    print("NIST-2025-0035 | Deadline: March 9, 2026 | 5 days remaining")
    print("=" * 70)

    evidence = build_evidence_inventory()
    result = validate_submission(evidence)

    print(f"\n--- Coverage: {result['covered']}/{result['total_questions']} questions ---")
    print(f"{'Q':<5} {'Priority':<10} {'Evidence':<10} {'Empirical':<10} {'Unique':<8} {'Question'}")
    print("-" * 80)
    
    for q_id, info in result["coverage"].items():
        priority = "★" if info["priority"] else " "
        status = "✅" if info["total"] > 0 else "❌"
        print(f"{q_id:<5} {priority:<10} {info['total']:<10} {info['empirical']:<10} "
              f"{info['unique']:<8} {NIST_QUESTIONS[q_id][:40]}")

    print(f"\n--- Summary ---")
    print(f"Grade: {result['grade']} (score: {result['score']})")
    print(f"Coverage: {result['covered']}/{result['total_questions']} questions")
    print(f"Priority: {result['priority_covered']}/{result['priority_total']} covered")
    print(f"Evidence: {result['total_evidence']} items ({result['empirical']} empirical, {result['unique']} unique)")

    # Gaps
    gaps = [q_id for q_id, info in result["coverage"].items() if info["total"] == 0]
    if gaps:
        print(f"\n--- GAPS ({len(gaps)}) ---")
        for q_id in gaps:
            print(f"  ❌ {q_id}: {NIST_QUESTIONS[q_id]}")

    # Differentiators
    print(f"\n--- Key Differentiators ---")
    print("1. EMPIRICAL: Live agent-to-agent escrow with real disputes (TC3/TC4)")
    print("2. TOOLING: 299+ runnable scripts, not just recommendations")
    print("3. CROSS-AGENT: Multi-agent validation with measured divergence")
    print("4. DETERMINISM: Integer scoring for cross-VM audit (no float problems)")
    print("5. OPEN: isnad sandbox live, tools open-source, methodology published")


if __name__ == "__main__":
    main()
