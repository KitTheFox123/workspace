#!/usr/bin/env python3
"""
scope-expiry-monitor.py — Monitor agent scope certificates for TTL expiry.

Implements the CT-log-inspired model: each heartbeat is a leaf in an
append-only log. Missing N consecutive heartbeats = scope auto-expires.

Usage:
    python3 scope-expiry-monitor.py [--max-missed 3] [--heartbeat-interval 1200] [logfile]

Log format (JSONL):
    {"ts": "2026-03-06T17:00:00Z", "scope_hash": "sha256:...", "agent": "kit_fox"}

Checks:
1. Consecutive missed heartbeats (gap > interval * 1.5)
2. Scope hash drift (changed without re-issuance)
3. Total uptime vs expected beats
4. Generates a trust score: beats_present / beats_expected
"""

import json
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path


def parse_ts(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def load_log(path: str) -> list[dict]:
    """Load JSONL heartbeat log."""
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return sorted(entries, key=lambda e: e["ts"])


def analyze(entries: list[dict], max_missed: int, interval_s: int) -> dict:
    """Analyze heartbeat log for scope violations."""
    if not entries:
        return {"status": "NO_DATA", "trust_score": 0.0}

    threshold = interval_s * 1.5
    violations = []
    consecutive_misses = 0
    max_consecutive = 0
    scope_changes = []
    prev = None

    for entry in entries:
        ts = parse_ts(entry["ts"])
        scope = entry.get("scope_hash", "unknown")

        if prev is not None:
            gap = (ts - prev["ts_parsed"]).total_seconds()
            missed = int(gap / interval_s) - 1

            if missed > 0:
                consecutive_misses += missed
                max_consecutive = max(max_consecutive, consecutive_misses)

                if consecutive_misses >= max_missed:
                    violations.append({
                        "type": "SCOPE_EXPIRED",
                        "at": entry["ts"],
                        "missed": consecutive_misses,
                        "gap_seconds": gap,
                    })
            else:
                consecutive_misses = 0

            if scope != prev.get("scope_hash", "unknown") and scope != "unknown":
                scope_changes.append({
                    "type": "SCOPE_DRIFT",
                    "from": prev.get("scope_hash"),
                    "to": scope,
                    "at": entry["ts"],
                })

        entry["ts_parsed"] = ts
        prev = entry

    # Trust score
    first_ts = parse_ts(entries[0]["ts"])
    last_ts = parse_ts(entries[-1]["ts"])
    total_span = (last_ts - first_ts).total_seconds()
    expected_beats = max(1, int(total_span / interval_s))
    actual_beats = len(entries)
    trust_score = min(1.0, actual_beats / expected_beats)

    expired = any(v["type"] == "SCOPE_EXPIRED" for v in violations)

    return {
        "status": "EXPIRED" if expired else "ACTIVE",
        "trust_score": round(trust_score, 4),
        "total_beats": actual_beats,
        "expected_beats": expected_beats,
        "max_consecutive_missed": max_consecutive,
        "violations": violations,
        "scope_changes": scope_changes,
        "first_beat": entries[0]["ts"],
        "last_beat": entries[-1]["ts"],
    }


def generate_sample_log(path: str, n_beats: int = 20, interval_s: int = 1200):
    """Generate a sample heartbeat log with some gaps for testing."""
    import hashlib
    import random

    base = datetime(2026, 3, 6, 10, 0, 0, tzinfo=timezone.utc)
    scope = hashlib.sha256(b"HEARTBEAT.md:v1").hexdigest()[:16]

    with open(path, "w") as f:
        for i in range(n_beats):
            # Introduce random gaps
            jitter = random.randint(-60, 60)
            skip = 0
            if random.random() < 0.15:  # 15% chance of missing 1-3 beats
                skip = random.randint(1, 3)

            ts = base + timedelta(seconds=(i + skip) * interval_s + jitter)
            entry = {
                "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scope_hash": f"sha256:{scope}",
                "agent": "kit_fox",
            }

            # Occasional scope drift
            if random.random() < 0.05:
                entry["scope_hash"] = f"sha256:{hashlib.sha256(f'drift-{i}'.encode()).hexdigest()[:16]}"

            f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Monitor agent scope TTL via heartbeat log")
    parser.add_argument("logfile", nargs="?", help="JSONL heartbeat log file")
    parser.add_argument("--max-missed", type=int, default=3, help="Max missed beats before expiry (default: 3)")
    parser.add_argument("--heartbeat-interval", type=int, default=1200, help="Expected interval in seconds (default: 1200)")
    parser.add_argument("--generate-sample", type=str, help="Generate a sample log file for testing")
    args = parser.parse_args()

    if args.generate_sample:
        generate_sample_log(args.generate_sample, interval_s=args.heartbeat_interval)
        print(f"Generated sample log: {args.generate_sample}")
        return

    if not args.logfile:
        parser.error("Provide a logfile or use --generate-sample")

    entries = load_log(args.logfile)
    result = analyze(entries, args.max_missed, args.heartbeat_interval)

    print(json.dumps(result, indent=2))

    # Exit code: 0 = active, 1 = expired, 2 = no data
    if result["status"] == "EXPIRED":
        sys.exit(1)
    elif result["status"] == "NO_DATA":
        sys.exit(2)


if __name__ == "__main__":
    main()
