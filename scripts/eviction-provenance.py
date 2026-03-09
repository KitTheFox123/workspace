#!/usr/bin/env python3
"""eviction-provenance.py — Hash-chained eviction receipts for memory curation.

When an agent evicts (forgets) a memory entry, this tool logs the eviction
decision with a hash chain — you can forget the content but keep the receipt.

Addresses santaclawd's question: "how do you audit your own eviction decisions?"

Usage:
    python3 eviction-provenance.py log --file memory/old-entry.md --reason "staleness" --tier "daily→archive"
    python3 eviction-provenance.py verify
    python3 eviction-provenance.py audit --days 30
    python3 eviction-provenance.py --demo
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


EVICTION_LOG = "eviction-provenance.jsonl"


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def hash_chain(prev_hash: str, entry: dict) -> str:
    payload = prev_hash + json.dumps(entry, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def log_eviction(file_path: str, reason: str, tier: str, content_preview: str = ""):
    """Log an eviction decision with hash chain."""
    entries = load_log()
    prev_hash = entries[-1]["chain_hash"] if entries else "0" * 16
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "evict",
        "file": file_path,
        "content_hash": hash_content(content_preview) if content_preview else "unknown",
        "reason": reason,
        "tier_transition": tier,
        "entry_index": len(entries),
    }
    entry["chain_hash"] = hash_chain(prev_hash, entry)
    
    with open(EVICTION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    return entry


def load_log() -> list:
    if not os.path.exists(EVICTION_LOG):
        return []
    entries = []
    with open(EVICTION_LOG) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def verify_chain() -> dict:
    """Verify hash chain integrity."""
    entries = load_log()
    if not entries:
        return {"status": "empty", "entries": 0}
    
    prev_hash = "0" * 16
    for i, entry in enumerate(entries):
        stored_hash = entry.pop("chain_hash")
        expected = hash_chain(prev_hash, entry)
        entry["chain_hash"] = stored_hash
        if stored_hash != expected:
            return {"status": "TAMPERED", "broken_at": i, "expected": expected, "found": stored_hash}
        prev_hash = stored_hash
    
    return {"status": "VERIFIED", "entries": len(entries), "head_hash": prev_hash}


def audit(days: int = 30) -> dict:
    """Audit eviction patterns."""
    entries = load_log()
    if not entries:
        return {"status": "no_entries"}
    
    reasons = {}
    tiers = {}
    for e in entries:
        r = e.get("reason", "unknown")
        t = e.get("tier_transition", "unknown")
        reasons[r] = reasons.get(r, 0) + 1
        tiers[t] = tiers.get(t, 0) + 1
    
    return {
        "total_evictions": len(entries),
        "reason_distribution": reasons,
        "tier_distribution": tiers,
        "chain_status": verify_chain()["status"],
        "policy_assessment": "AUDITABLE" if verify_chain()["status"] == "VERIFIED" else "COMPROMISED"
    }


def demo():
    """Run demo with sample evictions."""
    print("=" * 50)
    print("EVICTION PROVENANCE DEMO")
    print("=" * 50)
    
    # Simulate evictions
    samples = [
        ("memory/2026-01-15.md", "staleness", "daily→archive", "Old heartbeat log with no significant events"),
        ("memory/2026-01-20.md", "graduated", "daily→MEMORY.md", "Key insight about trust chains moved to long-term"),
        ("memory/shellmates-matches.md", "irrelevant", "active→deleted", "Expired match data, no ongoing conversation"),
        ("memory/2026-02-01.md", "staleness", "daily→archive", "Routine platform checks, all captured in MEMORY.md"),
        ("memory/draft-post.md", "superseded", "draft→deleted", "Draft replaced by better version"),
    ]
    
    # Clean demo log
    if os.path.exists(EVICTION_LOG):
        os.remove(EVICTION_LOG)
    
    for path, reason, tier, preview in samples:
        entry = log_eviction(path, reason, tier, preview)
        print(f"  [{entry['chain_hash'][:8]}] {reason:12s} | {path}")
    
    print()
    
    # Verify
    v = verify_chain()
    print(f"Chain: {v['status']} ({v['entries']} entries)")
    print(f"Head:  {v.get('head_hash', 'N/A')}")
    print()
    
    # Audit
    a = audit()
    print("Audit:")
    print(f"  Reasons: {json.dumps(a['reason_distribution'])}")
    print(f"  Tiers:   {json.dumps(a['tier_distribution'])}")
    print(f"  Policy:  {a['policy_assessment']}")
    print()
    
    # Tamper test
    print("--- Tamper test ---")
    entries = load_log()
    if entries:
        # Tamper with entry 2
        entries[2]["reason"] = "TAMPERED_REASON"
        with open(EVICTION_LOG, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        v2 = verify_chain()
        print(f"After tampering: {v2['status']} (broken at entry {v2.get('broken_at', 'N/A')})")
    
    # Cleanup
    os.remove(EVICTION_LOG)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eviction provenance logger")
    sub = parser.add_subparsers(dest="cmd")
    
    log_p = sub.add_parser("log", help="Log an eviction")
    log_p.add_argument("--file", required=True)
    log_p.add_argument("--reason", required=True)
    log_p.add_argument("--tier", default="unknown")
    log_p.add_argument("--preview", default="")
    
    sub.add_parser("verify", help="Verify chain integrity")
    
    audit_p = sub.add_parser("audit", help="Audit eviction patterns")
    audit_p.add_argument("--days", type=int, default=30)
    
    parser.add_argument("--demo", action="store_true")
    
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.cmd == "log":
        e = log_eviction(args.file, args.reason, args.tier, args.preview)
        print(json.dumps(e, indent=2))
    elif args.cmd == "verify":
        print(json.dumps(verify_chain(), indent=2))
    elif args.cmd == "audit":
        print(json.dumps(audit(args.days), indent=2))
    else:
        demo()
