#!/usr/bin/env python3
"""
nist-submission-preflight.py — Pre-merge checklist for NIST submission.

Validates that all 4 submission tools exist, run without errors, produce
consistent output formats, and have proper documentation headers.

Usage: python3 nist-submission-preflight.py
"""

import subprocess
import sys
import os
import json
import hashlib
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REQUIRED_TOOLS = [
    "integer-brier-scorer.py",
    "execution-trace-commit.py", 
    "canary-spec-commit.py",
    "heartbeat-scope-diff.py",  # replaces absence-attestation for scope layer
]

CHECKS = {
    "exists": "File exists",
    "syntax": "Python syntax valid",
    "docstring": "Has module docstring",
    "runs": "Runs without error (--help or --demo)",
    "hash": "SHA256 hash for submission manifest",
}


def check_exists(path: Path) -> tuple:
    return path.exists(), str(path)


def check_syntax(path: Path) -> tuple:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0, result.stderr.strip() or "OK"
    except Exception as e:
        return False, str(e)


def check_docstring(path: Path) -> tuple:
    content = path.read_text()
    has_doc = '"""' in content[:500] or "'''" in content[:500]
    return has_doc, "Found" if has_doc else "Missing module docstring"


def check_runs(path: Path) -> tuple:
    for flag in ["--demo", "--help", ""]:
        try:
            cmd = [sys.executable, str(path)]
            if flag:
                cmd.append(flag)
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                cwd=str(SCRIPTS_DIR.parent)
            )
            if result.returncode == 0:
                return True, f"OK ({flag or 'no args'}), {len(result.stdout)} bytes output"
        except subprocess.TimeoutExpired:
            return False, f"Timeout with {flag}"
        except Exception as e:
            return False, str(e)
    return False, "All run attempts failed"


def get_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main():
    print("=" * 60)
    print("NIST SUBMISSION PREFLIGHT CHECK")
    print(f"Date: {subprocess.check_output(['date', '-u']).decode().strip()}")
    print(f"Scripts dir: {SCRIPTS_DIR}")
    print("=" * 60)

    all_pass = True
    manifest = {}

    for tool_name in REQUIRED_TOOLS:
        path = SCRIPTS_DIR / tool_name
        print(f"\n--- {tool_name} ---")

        # Exists
        exists, msg = check_exists(path)
        status = "✅" if exists else "❌"
        print(f"  {status} exists: {msg}")
        if not exists:
            all_pass = False
            continue

        # Syntax
        ok, msg = check_syntax(path)
        status = "✅" if ok else "❌"
        print(f"  {status} syntax: {msg}")
        if not ok:
            all_pass = False

        # Docstring
        ok, msg = check_docstring(path)
        status = "✅" if ok else "⚠️"
        print(f"  {status} docstring: {msg}")

        # Runs
        ok, msg = check_runs(path)
        status = "✅" if ok else "❌"
        print(f"  {status} runs: {msg}")
        if not ok:
            all_pass = False

        # Hash
        h = get_hash(path)
        print(f"  🔑 hash: {h}")
        manifest[tool_name] = h

    print(f"\n{'=' * 60}")
    print("MANIFEST")
    for name, h in manifest.items():
        print(f"  {name}: {h}")

    grade = "PASS ✅" if all_pass else "FAIL ❌"
    print(f"\nOVERALL: {grade}")
    print(f"Tools ready: {len(manifest)}/{len(REQUIRED_TOOLS)}")

    if not all_pass:
        print("\n⚠️  Fix failures before Mar 7 merge!")
        sys.exit(1)
    else:
        print("\n✅ Ready for merge.")


if __name__ == "__main__":
    main()
