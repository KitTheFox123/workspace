#!/usr/bin/env python3
"""
scope-log.py — Append-only scope log with Merkle verification.

CT-inspired: each heartbeat = a leaf. The log is append-only,
and any consumer can verify consistency by recomputing the tree.

Usage:
    python scope-log.py append --scope "HEARTBEAT.md actions" --agent kit_fox
    python scope-log.py verify
    python scope-log.py show [--last N]
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path.home() / ".openclaw" / "workspace" / "data" / "scope-logs"
LOG_FILE = LOG_DIR / "scope-log.jsonl"


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def merkle_parent(left: str, right: str) -> str:
    return sha256(left + right)


def compute_merkle_root(hashes: list[str]) -> str:
    """Compute Merkle root from list of leaf hashes."""
    if not hashes:
        return sha256("")
    level = list(hashes)
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                next_level.append(merkle_parent(level[i], level[i + 1]))
            else:
                next_level.append(level[i])  # odd node promoted
        level = next_level
    return level[0]


def load_entries() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    entries = []
    with open(LOG_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def append_entry(agent: str, scope: str, metadata: dict | None = None):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    entries = load_entries()
    prev_hash = entries[-1]["hash"] if entries else sha256("genesis")
    
    entry = {
        "seq": len(entries),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "scope": scope,
        "prev_hash": prev_hash,
    }
    if metadata:
        entry["metadata"] = metadata
    
    # Hash = H(seq || timestamp || agent || scope || prev_hash)
    payload = f"{entry['seq']}|{entry['timestamp']}|{entry['agent']}|{entry['scope']}|{entry['prev_hash']}"
    entry["hash"] = sha256(payload)
    
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    print(f"✅ Appended entry #{entry['seq']} hash={entry['hash'][:16]}...")
    return entry


def verify_log():
    entries = load_entries()
    if not entries:
        print("📭 Empty log, nothing to verify.")
        return True
    
    errors = 0
    expected_prev = sha256("genesis")
    
    for i, entry in enumerate(entries):
        # Check chain link
        if entry["prev_hash"] != expected_prev:
            print(f"❌ Entry #{i}: prev_hash mismatch (expected {expected_prev[:16]}, got {entry['prev_hash'][:16]})")
            errors += 1
        
        # Recompute hash
        payload = f"{entry['seq']}|{entry['timestamp']}|{entry['agent']}|{entry['scope']}|{entry['prev_hash']}"
        recomputed = sha256(payload)
        if entry["hash"] != recomputed:
            print(f"❌ Entry #{i}: hash mismatch (expected {recomputed[:16]}, got {entry['hash'][:16]})")
            errors += 1
        
        expected_prev = entry["hash"]
    
    # Compute Merkle root
    leaf_hashes = [e["hash"] for e in entries]
    root = compute_merkle_root(leaf_hashes)
    
    if errors == 0:
        print(f"✅ Log verified: {len(entries)} entries, 0 errors")
        print(f"🌳 Merkle root: {root[:32]}...")
    else:
        print(f"⚠️  Log has {errors} error(s) across {len(entries)} entries")
    
    return errors == 0


def show_log(last_n: int | None = None):
    entries = load_entries()
    if not entries:
        print("📭 Empty log.")
        return
    
    if last_n:
        entries = entries[-last_n:]
    
    for e in entries:
        ts = e["timestamp"][:19].replace("T", " ")
        print(f"  #{e['seq']:>4}  {ts}  {e['agent']:>12}  {e['hash'][:12]}  {e['scope'][:60]}")
    
    leaf_hashes = [e["hash"] for e in load_entries()]
    root = compute_merkle_root(leaf_hashes)
    print(f"\n  Total: {len(load_entries())} entries | Merkle root: {root[:24]}...")


def main():
    parser = argparse.ArgumentParser(description="Append-only scope log with Merkle verification")
    sub = parser.add_subparsers(dest="command")
    
    ap = sub.add_parser("append", help="Append a scope entry")
    ap.add_argument("--agent", required=True)
    ap.add_argument("--scope", required=True)
    ap.add_argument("--meta", help="JSON metadata string")
    
    sub.add_parser("verify", help="Verify log integrity")
    
    sp = sub.add_parser("show", help="Show log entries")
    sp.add_argument("--last", type=int, help="Show only last N entries")
    
    args = parser.parse_args()
    
    if args.command == "append":
        meta = json.loads(args.meta) if hasattr(args, "meta") and args.meta else None
        append_entry(args.agent, args.scope, meta)
    elif args.command == "verify":
        ok = verify_log()
        sys.exit(0 if ok else 1)
    elif args.command == "show":
        show_log(args.last if hasattr(args, "last") else None)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
