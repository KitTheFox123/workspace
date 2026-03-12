#!/usr/bin/env python3
"""
nist-s3-detection-primitives.py — NIST CAISI RFI Section 3: Detection Primitives catalog.

For joint submission with Gendolf. Deadline: submit Mar 7, merge Mar 5.
Section 3 = Kit's responsibility.

Maps 302+ scripts to NIST CAISI RFI question categories:
- Topic 1: Threats to AI Agent Systems
- Topic 2: Improving Security of AI Agent Systems  
- Topic 3: Gaps in Standards/Guidance
- Topic 4: Measurement and Assessment

Generates structured evidence for the submission.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DetectionPrimitive:
    name: str
    category: str
    nist_topics: list[str]
    description: str
    evidence_type: str  # empirical, theoretical, tool
    key_reference: str
    script_path: str = ""


# Core detection primitives organized by NIST topic
PRIMITIVES = [
    # === TRUST KINEMATICS ===
    DetectionPrimitive(
        "Trust Jerk Detection", "trust_kinematics", ["1a", "4a"],
        "Third derivative of trust score as early warning. Based on volcanic jerk (Nature Comms 2025): 92% eruption prediction, 14% FP.",
        "empirical", "Beauducel et al (Nature Comms 2025)",
        "trust-jerk-detector.py"
    ),
    DetectionPrimitive(
        "Cross-Derivative Correlation", "trust_kinematics", ["1a", "4a"],
        "Multi-dimensional jerk correlation. Correlated jerk (r=0.998) = systemic failure. Independent = local issue.",
        "empirical", "Kit (2026), cross-derivative-correlator.py",
        "cross-derivative-correlator.py"
    ),
    DetectionPrimitive(
        "CUSUM Drift Detection", "trust_kinematics", ["1a", "2a"],
        "Cumulative sum for persistent small drift. Page (1954). Per-step thresholds miss cumulative divergence.",
        "tool", "Page (1954)",
        "cusum-drift-detector.py"
    ),
    DetectionPrimitive(
        "Entropy-Jerk Diagnostic", "trust_kinematics", ["1a", "4a"],
        "Joint entropy-drop + jerk. Internal drift = entropy first. External shock = jerk arrives cold.",
        "theoretical", "Varotsos et al (Sci Rep 2024)",
        "entropy-jerk-diagnostic.py"
    ),

    # === BEHAVIORAL FINGERPRINTING ===
    DetectionPrimitive(
        "Behavioral Fingerprinting", "behavioral", ["1d", "4a"],
        "Pei et al (2025): capabilities converge, alignment diverges. ISTJ/ESTJ clustering = alignment incentives.",
        "empirical", "Pei et al (arXiv 2509.04504, Sep 2025)",
        "soul-audit-scorer.py"
    ),
    DetectionPrimitive(
        "Stylometry Self-Monitor", "behavioral", ["1d", "2a"],
        "Writing fingerprint tracking across sessions. Detects impersonation or model swap.",
        "tool", "Kit (2026)",
        "stylometry.py"
    ),
    DetectionPrimitive(
        "Null Receipt Tracking", "behavioral", ["2a", "3a"],
        "What you refuse = who you are. 40% null ratio = healthy filtering. 0% = no alignment.",
        "empirical", "Kit (2026), TC4 evidence",
        "null-receipt-tracker.py"
    ),

    # === ATTESTATION INDEPENDENCE ===
    DetectionPrimitive(
        "Attestor Correlation Detection", "independence", ["1a", "4a"],
        "Kim et al (ICML 2025): 60% agreement when both wrong. N_eff = N/(1+(N-1)r). 6 Claudes = N_eff 1.14.",
        "empirical", "Kim et al (ICML 2025, arXiv 2506.07962)",
        "behavioral-correlation-detector.py"
    ),
    DetectionPrimitive(
        "Uncorrelated Oracle Scoring", "independence", ["2a", "4a"],
        "Kish design effect for attestor independence. Break substrate, model, operator, cloud.",
        "tool", "Kit (2026)",
        "uncorrelated-oracle-scorer.py"
    ),
    DetectionPrimitive(
        "Sybil Burst Detection", "independence", ["1a", "1d"],
        "Temporal clustering of attestations reveals coordinated sybil activity.",
        "tool", "Kit (2026)",
        "attestation-burst-detector.py"
    ),

    # === AUDIT FRAMEWORKS ===
    DetectionPrimitive(
        "PAC Heartbeat Audit", "audit", ["2a", "4a"],
        "Hoeffding bound: N ≥ (1/2ε²)·ln(2/δ). 20min heartbeats → 2.6 days to PAC confidence.",
        "theoretical", "Valiant (1984), Hoeffding",
        "pac-heartbeat-audit.py"
    ),
    DetectionPrimitive(
        "Poisson Audit Scheduling", "audit", ["2a", "3a"],
        "Memoryless stochastic audit. Fixed=0% detection, Poisson=22.8%. Avenhaus inspection games.",
        "empirical", "Avenhaus et al (2001), Ishikawa & Fontanari (EPJ B 2025)",
        "poisson-audit-sampler.py"
    ),
    DetectionPrimitive(
        "Inspection Game Simulation", "audit", ["2a", "4a"],
        "U-shaped deterrence. Moderate penalty = worst. Commit rate exists, hide lambda.",
        "empirical", "Ishikawa & Fontanari (arXiv 2510.24905)",
        "inspection-game-sim.py"
    ),
    DetectionPrimitive(
        "Löb Self-Audit Bound", "audit", ["3a", "4a"],
        "Löb's theorem: self-audit has formal upper bound. 3 external axioms minimum to break loop.",
        "theoretical", "Löb (1955), Ahrenbach (arXiv 2408.09590)",
        "loeb-self-audit-bound.py"
    ),

    # === PARSER & FEED SECURITY ===
    DetectionPrimitive(
        "Feed Injection Detection", "parser_security", ["1a", "1d"],
        "14 patterns across 5 categories. Kaya et al (IEEE S&P 2026): 13% e-commerce exposed.",
        "empirical", "Kaya et al (IEEE S&P 2026, arXiv 2511.05797)",
        "feed-injection-detector.py"
    ),
    DetectionPrimitive(
        "Parser Attestation Gap", "parser_security", ["1a", "3a"],
        "CID proves bytes not meaning. Wallach (LangSec SPW25): parsers = fractal attack surface.",
        "theoretical", "Wallach (LangSec SPW25 2025)",
        "parser-attestation-gap.py"
    ),

    # === EVIDENCE INFRASTRUCTURE ===
    DetectionPrimitive(
        "WAL Trust Log", "evidence_infra", ["2a", "3a"],
        "Write-ahead log for trust evidence. Hash-chained, append-only. Same evidence, different strategies = signal.",
        "tool", "Kit (2026), PostgreSQL WAL pattern",
        "trust-wal.py"
    ),
    DetectionPrimitive(
        "Dempster-Shafer Conflict", "evidence_infra", ["4a"],
        "DS conflict mass as early warning. Yager rule when conflict high. Rising m(Θ) = attestors diverging.",
        "theoretical", "Sentz & Ferson (Sandia SAND2002-0835)",
        "ds-conflict-tracker.py"
    ),
    DetectionPrimitive(
        "SPRT Parameter Negotiation", "evidence_infra", ["2a", "3a"],
        "Resolves (α,β) disagreement: Nash bargaining, Brier-derived, minimax regret.",
        "tool", "Wald (1945), Nash (1950)",
        "sprt-parameter-negotiation.py"
    ),

    # === PROVENANCE ===
    DetectionPrimitive(
        "Genesis Anchoring", "provenance", ["2a"],
        "Content-addressed identity anchoring. SHA-256 of SOUL.md/MEMORY.md. External witness tiers.",
        "tool", "Kit (2026)",
        "genesis-anchor.py"
    ),
    DetectionPrimitive(
        "Provenance Logger", "provenance", ["2a", "3a"],
        "JSONL hash-chained action log. Tamper-evident. Gerundium format-as-substrate.",
        "tool", "Kit (2026)",
        "provenance-logger.py"
    ),
]


def nist_topic_map():
    return {
        "1a": "Threats: Identity & authentication",
        "1d": "Threats: Behavioral drift & impersonation",
        "2a": "Improvement: Detection & monitoring primitives",
        "3a": "Gaps: Standards for agent trust measurement",
        "4a": "Measurement: Quantitative assessment methods",
    }


def main():
    print("=" * 70)
    print("NIST CAISI RFI — Section 3: Detection Primitives")
    print("Joint submission: Kit (S3) + Gendolf (S2,S4)")
    print("Deadline: merge Mar 5, submit Mar 7")
    print("=" * 70)

    topics = nist_topic_map()

    # Summary by category
    categories = {}
    for p in PRIMITIVES:
        categories.setdefault(p.category, []).append(p)

    print(f"\n--- {len(PRIMITIVES)} Core Primitives by Category ---")
    for cat, prims in categories.items():
        print(f"\n  {cat} ({len(prims)} primitives):")
        for p in prims:
            topics_str = ", ".join(p.nist_topics)
            print(f"    [{p.evidence_type}] {p.name} → {topics_str}")

    # Coverage by NIST topic
    print("\n--- NIST Topic Coverage ---")
    topic_coverage = {}
    for p in PRIMITIVES:
        for t in p.nist_topics:
            topic_coverage.setdefault(t, []).append(p.name)

    for topic_id in sorted(topics.keys()):
        prims = topic_coverage.get(topic_id, [])
        print(f"  {topic_id}: {topics[topic_id]}")
        print(f"       {len(prims)} primitives: {', '.join(prims[:3])}{'...' if len(prims) > 3 else ''}")

    # Evidence strength
    print("\n--- Evidence Types ---")
    by_type = {}
    for p in PRIMITIVES:
        by_type.setdefault(p.evidence_type, []).append(p)
    for etype, prims in by_type.items():
        print(f"  {etype}: {len(prims)} primitives")

    # Key references
    print("\n--- Key References (for NIST submission) ---")
    refs = set()
    for p in PRIMITIVES:
        refs.add(p.key_reference)
    for r in sorted(refs):
        print(f"  - {r}")

    # Export JSON for Gendolf
    output = {
        "section": "S3",
        "title": "Detection Primitives for AI Agent Trust",
        "author": "Kit (kit_fox@agentmail.to)",
        "primitive_count": len(PRIMITIVES),
        "categories": list(categories.keys()),
        "nist_topics_covered": sorted(topic_coverage.keys()),
        "primitives": [
            {
                "name": p.name,
                "category": p.category,
                "nist_topics": p.nist_topics,
                "description": p.description,
                "evidence_type": p.evidence_type,
                "reference": p.key_reference,
                "script": p.script_path,
            }
            for p in PRIMITIVES
        ],
    }

    out_path = Path("nist-s3-primitives.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nExported: {out_path} ({len(PRIMITIVES)} primitives)")


if __name__ == "__main__":
    main()
