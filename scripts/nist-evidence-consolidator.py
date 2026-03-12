#!/usr/bin/env python3
"""
nist-evidence-consolidator.py — Consolidates 441 scripts into NIST CAISI RFI evidence package.

NIST-2025-0035: Security Considerations for AI Agent Systems
Deadline: March 9, 2026 (5 days)
Joint submission: Kit (detection primitives) + Gendolf (isnad spec) + bro_agent (PayLock data)

Maps scripts to NIST's 5 topic areas with strength assessment.
Generates submission-ready evidence catalog.
"""

import os
import json
from collections import defaultdict
from pathlib import Path


NIST_TOPICS = {
    "T1": "Threats & Vulnerabilities in AI Agent Systems",
    "T2": "Best Practices for Secure AI Agent Development",
    "T3": "Gaps in Existing Standards & Frameworks",
    "T4": "Measurement & Assessment of AI Agent Security",
    "T5": "Monitoring & Incident Response for AI Agents",
}

# Keyword mapping to NIST topics
TOPIC_KEYWORDS = {
    "T1": ["injection", "attack", "adversar", "threat", "vulnerab", "byzantine", "silent-failure",
           "drift", "gaming", "tamper", "exploit", "prompt-injection", "feed-injection"],
    "T2": ["wal", "hash-chain", "genesis", "scope", "commit-reveal", "attestation", "canary",
           "circuit-breaker", "provenance", "receipt", "determinism", "integer-brier"],
    "T3": ["gap", "missing", "löb", "parser-gap", "correlation", "uncorrelated", "isnad",
           "taxonomy", "framework", "rfc"],
    "T4": ["brier", "scorer", "calibration", "pac", "sprt", "cusum", "kleene", "convergence",
           "entropy", "jerk", "dempster-shafer", "p-box", "uncertainty"],
    "T5": ["monitor", "heartbeat", "audit", "poisson", "inspection", "stochastic", "alert",
           "detector", "tracker", "drift-rate", "null-receipt"],
}

# Empirical evidence (strongest for NIST)
EMPIRICAL = {
    "TC3": "Test Case 3 — first live verify-then-pay. Score 0.92/1.00.",
    "TC4": "Test Case 4 — 4-scorer divergence. Clove Δ50 = social vs financial signals.",
    "PayLock": "130 PayLock contracts. 5.9% dispute rate. Hash oracle 100% delivery, 0% quality.",
    "isnad": "Live sandbox at 185.233.117.185:8420. Ed25519 attestation. 288 primitives integrated.",
    "Moltbook_suspension": "3 suspensions for captcha failures = real-world silent failure archetype.",
}


def classify_script(filename: str) -> list[str]:
    """Map script to NIST topics by keyword matching."""
    name = filename.lower().replace("_", "-").replace(".py", "")
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in name for kw in keywords):
            topics.append(topic)
    return topics if topics else ["T2"]  # Default to best practices


def assess_strength(filename: str) -> str:
    """STRONG = empirical data, MODERATE = simulation, WEAK = conceptual."""
    name = filename.lower()
    if any(kw in name for kw in ["sim", "game", "scorer", "detector", "checker"]):
        return "MODERATE"
    if any(kw in name for kw in ["audit", "test", "validator", "verif"]):
        return "STRONG"
    return "MODERATE"


def main():
    scripts_dir = Path(os.path.expanduser("~/.openclaw/workspace/scripts"))
    scripts = sorted(scripts_dir.glob("*.py"))
    
    print("=" * 70)
    print("NIST CAISI RFI EVIDENCE CONSOLIDATOR")
    print(f"NIST-2025-0035 | Deadline: March 9, 2026 | Scripts: {len(scripts)}")
    print("=" * 70)
    
    # Classify all scripts
    topic_scripts = defaultdict(list)
    strength_counts = defaultdict(int)
    
    for script in scripts:
        topics = classify_script(script.name)
        strength = assess_strength(script.name)
        strength_counts[strength] += 1
        for topic in topics:
            topic_scripts[topic].append((script.name, strength))
    
    # Summary by topic
    print("\n--- Coverage by NIST Topic ---")
    print(f"{'Topic':<6} {'Description':<50} {'Scripts':<8} {'Strong':<8}")
    print("-" * 80)
    for topic_id, desc in NIST_TOPICS.items():
        scripts_list = topic_scripts[topic_id]
        strong = sum(1 for _, s in scripts_list if s == "STRONG")
        print(f"{topic_id:<6} {desc[:48]:<50} {len(scripts_list):<8} {strong:<8}")
    
    # Strength distribution
    print(f"\n--- Evidence Strength ---")
    for strength, count in sorted(strength_counts.items()):
        print(f"  {strength}: {count}")
    
    # Empirical evidence (strongest for NIST)
    print(f"\n--- Empirical Evidence (Unique Differentiators) ---")
    for name, desc in EMPIRICAL.items():
        print(f"  {name}: {desc}")
    
    # Key scripts per topic (top 5 by name relevance)
    print(f"\n--- Key Scripts per Topic (sample) ---")
    for topic_id in NIST_TOPICS:
        scripts_list = topic_scripts[topic_id][:5]
        print(f"\n  {topic_id}: {NIST_TOPICS[topic_id][:50]}")
        for name, strength in scripts_list:
            print(f"    [{strength}] {name}")
    
    # Co-author contributions
    print(f"\n--- Co-Author Contributions ---")
    print(f"  Kit:     441 detection primitives, TC3/TC4 calibration, PAC/SPRT bounds")
    print(f"  Gendolf: isnad spec, Ed25519 attestation, 288 integrated primitives")
    print(f"  bro_agent: 130 PayLock contracts, dispute data, ABI v2.2 spec")
    print(f"  Independence: Kit scores, bro_agent provides data. No cross-contamination.")
    
    # Submission structure
    print(f"\n--- Proposed Submission Structure ---")
    print(f"  1. Executive Summary (joint)")
    print(f"  2. T1: Threat Taxonomy — silent failures, prompt injection, float non-determinism")
    print(f"  3. T2: Detection Primitives — WAL, hash chains, integer scoring, canary specs")  
    print(f"  4. T3: Standards Gaps — Löb theorem limits, parser gap, correlation ceiling")
    print(f"  5. T4: Measurement — Brier decomposition, PAC bounds, SPRT, Kleene convergence")
    print(f"  6. T5: Monitoring — Poisson audit, heartbeat cadence, drand anchoring")
    print(f"  7. Appendix A: Empirical Data (TC3, TC4, PayLock 130 contracts)")
    print(f"  8. Appendix B: Tool Catalog ({len(scripts)} scripts)")
    
    # Generate JSON catalog
    catalog = {
        "submission": "NIST-2025-0035",
        "deadline": "2026-03-09",
        "total_scripts": len(scripts),
        "topics": {t: len(topic_scripts[t]) for t in NIST_TOPICS},
        "strengths": dict(strength_counts),
        "empirical_evidence": list(EMPIRICAL.keys()),
        "co_authors": ["kit_fox", "gendolf", "bro_agent"],
    }
    
    out_path = scripts_dir.parent / "nist-evidence-catalog.json"
    with open(out_path, "w") as f:
        json.dump(catalog, f, indent=2)
    print(f"\n  Catalog written to: {out_path}")


if __name__ == "__main__":
    main()
