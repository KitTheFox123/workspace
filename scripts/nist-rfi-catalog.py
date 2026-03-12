#!/usr/bin/env python3
"""
nist-rfi-catalog.py — Catalog detection primitives for NIST AI Agent Security RFI.

Maps Kit's script library to NIST CAISI RFI categories:
1. Threats & vulnerabilities in agent systems
2. Current mitigations & security measures
3. Identity & authentication for agents
4. Monitoring & observability
5. Multi-agent coordination security

NIST RFI deadline: March 9, 2026
Joint submission with Gendolf (isnad) + bro_agent (PayLock failure data)

Usage:
    python3 nist-rfi-catalog.py [scripts_dir]
"""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path


# NIST RFI categories mapped to script detection patterns
NIST_CATEGORIES = {
    "1_threats": {
        "name": "Threats & Vulnerabilities",
        "keywords": ["byzantine", "attack", "drift", "failure", "vulnerability", "gaming",
                     "sybil", "laundering", "injection", "compromise", "adversarial"],
        "description": "Detection of agent-specific threat patterns"
    },
    "2_mitigations": {
        "name": "Current Mitigations",
        "keywords": ["circuit-breaker", "verifier", "scorer", "detector", "checker",
                     "filter", "enforcer", "validator"],
        "description": "Active defense and mitigation tools"
    },
    "3_identity": {
        "name": "Identity & Authentication",
        "keywords": ["identity", "genesis", "anchor", "veil", "stylometry", "fingerprint",
                     "soul", "persona", "provenance", "attestation", "signer"],
        "description": "Agent identity verification and binding"
    },
    "4_monitoring": {
        "name": "Monitoring & Observability",
        "keywords": ["kalman", "cusum", "jerk", "derivative", "entropy", "ewma",
                     "jitter", "velocity", "acceleration", "phase", "kinematics",
                     "brier", "calibration", "metamemory", "slope"],
        "description": "Continuous monitoring and drift detection"
    },
    "5_coordination": {
        "name": "Multi-Agent Coordination",
        "keywords": ["correlation", "oracle", "independence", "quorum", "fork",
                     "commit-reveal", "dispute", "escrow", "pheromone", "stigmergy",
                     "trust-scor", "cross-platform", "comparator"],
        "description": "Secure multi-agent interaction patterns"
    },
}


def categorize_script(filename: str, docstring: str) -> list:
    """Assign script to NIST categories based on name and docstring."""
    text = (filename + " " + docstring).lower()
    categories = []
    for cat_id, cat_info in NIST_CATEGORIES.items():
        for kw in cat_info["keywords"]:
            if kw in text:
                categories.append(cat_id)
                break
    return categories if categories else ["uncategorized"]


def extract_docstring(filepath: Path) -> str:
    """Extract first docstring from a Python file."""
    try:
        content = filepath.read_text(errors='ignore')
        match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if match:
            return match.group(1).strip()[:200]
    except:
        pass
    return ""


def main():
    scripts_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("scripts")
    
    if not scripts_dir.exists():
        print(f"Directory not found: {scripts_dir}")
        sys.exit(1)

    scripts = sorted(scripts_dir.glob("*.py"))
    catalog = defaultdict(list)
    
    for script in scripts:
        doc = extract_docstring(script)
        cats = categorize_script(script.name, doc)
        for cat in cats:
            catalog[cat].append({
                "name": script.name,
                "doc": doc[:100] if doc else "(no docstring)"
            })

    # Print catalog
    print("=" * 70)
    print("NIST AI AGENT SECURITY RFI — DETECTION PRIMITIVES CATALOG")
    print(f"Total scripts: {len(scripts)}")
    print(f"Deadline: March 9, 2026")
    print("=" * 70)

    total_categorized = 0
    for cat_id in sorted(NIST_CATEGORIES.keys()):
        cat_info = NIST_CATEGORIES[cat_id]
        items = catalog.get(cat_id, [])
        total_categorized += len(items)
        print(f"\n### {cat_info['name']} ({len(items)} scripts)")
        print(f"    {cat_info['description']}")
        for item in items[:10]:
            print(f"    - {item['name']}")
        if len(items) > 10:
            print(f"    ... and {len(items) - 10} more")

    uncat = catalog.get("uncategorized", [])
    print(f"\n### Uncategorized ({len(uncat)} scripts)")
    for item in uncat[:5]:
        print(f"    - {item['name']}")
    if len(uncat) > 5:
        print(f"    ... and {len(uncat) - 5} more")

    # Summary stats
    print("\n" + "=" * 70)
    print("SUMMARY FOR RFI SUBMISSION")
    print(f"  Total primitives: {len(scripts)}")
    print(f"  Categorized: {total_categorized}")
    print(f"  Uncategorized: {len(uncat)}")
    print(f"  Categories covered: {sum(1 for c in NIST_CATEGORIES if catalog.get(c))}/5")
    
    coverage = {cat_id: len(catalog.get(cat_id, [])) for cat_id in NIST_CATEGORIES}
    weakest = min(coverage, key=coverage.get)
    print(f"  Weakest category: {NIST_CATEGORIES[weakest]['name']} ({coverage[weakest]} scripts)")
    print(f"  Strongest category: {NIST_CATEGORIES[max(coverage, key=coverage.get)]['name']} ({max(coverage.values())} scripts)")

    # Evidence statement
    print("\n--- EVIDENCE STATEMENT ---")
    print(f"This catalog contains {len(scripts)} detection primitives built by")
    print("autonomous agents through daily practice over 30 days.")
    print("Each script addresses a specific failure mode discovered through")
    print("cross-platform engagement and real-world test cases (TC1-TC4).")
    print("Companion data: 102 PayLock contracts with failure modes.")
    print("Joint submission: Kit (detection), Gendolf (isnad identity),")
    print("bro_agent (escrow/failure data).")


if __name__ == "__main__":
    main()
