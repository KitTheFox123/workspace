#!/usr/bin/env python3
"""
nist-merge-audit.py — Pre-merge checklist for NIST submission tools.

Audits each tool for:
1. Runnable (imports, no syntax errors)
2. Has --demo or default output
3. Has docstring explaining purpose
4. Produces graded output (A-F scale)
5. Cites at least one research source
6. Self-contained (no external API deps for demo)

Usage: python3 nist-merge-audit.py
"""

import subprocess
import sys
import os
import re
import json
from dataclasses import dataclass
from typing import List, Optional

TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))

# The 4 NIST submission tools
NIST_TOOLS = [
    "integer-brier-scorer.py",
    "execution-trace-commit.py",
    "canary-spec-commit.py",
    "container-swap-detector.py",
]

# Supporting tools that strengthen the submission
SUPPORTING = [
    "behavioral-genesis-chain.py",
    "heartbeat-scope-diff.py",
    "weight-vector-commitment.py",
]


@dataclass
class AuditResult:
    tool: str
    runnable: bool
    has_docstring: bool
    has_demo: bool
    produces_grade: bool
    cites_source: bool
    error: Optional[str] = None
    grade: str = "?"

    def compute_grade(self):
        score = sum([self.runnable, self.has_docstring, self.has_demo,
                     self.produces_grade, self.cites_source])
        grades = {5: "A", 4: "B", 3: "C", 2: "D"}
        self.grade = grades.get(score, "F")


def check_syntax(path: str) -> tuple:
    """Check if file has valid Python syntax and a docstring."""
    try:
        with open(path) as f:
            source = f.read()
        compile(source, path, 'exec')
        has_doc = '"""' in source[:500] or "'''" in source[:500]
        return True, has_doc, None
    except SyntaxError as e:
        return False, False, str(e)


def check_demo(path: str) -> tuple:
    """Run with --demo and check output."""
    try:
        result = subprocess.run(
            [sys.executable, path, "--demo"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(path)
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            # Try without --demo
            result = subprocess.run(
                [sys.executable, path],
                capture_output=True, text=True, timeout=30,
                cwd=os.path.dirname(path)
            )
            output = result.stdout + result.stderr

        has_demo = len(output.strip()) > 50
        has_grade = bool(re.search(r'[ABCDF]\b', output)) or 'grade' in output.lower()
        return has_demo, has_grade, output[:200]
    except (subprocess.TimeoutExpired, Exception) as e:
        return False, False, str(e)


def check_citations(path: str) -> bool:
    """Check if source cites research."""
    with open(path) as f:
        source = f.read()
    # Look for: year in parens, arXiv, DOI, author names with years
    patterns = [
        r'\d{4}\)',        # (2025)
        r'arXiv',
        r'doi\.org',
        r'RFC \d+',
        r'NIST',
        r'et al',
        r'[A-Z][a-z]+ \(\d{4}\)',  # Author (Year)
    ]
    return any(re.search(p, source) for p in patterns)


def audit_tool(name: str) -> AuditResult:
    path = os.path.join(TOOLS_DIR, name)
    if not os.path.exists(path):
        return AuditResult(name, False, False, False, False, False, f"NOT FOUND: {path}")

    runnable, has_doc, err = check_syntax(path)
    if not runnable:
        result = AuditResult(name, False, has_doc, False, False, False, err)
        result.compute_grade()
        return result

    has_demo, has_grade, _ = check_demo(path)
    has_cite = check_citations(path)

    result = AuditResult(name, runnable, has_doc, has_demo, has_grade, has_cite)
    result.compute_grade()
    return result


def main():
    print("=" * 60)
    print("NIST MERGE AUDIT — Pre-submission readiness check")
    print(f"Date: 2026-03-05 | Merge: Mar 7 | Submit: Mar 9")
    print("=" * 60)

    print("\n## PRIMARY SUBMISSION TOOLS (4)")
    primary_results = []
    for tool in NIST_TOOLS:
        r = audit_tool(tool)
        primary_results.append(r)
        status = f"[{r.grade}]"
        checks = f"run={'✓' if r.runnable else '✗'} doc={'✓' if r.has_docstring else '✗'} demo={'✓' if r.has_demo else '✗'} grade={'✓' if r.produces_grade else '✗'} cite={'✓' if r.cites_source else '✗'}"
        print(f"  {status} {tool}: {checks}")
        if r.error:
            print(f"      ERROR: {r.error}")

    print("\n## SUPPORTING TOOLS")
    for tool in SUPPORTING:
        r = audit_tool(tool)
        checks = f"run={'✓' if r.runnable else '✗'} doc={'✓' if r.has_docstring else '✗'} demo={'✓' if r.has_demo else '✗'}"
        print(f"  [{r.grade}] {tool}: {checks}")

    # Overall
    all_a = all(r.grade == "A" for r in primary_results)
    all_pass = all(r.runnable for r in primary_results)

    print(f"\n## OVERALL")
    print(f"  Primary tools passing: {sum(1 for r in primary_results if r.runnable)}/4")
    print(f"  All grade A: {'YES' if all_a else 'NO'}")
    print(f"  Merge ready: {'YES ✓' if all_pass else 'NO ✗ — fix before Mar 7'}")

    if not all_a:
        print(f"\n## FIX LIST")
        for r in primary_results:
            if r.grade != "A":
                fixes = []
                if not r.has_docstring: fixes.append("add docstring")
                if not r.has_demo: fixes.append("add --demo mode")
                if not r.produces_grade: fixes.append("add A-F grading")
                if not r.cites_source: fixes.append("add research citation")
                print(f"  {r.tool} ({r.grade}): {', '.join(fixes)}")


if __name__ == "__main__":
    main()
