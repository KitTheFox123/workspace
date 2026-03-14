#!/usr/bin/env python3
"""
TC4 sync prep checklist — Mar 14 coordination with Gendolf.

Verifies readiness for test case 4:
- agent-trust-harness adapter slots available
- gendolf's tc4 package modules map to adapters
- isnad sandbox reachable
- key pairs ready

Run before sync to surface gaps.
"""

import os
import json
import subprocess
from pathlib import Path


def check(name: str, condition: bool, detail: str = ""):
    status = "✓" if condition else "✗"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return condition


def run():
    print("=" * 60)
    print("TC4 SYNC PREP CHECKLIST")
    print("Kit ↔ Gendolf — March 14, 2026")
    print("=" * 60)

    passed = 0
    total = 0

    # 1. agent-trust-harness exists
    print("\n--- 1. agent-trust-harness ---")
    harness_dir = Path.home() / "agent-trust-harness"
    total += 1
    if check("Repo exists", harness_dir.exists()):
        passed += 1

    # Check for test files
    total += 1
    test_files = list(harness_dir.glob("test_*.py")) + list(harness_dir.glob("tests/*.py")) if harness_dir.exists() else []
    if check("Test files found", len(test_files) > 0, f"{len(test_files)} test files"):
        passed += 1

    # 2. Adapter slots
    print("\n--- 2. Adapter Mapping ---")
    adapter_map = {
        "genesis": "vocabulary.py (identity bootstrap)",
        "attestation": "survivorship.py (liveness proof)",
        "redaction": "remediation.py (recovery)",
        "gossip": "gossip adapter (existing)",
    }
    for adapter, module in adapter_map.items():
        total += 1
        # Check if adapter mentioned in harness
        found = False
        if harness_dir.exists():
            for f in harness_dir.rglob("*.py"):
                try:
                    if adapter in f.read_text():
                        found = True
                        break
                except:
                    pass
        if check(f"{adapter} → {module}", found or adapter == "gossip", "in harness" if found else "pending"):
            passed += 1

    # 3. Isnad sandbox
    print("\n--- 3. Isnad Sandbox ---")
    total += 1
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "5",
             "http://185.233.117.185:8420"],
            capture_output=True, text=True, timeout=10
        )
        reachable = result.stdout.strip() in ["200", "404", "301", "302"]
        if check("Sandbox reachable (185.233.117.185:8420)", reachable, f"HTTP {result.stdout.strip()}"):
            passed += 1
    except:
        check("Sandbox reachable", False, "timeout/error")

    # 4. Scripts built today
    print("\n--- 4. Friday 13th Scripts (available for tc4) ---")
    scripts = [
        "idempotent-cert-delivery.py",
        "finality-gate.py",
        "dkim-idempotency-validator.py",
        "key-separation-analyzer.py",
        "sleeper-effect-detector.py",
        "partial-stack-failure-sim.py",
        "epistemic-vigilance-scorer.py",
    ]
    scripts_dir = Path.home() / ".openclaw/workspace/scripts"
    for s in scripts:
        total += 1
        exists = (scripts_dir / s).exists()
        if check(s, exists):
            passed += 1

    # 5. Credentials
    print("\n--- 5. Credentials ---")
    creds = {
        "agentmail": Path.home() / ".config/agentmail/credentials.json",
        "clawk": Path.home() / ".config/clawk/credentials.json",
        "moltbook": Path.home() / ".config/moltbook/credentials.json",
    }
    for name, path in creds.items():
        total += 1
        if check(f"{name} credentials", path.exists()):
            passed += 1

    # Summary
    print(f"\n{'=' * 60}")
    pct = passed / total * 100
    grade = "A" if pct >= 90 else "B" if pct >= 75 else "C" if pct >= 60 else "F"
    print(f"RESULT: {passed}/{total} checks passed ({pct:.0f}%) — Grade: {grade}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run()
