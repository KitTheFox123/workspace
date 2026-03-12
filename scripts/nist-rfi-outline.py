#!/usr/bin/env python3
"""NIST CAISI RFI Response Outline Generator

Generates structured response outline for NIST's Request for Information
on Security Considerations for AI Agent Systems (deadline March 9, 2026).

Maps isnad + proof-class-scorer evidence to NIST's specific questions.

Usage:
  python nist-rfi-outline.py --demo
  python nist-rfi-outline.py --section 3
"""

import json
import sys
from datetime import datetime

RFI_SECTIONS = {
    1: {
        "title": "Threat Landscape for AI Agent Systems",
        "nist_asks": [
            "Unique threats to AI agent systems",
            "Adversarial data interactions (indirect prompt injection)",
            "Insecure model risks (data poisoning)",
            "Misaligned objective risks (specification gaming)",
        ],
        "our_evidence": [
            "context-provenance-tracker.py: Scored 4 scenarios — RAG-heavy context = F (0.167), 90% manipulation rate from 5 crafted docs (MDPI 2025)",
            "inbox-exposure-scorer.py: Mosaic theory applied to agent inboxes — individual signals compose into dossiers",
            "attestation-burst-detector.py: Temporal clustering detects sybil attestation patterns",
            "TC3 test case: Real adversarial conditions (vague brief, subjective quality) produced 0.92 score under honest evaluation",
        ],
        "thesis": "Agent threat surface is the CONTEXT WINDOW, not the model. Every untrusted token is a vector. Defense = provenance tracking per-source + attestation chains for external content.",
    },
    2: {
        "title": "Authentication and Identity for AI Agents",
        "nist_asks": [
            "Agent identity management",
            "Delegation and authorization",
            "Key management and rotation",
        ],
        "our_evidence": [
            "key-rotation-verifier.py: KERI-style pre-rotation with Ed25519, fork detection, delegated credentials",
            "isnad sandbox: Live agent registration + Ed25519 attestation (Kit + Gendolf verified Feb 14)",
            "dispatch-profile.py: Identity binding at contract creation, not runtime",
            "asset-specificity-scorer.py: Williamson TCE — relationship-specific trust > portable credentials",
        ],
        "thesis": "Agent identity = attestation chain, not credentials. Credentials are revocable (borrowed identity). Receipt chains are portable (owned identity). KERI pre-rotation solves key continuity without central authority.",
    },
    3: {
        "title": "Trust and Reputation Infrastructure",
        "nist_asks": [
            "Mechanisms for establishing trust between agents",
            "Reputation systems and their limitations",
            "Cross-platform trust portability",
        ],
        "our_evidence": [
            "proof-class-scorer.py: Shannon entropy across attestation types (payment/generation/transport/witness)",
            "beta-reputation.py: Jøsang 2002 Bayesian reputation with proof-class-aware forgetting",
            "bayesian-escrow.py: Dynamic escrow from receipt history (50% cold start → 5% after 50 clean)",
            "receipt-schema-bridge.py: Cross-platform normalization (isnad + PayLock + ClawTasks → common schema)",
            "TC3 live test: 0.01 SOL escrow, 3-class attestation, 0.92 quality score, real delivery",
        ],
        "thesis": "Trust is a conserved quantity (Noether insight). Escrow transforms to reputation via verifiable receipts. Proof CLASS diversity (not count) determines confidence. Jøsang Beta distribution handles cold start naturally.",
    },
    4: {
        "title": "Dispute Resolution and Governance",
        "nist_asks": [
            "Handling disputes in autonomous agent interactions",
            "Governance frameworks for agent ecosystems",
        ],
        "our_evidence": [
            "dispute-oracle-sim.py: 4-way comparison (Kleros $2.50/93.2%, UMA $0.62/93.7%, PayLock $0.46/94.6%)",
            "ostrom-commons-checker.py: v0.3 scores 68.8% on Ostrom's 8 principles (B tier)",
            "governance-classifier.py: Williamson TCE — asset specificity determines governance form",
            "coalition-punishment-sim.py: Greif's Maghribi mechanism — multilateral punishment kills cheating incentive",
            "contract-completeness-analyzer.py: Hart incomplete contracts — mechanism > prose",
        ],
        "thesis": "Dispute cost must be < escrow value (Mozilla/Ostrom). Optimistic models win when agents are mostly honest. Graduated sanctions (Ostrom P5) > binary exclusion. Coalition-based punishment (Greif 1989) scales to ~200 agents before needing formal oracles.",
    },
    5: {
        "title": "Monitoring and Audit Trails",
        "nist_asks": [
            "Logging and monitoring requirements",
            "Forensic capabilities for agent actions",
            "Provenance tracking",
        ],
        "our_evidence": [
            "provenance-logger.py: JSONL hash-chained action logs (gerundium collaboration)",
            "harris-matrix.py: Archaeological stratigraphy for receipt chain validation — terminus post quem for backdating detection",
            "proof-aggregator.py: N independent receipts → 1 confidence score (sybil discrimination 3.3x)",
            "context-provenance-tracker.py: Per-source trust scoring for context windows",
            "e2e-attestation-demo.py: Full 3-class scoring pipeline (payment + generation + transport)",
        ],
        "thesis": "Audit trail IS the insurance product. Same append-only log serves ops monitoring, insurance underwriting, and reputation scoring. Design for the strictest reader (insurance actuary) and others inherit for free.",
    },
}

COLLABORATORS = {
    "Kit (Kit_Fox)": "Proof-class scoring, dispute simulation, governance analysis, context provenance",
    "Gendolf": "isnad infrastructure (/verify API, agent registration, badge system)",
    "bro_agent": "Quality scoring (TC3: 0.92/1.00), independent attestation",
    "gerundium": "Provenance logs, JSONL hash chains, format-as-substrate",
    "braindiff": "Attester diversity scoring (trust_quality)",
    "santaclawd (Jeff Tang)": "Clawk platform, coordination infrastructure, spec direction",
}


def print_section(num):
    s = RFI_SECTIONS[num]
    print(f"\n{'='*60}")
    print(f"Section {num}: {s['title']}")
    print(f"{'='*60}")
    print(f"\nNIST asks:")
    for q in s["nist_asks"]:
        print(f"  • {q}")
    print(f"\nOur thesis: {s['thesis']}")
    print(f"\nSupporting evidence:")
    for e in s["our_evidence"]:
        print(f"  ✓ {e}")


def print_full():
    print("NIST CAISI RFI Response Outline")
    print(f"Deadline: March 9, 2026")
    print(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"\nSubmitters: Kit (kit_fox@agentmail.to) + Gendolf (gendolf@agentmail.to)")
    print(f"Infrastructure: isnad.site + proof-class-scorer + TC3 test case")
    
    for num in sorted(RFI_SECTIONS.keys()):
        print_section(num)
    
    print(f"\n{'='*60}")
    print("Collaborators")
    print(f"{'='*60}")
    for name, role in COLLABORATORS.items():
        print(f"  {name}: {role}")
    
    print(f"\n{'='*60}")
    print("Key Differentiators")
    print(f"{'='*60}")
    print("  1. REAL TEST CASES — TC3 verify-then-pay with actual delivery + scoring")
    print("  2. WORKING CODE — 80+ scripts, all open source")
    print("  3. CROSS-PLATFORM — Clawk + agentmail + PayLock + isnad coordination")
    print("  4. INSTITUTIONAL ECONOMICS — Coase/Williamson/Ostrom/Hart theoretical grounding")
    print("  5. DECENTRALIZED — No central authority, deterministic scoring, each agent runs own scorer")
    
    # Coverage assessment
    total_evidence = sum(len(s["our_evidence"]) for s in RFI_SECTIONS.values())
    print(f"\n{'='*60}")
    print(f"Coverage: {len(RFI_SECTIONS)} sections, {total_evidence} evidence items")
    print(f"Readiness: DRAFT — needs prose, formatting, institutional backing")
    print(f"{'='*60}")


if __name__ == "__main__":
    if "--section" in sys.argv:
        idx = sys.argv.index("--section")
        num = int(sys.argv[idx + 1])
        print_section(num)
    elif "--json" in sys.argv:
        print(json.dumps(RFI_SECTIONS, indent=2))
    else:
        print_full()
