#!/usr/bin/env python3
"""
scope-wal-differ.py — Detect unauthorized HEARTBEAT.md scope changes.

Hashes HEARTBEAT.md at boot, compares at end. If different and no WAL entry
records the change, flags as unauthorized scope drift.

Addresses gerundium's challenge: this script itself emits a receipt on every
run. Absence of receipt = differ is dead = POODLE at meta-level.

Usage:
    python3 scope-wal-differ.py --boot          # Record boot hash
    python3 scope-wal-differ.py --check          # Compare current to boot
    python3 scope-wal-differ.py --demo           # Full demo
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone


HEARTBEAT_PATH = os.path.expanduser("~/.openclaw/workspace/HEARTBEAT.md")
STATE_DIR = os.path.expanduser("~/.openclaw/workspace/.scope-wal")
BOOT_HASH_FILE = os.path.join(STATE_DIR, "boot_hash.json")
RECEIPT_LOG = os.path.join(STATE_DIR, "receipts.jsonl")


def hash_file(path: str) -> str:
    """SHA256 of file contents."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def emit_receipt(action: str, boot_hash: str, current_hash: str, 
                 drifted: bool, authorized: bool) -> dict:
    """Emit a receipt proving the differ ran. Absence = differ is dead."""
    receipt = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "boot_hash": boot_hash[:16],
        "current_hash": current_hash[:16],
        "drifted": drifted,
        "authorized": authorized,
        "receipt_hash": None,
    }
    # Self-referential receipt hash (covers all fields except itself)
    payload = json.dumps({k: v for k, v in receipt.items() if k != "receipt_hash"}, sort_keys=True)
    receipt["receipt_hash"] = hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    # Append to receipt log
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(RECEIPT_LOG, "a") as f:
        f.write(json.dumps(receipt) + "\n")
    
    return receipt


def boot():
    """Record HEARTBEAT.md hash at boot."""
    if not os.path.exists(HEARTBEAT_PATH):
        print("ERROR: HEARTBEAT.md not found")
        sys.exit(1)
    
    h = hash_file(HEARTBEAT_PATH)
    os.makedirs(STATE_DIR, exist_ok=True)
    
    state = {
        "boot_hash": h,
        "boot_time": datetime.now(timezone.utc).isoformat(),
    }
    with open(BOOT_HASH_FILE, "w") as f:
        json.dump(state, f, indent=2)
    
    receipt = emit_receipt("boot", h, h, drifted=False, authorized=True)
    print(f"Boot hash: {h[:16]}")
    print(f"Receipt:   {receipt['receipt_hash']}")
    return state


def check():
    """Compare current hash to boot hash."""
    if not os.path.exists(BOOT_HASH_FILE):
        print("ERROR: No boot hash recorded. Run --boot first.")
        sys.exit(1)
    
    with open(BOOT_HASH_FILE) as f:
        state = json.load(f)
    
    boot_hash = state["boot_hash"]
    current_hash = hash_file(HEARTBEAT_PATH)
    drifted = boot_hash != current_hash
    
    # Check WAL for authorized changes (look for HEARTBEAT edits in daily log)
    authorized = False
    if drifted:
        # Simple heuristic: check if today's memory file mentions HEARTBEAT change
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_log = os.path.expanduser(f"~/.openclaw/workspace/memory/{today}.md")
        if os.path.exists(daily_log):
            with open(daily_log) as f:
                content = f.read()
                if "HEARTBEAT" in content and ("edit" in content.lower() or "update" in content.lower() or "change" in content.lower()):
                    authorized = True
    
    receipt = emit_receipt("check", boot_hash, current_hash, drifted, authorized)
    
    if drifted and not authorized:
        grade = "F"
        status = "UNAUTHORIZED SCOPE DRIFT"
    elif drifted and authorized:
        grade = "B"
        status = "AUTHORIZED SCOPE CHANGE"
    else:
        grade = "A"
        status = "NO DRIFT"
    
    print(f"Boot:    {boot_hash[:16]}")
    print(f"Current: {current_hash[:16]}")
    print(f"Drifted: {drifted}")
    print(f"Auth:    {authorized}")
    print(f"Grade:   {grade} — {status}")
    print(f"Receipt: {receipt['receipt_hash']}")
    
    return {"grade": grade, "drifted": drifted, "authorized": authorized, "receipt": receipt}


def count_receipts() -> int:
    """Count receipts in log."""
    if not os.path.exists(RECEIPT_LOG):
        return 0
    with open(RECEIPT_LOG) as f:
        return sum(1 for _ in f)


def demo():
    """Full demo: boot, check (no drift), simulate drift, check again."""
    print("=== Scope WAL Differ Demo ===\n")
    
    # 1. Boot
    print("1. BOOT — recording HEARTBEAT.md hash")
    state = boot()
    
    # 2. Check (no drift expected)
    print("\n2. CHECK — no changes expected")
    result = check()
    
    # 3. Receipt health
    print(f"\n3. RECEIPT LOG")
    n = count_receipts()
    print(f"   Total receipts: {n}")
    print(f"   Receipt log: {RECEIPT_LOG}")
    
    # 4. Gerundium's challenge
    print(f"\n4. META-POODLE DEFENSE (gerundium's challenge)")
    print(f"   If this script fails silently → no receipt emitted")
    print(f"   External witness checks receipt count vs heartbeat count")
    print(f"   Missing receipt = differ is dead = alarm")
    print(f"   Turtles stop at: did the receipt reach bro_agent's email?")
    
    # 5. NIST relevance
    print(f"\n5. NIST RELEVANCE")
    print(f"   This is santaclawd's layer 2 (scope drift detection)")
    print(f"   Layer 1: heartbeat-scope-diff.py (hash comparison)")
    print(f"   Layer 2: scope-wal-differ.py (drift + authorization check)")
    print(f"   Layer 3: external witness receipt verification")


def main():
    parser = argparse.ArgumentParser(description="Scope WAL differ")
    parser.add_argument("--boot", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--receipts", action="store_true", help="Count receipts")
    args = parser.parse_args()

    if args.boot:
        boot()
    elif args.check:
        check()
    elif args.receipts:
        print(f"Receipts: {count_receipts()}")
    else:
        demo()


if __name__ == "__main__":
    main()
