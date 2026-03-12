#!/usr/bin/env python3
"""
nist-rfi-response-mapper.py — Map Kit's detection primitives to NIST CAISI RFI questions.

NIST-2025-0035: "Security Considerations for AI Agent Systems"
Deadline: March 9, 2026
Priority questions (per RFI): 1(a), 1(d), 2(a), 3(a), 4(a)

Maps our empirical work (302+ scripts, TC3/TC4, isnad) to specific RFI questions
with evidence quality grades.

Usage:
    python3 nist-rfi-response-mapper.py
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict

# NIST CAISI RFI Questions (4 topics)
RFI_QUESTIONS = {
    "1a": "Unique security threats/risks/vulnerabilities affecting AI agent systems",
    "1b": "How threats vary by model capability, scaffold, tool use, deployment",
    "1c": "Barriers to adoption from security threats",
    "1d": "How threats changed over time / likely evolution",
    "1e": "Unique threats to multi-agent systems",
    "2a": "Technical controls/processes to improve security",
    "2b": "Effectiveness variation with changes to capability/deployment",
    "2c": "How controls need to change with evolution",
    "2d": "Patching/updating AI agent systems",
    "2e": "Relevant cybersecurity guidelines/frameworks",
    "3a": "Methods to anticipate/identify/assess threats during development",
    "3b": "How to assess security of a particular agent system",
    "3c": "Documentation from upstream that aids downstream security",
    "3d": "User-facing documentation for secure deployment",
    "4a": "Limiting access/extent of deployment environments",
    "4b": "Modifying environments to mitigate threats; rollbacks/undoes",
}

PRIORITY_QUESTIONS = {"1a", "1d", "2a", "3a", "4a"}


@dataclass
class Evidence:
    name: str
    description: str
    questions: List[str]  # which RFI questions this addresses
    evidence_type: str    # "script" | "test_case" | "framework" | "research"
    strength: str         # "STRONG" | "MODERATE" | "WEAK"
    source: str           # file path or reference


# Our empirical evidence mapped to RFI questions
EVIDENCE = [
    # Topic 1: Threats
    Evidence("Silent Failure Detection", "Abyrint (2025): 4 archetypes of silent failure in agent systems. AIRT: 7/11 failures were silent.",
             ["1a", "1b"], "research", "STRONG", "silent-failure-classifier.py"),
    Evidence("Behavioral Correlation", "Kim et al (ICML 2025): 60% agreement when both wrong across 350 LLMs. Training data overlap = invisible collusion.",
             ["1a", "1e"], "research", "STRONG", "behavioral-correlation-detector.py"),
    Evidence("Identity Drift", "Pei et al (2025): capabilities converge, alignment diverges. Behavioral fingerprinting of 18 models.",
             ["1a", "1d"], "research", "STRONG", "soul-audit-scorer.py"),
    Evidence("Trust Jerk (3rd Derivative)", "Beauducel et al (Nature Comms 2025): jerk predicted 92% of volcanic eruptions. Applied to agent drift.",
             ["1a", "1d"], "script", "STRONG", "trust-jerk-detector.py"),
    Evidence("Cross-Derivative Correlation", "Correlated jerk across dimensions = systemic failure. Independent = local.",
             ["1a", "1b"], "script", "MODERATE", "cross-derivative-correlator.py"),
    Evidence("Löb Self-Audit Bound", "Löb (1955): system proving own consistency = inconsistent. Formal upper bound on self-audit.",
             ["1a", "3a"], "framework", "STRONG", "loeb-self-audit-bound.py"),

    # Topic 2: Controls
    Evidence("Commit-Reveal Intent Binding", "Hoyte (2024) two attacks + ERC-5732. Hash intent before execution, reveal after.",
             ["2a", "2c"], "script", "STRONG", "commit-reveal-intent.py"),
    Evidence("WAL for Agent Trust", "Write-ahead log pattern from databases (1970s). Append-only, hash-chained, tamper-evident.",
             ["2a", "2e"], "script", "STRONG", "trust-wal.py"),
    Evidence("Null Receipt Tracking", "Track refusals as alignment fingerprint. What you refuse = who you are.",
             ["2a", "2b"], "script", "MODERATE", "null-receipt-tracker.py"),
    Evidence("Genesis Anchor", "Content-addressed identity anchoring. SHA-256 of SOUL.md at creation time.",
             ["2a", "2d"], "script", "MODERATE", "genesis-anchor.py"),
    Evidence("Poisson Audit Scheduling", "Ishikawa & Fontanari (EPJ B 2025): memoryless = ungameable. 22.8% detection vs 0% for fixed.",
             ["2a", "2c"], "script", "STRONG", "poisson-audit-sampler.py"),
    Evidence("Dempster-Shafer Conflict Detection", "Sentz & Ferson (Sandia 2002). Yager rule preserves conflict as ignorance.",
             ["2a", "3a"], "script", "MODERATE", "dempster-shafer-trust.py"),
    Evidence("Principal-Cost Scope", "Goshen & Squire (2017). Co-signed scope manifest minimizes total control cost.",
             ["2a", "4a"], "framework", "STRONG", "principal-cost-scope.py"),
    Evidence("Inspection Game", "Avenhaus et al (2001): IAEA nuclear safeguards game theory for agent audit.",
             ["2a", "2c"], "script", "STRONG", "inspection-game.py"),

    # Topic 3: Assessment
    Evidence("TC3/TC4 Test Cases", "Live verify-then-pay with escrow. TC3 scored 0.92, TC4 scored 0.91. Cross-agent attestation.",
             ["3a", "3b"], "test_case", "STRONG", "dispute-oracle-sim.py"),
    Evidence("Uncertainty Type Classification", "Kirchhof et al (ICLR 2025). Source-wise > aleatoric/epistemic dichotomy.",
             ["3a", "3b"], "script", "STRONG", "uncertainty-type-classifier.py"),
    Evidence("Johari Scope Audit", "Luft & Ingham (1955) for agent scope. 4 quadrants: open/blind/hidden/unknown.",
             ["3a", "3b"], "script", "MODERATE", "johari-scope-audit.py"),
    Evidence("Attester Independence", "Kish design effect. effective_N = N/(1+(N-1)*r). 6 Claudes at r=0.9 = N=1.5.",
             ["3a", "1e"], "script", "STRONG", "uncorrelated-oracle-scorer.py"),
    Evidence("Heisenberg Trust Uncertainty", "Meng (Harvard 2025): can't optimize + assess error from same data.",
             ["3a", "3c"], "framework", "STRONG", "heisenberg-trust-uncertainty.py"),

    # Topic 4: Deployment
    Evidence("Scope Manifest + WAL", "Declare capabilities, log actions, diff = absence evidence. Constrains deployment.",
             ["4a", "4b"], "script", "STRONG", "absence-evidence-scorer.py"),
    Evidence("drand Trust Anchor", "External timestamp via drand beacon. Unforgeable, 30s rounds, threshold BLS.",
             ["4a", "2a"], "script", "MODERATE", "drand-trust-anchor.py"),
    Evidence("Merkle Trust Batch", "RFC 6962 Certificate Transparency pattern for agent evidence. O(log n) proofs.",
             ["4a", "2a"], "script", "MODERATE", "merkle-trust-batch.py"),
    Evidence("Isnad Framework", "Live trust chain infrastructure. Ed25519 signing, cross-agent attestation.",
             ["4a", "3b"], "framework", "STRONG", "isnad-client.py"),
    Evidence("Lancashire Mechanism Design", "Beyond Hurwicz impossibility. Front-loaded costs under uncertainty.",
             ["4b", "2c"], "framework", "STRONG", "mechanism-design-trust.py"),
]


def generate_report():
    print("=" * 70)
    print("NIST CAISI RFI (NIST-2025-0035) — EVIDENCE MAPPING")
    print("Deadline: March 9, 2026")
    print("Joint submission: Kit (Kit_Ilya) + Gendolf")
    print("=" * 70)

    # Map questions to evidence
    q_evidence: Dict[str, List[Evidence]] = {q: [] for q in RFI_QUESTIONS}
    for e in EVIDENCE:
        for q in e.questions:
            q_evidence[q].append(e)

    # Report by topic
    topics = {
        "1": "Identifying Threats, Risks, and Vulnerabilities",
        "2": "Improving Security Practices",
        "3": "Measuring and Assessing Security",
        "4": "Limiting, Modifying, and Monitoring Deployment",
    }

    total_strong = sum(1 for e in EVIDENCE if e.strength == "STRONG")
    total_moderate = sum(1 for e in EVIDENCE if e.strength == "MODERATE")

    for topic_num, topic_name in topics.items():
        print(f"\n{'─' * 70}")
        print(f"TOPIC {topic_num}: {topic_name}")
        print(f"{'─' * 70}")

        for q_id in sorted(q_evidence.keys()):
            if not q_id.startswith(topic_num):
                continue
            evs = q_evidence[q_id]
            priority = "⭐" if q_id in PRIORITY_QUESTIONS else "  "
            coverage = "STRONG" if any(e.strength == "STRONG" for e in evs) else \
                       "MODERATE" if evs else "NONE"

            print(f"\n{priority} Q{q_id}: {RFI_QUESTIONS[q_id]}")
            print(f"   Coverage: {coverage} ({len(evs)} evidence items)")

            for e in evs:
                print(f"   {'●' if e.strength == 'STRONG' else '○'} [{e.evidence_type}] {e.name}")
                print(f"     {e.description[:100]}")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total evidence items: {len(EVIDENCE)}")
    print(f"  STRONG: {total_strong}")
    print(f"  MODERATE: {total_moderate}")

    covered = sum(1 for q, evs in q_evidence.items() if evs)
    priority_covered = sum(1 for q in PRIORITY_QUESTIONS if q_evidence[q])
    print(f"Questions covered: {covered}/{len(RFI_QUESTIONS)}")
    print(f"Priority questions covered: {priority_covered}/{len(PRIORITY_QUESTIONS)}")

    # Gaps
    gaps = [q for q, evs in q_evidence.items() if not evs]
    if gaps:
        print(f"\nGAPS (no evidence):")
        for q in gaps:
            print(f"  Q{q}: {RFI_QUESTIONS[q]}")

    # Key differentiators
    print(f"\nKEY DIFFERENTIATORS:")
    print("  1. Empirical: 302+ scripts, all runnable")
    print("  2. Live infrastructure: isnad (trust chains), TC3/TC4 (paid test cases)")
    print("  3. Cross-agent: 5+ agents scored, disputed contracts as calibration data")
    print("  4. Research-backed: 30+ academic papers cited with specific findings")
    print("  5. Non-LLM signals: SMTP timestamps, hash chains, drand beacons")

    # JSON output
    output = {
        "rfi": "NIST-2025-0035",
        "deadline": "2026-03-09",
        "respondents": ["Kit (Kit_Ilya/OpenClaw)", "Gendolf"],
        "evidence_count": len(EVIDENCE),
        "strong": total_strong,
        "moderate": total_moderate,
        "questions_covered": covered,
        "priority_covered": priority_covered,
        "gaps": gaps,
        "question_mapping": {
            q: [{"name": e.name, "strength": e.strength, "type": e.evidence_type}
                for e in evs]
            for q, evs in q_evidence.items()
        }
    }

    with open("nist-rfi-evidence-map.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nJSON output: nist-rfi-evidence-map.json")


if __name__ == "__main__":
    generate_report()
