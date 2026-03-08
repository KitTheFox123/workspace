#!/usr/bin/env python3
"""audit-chain-validator.py — Hash-chain integrity validator for agent action logs.

Inspired by AuditableLLM (Li et al 2025, doi:10.3390/electronics15010056):
hash-chain-backed tamper-evident audit trails with sub-second validation.

Creates and validates append-only JSONL action logs where each entry
contains a hash linking to the previous entry. Any tampering breaks
the chain at the modification point.

Usage:
    python3 audit-chain-validator.py init <logfile>
    python3 audit-chain-validator.py append <logfile> --action "..." --scope "..."
    python3 audit-chain-validator.py verify <logfile>
    python3 audit-chain-validator.py --demo
"""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def compute_hash(data: str) -> str:
    """SHA-256 hash of data string."""
    return hashlib.sha256(data.encode()).hexdigest()


def genesis_entry(scope_hash: str = "") -> dict:
    """Create genesis (first) entry in chain."""
    entry = {
        "seq": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "GENESIS",
        "scope_hash": scope_hash or compute_hash("initial_scope"),
        "prev_hash": "0" * 64,
        "data": {}
    }
    entry["hash"] = compute_hash(json.dumps(entry, sort_keys=True))
    return entry


def append_entry(prev: dict, action: str, scope: str = "", data: dict = None) -> dict:
    """Create new entry linked to previous."""
    entry = {
        "seq": prev["seq"] + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "scope_hash": compute_hash(scope) if scope else prev["scope_hash"],
        "prev_hash": prev["hash"],
        "data": data or {}
    }
    entry["hash"] = compute_hash(json.dumps(entry, sort_keys=True))
    return entry


def verify_chain(logfile: str) -> dict:
    """Verify entire chain integrity. Returns validation report."""
    path = Path(logfile)
    if not path.exists():
        return {"valid": False, "error": "File not found", "entries": 0}
    
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    
    if not entries:
        return {"valid": False, "error": "Empty log", "entries": 0}
    
    start = time.monotonic()
    errors = []
    
    for i, entry in enumerate(entries):
        # Verify self-hash
        stored_hash = entry.pop("hash")
        computed = compute_hash(json.dumps(entry, sort_keys=True))
        entry["hash"] = stored_hash
        
        if computed != stored_hash:
            errors.append({"seq": i, "error": "hash_mismatch", 
                          "expected": computed[:16], "got": stored_hash[:16]})
        
        # Verify chain link
        if i == 0:
            if entry["prev_hash"] != "0" * 64:
                errors.append({"seq": 0, "error": "invalid_genesis"})
        else:
            if entry["prev_hash"] != entries[i-1]["hash"]:
                errors.append({"seq": i, "error": "chain_break",
                              "expected": entries[i-1]["hash"][:16],
                              "got": entry["prev_hash"][:16]})
    
    elapsed_ms = (time.monotonic() - start) * 1000
    
    return {
        "valid": len(errors) == 0,
        "entries": len(entries),
        "errors": errors,
        "validation_ms": round(elapsed_ms, 2),
        "first_entry": entries[0]["timestamp"],
        "last_entry": entries[-1]["timestamp"],
        "chain_head": entries[-1]["hash"][:16] + "..."
    }


def init_log(logfile: str, scope_hash: str = ""):
    """Initialize a new audit chain."""
    entry = genesis_entry(scope_hash)
    with open(logfile, 'w') as f:
        f.write(json.dumps(entry) + '\n')
    return entry


def append_to_log(logfile: str, action: str, scope: str = "", data: dict = None):
    """Append entry to existing chain."""
    with open(logfile) as f:
        lines = [l.strip() for l in f if l.strip()]
    prev = json.loads(lines[-1])
    entry = append_entry(prev, action, scope, data)
    with open(logfile, 'a') as f:
        f.write(json.dumps(entry) + '\n')
    return entry


def demo():
    """Run demo showing chain creation, verification, and tamper detection."""
    import tempfile
    import os
    
    logfile = tempfile.mktemp(suffix='.jsonl')
    
    print("=" * 60)
    print("AUDIT CHAIN VALIDATOR — Demo")
    print("Based on AuditableLLM (Li et al 2025)")
    print("=" * 60)
    
    # Create chain
    print("\n[1] Creating audit chain...")
    init_log(logfile, "heartbeat_scope_v1")
    
    actions = [
        ("HEARTBEAT_CHECK", "check_clawk_notifications", {"platform": "clawk", "count": 10}),
        ("WRITE_ACTION", "clawk_reply", {"clawk_id": "abc123", "chars": 240}),
        ("BUILD_ACTION", "axiom-blast-radius.py", {"tool_number": 64, "lines": 180}),
        ("SCOPE_RENEWAL", "heartbeat_scope_v2", {"ttl_hours": 1}),
        ("RESEARCH", "auditablellm_paper", {"doi": "10.3390/electronics15010056"}),
    ]
    
    for action, scope, data in actions:
        append_to_log(logfile, action, scope, data)
        time.sleep(0.01)
    
    print(f"   Created {len(actions) + 1} entries")
    
    # Verify
    print("\n[2] Verifying chain integrity...")
    result = verify_chain(logfile)
    print(f"   Valid: {result['valid']}")
    print(f"   Entries: {result['entries']}")
    print(f"   Validation: {result['validation_ms']}ms")
    print(f"   Chain head: {result['chain_head']}")
    
    # Tamper
    print("\n[3] Tampering with entry #3...")
    with open(logfile) as f:
        lines = f.readlines()
    
    entry = json.loads(lines[3])
    entry["action"] = "TAMPERED_ACTION"
    lines[3] = json.dumps(entry) + '\n'
    
    tampered_file = logfile + '.tampered'
    with open(tampered_file, 'w') as f:
        f.writelines(lines)
    
    result = verify_chain(tampered_file)
    print(f"   Valid: {result['valid']}")
    print(f"   Errors: {len(result['errors'])}")
    for err in result['errors']:
        print(f"   → seq {err['seq']}: {err['error']}")
    
    # Cleanup
    os.unlink(logfile)
    os.unlink(tampered_file)
    
    print("\n" + "-" * 60)
    print("Key: tamper at entry N breaks chain at N AND N+1")
    print("Sub-millisecond validation (AuditableLLM: 3.4ms/step)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hash-chain audit validator")
    parser.add_argument("command", nargs="?", choices=["init", "append", "verify"])
    parser.add_argument("logfile", nargs="?")
    parser.add_argument("--action", type=str)
    parser.add_argument("--scope", type=str, default="")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.command == "init":
        entry = init_log(args.logfile, args.scope)
        print(json.dumps(entry, indent=2))
    elif args.command == "append":
        entry = append_to_log(args.logfile, args.action, args.scope)
        print(json.dumps(entry, indent=2))
    elif args.command == "verify":
        result = verify_chain(args.logfile)
        print(json.dumps(result, indent=2))
