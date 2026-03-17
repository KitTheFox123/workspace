#!/usr/bin/env python3
"""provenance-logger.py — Append-only JSONL provenance log for agent actions.

Inspired by gerundium's JSONL provenance approach: each line = one decision.
Logs the WHAT (action) and WHY (reasoning) for auditability.

Usage:
    python3 provenance-logger.py log --action "clawk_reply" --target "funwolf" --reason "threading on brume concept"
    python3 provenance-logger.py log --action "attestation" --target "gendolf" --reason "sandbox test"
    python3 provenance-logger.py query --action clawk_reply --last 5
    python3 provenance-logger.py stats
"""

import argparse
import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path(__file__).parent.parent / "memory" / "provenance.jsonl"


def compute_hash(entry: dict) -> str:
    """SHA-256 of canonical JSON for chain linking."""
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()[:16]


def get_last_hash() -> str | None:
    """Get hash of last entry for chain linking."""
    if not LOG_FILE.exists():
        return None
    last = None
    for line in LOG_FILE.open():
        line = line.strip()
        if line:
            last = line
    if last:
        try:
            entry = json.loads(last)
            return entry.get("hash")
        except json.JSONDecodeError:
            return None
    return None


def log_termination(agent_id: str, reason_code: str, successor_chain: str | None = None):
    """Log a chain termination record (santaclawd's gap 4).
    
    Different from null nodes: null = considered-and-declined (ongoing).
    Termination = deliberate chain close. Final receipt in the chain.
    """
    extra = {
        "termination": True,
        "agent_id": agent_id,
        "reason_code": reason_code,
        "revocation_status": "terminated",
    }
    if successor_chain:
        extra["successor_chain_id"] = successor_chain
    
    entry = log_action(
        action="chain_termination",
        target=None,
        reason=f"Chain terminated: {reason_code}",
        platform=None,
        extra=extra,
    )
    # The final_hash IS this entry's hash — it seals the chain
    print(f"  ⛓️  Chain sealed. Final hash: {entry.get('hash', '?')}")
    if successor_chain:
        print(f"  → Successor: {successor_chain}")
    return entry


def log_null(action: str, target: str | None = None, reason: str | None = None,
             platform: str | None = None):
    """Log a null node — action CONSIDERED but NOT taken.
    
    santaclawd's insight: 'null nodes = the diff. if you cannot answer what
    the agent CONSIDERED and declined, you have a press release, not an audit.'
    """
    return log_action(
        action=f"null:{action}",
        target=target,
        reason=reason,
        platform=platform,
        extra={"null_node": True, "considered_at": datetime.now(timezone.utc).isoformat()},
    )


def classify_entry_type(action: str) -> str:
    """MEMORY-CHAIN v0.1: classify action into entry_type.
    
    Per funwolf (2026-03-17): observation|decision|relationship
    Three values. Proves what KIND of memory this is.
    """
    if action.startswith("null:"):
        return "decision"  # considered-and-declined is a decision
    if action in ("chain_termination", "attestation", "slash"):
        return "decision"
    if action in ("follow", "dm", "shellmates_swipe", "welcome"):
        return "relationship"
    # Default: observation (posts, comments, searches, builds)
    return "observation"


def log_action(action: str, target: str | None, reason: str | None, 
               platform: str | None, extra: dict | None = None):
    """Append a provenance entry. MEMORY-CHAIN v0.1 compatible."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "entry_type": classify_entry_type(action),  # MEMORY-CHAIN v0.1
    }
    if target:
        entry["target"] = target
    if reason:
        entry["reason"] = reason
    if platform:
        entry["platform"] = platform
    if extra:
        entry.update(extra)

    # Chain link
    prev = get_last_hash()
    if prev:
        entry["prev_hash"] = prev

    entry["hash"] = compute_hash(entry)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")

    print(f"✓ Logged: {action} → {target or '-'} [{entry['hash']}]")
    return entry


def query_log(action: str | None = None, target: str | None = None,
              last: int = 10):
    """Query provenance log with filters."""
    if not LOG_FILE.exists():
        print("No provenance log yet.")
        return

    entries = []
    for line in LOG_FILE.open():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            if action and e.get("action") != action:
                continue
            if target and e.get("target") != target:
                continue
            entries.append(e)
        except json.JSONDecodeError:
            continue

    for e in entries[-last:]:
        ts = e.get("timestamp", "?")[:19]
        act = e.get("action", "?")
        tgt = e.get("target", "-")
        reason = e.get("reason", "")[:60]
        h = e.get("hash", "?")[:8]
        print(f"  [{ts}] {act:20s} → {tgt:15s} {reason}  ({h})")

    print(f"\n{len(entries)} entries matched (showing last {last})")


def show_stats():
    """Show provenance statistics."""
    if not LOG_FILE.exists():
        print("No provenance log yet.")
        return

    from collections import Counter
    actions = Counter()
    targets = Counter()
    platforms = Counter()
    total = 0
    chain_valid = 0
    prev_hash = None

    for line in LOG_FILE.open():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            total += 1
            actions[e.get("action", "?")] += 1
            if e.get("target"):
                targets[e["target"]] += 1
            if e.get("platform"):
                platforms[e["platform"]] += 1

            # Chain integrity
            if prev_hash is None or e.get("prev_hash") == prev_hash:
                chain_valid += 1
            prev_hash = e.get("hash")
        except json.JSONDecodeError:
            continue

    print("═══ PROVENANCE STATS ═══")
    print(f"Total entries: {total}")
    print(f"Chain integrity: {chain_valid}/{total} ({chain_valid/total*100:.0f}%)" if total else "")
    print(f"\nActions:")
    for act, count in actions.most_common(10):
        print(f"  {act:25s} {count:>4}")
    print(f"\nTop targets:")
    for tgt, count in targets.most_common(10):
        print(f"  {tgt:25s} {count:>4}")
    if platforms:
        print(f"\nPlatforms:")
        for plat, count in platforms.most_common():
            print(f"  {plat:25s} {count:>4}")
    print("═" * 24)


def main():
    parser = argparse.ArgumentParser(description="Append-only provenance logger")
    sub = parser.add_subparsers(dest="cmd")

    log_p = sub.add_parser("log", help="Log an action")
    log_p.add_argument("--action", required=True)
    log_p.add_argument("--target")
    log_p.add_argument("--reason")
    log_p.add_argument("--platform")

    null_p = sub.add_parser("null", help="Log a null node (considered but not taken)")
    null_p.add_argument("--action", required=True)
    null_p.add_argument("--target")
    null_p.add_argument("--reason")
    null_p.add_argument("--platform")

    term_p = sub.add_parser("terminate", help="Seal the chain (gap 4: offboarding receipt)")
    term_p.add_argument("--agent-id", required=True)
    term_p.add_argument("--reason-code", required=True, choices=["migration", "decommission", "compromise", "operator_request", "voluntary"])
    term_p.add_argument("--successor-chain")

    query_p = sub.add_parser("query", help="Query log")
    query_p.add_argument("--action")
    query_p.add_argument("--target")
    query_p.add_argument("--last", type=int, default=10)

    sub.add_parser("stats", help="Show statistics")
    sub.add_parser("verify", help="Verify chain integrity")

    args = parser.parse_args()

    if args.cmd == "log":
        log_action(args.action, args.target, args.reason, args.platform)
    elif args.cmd == "null":
        log_null(args.action, args.target, args.reason, args.platform)
    elif args.cmd == "terminate":
        log_termination(args.agent_id, args.reason_code, args.successor_chain)
    elif args.cmd == "query":
        query_log(args.action, args.target, args.last)
    elif args.cmd == "stats":
        show_stats()
    elif args.cmd == "verify":
        # Quick chain verification
        if not LOG_FILE.exists():
            print("No log.")
            return
        total = broken = 0
        prev_hash = None
        for line in LOG_FILE.open():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                total += 1
                if prev_hash and e.get("prev_hash") != prev_hash:
                    broken += 1
                    print(f"  ⚠️  Chain break at entry {total}: expected {prev_hash}, got {e.get('prev_hash')}")
                prev_hash = e.get("hash")
            except json.JSONDecodeError:
                broken += 1
        print(f"Verified {total} entries: {broken} breaks")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
