#!/usr/bin/env python3
"""soul-hash-drift.py — Detect identity drift via soul_hash across receipts.

Per santaclawd: soul_hash in receipts = consistency auditing.
Same agent, different soul_hash = configuration change event.
MEMORY-CHAIN prev_hash = continuity. soul_hash = consistency.
Two orthogonal signals.

Parfit (1984): Identity = overlapping chains of psychological connection.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Receipt:
    timestamp: str
    soul_hash: str | None
    action_type: str
    decision_type: str


def sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def detect_drift(receipts: list[Receipt]) -> dict:
    """Analyze soul_hash drift across a receipt history."""
    hashes_seen = {}
    drift_events = []
    gaps = []
    prev_hash = None

    for i, r in enumerate(receipts):
        if r.soul_hash is None:
            gaps.append({"index": i, "timestamp": r.timestamp, "type": "missing"})
            continue

        if r.soul_hash not in hashes_seen:
            hashes_seen[r.soul_hash] = {
                "first_seen": r.timestamp,
                "last_seen": r.timestamp,
                "count": 1,
            }
        else:
            hashes_seen[r.soul_hash]["last_seen"] = r.timestamp
            hashes_seen[r.soul_hash]["count"] += 1

        if prev_hash and r.soul_hash != prev_hash:
            drift_events.append({
                "index": i,
                "timestamp": r.timestamp,
                "from_hash": prev_hash,
                "to_hash": r.soul_hash,
                "type": classify_drift(prev_hash, r.soul_hash, hashes_seen),
            })

        prev_hash = r.soul_hash

    # Classify overall pattern
    total = len(receipts)
    with_hash = total - len(gaps)
    coverage = with_hash / total if total > 0 else 0

    verdict = classify_agent(drift_events, coverage, len(hashes_seen))

    return {
        "total_receipts": total,
        "soul_hash_coverage": round(coverage * 100, 1),
        "unique_hashes": len(hashes_seen),
        "drift_events": len(drift_events),
        "gaps": len(gaps),
        "hashes": hashes_seen,
        "drifts": drift_events,
        "verdict": verdict,
    }


def classify_drift(from_h: str, to_h: str, seen: dict) -> str:
    """Classify a drift event."""
    if to_h in seen and seen[to_h]["count"] > 1:
        return "REVERT"  # returned to a previous soul_hash
    return "UPDATE"  # new soul_hash, likely config change


def classify_agent(drifts: list, coverage: float, unique: int) -> dict:
    if coverage < 0.5:
        return {
            "grade": "D",
            "label": "LOW_COVERAGE",
            "note": "soul_hash present in <50% of receipts. Cannot audit consistency.",
        }
    if unique == 1 and len(drifts) == 0:
        return {
            "grade": "A",
            "label": "STABLE",
            "note": "Single soul_hash across all receipts. Consistent identity.",
        }
    if unique <= 3 and all(d["type"] in ("UPDATE", "REVERT") for d in drifts):
        return {
            "grade": "B",
            "label": "EVOLVING",
            "note": f"{unique} soul versions. Configuration changes are normal — drift is auditable.",
        }
    if unique > 5:
        return {
            "grade": "C",
            "label": "UNSTABLE",
            "note": f"{unique} distinct soul_hashes. Either rapid iteration or identity instability.",
        }
    return {
        "grade": "B",
        "label": "NORMAL",
        "note": "Some drift detected. Within expected range.",
    }


def demo():
    now = datetime(2026, 3, 19)

    # Agent 1: Stable identity
    stable = [
        Receipt((now - timedelta(days=i)).isoformat(), sha256("soul_v1"), "task", "completed")
        for i in range(30)
    ]

    # Agent 2: Model migration (like Kit: Opus 4.5 → 4.6)
    migrated = [
        Receipt((now - timedelta(days=i)).isoformat(),
                sha256("soul_v1") if i > 15 else sha256("soul_v2"),
                "task", "completed")
        for i in range(30)
    ]

    # Agent 3: Suspicious — new soul every few days
    chaotic = [
        Receipt((now - timedelta(days=i)).isoformat(),
                sha256(f"soul_v{i // 3}"), "task", "completed")
        for i in range(30)
    ]

    # Agent 4: No soul_hash (opted out)
    no_soul = [
        Receipt((now - timedelta(days=i)).isoformat(), None, "task", "completed")
        for i in range(30)
    ]

    agents = {
        "stable_agent": stable,
        "migrated_agent": migrated,
        "chaotic_agent": chaotic,
        "no_soul_agent": no_soul,
    }

    print("=" * 60)
    print("Soul Hash Drift Analysis")
    print("=" * 60)

    for name, receipts in agents.items():
        result = detect_drift(receipts)
        print(f"\n{'─' * 40}")
        print(f"Agent: {name}")
        print(f"  Receipts: {result['total_receipts']}")
        print(f"  Coverage: {result['soul_hash_coverage']}%")
        print(f"  Unique hashes: {result['unique_hashes']}")
        print(f"  Drift events: {result['drift_events']}")
        print(f"  Verdict: {result['verdict']['grade']} — {result['verdict']['label']}")
        print(f"  Note: {result['verdict']['note']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  soul_hash SHOULD not MUST (not every agent has SOUL.md).")
    print("  When present: continuity (prev_hash) + consistency (soul_hash)")
    print("  = two orthogonal identity signals.")
    print("  Drift ≠ bad. Unauditable drift = bad.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
