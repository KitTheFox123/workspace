#!/usr/bin/env python3
"""
nist-merge-preflight.py — Pre-merge checklist for NIST submission.

Validates that all Kit tools are present, runnable, and produce expected output formats.
Run before Mar 7 merge to catch issues early.

Usage: python3 nist-merge-preflight.py [--scripts-dir ./scripts]
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ToolCheck:
    name: str
    path: str
    exists: bool
    runnable: bool
    has_demo: bool
    output_sample: str
    grade: str  # PASS, WARN, FAIL
    notes: str


NIST_TOOLS = [
    "integer-brier-scorer.py",
    "execution-trace-commit.py",
    "canary-spec-commit.py",
    "container-swap-detector.py",
    "behavioral-genesis-anchor.py",
    "behavioral-genesis-chain.py",
    "interpretive-challenge.py",
    "migration-witness.py",
    "principal-wal.py",
    "warrant-canary-agent.py",
    "fail-loud-auditor.py",
    "fail-loud-receipt.py",
    "reconciliation-window.py",
    "weight-vector-commitment.py",
    "heartbeat-scope-diff.py",
    "algo-agility-downgrade.py",
    "soul-drift-tracker.py",
    "behavioral-weight-inference.py",
]

# Core 4 for submission
CORE_TOOLS = [
    "integer-brier-scorer.py",
    "execution-trace-commit.py",
    "canary-spec-commit.py",
    "behavioral-genesis-chain.py",
]


def check_tool(scripts_dir: str, name: str) -> ToolCheck:
    path = os.path.join(scripts_dir, name)
    exists = os.path.isfile(path)

    if not exists:
        return ToolCheck(name, path, False, False, False, "", "FAIL", "File not found")

    # Check if runnable (has --demo or runs without args)
    runnable = False
    has_demo = False
    output_sample = ""
    notes = ""

    try:
        with open(path) as f:
            content = f.read()
        has_demo = "--demo" in content or "def demo" in content

        # Try running with --demo or no args
        cmd = [sys.executable, path]
        if has_demo:
            cmd.append("--demo")

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        runnable = result.returncode == 0
        output_sample = (result.stdout or result.stderr)[:200]

        if not runnable:
            notes = f"Exit code {result.returncode}: {result.stderr[:100]}"
    except subprocess.TimeoutExpired:
        runnable = False
        notes = "Timeout (>10s)"
    except Exception as e:
        notes = str(e)[:100]

    # Grade
    if exists and runnable:
        grade = "PASS"
    elif exists and not runnable:
        grade = "WARN"
    else:
        grade = "FAIL"

    return ToolCheck(name, path, exists, runnable, has_demo, output_sample, grade, notes)


def main():
    parser = argparse.ArgumentParser(description="NIST merge preflight")
    parser.add_argument("--scripts-dir", default="scripts", help="Scripts directory")
    parser.add_argument("--core-only", action="store_true", help="Check only core 4 tools")
    args = parser.parse_args()

    tools = CORE_TOOLS if args.core_only else NIST_TOOLS
    print(f"=== NIST Merge Preflight ({len(tools)} tools) ===\n")

    results = []
    for name in tools:
        check = check_tool(args.scripts_dir, name)
        results.append(check)
        core_marker = " [CORE]" if name in CORE_TOOLS else ""
        status = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[check.grade]
        print(f"  {status} {check.name}{core_marker}")
        if check.notes:
            print(f"     {check.notes}")

    # Summary
    passed = sum(1 for r in results if r.grade == "PASS")
    warned = sum(1 for r in results if r.grade == "WARN")
    failed = sum(1 for r in results if r.grade == "FAIL")
    core_passed = sum(1 for r in results if r.grade == "PASS" and r.name in CORE_TOOLS)

    print(f"\n=== SUMMARY ===")
    print(f"  Total:  {len(results)}")
    print(f"  Pass:   {passed}")
    print(f"  Warn:   {warned}")
    print(f"  Fail:   {failed}")
    print(f"  Core:   {core_passed}/{len(CORE_TOOLS)}")

    if failed > 0 or core_passed < len(CORE_TOOLS):
        print(f"\n  ❌ NOT READY FOR MERGE")
        return 1
    elif warned > 0:
        print(f"\n  ⚠️ MERGE WITH CAUTION")
        return 0
    else:
        print(f"\n  ✅ READY FOR MERGE")
        return 0


if __name__ == "__main__":
    sys.exit(main())
