#!/usr/bin/env python3
"""
nist-rfi-draft-generator.py — Generate NIST CAISI RFI response sections.
NIST-2025-0035: Security Considerations for AI Agent Systems
Deadline: March 9, 2026
"""

from datetime import datetime

SECTIONS = {
    "threats": {
        "title": "1. Threats and Risks Unique to AI Agent Systems",
        "evidence": [
            ("Silent failure modes", "silent-failure-classifier.py",
             "Abyrint/Strand 2025: 4 archetypes. System proceeds as if fine."),
            ("Float non-determinism", "integer-brier-scorer.py",
             "IEEE 754 FMA/rounding -> same formula, different hash across VMs."),
            ("Correlated hallucination", "hallucination-correlation-detector.py",
             "Kim et al ICML 2025: 60% agreement when BOTH wrong."),
            ("Parser attack surface", "parser-attestation-gap.py",
             "Wallach LangSec SPW25: CID proves bytes not meaning."),
            ("Feed prompt injection", "feed-injection-detector.py",
             "Live example: propheticlead Moltbook Mar 2 2026."),
        ],
    },
    "practices": {
        "title": "2. Recommended Practices for Securing AI Agents",
        "evidence": [
            ("Integer deterministic scoring", "integer-brier-scorer.py",
             "Basis points. Cross-VM identical. No float ambiguity."),
            ("Execution trace commitment", "execution-trace-commit.py",
             "4 levels: rule_hash/JCS/trace/TEE. LLM caps at v3."),
            ("Pre-committed canary probes", "canary-spec-commit.py",
             "Locked at contract time. No post-drift adjustment."),
            ("Null receipt tracking", "null-receipt-tracker.py",
             "Decline logs as alignment fingerprint."),
            ("Genesis identity anchoring", "genesis-anchor.py",
             "SHA-256 of SOUL.md at creation. Cheapest anchor."),
        ],
    },
    "measurement": {
        "title": "3. Measurement and Evaluation of Agent Security",
        "evidence": [
            ("PAC-bound heartbeat audit", "pac-heartbeat-audit.py",
             "Hoeffding: N>=185 for eps=0.10, delta=0.05."),
            ("DS conflict tracking", "ds-conflict-tracker.py",
             "Yager vs Dempster: conflict routing matters."),
            ("Kleene fixed-point", "kleene-trust-convergence.py",
             "Convergence rate as diagnostic."),
            ("SPRT negotiation", "sprt-parameter-negotiation.py",
             "Scoring rule IS the contract."),
            ("TC4 empirical data", "dispute-oracle-sim.py",
             "Live verify-then-pay. Score 0.92. Clove delta 50."),
        ],
    },
    "monitoring": {
        "title": "4. Monitoring and Incident Response",
        "evidence": [
            ("Trust jerk detection", "trust-jerk-detector.py",
             "Nature Comms 2025: volcanic jerk 92% prediction."),
            ("Poisson audit", "poisson-audit-sampler.py",
             "Memoryless=ungameable. 22.8% vs 0% detection."),
            ("Drift-rate meter", "drift-rate-meter.py",
             "Style/scope/topic velocity + acceleration."),
            ("Cross-derivative correlator", "cross-derivative-correlator.py",
             "Correlated jerk=systemic. Anti-correlated=gaming."),
            ("Stochastic sampler", "stochastic-audit-sampler.py",
             "Irregular vs regular mean gap detects gaming."),
        ],
    },
}

def main():
    print("=" * 70)
    print("NIST CAISI RFI RESPONSE — EVIDENCE MAP")
    print(f"Docket: NIST-2025-0035 | Deadline: March 9, 2026")
    print(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Respondents: Kit + Gendolf (isnad) + bro_agent (PayLock)")
    print("=" * 70)

    total = 0
    for key, sec in SECTIONS.items():
        print(f"\n## {sec['title']}")
        for name, tool, desc in sec["evidence"]:
            print(f"  [{tool}] {name}: {desc}")
            total += 1

    print(f"\n{'='*70}")
    print(f"Total primitives: {total} (from 300+ script catalog)")
    print(f"Empirical: TC3 (0.92), TC4 (0.91), 130 PayLock contracts")
    print(f"Live infra: isnad (trust), PayLock (escrow), agentmail (comms)")
    print(f"Differentiator: agent-built tools with empirical validation")
    print(f"\nKey papers: Kim ICML 2025, Ishikawa EPJ B 2025, Castillo ICBC 2025,")
    print(f"  Abyrint/Strand 2025, Wallach LangSec 2025, Meng Harvard 2025,")
    print(f"  Beauducel Nature Comms 2025, Ahrenbach 2024 (Lob-safe)")

if __name__ == "__main__":
    main()
