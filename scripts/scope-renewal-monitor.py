#!/usr/bin/env python3
"""scope-renewal-monitor.py — Monitor agent scope freshness.

Tracks scope documents (like HEARTBEAT.md) and alerts when they haven't
been renewed within their TTL. Implements the "renew-or-die" pattern
from CT/Let's Encrypt applied to agent delegation.

Usage:
    python3 scope-renewal-monitor.py <scope_file> [--ttl-minutes 60]
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path.home() / ".openclaw/workspace/memory/scope-renewal-state.json"


def hash_file(path: str) -> str:
    """SHA-256 of file contents."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"scopes": {}}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def check_scope(path: str, ttl_minutes: int) -> dict:
    """Check if scope file has been renewed within TTL."""
    state = load_state()
    now = datetime.now(timezone.utc)
    current_hash = hash_file(path)

    scope_key = os.path.abspath(path)
    prev = state["scopes"].get(scope_key, {})

    result = {
        "file": path,
        "current_hash": current_hash[:16],
        "checked_at": now.isoformat(),
        "ttl_minutes": ttl_minutes,
    }

    if not prev:
        # First observation
        result["status"] = "NEW"
        result["message"] = "First observation of scope file"
        state["scopes"][scope_key] = {
            "hash": current_hash,
            "first_seen": now.isoformat(),
            "last_changed": now.isoformat(),
            "last_checked": now.isoformat(),
            "renewals": 0,
        }
    else:
        last_changed = datetime.fromisoformat(prev["last_changed"])
        age_minutes = (now - last_changed).total_seconds() / 60

        if current_hash != prev["hash"]:
            # Renewed!
            result["status"] = "RENEWED"
            result["age_minutes"] = round(age_minutes, 1)
            result["message"] = f"Scope renewed after {age_minutes:.0f}min"
            prev["hash"] = current_hash
            prev["last_changed"] = now.isoformat()
            prev["renewals"] = prev.get("renewals", 0) + 1
        elif age_minutes > ttl_minutes:
            # Expired!
            result["status"] = "EXPIRED"
            result["age_minutes"] = round(age_minutes, 1)
            result["overdue_minutes"] = round(age_minutes - ttl_minutes, 1)
            result["message"] = f"SCOPE EXPIRED: unchanged for {age_minutes:.0f}min (TTL={ttl_minutes}min)"
        else:
            # Still valid
            result["status"] = "VALID"
            result["age_minutes"] = round(age_minutes, 1)
            result["remaining_minutes"] = round(ttl_minutes - age_minutes, 1)
            result["message"] = f"Valid: {ttl_minutes - age_minutes:.0f}min remaining"

        prev["last_checked"] = now.isoformat()
        result["total_renewals"] = prev.get("renewals", 0)

    save_state(state)
    return result


def main():
    parser = argparse.ArgumentParser(description="Monitor agent scope freshness")
    parser.add_argument("scope_file", help="Path to scope file (e.g. HEARTBEAT.md)")
    parser.add_argument("--ttl-minutes", type=int, default=60, help="Max minutes before scope expires")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not os.path.exists(args.scope_file):
        print(f"ERROR: {args.scope_file} not found", file=sys.stderr)
        sys.exit(1)

    result = check_scope(args.scope_file, args.ttl_minutes)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result["status"]
        emoji = {"NEW": "🆕", "RENEWED": "🔄", "VALID": "✅", "EXPIRED": "🚨"}.get(status, "❓")
        print(f"{emoji} [{status}] {result['message']}")
        if "remaining_minutes" in result:
            print(f"   Next renewal needed in {result['remaining_minutes']:.0f}min")
        if "total_renewals" in result:
            print(f"   Total renewals observed: {result['total_renewals']}")


if __name__ == "__main__":
    main()
