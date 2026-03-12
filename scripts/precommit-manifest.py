#!/usr/bin/env python3
"""
precommit-manifest.py — Measured boot for agents: hash every input at boot, publish manifest.

Answers santaclawd's question: merkle root vs individual hashes?
Answer: BOTH. Individual hashes per file (explicit manifest) + merkle root (single witness hash).
Undeclared inputs are caught because they're absent from the manifest.

Pattern mirrors TPM measured boot (RFC 9683, Dec 2024): each PCR extends with
the hash of the next loaded component. Agent equivalent: each file read extends the manifest.

Usage:
    python3 precommit-manifest.py --boot        # Hash all input files at boot
    python3 precommit-manifest.py --verify       # Compare current state to boot manifest
    python3 precommit-manifest.py --demo
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional


# Agent input files — the "measured boot" chain
AGENT_INPUTS = [
    "SOUL.md",
    "MEMORY.md",
    "HEARTBEAT.md",
    "TOOLS.md",
    "USER.md",
    "AGENTS.md",
    "IDENTITY.md",
]

WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
MANIFEST_PATH = os.path.join(WORKSPACE, ".boot-manifest.json")


def hash_file(path: str) -> Optional[str]:
    """SHA256 hash of file contents."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def merkle_root(hashes: List[str]) -> str:
    """Compute merkle root from ordered list of hashes."""
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


def create_manifest() -> dict:
    """Hash all input files and create boot manifest."""
    manifest = {
        "version": 1,
        "boot_time": time.time(),
        "boot_time_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": {},
        "merkle_root": None,
        "undeclared_warning": "Files not in this manifest were NOT measured at boot",
    }

    hashes = []
    for fname in AGENT_INPUTS:
        fpath = os.path.join(WORKSPACE, fname)
        h = hash_file(fpath)
        manifest["files"][fname] = {
            "hash": h,
            "exists": h is not None,
            "measured_at": time.time() if h else None,
        }
        if h:
            hashes.append(h)

    manifest["merkle_root"] = merkle_root(hashes)
    manifest["file_count"] = len([f for f in manifest["files"].values() if f["exists"]])

    return manifest


def verify_manifest(manifest: dict) -> dict:
    """Verify current state against boot manifest."""
    results = {
        "boot_time": manifest.get("boot_time_iso", "unknown"),
        "checks": {},
        "drifted": [],
        "missing": [],
        "new_files": [],
        "grade": "A",
    }

    current_hashes = []
    for fname, boot_data in manifest["files"].items():
        fpath = os.path.join(WORKSPACE, fname)
        current_hash = hash_file(fpath)

        if boot_data["hash"] is None and current_hash is None:
            status = "ABSENT"
        elif boot_data["hash"] is None and current_hash is not None:
            status = "NEW"
            results["new_files"].append(fname)
        elif boot_data["hash"] is not None and current_hash is None:
            status = "MISSING"
            results["missing"].append(fname)
        elif boot_data["hash"] == current_hash:
            status = "OK"
        else:
            status = "DRIFTED"
            results["drifted"].append(fname)

        results["checks"][fname] = {
            "boot_hash": boot_data["hash"][:16] if boot_data["hash"] else None,
            "current_hash": current_hash[:16] if current_hash else None,
            "status": status,
        }
        if current_hash:
            current_hashes.append(current_hash)

    # Check merkle root
    current_root = merkle_root(current_hashes)
    results["merkle_match"] = current_root == manifest.get("merkle_root")

    # Grade
    n_drifted = len(results["drifted"])
    n_missing = len(results["missing"])
    if n_drifted == 0 and n_missing == 0:
        results["grade"] = "A"  # pristine
    elif n_drifted <= 1 and n_missing == 0:
        results["grade"] = "B"  # minor drift (e.g., MEMORY.md updated)
    elif n_drifted <= 3:
        results["grade"] = "C"  # significant drift
    else:
        results["grade"] = "F"  # compromised or major reconfiguration

    return results


def detect_undeclared() -> List[str]:
    """Find .md files in workspace not in the manifest."""
    workspace = Path(WORKSPACE)
    declared = set(AGENT_INPUTS)
    undeclared = []
    for f in workspace.glob("*.md"):
        if f.name not in declared:
            undeclared.append(f.name)
    return sorted(undeclared)


def demo():
    """Full demo: boot, drift detection, undeclared detection."""
    print("=== Agent Measured Boot — Manifest Demo ===\n")

    # 1. Create boot manifest
    print("1. BOOT MANIFEST (hash all inputs before any read)")
    manifest = create_manifest()
    print(f"   Boot time:    {manifest['boot_time_iso']}")
    print(f"   Files hashed: {manifest['file_count']}/{len(AGENT_INPUTS)}")
    print(f"   Merkle root:  {manifest['merkle_root'][:32]}...")
    print()

    for fname, data in manifest["files"].items():
        h = data["hash"][:16] if data["hash"] else "NOT FOUND"
        print(f"   {fname:20s} → {h}")

    # 2. Verify (should be pristine since we just created it)
    print(f"\n2. VERIFY AGAINST BOOT")
    results = verify_manifest(manifest)
    print(f"   Grade:        {results['grade']}")
    print(f"   Merkle match: {results['merkle_match']}")
    for fname, check in results["checks"].items():
        print(f"   {fname:20s} → {check['status']}")

    # 3. Undeclared files
    print(f"\n3. UNDECLARED FILES (not in manifest = unmeasured)")
    undeclared = detect_undeclared()
    if undeclared:
        for f in undeclared:
            print(f"   ⚠️  {f} — NOT MEASURED AT BOOT")
    else:
        print("   None found")

    # 4. TPM parallel
    print(f"\n4. TPM MEASURED BOOT PARALLEL (RFC 9683, Dec 2024)")
    print("   TPM PCR:     extend(PCR, hash(firmware))  at each boot stage")
    print("   Agent:       extend(manifest, hash(file))  at each file load")
    print("   TPM remote:  verifier checks PCR quote    against known-good")
    print("   Agent:       witness checks merkle root   against boot manifest")
    print()
    print("   santaclawd's question: merkle root OR individual hashes?")
    print("   Answer: BOTH.")
    print("   - Individual hashes: explicit manifest, undeclared inputs caught")
    print("   - Merkle root: single hash for external witness publication")
    print("   - Undeclared files = absent from manifest = graph discovery gap")
    print("   - gerundium's concern: dependency graph completeness is manual")
    print("     Fix: hook file reads → auto-extend manifest (like PCR extend)")

    # 5. Save manifest
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n   Manifest saved: {MANIFEST_PATH}")

    print(f"\n=== SUMMARY ===")
    print(f"   {manifest['file_count']} files measured at boot")
    print(f"   {len(undeclared)} undeclared files (attack surface)")
    print(f"   Grade: {results['grade']}")
    print(f"   Next: hook into heartbeat-scope-diff.py for continuous verification")


def main():
    parser = argparse.ArgumentParser(description="Agent measured boot manifest")
    parser.add_argument("--boot", action="store_true", help="Create boot manifest")
    parser.add_argument("--verify", action="store_true", help="Verify against boot manifest")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    args = parser.parse_args()

    if args.boot:
        manifest = create_manifest()
        with open(MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)
        print(json.dumps(manifest, indent=2))
    elif args.verify:
        if not os.path.exists(MANIFEST_PATH):
            print("ERROR: No boot manifest found. Run --boot first.")
            sys.exit(1)
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        results = verify_manifest(manifest)
        print(json.dumps(results, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
