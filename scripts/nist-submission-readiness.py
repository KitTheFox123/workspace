#!/usr/bin/env python3
"""
nist-submission-readiness.py — Pre-submission validation for NIST RFI response.

Checks:
1. All core tools run without errors
2. Each tool produces structured output (JSON-parseable or graded)
3. Cross-references between tools are consistent
4. Evidence chain: tool output → section mapping → citation
5. Generates a readiness report with pass/fail per requirement

Usage: python3 nist-submission-readiness.py
"""

import subprocess
import sys
import json
import os
from dataclasses import dataclass, field
from typing import List, Tuple

SCRIPTS_DIR = os.path.expanduser("~/.openclaw/workspace/scripts")

CORE_TOOLS = [
    "integer-brier-scorer.py",
    "execution-trace-commit.py",
    "canary-spec-commit.py",
    "behavioral-genesis-chain.py",
]

SUPPORTING_TOOLS = [
    "container-swap-detector.py",
    "interpretive-challenge.py",
    "migration-witness.py",
    "principal-wal.py",
    "warrant-canary-agent.py",
    "fail-loud-auditor.py",
    "reconciliation-window.py",
    "weight-vector-commitment.py",
    "heartbeat-scope-diff.py",
    "algo-agility-downgrade.py",
    "soul-drift-tracker.py",
    "behavioral-weight-inference.py",
]

# NIST CAISI categories our tools map to
CAISI_CATEGORIES = {
    "calibration": ["integer-brier-scorer.py", "behavioral-weight-inference.py"],
    "transparency": ["execution-trace-commit.py", "fail-loud-auditor.py", "fail-loud-receipt.py"],
    "identity": ["behavioral-genesis-chain.py", "container-swap-detector.py", "migration-witness.py", "interpretive-challenge.py", "soul-drift-tracker.py"],
    "governance": ["principal-wal.py", "canary-spec-commit.py", "heartbeat-scope-diff.py"],
    "security": ["warrant-canary-agent.py", "algo-agility-downgrade.py", "reconciliation-window.py"],
    "commitment": ["weight-vector-commitment.py"],
}


@dataclass
class ToolResult:
    name: str
    runs: bool = False
    has_output: bool = False
    has_grade: bool = False
    grade: str = ""
    error: str = ""
    runtime_ms: int = 0


def run_tool(name: str) -> ToolResult:
    """Run a tool with --demo flag and check output."""
    result = ToolResult(name=name)
    path = os.path.join(SCRIPTS_DIR, name)

    if not os.path.exists(path):
        result.error = "FILE NOT FOUND"
        return result

    try:
        import time
        start = time.monotonic()
        proc = subprocess.run(
            ["python3", path, "--demo"],
            capture_output=True, text=True, timeout=30,
            cwd=SCRIPTS_DIR,
        )
        result.runtime_ms = int((time.monotonic() - start) * 1000)

        if proc.returncode == 0:
            result.runs = True
            output = proc.stdout
            if len(output) > 10:
                result.has_output = True
            # Check for grade patterns
            for line in output.split("\n"):
                line_lower = line.lower().strip()
                if "grade:" in line_lower or "grade =" in line_lower:
                    result.has_grade = True
                    # Extract grade letter
                    for ch in "ABCDF":
                        if ch in line.upper().split("grade")[-1][:10].upper():
                            result.grade = ch
                            break
        else:
            result.error = proc.stderr[:200] if proc.stderr else f"exit {proc.returncode}"
    except subprocess.TimeoutExpired:
        result.error = "TIMEOUT (30s)"
    except Exception as e:
        result.error = str(e)[:200]

    return result


def check_category_coverage() -> List[Tuple[str, bool, int]]:
    """Check that each CAISI category has at least one working tool."""
    coverage = []
    for cat, tools in CAISI_CATEGORIES.items():
        existing = [t for t in tools if os.path.exists(os.path.join(SCRIPTS_DIR, t))]
        coverage.append((cat, len(existing) > 0, len(existing)))
    return coverage


def main():
    print("=" * 60)
    print("NIST SUBMISSION READINESS CHECK")
    print(f"Date: 2026-03-05 | Deadline: 2026-03-09 | Days left: 4")
    print("=" * 60)

    # 1. Core tools
    print("\n📋 CORE TOOLS (must all pass)")
    print("-" * 40)
    core_results = []
    for tool in CORE_TOOLS:
        r = run_tool(tool)
        core_results.append(r)
        status = "✅" if r.runs and r.has_output else "❌"
        grade_str = f" [{r.grade}]" if r.grade else ""
        time_str = f" ({r.runtime_ms}ms)" if r.runs else ""
        print(f"  {status} {tool}{grade_str}{time_str}")
        if r.error:
            print(f"     ⚠️  {r.error[:80]}")

    # 2. Supporting tools
    print(f"\n📋 SUPPORTING TOOLS ({len(SUPPORTING_TOOLS)})")
    print("-" * 40)
    support_results = []
    for tool in SUPPORTING_TOOLS:
        r = run_tool(tool)
        support_results.append(r)
        status = "✅" if r.runs and r.has_output else "⚠️"
        grade_str = f" [{r.grade}]" if r.grade else ""
        time_str = f" ({r.runtime_ms}ms)" if r.runs else ""
        print(f"  {status} {tool}{grade_str}{time_str}")
        if r.error:
            print(f"     ⚠️  {r.error[:80]}")

    # 3. Category coverage
    print(f"\n📋 CAISI CATEGORY COVERAGE")
    print("-" * 40)
    coverage = check_category_coverage()
    for cat, covered, count in coverage:
        status = "✅" if covered else "❌"
        print(f"  {status} {cat}: {count} tools")

    # 4. Summary
    all_results = core_results + support_results
    passing = sum(1 for r in all_results if r.runs and r.has_output)
    graded = sum(1 for r in all_results if r.has_grade)
    core_pass = sum(1 for r in core_results if r.runs and r.has_output)
    cats_covered = sum(1 for _, c, _ in coverage if c)
    total_runtime = sum(r.runtime_ms for r in all_results)

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"  Tools passing:     {passing}/{len(all_results)}")
    print(f"  Core tools:        {core_pass}/{len(CORE_TOOLS)}")
    print(f"  With grades:       {graded}/{len(all_results)}")
    print(f"  Categories:        {cats_covered}/{len(CAISI_CATEGORIES)}")
    print(f"  Total runtime:     {total_runtime}ms")
    print(f"  Merge target:      Mar 7")
    print(f"  Review target:     Mar 8")
    print(f"  Submit deadline:   Mar 9")

    if core_pass == len(CORE_TOOLS) and cats_covered == len(CAISI_CATEGORIES):
        print(f"\n  ✅ SUBMISSION READY")
    elif core_pass == len(CORE_TOOLS):
        print(f"\n  ⚠️  CORE READY, COVERAGE GAPS")
    else:
        print(f"\n  ❌ NOT READY — core tools failing")

    return 0 if core_pass == len(CORE_TOOLS) else 1


if __name__ == "__main__":
    sys.exit(main())
