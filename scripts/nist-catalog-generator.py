#!/usr/bin/env python3
"""
nist-catalog-generator.py — Categorize detection scripts for NIST RFI submission.

Maps ~300 scripts to NIST AI safety categories:
- Reliability & Robustness
- Trust & Transparency
- Security & Privacy
- Accountability & Governance

Output: JSON catalog with script name, category, description, key technique.
"""

import os
import re
import json
from pathlib import Path


CATEGORIES = {
    "reliability": {
        "keywords": ["calibration", "brier", "kalman", "cusum", "drift", "jerk", "velocity",
                      "acceleration", "kinematics", "deviance", "decay", "slope", "derivative",
                      "phase", "asymmetry", "circuit-breaker", "state-vector", "ewma"],
        "nist": "Reliability & Robustness",
    },
    "trust": {
        "keywords": ["trust", "reputation", "josang", "beta", "attestation", "isnad",
                      "receipt", "chain", "provenance", "commit-reveal", "scope", "anchor",
                      "genesis", "verify", "scorer", "comparator"],
        "nist": "Trust & Transparency",
    },
    "security": {
        "keywords": ["byzantine", "sybil", "gaming", "laundering", "envelope", "injection",
                      "canary", "attacker", "adversarial", "collusion", "independence",
                      "correlation", "fingerprint", "stylometry", "veil", "piercing"],
        "nist": "Security & Privacy",
    },
    "governance": {
        "keywords": ["audit", "airt", "taxonomy", "failure", "goodhart", "godel",
                      "metamemory", "compression", "memory", "soul", "identity",
                      "oracle", "dispute", "pheromone", "stigmergy"],
        "nist": "Accountability & Governance",
    },
}


def extract_docstring(filepath: Path) -> str:
    """Extract first docstring from a Python file."""
    try:
        text = filepath.read_text(errors="ignore")
        match = re.search(r'"""(.*?)"""', text, re.DOTALL)
        if match:
            doc = match.group(1).strip()
            # First line only
            return doc.split("\n")[0].strip()
    except Exception:
        pass
    return ""


def categorize(name: str, docstring: str) -> str:
    """Categorize a script by name + docstring keywords."""
    text = (name + " " + docstring).lower()
    scores = {}
    for cat, info in CATEGORIES.items():
        scores[cat] = sum(1 for kw in info["keywords"] if kw in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "uncategorized"


def main():
    scripts_dir = Path(__file__).parent
    catalog = {"categories": {}, "scripts": [], "summary": {}}

    for cat, info in CATEGORIES.items():
        catalog["categories"][cat] = info["nist"]

    py_files = sorted(scripts_dir.glob("*.py"))
    cat_counts = {}

    for f in py_files:
        if f.name == "nist-catalog-generator.py":
            continue
        doc = extract_docstring(f)
        cat = categorize(f.name, doc)
        nist_cat = CATEGORIES.get(cat, {}).get("nist", "Uncategorized")

        catalog["scripts"].append({
            "name": f.name,
            "category": nist_cat,
            "description": doc[:120] if doc else f.stem.replace("-", " ").replace("_", " "),
        })
        cat_counts[nist_cat] = cat_counts.get(nist_cat, 0) + 1

    catalog["summary"] = {
        "total": len(catalog["scripts"]),
        "by_category": cat_counts,
    }

    # Print summary
    print(f"NIST Detection Primitives Catalog")
    print(f"Total scripts: {catalog['summary']['total']}")
    print()
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
        # Show first 3 examples
        examples = [s for s in catalog["scripts"] if s["category"] == cat][:3]
        for e in examples:
            print(f"    - {e['name']}: {e['description'][:80]}")
    print()

    # Save catalog
    out = scripts_dir.parent / "nist-catalog.json"
    with open(out, "w") as f:
        json.dump(catalog, f, indent=2)
    print(f"Catalog saved to {out}")


if __name__ == "__main__":
    main()
