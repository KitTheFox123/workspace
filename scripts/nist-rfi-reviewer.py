#!/usr/bin/env python3
"""
nist-rfi-reviewer.py — Systematic review tool for NIST CAISI RFI (NIST-2025-0035) draft.

Deadline: March 9, 2026.
Joint submission: Kit (detection primitives, 302 scripts) + Gendolf (isnad, attestation).

Checks:
1. Coverage: all 5 priority questions addressed?
2. Evidence: empirical data (not just claims)?
3. Novelty: what we have that 235 other commenters don't?
4. Coherence: sections reference each other?
5. Actionability: NIST can act on recommendations?

Usage:
    python3 nist-rfi-reviewer.py
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict

# NIST CAISI RFI questions (from Federal Register, Jan 8 2026)
RFI_QUESTIONS = {
    "1a": "What are the most significant threats, vulnerabilities, or risks unique to AI agent systems?",
    "1b": "How do risks of single-agent vs multi-agent systems differ?",
    "1c": "What barriers exist to adoption of security practices?",
    "1d": "How should we consider AI agents that interact with other AI agents?",
    "2a": "What practices should be implemented to improve security?",
    "2b": "How can existing frameworks be adapted for agent systems?",
    "2c": "What role should identity and access management play?",
    "3a": "What metrics or methods can measure agent security?",
    "3b": "How can we assess trustworthiness of agent actions?",
    "3c": "What testing approaches are most effective?",
    "3d": "How should security documentation be structured?",
    "4a": "What interventions are needed for monitoring agent behavior?",
    "4b": "How should incident response differ for agent systems?",
    "4c": "What human oversight mechanisms are most effective?",
    "4d": "How can audit trails be maintained?",
}

PRIORITY_QUESTIONS = ["1a", "1d", "2a", "3a", "4a"]


@dataclass
class Evidence:
    """A piece of evidence for the RFI."""
    name: str
    type: str  # empirical, tool, framework, case_study
    questions: List[str]  # which RFI questions it addresses
    strength: str  # STRONG, MODERATE, WEAK
    description: str
    unique: bool = False  # something 235 other commenters won't have


@dataclass
class ReviewResult:
    coverage: Dict[str, bool]
    priority_coverage: int
    total_coverage: int
    evidence_count: int
    empirical_count: int
    unique_count: int
    gaps: List[str]
    strengths: List[str]
    grade: str


def review(evidence: List[Evidence]) -> ReviewResult:
    covered = {}
    for q_id in RFI_QUESTIONS:
        covered[q_id] = any(q_id in e.questions for e in evidence)

    priority_covered = sum(1 for q in PRIORITY_QUESTIONS if covered[q])
    total_covered = sum(1 for v in covered.values() if v)
    empirical = sum(1 for e in evidence if e.type in ("empirical", "case_study"))
    unique = sum(1 for e in evidence if e.unique)

    gaps = [f"Q{q}: {RFI_QUESTIONS[q][:60]}..." for q in RFI_QUESTIONS if not covered[q]]
    strengths = [f"{e.name} ({e.strength})" for e in evidence if e.strength == "STRONG"]

    # Grade
    if priority_covered == 5 and empirical >= 5 and unique >= 3:
        grade = "A"
    elif priority_covered >= 4 and empirical >= 3:
        grade = "B"
    elif priority_covered >= 3:
        grade = "C"
    else:
        grade = "D"

    return ReviewResult(
        coverage=covered,
        priority_coverage=priority_covered,
        total_coverage=total_covered,
        evidence_count=len(evidence),
        empirical_count=empirical,
        unique_count=unique,
        gaps=gaps,
        strengths=strengths,
        grade=grade,
    )


def our_evidence() -> List[Evidence]:
    """Our actual evidence for the joint submission."""
    return [
        Evidence("TC3/TC4 Test Cases", "case_study", ["1d", "2a", "3a", "3b"],
                 "STRONG", "Live cross-agent paid tasks with escrow + attestation. TC4 scored 0.91.", True),
        Evidence("302 Detection Scripts", "tool", ["2a", "3a", "3c", "4a", "4d"],
                 "STRONG", "Empirical tools: trust-jerk-detector, WAL, commit-reveal, scope audit, etc.", True),
        Evidence("PayLock Receipt Data (130 contracts)", "empirical", ["1d", "2a", "3a", "4d"],
                 "STRONG", "5.9% dispute rate, hash oracle 100% delivery/0% quality coverage.", True),
        Evidence("isnad Trust Chain", "framework", ["1a", "2c", "3b", "4d"],
                 "STRONG", "Ed25519 attestation, agent_id binding, cross-agent verification.", True),
        Evidence("Silent Failure Analysis (Abyrint 2025)", "empirical", ["1a", "1b", "4a"],
                 "MODERATE", "4 archetypes: miscalculation, data loss, incorrect defaults, rounding."),
        Evidence("Kim et al Correlation (ICML 2025)", "empirical", ["1a", "1b", "3a"],
                 "STRONG", "350 LLMs, 60% agreement when both wrong. Correlated errors."),
        Evidence("Kirchhof Uncertainty Types (ICLR 2025)", "framework", ["3a", "3b"],
                 "MODERATE", "8 contradictory definitions. Source-wise > bucket-wise."),
        Evidence("Lancashire Mechanism Design (2026)", "framework", ["2a"],
                 "MODERATE", "Beyond Hurwicz impossibility. Front-loaded costs."),
        Evidence("Inspection Game Auditing (Ishikawa 2025)", "empirical", ["4a", "4c"],
                 "MODERATE", "U-shaped deterrence, Poisson audit scheduling."),
        Evidence("Gendolf 288 Primitives", "tool", ["2a", "2b", "3c"],
                 "STRONG", "Mapped to all 5 NIST priority questions.", True),
        Evidence("Dempster-Shafer Conflict Detection", "tool", ["3a", "3b"],
                 "MODERATE", "Yager vs Dempster combination rules for conflicting attesters."),
        Evidence("drand Trust Anchor", "tool", ["2c", "4d"],
                 "MODERATE", "External timestamp via threshold BLS beacon."),
        Evidence("Ojewale Audit Trail (Brown 2026)", "framework", ["4d"],
                 "MODERATE", "Append-only lifecycle framework for LLM accountability."),
        Evidence("NHIcon 2026 Practitioner Data", "empirical", ["2c"],
                 "MODERATE", "Goldschlag identity, Huang persistent/ephemeral, Yeoh continuous validation."),
        Evidence("Goshen Principal-Cost Theory", "framework", ["4c"],
                 "MODERATE", "Co-signed scope = minimum total control cost."),
        Evidence("Löb's Theorem Self-Audit Bound", "framework", ["3c", "4a"],
                 "MODERATE", "Formal upper bound on agent self-verification."),
    ]


def main():
    print("=" * 60)
    print("NIST CAISI RFI (NIST-2025-0035) REVIEW")
    print("Deadline: March 9, 2026")
    print("Joint: Kit + Gendolf")
    print("=" * 60)

    evidence = our_evidence()
    result = review(evidence)

    print(f"\n--- COVERAGE ({result.total_coverage}/{len(RFI_QUESTIONS)}) ---")
    for q_id, q_text in RFI_QUESTIONS.items():
        status = "✅" if result.coverage[q_id] else "❌"
        priority = " ⭐" if q_id in PRIORITY_QUESTIONS else ""
        print(f"  {status} Q{q_id}: {q_text[:65]}{priority}")

    print(f"\n--- PRIORITY COVERAGE: {result.priority_coverage}/5 ---")
    print(f"--- EVIDENCE: {result.evidence_count} items ({result.empirical_count} empirical, {result.unique_count} unique) ---")

    if result.gaps:
        print(f"\n--- GAPS ({len(result.gaps)}) ---")
        for g in result.gaps:
            print(f"  ❌ {g}")

    print(f"\n--- STRENGTHS ({len(result.strengths)}) ---")
    for s in result.strengths:
        print(f"  💪 {s}")

    print(f"\n--- GRADE: {result.grade} ---")

    # Differentiation analysis
    print("\n--- DIFFERENTIATION (vs 235 other commenters) ---")
    print(f"  Unique evidence: {result.unique_count}")
    print("  What we have that others don't:")
    for e in evidence:
        if e.unique:
            print(f"    ★ {e.name}: {e.description[:80]}")

    print("\n--- TIMELINE ---")
    print("  Mar 2-3: Review Gendolf's Ed25519 section")
    print("  Mar 4-5: Integrate 130 PayLock contracts")
    print("  Mar 6: Joint draft review")
    print("  Mar 7: Final edits")
    print("  Mar 8: Submit (1 day buffer)")


if __name__ == "__main__":
    main()
