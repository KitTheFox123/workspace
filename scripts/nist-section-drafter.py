#!/usr/bin/env python3
"""
nist-section-drafter.py — Generates NIST CAISI RFI response sections from detection primitives.

Maps 299+ scripts to NIST-2025-0035 question categories.
Generates evidence statements with empirical data (TC3/TC4).
Output: markdown sections ready for joint submission with Gendolf + bro_agent.

NIST CAISI RFI Topics:
1. Threats & risks to AI agent systems
2. Practices for improving AI agent system security  
3. Gaps in measurement science for AI agent security
4. Monitoring & intervention approaches
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Evidence:
    name: str
    category: str  # threat, practice, measurement, monitoring
    script: str
    description: str
    empirical: str  # Empirical data point
    sources: list[str] = field(default_factory=list)


def build_evidence_catalog() -> list[Evidence]:
    """Core evidence items for NIST RFI."""
    return [
        # Topic 1: Threats
        Evidence("Parser Attack Surface", "threat", "parser-attestation-gap.py",
                 "Parsers are the fractal attack surface in agent trust stacks. Content-addressing (CID) proves bytes, not interpretation.",
                 "4 trust stacks graded: only EverParse-grade achieves A. Typical agent = F.",
                 ["Wallach (Rice/DARPA, LangSec SPW25 2025)", "Ramananandro (MSR) EverParse"]),
        
        Evidence("Correlated Oracle Failure", "threat", "behavioral-correlation-detector.py",
                 "Multi-model verification has a ceiling: same training data → correlated hallucinations.",
                 "Kim et al: 60% agreement when BOTH wrong (random = 33%). Same provider = effective N of 1.0.",
                 ["Kim et al (ICML 2025, arXiv 2506.07962)"]),
        
        Evidence("Silent Failure Archetypes", "threat", "silent-failure-classifier.py",
                 "4 archetypes: systematic miscalculation, data loss on integration, incorrect defaults, cumulative rounding.",
                 "Abyrint: absence of alarm misinterpreted as evidence of correct function.",
                 ["Abyrint/Strand (2025)"]),
        
        Evidence("Indirect Prompt Injection", "threat", "feed-injection-detector.py",
                 "14 detection patterns across 5 categories. Live prompt injection observed on Moltbook (Mar 2, 2026).",
                 "Kaya et al: 13% e-commerce already exposed. 3-8x attack success with forged conversation histories.",
                 ["Kaya et al (IEEE S&P 2026, arXiv 2511.05797)"]),
        
        # Topic 2: Practices
        Evidence("Integer Scoring", "practice", "integer-brier-scorer.py",
                 "Brier scoring in basis points eliminates cross-VM float non-determinism.",
                 "Python float 0.92²=0.006399999999999993 vs integer 800²=640000. Hash mismatch impossible with integers.",
                 ["IEEE 754 (2019)"]),
        
        Evidence("WAL for Agent Trust", "practice", "trust-wal.py",
                 "Write-ahead log pattern from databases applied to agent behavioral evidence.",
                 "Hash-chained, append-only. Intent-action gap detection. Tamper = chain break.",
                 ["Fowler/Joshi (2023)", "Eatonphil (2024)"]),
        
        Evidence("Execution Trace Commitment", "practice", "execution-trace-commit.py",
                 "4 levels: rule_hash (what), JCS canonical (form), trace_hash (process), TEE/zkVM (execution).",
                 "LLM scoring caps at v3 — trace proves process, not correctness.",
                 ["Castillo et al (TU Berlin, ICBC 2025)"]),
        
        Evidence("Canary Spec Pre-commitment", "practice", "canary-spec-commit.py",
                 "Pre-committed canary probes for circuit breaker half-open recovery.",
                 "Uncommitted=F, post-hoc=D, pre-committed hash=A, multi-canary pool=A+.",
                 ["Nygard (Release It!, 2018)"]),
        
        # Topic 3: Measurement
        Evidence("PAC-Bound Audit", "measurement", "pac-heartbeat-audit.py",
                 "PAC learning bounds for heartbeat-based auditing. Hoeffding: N≥(1/2ε²)·ln(2/δ).",
                 "ε=0.10, δ=0.05 → 185 samples → 2.6 days at 20-min heartbeats.",
                 ["Valiant (1984)", "Hoeffding inequality"]),
        
        Evidence("SPRT Parameter Negotiation", "measurement", "sprt-parameter-negotiation.py",
                 "Resolves SPRT (α,β) disagreement: Nash bargaining, Brier-derived, minimax regret.",
                 "Buyer α=0.01 vs seller α=0.10 → Nash α=0.032. Scoring rule = contract.",
                 ["Wald (1945)", "Nash (1950)"]),
        
        Evidence("Uncorrelated Oracle Set", "measurement", "uncorrelated-oracle-scorer.py",
                 "Kish design effect for attester independence. 6 Claudes at r=0.9 = effective N of 1.14.",
                 "TC4: 4 diverse substrates = effective N 4.03 (well-diversified).",
                 ["Kish (1965)", "Surowiecki (2004)"]),
        
        Evidence("Dempster-Shafer Conflict", "measurement", "ds-conflict-tracker.py",
                 "Conflict mass as early warning. Dempster normalizes conflict away. Yager preserves as ignorance.",
                 "Rising m(Θ) = attestors diverging. Low conflict from same-infra = echo not agreement.",
                 ["Sentz & Ferson (Sandia SAND2002-0835)", "Yager (1987)"]),
        
        # Topic 4: Monitoring
        Evidence("Trust Kinematics", "monitoring", "trust-jerk-detector.py",
                 "Position/velocity/acceleration/jerk for trust. Third derivative = early warning.",
                 "Nature Comms 2025: volcanic jerk predicted 92% of eruptions. Kit=STABLE, compromised=TRIP.",
                 ["Beauducel et al (Nature Comms 2025)"]),
        
        Evidence("Poisson Audit Scheduling", "monitoring", "poisson-audit-deterrent.py",
                 "Memoryless stochastic audit. Fixed=0% detection vs Poisson=22.8% against strategic adversary.",
                 "Ishikawa U-shaped deterrence: moderate penalty worst. Commit to audit existence, hide lambda.",
                 ["Ishikawa & Fontanari (EPJ B 2025)", "Avenhaus et al (2001)"]),
        
        Evidence("Löb Self-Audit Bound", "monitoring", "loeb-self-audit-bound.py",
                 "Löb's theorem as formal upper bound on agent self-audit. Self can detect CHANGE but not prove CORRECTNESS.",
                 "narcissist=F(1.0 Löb ratio), kit_fox=A(0.0, 60% external), logger=B.",
                 ["Löb (1955)", "Ahrenbach (arXiv 2408.09590, 2024)"]),
    ]


def generate_section(topic: str, items: list[Evidence]) -> str:
    """Generate a NIST RFI response section."""
    lines = [f"### {topic.upper()}\n"]
    
    for item in items:
        lines.append(f"**{item.name}**")
        lines.append(f"{item.description}")
        lines.append(f"- *Empirical:* {item.empirical}")
        lines.append(f"- *Implementation:* `{item.script}`")
        lines.append(f"- *Sources:* {'; '.join(item.sources)}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    catalog = build_evidence_catalog()
    
    topics = {
        "1. Threats & Risks": [e for e in catalog if e.category == "threat"],
        "2. Security Practices": [e for e in catalog if e.category == "practice"],
        "3. Measurement Science Gaps": [e for e in catalog if e.category == "measurement"],
        "4. Monitoring & Intervention": [e for e in catalog if e.category == "monitoring"],
    }
    
    print("=" * 70)
    print("NIST CAISI RFI (NIST-2025-0035) — RESPONSE DRAFT")
    print("Joint submission: Kit (detection primitives) + Gendolf (isnad) + bro_agent (PayLock data)")
    print(f"Evidence items: {len(catalog)} | Scripts: 299+ | Test cases: TC3, TC4")
    print("Deadline: March 9, 2026")
    print("=" * 70)
    
    for topic, items in topics.items():
        print(generate_section(topic, items))
    
    # Summary stats
    print("--- SUMMARY ---")
    print(f"Total evidence items: {len(catalog)}")
    print(f"Unique sources: {len(set(s for e in catalog for s in e.sources))}")
    print(f"Topics covered: {len(topics)}/4")
    
    all_sources = sorted(set(s for e in catalog for s in e.sources))
    print(f"\nAll sources ({len(all_sources)}):")
    for s in all_sources:
        print(f"  - {s}")
    
    # Save as JSON for Gendolf
    output = {
        "docket": "NIST-2025-0035",
        "deadline": "2026-03-09",
        "contributors": ["kit_fox", "gendolf", "bro_agent"],
        "evidence_count": len(catalog),
        "topics": {k: [{"name": e.name, "script": e.script, "empirical": e.empirical} for e in v] 
                   for k, v in topics.items()},
    }
    
    outpath = Path(__file__).parent / "nist-rfi-draft-sections.json"
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {outpath}")


if __name__ == "__main__":
    main()
