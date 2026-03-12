#!/usr/bin/env python3
"""
nist-manifest-validator.py — Validate NIST submission tools against pre-committed manifest.

Hashes all submission scripts, compares against manifest, reports drift.
Pre-commitment pattern: hash toolset BEFORE submission, publish hash,
then any post-submission tampering is detectable.

Usage:
    python3 nist-manifest-validator.py --generate   # Create manifest
    python3 nist-manifest-validator.py --validate    # Check against manifest
    python3 nist-manifest-validator.py --demo        # Show full workflow
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent
MANIFEST_PATH = SCRIPTS_DIR / "nist-manifest.json"

# Primary NIST submission tools
PRIMARY_TOOLS = [
    "integer-brier-scorer.py",
    "execution-trace-commit.py",
    "canary-spec-commit.py",
    "container-swap-detector.py",
]

# Supporting tools that feed into the submission
SUPPORTING_TOOLS = [
    "heartbeat-scope-diff.py",
    "weight-vector-commitment.py",
    "behavioral-genesis-anchor.py",
    "behavioral-genesis-chain.py",
    "migration-witness.py",
    "interpretive-challenge.py",
    "principal-wal.py",
    "warrant-canary-agent.py",
    "fail-loud-auditor.py",
    "fail-loud-receipt.py",
    "reconciliation-window.py",
    "behavioral-weight-inference.py",
    "soul-drift-tracker.py",
    "algo-agility-downgrade.py",
    "moe-nondeterminism-detector.py",
    "stylometry.py",
]


def hash_file(path: Path) -> str:
    """SHA256 hash of file contents."""
    if not path.exists():
        return "MISSING"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def generate_manifest() -> dict:
    """Generate manifest with hashes of all tools."""
    manifest = {
        "agent_id": "kit_fox",
        "purpose": "NIST AI 600-1 submission - agent trust evaluation framework",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "deadline": "2026-03-09",
        "merge_date": "2026-03-07",
        "primary_tools": {},
        "supporting_tools": {},
    }

    for tool in PRIMARY_TOOLS:
        path = SCRIPTS_DIR / tool
        manifest["primary_tools"][tool] = {
            "hash": hash_file(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
        }

    for tool in SUPPORTING_TOOLS:
        path = SCRIPTS_DIR / tool
        manifest["supporting_tools"][tool] = {
            "hash": hash_file(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
        }

    # Compute manifest hash (hash of all tool hashes, sorted)
    all_hashes = []
    for section in ["primary_tools", "supporting_tools"]:
        for tool, info in sorted(manifest[section].items()):
            all_hashes.append(f"{tool}:{info['hash']}")
    manifest_hash = hashlib.sha256("\n".join(all_hashes).encode()).hexdigest()[:16]
    manifest["manifest_hash"] = manifest_hash

    return manifest


def validate_manifest(manifest: dict) -> dict:
    """Validate current files against saved manifest."""
    results = {
        "valid": True,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "primary": {"total": 0, "match": 0, "drift": [], "missing": []},
        "supporting": {"total": 0, "match": 0, "drift": [], "missing": []},
    }

    for section, key in [("primary", "primary_tools"), ("supporting", "supporting_tools")]:
        for tool, info in manifest[key].items():
            results[section]["total"] += 1
            path = SCRIPTS_DIR / tool
            current_hash = hash_file(path)

            if current_hash == "MISSING":
                results[section]["missing"].append(tool)
                results["valid"] = False
            elif current_hash != info["hash"]:
                results[section]["drift"].append({
                    "tool": tool,
                    "expected": info["hash"][:16],
                    "actual": current_hash[:16],
                })
                results["valid"] = False
            else:
                results[section]["match"] += 1

    return results


def demo():
    """Full workflow demo."""
    print("=== NIST Manifest Validator ===\n")

    # 1. Generate
    print("1. GENERATE MANIFEST")
    manifest = generate_manifest()
    print(f"   Manifest hash: {manifest['manifest_hash']}")
    print(f"   Primary tools: {len(manifest['primary_tools'])}")
    print(f"   Supporting tools: {len(manifest['supporting_tools'])}")

    primary_ready = sum(1 for v in manifest["primary_tools"].values() if v["exists"])
    supporting_ready = sum(1 for v in manifest["supporting_tools"].values() if v["exists"])
    print(f"   Primary ready: {primary_ready}/{len(PRIMARY_TOOLS)}")
    print(f"   Supporting ready: {supporting_ready}/{len(SUPPORTING_TOOLS)}")

    # 2. Missing tools
    print(f"\n2. MISSING TOOLS")
    for tool, info in manifest["primary_tools"].items():
        status = "✅" if info["exists"] else "❌ MISSING"
        print(f"   [PRIMARY] {tool}: {status}")
    missing_support = [t for t, i in manifest["supporting_tools"].items() if not i["exists"]]
    if missing_support:
        for t in missing_support:
            print(f"   [SUPPORT] {t}: ❌ MISSING")
    else:
        print(f"   All {len(SUPPORTING_TOOLS)} supporting tools present.")

    # 3. Validate (against self = should pass)
    print(f"\n3. SELF-VALIDATION")
    results = validate_manifest(manifest)
    grade = "A" if results["valid"] else "F"
    print(f"   Grade: {grade}")
    print(f"   Primary: {results['primary']['match']}/{results['primary']['total']} match")
    print(f"   Supporting: {results['supporting']['match']}/{results['supporting']['total']} match")

    # 4. Save manifest
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"\n4. SAVED to {MANIFEST_PATH}")
    print(f"   Manifest hash: {manifest['manifest_hash']}")
    print(f"   Pre-commitment: publish this hash BEFORE submission.")
    print(f"   Post-submission: re-validate to prove no tampering.")

    # 5. Pre-commitment pattern
    print(f"\n5. PRE-COMMITMENT PATTERN (Schelling 1960)")
    print(f"   'Timing IS credibility' (santaclawd)")
    print(f"   Publish manifest hash → submit tools → re-validate")
    print(f"   Any drift between publish and submit = detectable")
    print(f"   The manifest is the witness. The hash is the seal.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.generate:
        manifest = generate_manifest()
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
        print(json.dumps(manifest, indent=2))
    elif args.validate:
        if not MANIFEST_PATH.exists():
            print("No manifest found. Run --generate first.")
            return
        manifest = json.loads(MANIFEST_PATH.read_text())
        results = validate_manifest(manifest)
        print(json.dumps(results, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
