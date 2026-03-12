#!/usr/bin/env python3
"""
nist-submission-manifest.py — Generate a hash-chained manifest of all NIST submission tools.

Creates a verifiable inventory: each tool's SHA256, line count, key functions,
and a Merkle-style root hash. The manifest itself is the proof that these
specific versions were submitted.

For the isnad-rfc NIST submission (deadline: Mar 9, 2026).

Usage:
    python3 nist-submission-manifest.py [--output manifest.json]
"""

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path


SUBMISSION_TOOLS = [
    "integer-brier-scorer.py",
    "execution-trace-commit.py",
    "canary-spec-commit.py",
    "weight-vector-commitment.py",
    "heartbeat-scope-diff.py",
    "behavioral-genesis-chain.py",
    "container-swap-detector.py",
    "fail-loud-auditor.py",
    "warrant-canary-agent.py",
    "principal-wal.py",
    "reconciliation-window.py",
    "interpretive-challenge.py",
    "migration-witness.py",
    "soul-drift-tracker.py",
]

SCRIPTS_DIR = Path(__file__).parent


def hash_file(path: Path) -> str:
    """SHA256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_docstring(path: Path) -> str:
    """Extract first docstring from Python file."""
    content = path.read_text()
    match = re.search(r'"""(.*?)"""', content, re.DOTALL)
    if match:
        lines = match.group(1).strip().split('\n')
        # First non-empty line
        for line in lines:
            line = line.strip()
            if line and not line.startswith('Usage'):
                return line[:120]
    return ""


def extract_functions(path: Path) -> list:
    """Extract top-level function names."""
    content = path.read_text()
    return re.findall(r'^def (\w+)\(', content, re.MULTILINE)


def merkle_root(hashes: list) -> str:
    """Compute Merkle root of hash list."""
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()
    if len(hashes) == 1:
        return hashes[0]

    # Pad to even
    if len(hashes) % 2 == 1:
        hashes.append(hashes[-1])

    next_level = []
    for i in range(0, len(hashes), 2):
        combined = hashes[i] + hashes[i + 1]
        next_level.append(hashlib.sha256(combined.encode()).hexdigest())

    return merkle_root(next_level)


def generate_manifest():
    tools = []
    hashes = []
    missing = []

    for name in SUBMISSION_TOOLS:
        path = SCRIPTS_DIR / name
        if not path.exists():
            missing.append(name)
            continue

        h = hash_file(path)
        hashes.append(h)
        content = path.read_text()
        line_count = len(content.splitlines())

        tools.append({
            "name": name,
            "sha256": h,
            "lines": line_count,
            "bytes": len(content.encode()),
            "description": extract_docstring(path),
            "functions": extract_functions(path),
        })

    root = merkle_root(hashes)

    manifest = {
        "manifest_version": 1,
        "project": "isnad-rfc",
        "submission": "NIST SP 800-XXX Agent Trust Framework",
        "deadline": "2026-03-09",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_count": len(tools),
        "missing": missing,
        "merkle_root": root,
        "tools": tools,
    }

    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, help="Output file path")
    args = parser.parse_args()

    manifest = generate_manifest()

    print(f"=== NIST Submission Manifest ===")
    print(f"Tools:       {manifest['tool_count']}/{len(SUBMISSION_TOOLS)}")
    print(f"Missing:     {manifest['missing'] or 'none'}")
    print(f"Merkle root: {manifest['merkle_root'][:32]}...")
    print(f"Generated:   {manifest['generated_at']}")
    print()

    for t in manifest["tools"]:
        print(f"  {t['name']}")
        print(f"    SHA256: {t['sha256'][:24]}...")
        print(f"    Lines:  {t['lines']}  |  Functions: {len(t['functions'])}")
        print(f"    Desc:   {t['description'][:80]}")
        print()

    total_lines = sum(t["lines"] for t in manifest["tools"])
    total_bytes = sum(t["bytes"] for t in manifest["tools"])
    total_fns = sum(len(t["functions"]) for t in manifest["tools"])
    print(f"TOTALS: {total_lines} lines, {total_bytes:,} bytes, {total_fns} functions")

    if args.output:
        Path(args.output).write_text(json.dumps(manifest, indent=2))
        print(f"\nManifest written to {args.output}")


if __name__ == "__main__":
    main()
