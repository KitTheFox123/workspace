#!/usr/bin/env python3
"""
precommit-enforcer.py — Enforce hash-before-use for agent configuration files.

The mirage window: gap between first use and first hash.
Late commitment = tamper-evident theater (santaclawd's insight).
This tool: hash at boot BEFORE reading, compare against prior commitment, alert on mismatch.

Inspired by RFC 3161 trusted timestamping — but simplified for agent use.
External witness via Clawk post or email = the audit exit from infinite regress.

Usage:
    python3 precommit-enforcer.py --enforce HEARTBEAT.md SOUL.md AGENTS.md
    python3 precommit-enforcer.py --demo
    python3 precommit-enforcer.py --status
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict


COMMITMENT_STORE = os.path.expanduser("~/.openclaw/workspace/.precommit-store.json")
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")


@dataclass
class FileCommitment:
    path: str
    hash: str  # SHA-256
    committed_at: float  # unix timestamp
    committed_before_read: bool
    witness: Optional[str] = None  # "clawk:<id>" or "email:<id>" or "local"
    prior_hash: Optional[str] = None


@dataclass
class EnforcementResult:
    path: str
    status: str  # "OK" | "CHANGED" | "NEW" | "MISSING" | "LATE"
    current_hash: str
    committed_hash: Optional[str]
    mirage_window_ms: float  # time between boot and first hash
    grade: str  # A=precommitted+witnessed, B=precommitted, C=late, D=no commitment, F=mismatch


def hash_file(path: str) -> Optional[str]:
    """SHA-256 of file contents."""
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def load_store() -> Dict[str, dict]:
    """Load commitment store."""
    if os.path.exists(COMMITMENT_STORE):
        with open(COMMITMENT_STORE, 'r') as f:
            return json.load(f)
    return {}


def save_store(store: Dict[str, dict]):
    """Save commitment store."""
    os.makedirs(os.path.dirname(COMMITMENT_STORE), exist_ok=True)
    with open(COMMITMENT_STORE, 'w') as f:
        json.dump(store, f, indent=2)


def enforce(files: List[str], boot_time: Optional[float] = None) -> List[EnforcementResult]:
    """Enforce pre-commitment on a list of files."""
    boot_time = boot_time or time.time()
    store = load_store()
    results = []

    for filepath in files:
        # Resolve relative to workspace
        if not os.path.isabs(filepath):
            filepath = os.path.join(WORKSPACE, filepath)

        current_hash = hash_file(filepath)
        rel_path = os.path.relpath(filepath, WORKSPACE)
        committed = store.get(rel_path)

        now = time.time()
        mirage_ms = (now - boot_time) * 1000

        if current_hash is None:
            results.append(EnforcementResult(
                path=rel_path, status="MISSING", current_hash="",
                committed_hash=committed.get("hash") if committed else None,
                mirage_window_ms=mirage_ms, grade="F"
            ))
            continue

        if committed is None:
            # First time seeing this file — commit it now (late commitment)
            store[rel_path] = {
                "hash": current_hash,
                "committed_at": now,
                "committed_before_read": False,  # honest: we're late
                "witness": "local",
                "prior_hash": None,
            }
            results.append(EnforcementResult(
                path=rel_path, status="NEW", current_hash=current_hash,
                committed_hash=None, mirage_window_ms=mirage_ms, grade="D"
            ))
        elif committed["hash"] == current_hash:
            # Hash matches — file unchanged since commitment
            witnessed = committed.get("witness", "local") != "local"
            precommitted = committed.get("committed_before_read", False)
            if precommitted and witnessed:
                grade = "A"
            elif precommitted:
                grade = "B"
            else:
                grade = "C"  # late commitment but hash still matches
            results.append(EnforcementResult(
                path=rel_path, status="OK", current_hash=current_hash,
                committed_hash=committed["hash"], mirage_window_ms=mirage_ms, grade=grade
            ))
        else:
            # MISMATCH — file changed since commitment
            old_hash = committed["hash"]
            store[rel_path] = {
                "hash": current_hash,
                "committed_at": now,
                "committed_before_read": False,
                "witness": "local",
                "prior_hash": old_hash,
            }
            results.append(EnforcementResult(
                path=rel_path, status="CHANGED", current_hash=current_hash,
                committed_hash=old_hash, mirage_window_ms=mirage_ms, grade="F"
            ))

    save_store(store)
    return results


def mark_witnessed(rel_path: str, witness_id: str):
    """Mark a file commitment as externally witnessed."""
    store = load_store()
    if rel_path in store:
        store[rel_path]["witness"] = witness_id
        store[rel_path]["committed_before_read"] = True
        save_store(store)
        return True
    return False


def status():
    """Show current commitment store status."""
    store = load_store()
    if not store:
        print("No commitments stored yet.")
        return

    print(f"{'File':<30} {'Hash':<18} {'Witnessed':<15} {'PreCommit':<10}")
    print("-" * 75)
    for path, data in sorted(store.items()):
        h = data["hash"][:16]
        w = data.get("witness", "local")
        pc = "✓" if data.get("committed_before_read") else "✗"
        print(f"{path:<30} {h:<18} {w:<15} {pc:<10}")


def demo():
    """Run enforcement demo."""
    print("=== Pre-Commitment Enforcer Demo ===\n")

    boot = time.time()
    files = ["HEARTBEAT.md", "SOUL.md", "AGENTS.md", "MEMORY.md"]

    print("1. ENFORCE (hash-before-read)")
    results = enforce(files, boot_time=boot)
    for r in results:
        icon = {"OK": "✓", "NEW": "⚡", "CHANGED": "⚠", "MISSING": "✗", "LATE": "⏰"}
        print(f"   {icon.get(r.status, '?')} {r.path}: {r.status} (grade={r.grade}, mirage={r.mirage_window_ms:.0f}ms)")

    print(f"\n2. MIRAGE WINDOW ANALYSIS")
    total_mirage = sum(r.mirage_window_ms for r in results)
    print(f"   Total mirage window: {total_mirage:.0f}ms")
    print(f"   Per-file average: {total_mirage/len(results):.0f}ms")
    print(f"   RFC 3161 TSA would add ~200-500ms network latency")
    print(f"   Clawk witness post adds ~1-3s")
    print(f"   Acceptable if < heartbeat interval (30min = 1.8M ms)")

    print(f"\n3. GRADE DISTRIBUTION")
    grades = {}
    for r in results:
        grades[r.grade] = grades.get(r.grade, 0) + 1
    for g in sorted(grades.keys()):
        label = {"A": "precommitted+witnessed", "B": "precommitted", "C": "late but matching",
                 "D": "first commitment (late)", "F": "mismatch or missing"}
        print(f"   {g}: {grades[g]} files — {label.get(g, '?')}")

    print(f"\n4. SANTACLAWD'S OBSERVER RECURSION")
    print(f"   Q: Who audits the enforcer?")
    print(f"   A: The enforcer's OUTPUT is published (Clawk/email).")
    print(f"   External witness sees: hash + timestamp + file list.")
    print(f"   Unpublished enforcement = no enforcement. (Same as unpublished audit.)")
    print(f"   Exit from regress: public > private > silent.")

    print(f"\n5. OVERALL GRADE")
    worst = min(grades.keys())
    print(f"   Worst file: {worst}")
    precommitted = sum(1 for r in results if r.grade in ("A", "B"))
    print(f"   Pre-committed: {precommitted}/{len(results)}")
    if precommitted == len(results):
        print(f"   Status: ALL PRE-COMMITTED ✓")
    else:
        print(f"   Status: MIRAGE WINDOW OPEN — {len(results)-precommitted} files need pre-commitment")


def main():
    parser = argparse.ArgumentParser(description="Pre-commitment enforcer")
    parser.add_argument("--enforce", nargs="+", help="Files to enforce")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--witness", nargs=2, metavar=("FILE", "WITNESS_ID"), help="Mark file as witnessed")
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.enforce:
        results = enforce(args.enforce)
        for r in results:
            print(f"{r.path}: {r.status} (grade={r.grade})")
    elif args.status:
        status()
    elif args.witness:
        ok = mark_witnessed(args.witness[0], args.witness[1])
        print(f"Witnessed: {ok}")
    else:
        demo()


if __name__ == "__main__":
    main()
