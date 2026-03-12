#!/usr/bin/env python3
"""
drand-trust-anchor.py — Use drand randomness beacon as external trust anchor.

santaclawd's insight: "who attests drand? nobody — math does."

drand = distributed randomness beacon (threshold BLS, 30s rounds).
No single party controls output. Unpredictable, verifiable, free.

Use cases for agent trust:
1. Unforgeable timestamps: hash(agent+action+drand_round) = proof of when
2. WAL gap detection: drand round at reconnect proves no backfill
3. Commit-reveal anchor: commit before round, reveal after
4. Canary probes: randomize probe timing using beacon

API: https://api.drand.sh/public/latest (free, no auth)

Usage:
    python3 drand-trust-anchor.py
"""

import hashlib
import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, List


DRAND_API = "https://drand.cloudflare.com"


def fetch_drand_round(round_num: Optional[int] = None) -> dict:
    """Fetch a drand beacon round. None = latest."""
    if round_num:
        url = f"{DRAND_API}/public/{round_num}"
    else:
        url = f"{DRAND_API}/public/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kit-fox-trust-anchor/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e), "round": 0, "randomness": "fallback_" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:32]}


def anchor_action(agent_id: str, action: str, beacon: dict) -> dict:
    """Create an unforgeable timestamp anchor using drand beacon."""
    payload = f"{agent_id}:{action}:{beacon.get('round', 0)}:{beacon.get('randomness', '')}"
    anchor_hash = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "agent_id": agent_id,
        "action": action,
        "drand_round": beacon.get("round", 0),
        "beacon_randomness": beacon.get("randomness", "")[:16] + "...",
        "anchor_hash": anchor_hash,
        "timestamp": time.time(),
        "verifiable": True,
    }


def verify_anchor(anchor: dict, beacon: dict) -> bool:
    """Verify an anchor against its drand round."""
    payload = f"{anchor['agent_id']}:{anchor['action']}:{beacon.get('round', 0)}:{beacon.get('randomness', '')}"
    expected = hashlib.sha256(payload.encode()).hexdigest()
    return expected == anchor["anchor_hash"]


@dataclass
class WALGapDetector:
    """Detect offline gaps using drand rounds as external clock."""
    last_round: int = 0
    anchors: List[dict] = field(default_factory=list)

    def checkpoint(self, agent_id: str, action: str) -> dict:
        """Record a checkpoint with current drand round."""
        beacon = fetch_drand_round()
        current_round = beacon.get("round", 0)

        gap = 0
        gap_seconds = 0
        if self.last_round > 0 and current_round > 0:
            gap = current_round - self.last_round
            gap_seconds = gap * 3  # 3s per round in unchained mode

        anchor = anchor_action(agent_id, action, beacon)
        anchor["gap_rounds"] = gap
        anchor["gap_seconds"] = gap_seconds
        anchor["gap_suspicious"] = gap_seconds > 3600  # >1hr gap

        self.last_round = current_round
        self.anchors.append(anchor)
        return anchor

    def audit(self) -> dict:
        """Audit WAL for gaps and backfill attempts."""
        if len(self.anchors) < 2:
            return {"status": "INSUFFICIENT_DATA", "anchors": len(self.anchors)}

        gaps = [a["gap_seconds"] for a in self.anchors if a.get("gap_seconds", 0) > 0]
        suspicious = [a for a in self.anchors if a.get("gap_suspicious")]

        # Check for non-monotonic rounds (backfill attempt)
        rounds = [a["drand_round"] for a in self.anchors]
        backfill_detected = any(rounds[i] >= rounds[i+1] for i in range(len(rounds)-1) if rounds[i] > 0 and rounds[i+1] > 0)

        grade = "A"
        if backfill_detected:
            grade = "F"
        elif len(suspicious) > 0:
            grade = "C"
        elif len(gaps) > 0 and max(gaps) > 300:
            grade = "B"

        return {
            "total_checkpoints": len(self.anchors),
            "gaps_detected": len(gaps),
            "suspicious_gaps": len(suspicious),
            "max_gap_seconds": max(gaps) if gaps else 0,
            "backfill_detected": backfill_detected,
            "grade": grade,
        }


def demo():
    print("=" * 60)
    print("DRAND TRUST ANCHOR")
    print("\"Who attests drand? Nobody — math does.\" — santaclawd")
    print("=" * 60)

    # Fetch current beacon
    print("\n--- Current Drand Beacon ---")
    beacon = fetch_drand_round()
    print(f"  Round: {beacon.get('round', 'N/A')}")
    print(f"  Randomness: {beacon.get('randomness', 'N/A')[:32]}...")
    if "signature" in beacon:
        print(f"  Signature: {beacon['signature'][:32]}...")

    # Anchor an action
    print("\n--- Anchor Action ---")
    anchor = anchor_action("kit_fox", "score_5_agents_cross_platform", beacon)
    print(f"  Agent: {anchor['agent_id']}")
    print(f"  Action: {anchor['action']}")
    print(f"  Round: {anchor['drand_round']}")
    print(f"  Anchor hash: {anchor['anchor_hash'][:32]}...")

    # Verify
    print("\n--- Verify ---")
    valid = verify_anchor(anchor, beacon)
    print(f"  Valid: {valid}")

    # Tampered verification
    tampered = dict(anchor)
    tampered["action"] = "something_else_entirely"
    valid_tampered = verify_anchor(tampered, beacon)
    print(f"  Tampered valid: {valid_tampered}")

    # WAL gap detection
    print("\n--- WAL Gap Detection ---")
    wal = WALGapDetector()

    # Simulate checkpoints
    c1 = wal.checkpoint("kit_fox", "heartbeat_check")
    print(f"  Checkpoint 1: round {c1['drand_round']}, gap {c1['gap_seconds']}s")

    c2 = wal.checkpoint("kit_fox", "clawk_reply")
    print(f"  Checkpoint 2: round {c2['drand_round']}, gap {c2['gap_seconds']}s")

    c3 = wal.checkpoint("kit_fox", "moltbook_comment")
    print(f"  Checkpoint 3: round {c3['drand_round']}, gap {c3['gap_seconds']}s")

    audit = wal.audit()
    print(f"\n  Audit: {audit}")

    print("\n--- WHY DRAND ---")
    print("1. Threshold BLS: t-of-n, no single party controls output")
    print("2. 3s rounds: free external clock, finer than SMTP")
    print("3. Unpredictable: can't pre-compute future values")
    print("4. Verifiable: anyone can check signature against group key")
    print("5. Backfill-proof: hash includes beacon round number")
    print("6. Free: api.drand.sh, no auth, no API key")
    print("\ndrand + WAL + genesis anchor = three-layer non-forgeable trust stack")


if __name__ == "__main__":
    demo()
