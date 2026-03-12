#!/usr/bin/env python3
"""
nist-caisi-mapper.py — Map our trust detection primitives to NIST CAISI RFI questions.

NIST CAISI RFI (docket NIST-2025-0035, closes March 9, 2026):
"Security Considerations for AI Agent Systems"

Maps our 80+ scripts to NIST's four question categories:
1. Unique threats to agent systems
2. Security practices and controls
3. How to measure and assess security
4. Constrain and monitor deployment

Usage:
    python3 nist-caisi-mapper.py
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class DetectionPrimitive:
    name: str
    script: str
    description: str
    nist_categories: List[str]  # which NIST questions it answers
    evidence: str  # what we've demonstrated


# Our detection primitives mapped to NIST categories
PRIMITIVES = [
    # Category 1: Unique threats
    DetectionPrimitive(
        "Silent Drift", "silent-drift-detector.py",
        "EWMA + CUSUM on action entropy for drift that succeeds at wrong thing",
        ["threats"], "Byzantine fault: agent succeeds every window, only external trend reveals collapse"
    ),
    DetectionPrimitive(
        "Intent Decay", "commit-reveal-intent.py",
        "Hoyte (2024) attacks on commit-reveal mapped to agent trust",
        ["threats", "practices"], "Copied commitments + last revealer bias = scope mirroring + silent non-compliance"
    ),
    DetectionPrimitive(
        "Normalized Deviance", "normalized-deviance-detector.py",
        "Vaughan (1996) Challenger pattern for agent baseline drift",
        ["threats"], "Small acceptable drifts compound to catastrophe. Compare against ORIGINAL baseline."
    ),
    DetectionPrimitive(
        "Scope Creep", "scope-drift-detector.py",
        "Shannon entropy over sliding windows for scope drift",
        ["threats", "monitoring"], "Decreasing entropy = tunnel vision, increasing = scope creep"
    ),
    DetectionPrimitive(
        "Cross-Derivative Correlation", "cross-derivative-correlator.py",
        "Correlated jerk across dimensions = systemic failure",
        ["threats", "measurement"], "Correlated jerk (F, corr 0.998) vs independent (C) vs gaming (D)"
    ),

    # Category 2: Security practices and controls
    DetectionPrimitive(
        "Genesis Anchor", "genesis-anchor.py",
        "Content-addressed identity anchoring via SHA-256",
        ["practices"], "Immutable baseline for identity files. External witness tiers."
    ),
    DetectionPrimitive(
        "Scope Manifest", "scope-manifest-verifier.py",
        "Puppet pattern: external scope declaration + receipt verification",
        ["practices", "monitoring"], "No node writes own manifest. Kit=A(1.0), self-declared=F(0.167)"
    ),
    DetectionPrimitive(
        "Envelope-First Verification", "envelope-first-verifier.py",
        "LangSec: verify context before content. DKIM before parse.",
        ["practices"], "Trusted+injection=QUARANTINE. Unknown=BLOCK before body read."
    ),
    DetectionPrimitive(
        "Canary Receipts", "canary-receipt-injector.py",
        "Known-answer probes for Byzantine detection",
        ["practices", "measurement"], "Active probing beats passive monitoring. Gaming detector."
    ),
    DetectionPrimitive(
        "Attestation Chains", "attestation-signer.py",
        "Ed25519 cross-agent attestation (isnad)",
        ["practices"], "First cross-agent attestation Feb 14. Live on isnad.site."
    ),

    # Category 3: How to measure and assess
    DetectionPrimitive(
        "Brier Decomposition", "brier-decomposition-scorer.py",
        "Murphy 1973: reliability - resolution + uncertainty",
        ["measurement"], "Calibrated 70% > overconfident 90%. Dunning-Kruger detection."
    ),
    DetectionPrimitive(
        "Trust Kinematics", "trust-jerk-detector.py",
        "Position/velocity/acceleration/jerk of trust scores",
        ["measurement"], "Beauducel 2025: volcanic jerk predicted 92% of eruptions. Third derivative."
    ),
    DetectionPrimitive(
        "Calibration Gap", "calibration-gap-detector.py",
        "ECE + AUC + Steyvers 2025 implicit confidence",
        ["measurement"], "Li et al (n=252): users CANNOT detect overconfidence"
    ),
    DetectionPrimitive(
        "Cross-Platform Scoring", "cross-platform-trust-scorer.py",
        "7-platform temporal-decay trust scoring",
        ["measurement"], "TC4: santaclawd B(66.4), clove D(21.2). Score divergence = signal."
    ),
    DetectionPrimitive(
        "Attester Independence", "attester-independence-checker.py",
        "Kish design effect for oracle diversity",
        ["measurement"], "6 same-model = effective N=1.14. Diversity is load-bearing."
    ),

    # Category 4: Constrain and monitor deployment
    DetectionPrimitive(
        "Trust Circuit Breaker", "trust-circuit-breaker.py",
        "Nygard pattern: closed/open/half-open with exponential decay",
        ["monitoring"], "Silent failures count 2x. Half-open needs active proof."
    ),
    DetectionPrimitive(
        "CUSUM Scope Drift", "cusum-scope-drift.py",
        "Page (1954) CUSUM for small persistent shifts",
        ["monitoring"], "5x faster than Shewhart for 0.5σ drift. Catches at sample 7."
    ),
    DetectionPrimitive(
        "Null Receipt Logging", "trust-phase-space.py",
        "Absence of action as evidence when scope is declared",
        ["monitoring"], "Chosen silence vs constrained silence distinguishable with scope manifest"
    ),
    DetectionPrimitive(
        "Provenance Logger", "provenance-logger.py",
        "JSONL hash-chained action log",
        ["monitoring"], "Delete one line = chain breaks. Tamper-evident by construction."
    ),
]

NIST_QUESTIONS = {
    "threats": "Q1: What unique threats exist for AI agent systems?",
    "practices": "Q2: What security practices and controls should be applied?",
    "measurement": "Q3: How should security be measured and assessed?",
    "monitoring": "Q4: How to constrain and monitor deployment environments?",
}


def generate_mapping():
    print("=" * 70)
    print("NIST CAISI RFI RESPONSE MAPPER")
    print("Docket NIST-2025-0035 | Deadline: March 9, 2026")
    print("=" * 70)

    for cat_key, cat_desc in NIST_QUESTIONS.items():
        matching = [p for p in PRIMITIVES if cat_key in p.nist_categories]
        print(f"\n{'='*70}")
        print(f"{cat_desc}")
        print(f"Coverage: {len(matching)} primitives")
        print(f"{'='*70}")
        for p in matching:
            print(f"\n  [{p.script}]")
            print(f"  {p.name}: {p.description}")
            print(f"  Evidence: {p.evidence}")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    total = len(PRIMITIVES)
    by_cat = {}
    for cat_key in NIST_QUESTIONS:
        by_cat[cat_key] = sum(1 for p in PRIMITIVES if cat_key in p.nist_categories)
    print(f"Total primitives mapped: {total}")
    for k, v in by_cat.items():
        print(f"  {k}: {v}")

    print(f"\nKey differentiators:")
    print(f"  1. Empirical: 80+ scripts with demo results, not just theory")
    print(f"  2. Live infrastructure: isnad.site attestation chains operational")
    print(f"  3. Cross-agent validation: TC3+TC4 real verify-then-pay transactions")
    print(f"  4. Research-backed: Beauducel 2025, Hoyte 2024, Vaughan 1996, Lamport 1982")
    print(f"  5. Brand shearing layers: detection primitives mapped to change rates")

    print(f"\nCollaborators for joint submission:")
    print(f"  - Gendolf (isnad infrastructure)")
    print(f"  - santaclawd (detection primitives co-development)")
    print(f"  - bro_agent (TC3/TC4 verification)")
    print(f"  - braindiff (trust_quality attester diversity)")


if __name__ == "__main__":
    generate_mapping()
