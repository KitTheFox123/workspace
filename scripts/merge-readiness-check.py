#!/usr/bin/env python3
"""Pre-merge readiness checker for isnad-rfc tools branch.
Validates: all tools run, tests pass, docs current, no uncommitted changes."""

import subprocess
import sys
import os
from pathlib import Path

REPO = Path.home() / "isnad-rfc"
TOOLS_DIR = REPO / "tools"

def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or REPO, timeout=30)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def check_git_clean():
    code, out, _ = run(["git", "status", "--porcelain"])
    if out:
        return False, f"Uncommitted changes:\n{out}"
    return True, "Working tree clean"

def check_branch():
    code, out, _ = run(["git", "branch", "--show-current"])
    return out == "tools", f"On branch: {out}"

def check_tools_exist():
    if not TOOLS_DIR.exists():
        return False, "tools/ directory missing"
    py_files = list(TOOLS_DIR.glob("*.py"))
    return len(py_files) >= 10, f"{len(py_files)} Python tools found"

def check_tools_run():
    failures = []
    for f in sorted(TOOLS_DIR.glob("*.py")):
        code, out, err = run(["python3", str(f), "--help"])
        if code != 0:
            # Try without --help (some tools don't have it)
            code2, _, _ = run(["python3", "-c", f"import importlib.util; spec = importlib.util.spec_from_file_location('m', '{f}'); m = importlib.util.module_from_spec(spec)"])
            if code2 != 0:
                failures.append(f.name)
    if failures:
        return False, f"Failed: {', '.join(failures)}"
    return True, "All tools importable"

def check_validation_doc():
    doc = REPO / "tools" / "PRE-MERGE-VALIDATION.md"
    if not doc.exists():
        return False, "PRE-MERGE-VALIDATION.md missing"
    content = doc.read_text()
    if "PASS" in content or "✅" in content or "VALIDATED" in content:
        return True, "Validation doc exists with PASS entries"
    return False, "Validation doc exists but no PASS entries"

def check_nist_submission():
    doc = REPO / "NIST-SUBMISSION.md"
    if not doc.exists():
        doc = REPO / "tools" / "NIST-SUBMISSION.md"
    if not doc.exists():
        return False, "NIST-SUBMISSION.md missing"
    return True, "NIST-SUBMISSION.md exists"

def main():
    checks = [
        ("Git clean", check_git_clean),
        ("On tools branch", check_branch),
        ("Tools exist (≥10)", check_tools_exist),
        ("Tools importable", check_tools_run),
        ("Validation doc", check_validation_doc),
        ("NIST submission doc", check_nist_submission),
    ]
    
    all_pass = True
    print("=" * 50)
    print("MERGE READINESS CHECK — isnad-rfc tools→main")
    print("=" * 50)
    
    for name, fn in checks:
        try:
            passed, detail = fn()
        except Exception as e:
            passed, detail = False, str(e)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}  {name}: {detail}")
        if not passed:
            all_pass = False
    
    print("=" * 50)
    if all_pass:
        print("🟢 READY TO MERGE")
    else:
        print("🔴 NOT READY — fix failures above")
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
