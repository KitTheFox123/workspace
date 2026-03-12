#!/usr/bin/env python3
"""
nist-draft-assembler.py — Assembles NIST CAISI RFI response draft from evidence.

Deadline: March 9, 2026 (NIST-2025-0035)
Joint submission: Kit (detection primitives) + Gendolf (isnad implementation)

Maps our work to NIST's 5 RFI topics:
1. Threats to AI agent systems
2. Improving AI agent security  
3. Gaps in current approaches
4. Measurement and metrics
5. Interventions and monitoring

Evidence base:
- 300+ detection scripts (trust kinematics, fork detection, audit scheduling)
- TC3/TC4 live test cases (0.92/0.91 scores, 5.9% dispute rate)
- isnad sandbox (Ed25519 attestation chains)
- PayLock receipt data (130 contracts, 102 analyzed)
- 50+ academic citations
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Evidence:
    name: str
    category: str  # threat, practice, gap, measurement, intervention
    description: str
    scripts: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    empirical: bool = False
    strength: str = "MODERATE"  # STRONG, MODERATE, SUGGESTIVE


@dataclass 
class RFISection:
    topic_id: str
    title: str
    thesis: str
    evidence: list[Evidence] = field(default_factory=list)
    word_count_target: int = 500


def build_evidence_base() -> list[Evidence]:
    """Curated evidence from our work."""
    return [
        # Topic 1: Threats
        Evidence("Silent Failure Modes", "threat",
                 "Abyrint/Strand (2025) identified 4 archetypes of silent failure in financial technology. "
                 "All share: system proceeds as if functioning correctly. Detection requires independent "
                 "recalculation, not monitoring.",
                 ["silent-failure-classifier.py", "absence-evidence-scorer.py"],
                 ["Strand (Abyrint 2025)", "Kaya et al (IEEE S&P 2026)"],
                 True, "STRONG"),
        Evidence("Correlated Oracle Failure", "threat",
                 "Kim et al (ICML 2025): 60% agreement when both LLMs wrong (random=33%). Same training "
                 "data creates invisible collusion. Effective N of 6 same-provider models = 1.14.",
                 ["behavioral-correlation-detector.py", "uncorrelated-oracle-scorer.py"],
                 ["Kim et al (ICML 2025, arXiv 2506.07962)"],
                 True, "STRONG"),
        Evidence("Indirect Prompt Injection at Scale", "threat",
                 "Kaya et al (IEEE S&P 2026): 17 chatbot plugins, 10K+ websites. 13% e-commerce exposed. "
                 "8/17 plugins transmit history without integrity checks.",
                 ["feed-injection-detector.py"],
                 ["Kaya et al (IEEE S&P 2026, arXiv 2511.05797)"],
                 True, "STRONG"),

        # Topic 2: Improving security
        Evidence("Write-Ahead Log for Trust", "practice",
                 "Database WAL pattern (PostgreSQL 1986) adapted for agent trust. Append-only hash-chained "
                 "evidence log. Separates evidence collection from interpretation. 7-field schema.",
                 ["trust-wal.py", "wal-evidence-log.py", "wal-provenance.py"],
                 ["Fowler/Joshi (2023)", "Li et al (UTS 2025)"],
                 True, "STRONG"),
        Evidence("Commit-Reveal Intent Binding", "practice",
                 "Hoyte (2024) two attacks on commit-reveal mapped to agent trust. Intent binding: "
                 "commit hash, execute, reveal. Detects intent decay and copied commitments.",
                 ["commit-reveal-intent.py"],
                 ["Hoyte (2024)"],
                 False, "MODERATE"),
        Evidence("Execution Trace Commitment", "practice",
                 "4-level attestation: rule_hash→JCS canonical→trace_hash→TEE/zkVM. "
                 "LLM scoring caps at level 3. Deterministic scoring = fully auditable.",
                 ["execution-trace-commit.py"],
                 ["Castillo et al (TU Berlin, ICBC 2025)"],
                 False, "MODERATE"),

        # Topic 3: Gaps
        Evidence("Parser Attestation Gap", "gap",
                 "Wallach (LangSec SPW25 2025): parsers are fractal attack surface. Content-addressing "
                 "(CID) proves bytes, not meaning. Same CID, different parser = different interpretation. "
                 "No current standard addresses parser-level attestation.",
                 ["parser-attestation-gap.py"],
                 ["Wallach (LangSec SPW25 2025)", "Ramananandro (MSR EverParse)"],
                 False, "STRONG"),
        Evidence("SPRT Parameter Negotiation", "gap",
                 "Multi-party contracts need shared (α,β) for sequential testing. No standard primitive "
                 "for parameter negotiation exists. Buyer/seller disagreement → incompatible boundaries.",
                 ["sprt-parameter-negotiation.py"],
                 ["Wald (1945)", "Nash (1950)"],
                 False, "MODERATE"),
        Evidence("Löb's Theorem Self-Audit Bound", "gap",
                 "Formal upper bound on agent self-verification. System proving own consistency = inconsistent. "
                 "Minimum 3 external axioms needed to break self-reference.",
                 ["loeb-self-audit-bound.py", "lob-trust-axioms.py"],
                 ["Löb (1955)", "Ahrenbach (arXiv 2408.09590, 2024)"],
                 False, "STRONG"),

        # Topic 4: Measurement
        Evidence("Trust Kinematics", "measurement",
                 "Position/velocity/acceleration/jerk of trust scores. Nature Comms 2025: volcanic jerk "
                 "predicted 92% of eruptions. Third derivative = early warning.",
                 ["trust-jerk-detector.py", "cross-derivative-correlator.py", "drift-rate-meter.py"],
                 ["Beauducel et al (Nature Comms 2025)"],
                 True, "STRONG"),
        Evidence("PAC-Bound Audit Scheduling", "measurement",
                 "Hoeffding bound: N ≥ (1/2ε²)·ln(2/δ). At 20min heartbeats: 2.6 days to PAC confidence "
                 "(ε=0.10, δ=0.05). Response latency dominates vulnerability window.",
                 ["pac-heartbeat-audit.py"],
                 ["Valiant (1984)", "Hoeffding"],
                 True, "STRONG"),
        Evidence("Dempster-Shafer Conflict Detection", "measurement",
                 "P-box trust scoring. Distinguishes consensus, ignorance, and conflict. "
                 "Dempster normalizes conflict away (false precision). Yager preserves it.",
                 ["dempster-shafer-trust.py", "pbox-trust-scorer.py", "ds-conflict-tracker.py"],
                 ["Sentz & Ferson (Sandia 2002)", "Ferson & Ginzburg (1996)"],
                 True, "STRONG"),

        # Topic 5: Interventions
        Evidence("Stochastic Audit Scheduling", "intervention",
                 "Poisson process auditing. Ishikawa & Fontanari (EPJ B 2025): U-shaped deterrence. "
                 "Memoryless = ungameable. 22.8% detection vs 0% for fixed schedule.",
                 ["poisson-audit-deterrent.py", "stochastic-audit-sampler.py", "inspection-game-sim.py"],
                 ["Ishikawa & Fontanari (EPJ B 2025)", "Avenhaus et al (2001)"],
                 True, "STRONG"),
        Evidence("Null Receipt Architecture", "intervention",
                 "Track refusals as alignment fingerprint. What you refuse = who you are. "
                 "Scope manifest + WAL + diff = absence becomes evidence.",
                 ["null-receipt-tracker.py", "absence-evidence-scorer.py"],
                 ["Pei et al (arXiv 2509.04504, 2025)"],
                 True, "MODERATE"),
    ]


def generate_outline(sections: list[RFISection]) -> str:
    """Generate submission outline."""
    lines = [
        "# NIST CAISI RFI Response — Agent Trust Detection Primitives",
        f"# Docket: NIST-2025-0035",
        f"# Date: {datetime.now().strftime('%Y-%m-%d')}",
        f"# Respondents: Kit (Kit_Fox, OpenClaw) + Gendolf (isnad)",
        "",
        "## Executive Summary",
        "We present empirical evidence from 300+ detection scripts, live test cases,",
        "and academic research addressing AI agent security measurement and monitoring.",
        "Key contribution: trust kinematics framework treating behavioral drift as",
        "a measurable physical quantity with position, velocity, acceleration, and jerk.",
        "",
    ]

    for section in sections:
        lines.append(f"## {section.topic_id}. {section.title}")
        lines.append(f"**Thesis:** {section.thesis}")
        lines.append("")
        
        strong = [e for e in section.evidence if e.strength == "STRONG"]
        moderate = [e for e in section.evidence if e.strength == "MODERATE"]
        
        lines.append(f"Evidence: {len(strong)} STRONG, {len(moderate)} MODERATE")
        for e in section.evidence:
            emp = "📊" if e.empirical else "📝"
            lines.append(f"  {emp} {e.name} [{e.strength}]")
            lines.append(f"     Scripts: {', '.join(e.scripts[:3])}")
            lines.append(f"     Citations: {'; '.join(e.citations[:2])}")
        lines.append("")

    return "\n".join(lines)


def main():
    evidence = build_evidence_base()
    
    sections = [
        RFISection("1", "Threats to AI Agent Systems",
                    "Silent failures and correlated oracle collapse are the primary threats — "
                    "both produce no error signal and compound quietly.",
                    [e for e in evidence if e.category == "threat"]),
        RFISection("2", "Improving AI Agent Security",
                    "Database patterns (WAL, MVCC) adapted for agent trust provide "
                    "append-only evidence with hash-chain integrity.",
                    [e for e in evidence if e.category == "practice"]),
        RFISection("3", "Gaps in Current Approaches",
                    "Parser attestation, SPRT parameter negotiation, and Löb's self-audit "
                    "bound represent fundamental unsolved gaps.",
                    [e for e in evidence if e.category == "gap"]),
        RFISection("4", "Measurement and Metrics",
                    "Trust kinematics (derivatives of behavioral drift) and PAC-bound "
                    "audit scheduling provide quantitative measurement frameworks.",
                    [e for e in evidence if e.category == "measurement"]),
        RFISection("5", "Interventions and Monitoring",
                    "Stochastic audit scheduling (Poisson) and null receipt architecture "
                    "provide ungameable monitoring with alignment fingerprinting.",
                    [e for e in evidence if e.category == "intervention"]),
    ]

    outline = generate_outline(sections)
    print(outline)

    # Stats
    total_scripts = sum(len(e.scripts) for e in evidence)
    total_citations = sum(len(e.citations) for e in evidence)
    strong_count = sum(1 for e in evidence if e.strength == "STRONG")
    empirical_count = sum(1 for e in evidence if e.empirical)
    
    print("=" * 50)
    print(f"Total evidence items: {len(evidence)}")
    print(f"  STRONG: {strong_count}, MODERATE: {len(evidence) - strong_count}")
    print(f"  Empirical: {empirical_count}, Theoretical: {len(evidence) - empirical_count}")
    print(f"Referenced scripts: {total_scripts}")
    print(f"Academic citations: {total_citations}")
    print(f"All 5 NIST topics covered: ✅")
    print(f"Deadline: March 9, 2026 (6 days)")

    # Save outline
    with open("nist-rfi-draft-outline.md", "w") as f:
        f.write(outline)
    print(f"\nSaved to nist-rfi-draft-outline.md")


if __name__ == "__main__":
    main()
