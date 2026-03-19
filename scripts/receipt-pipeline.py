#!/usr/bin/env python3
"""receipt-pipeline.py — Complete receipt validation pipeline.

Chains: format validation → replay guard → collision dedup → accept/reject.
Three tools unified into one pipeline per santaclawd's ADV threat model:
  1. Format: receipt-validator-cli (schema, required fields, evidence grade)
  2. Replay: replay-guard (monotonic sequence, equivocation detection)
  3. Collision: collision-dedup-validator (emitter_id+sequence_id composite key)

Usage: cat receipts.jsonl | python3 receipt-pipeline.py
   or: python3 receipt-pipeline.py --demo
"""

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# --- Stage 1: Format Validation ---

REQUIRED_FIELDS = {
    "emitter_id", "counterparty_id", "decision_type",
    "timestamp", "evidence_grade", "sequence_id",
    "rationale_hash", "signature",
}

VALID_DECISION_TYPES = {"completed", "refusal", "partial", "disputed", "timeout"}
VALID_EVIDENCE_GRADES = {"chain", "witness", "self"}


def validate_format(receipt: dict) -> tuple[bool, str]:
    """Stage 1: Schema validation."""
    missing = REQUIRED_FIELDS - set(receipt.keys())
    if missing:
        return False, f"missing fields: {', '.join(sorted(missing))}"

    if receipt.get("decision_type") not in VALID_DECISION_TYPES:
        return False, f"invalid decision_type: {receipt.get('decision_type')}"

    if receipt.get("evidence_grade") not in VALID_EVIDENCE_GRADES:
        return False, f"invalid evidence_grade: {receipt.get('evidence_grade')}"

    if not isinstance(receipt.get("sequence_id"), int) or receipt["sequence_id"] < 0:
        return False, "sequence_id must be non-negative integer"

    return True, "ok"


# --- Stage 2: Replay Guard ---

class ReplayGuard:
    def __init__(self):
        self.state: dict[str, tuple[int, str]] = {}

    def check(self, emitter_id: str, seq: int, content_hash: str) -> tuple[bool, str]:
        if emitter_id not in self.state:
            self.state[emitter_id] = (seq, content_hash)
            return True, "first_receipt"

        last_seq, last_hash = self.state[emitter_id]

        if seq < last_seq:
            return False, f"backwards: seq {seq} < last {last_seq}"
        if seq == last_seq:
            if content_hash == last_hash:
                return False, f"replay: seq {seq} already seen"
            else:
                return False, f"equivocation: seq {seq} different content"

        gap = seq - last_seq
        self.state[emitter_id] = (seq, content_hash)
        if gap > 1:
            return True, f"accepted_with_gap: {gap-1} missing"
        return True, "ok"


# --- Stage 3: Collision Dedup ---

class CollisionDedup:
    def __init__(self):
        self.seen: dict[str, str] = {}  # composite_key -> content_hash

    def check(self, emitter_id: str, seq: int, content_hash: str) -> tuple[bool, str]:
        key = f"{emitter_id}:{seq}"
        if key in self.seen:
            if self.seen[key] == content_hash:
                return False, "duplicate"
            else:
                return False, "collision: same key, different content"
        self.seen[key] = content_hash
        return True, "ok"


# --- Pipeline ---

@dataclass
class PipelineStats:
    total: int = 0
    accepted: int = 0
    rejected_format: int = 0
    rejected_replay: int = 0
    rejected_collision: int = 0
    warnings: int = 0

    def summary(self) -> dict:
        return {
            "total": self.total,
            "accepted": self.accepted,
            "rejected": self.total - self.accepted,
            "reject_breakdown": {
                "format": self.rejected_format,
                "replay": self.rejected_replay,
                "collision": self.rejected_collision,
            },
            "warnings": self.warnings,
            "accept_rate": f"{self.accepted/max(1,self.total)*100:.1f}%",
        }


def content_hash(receipt: dict) -> str:
    canonical = json.dumps(
        {k: v for k, v in sorted(receipt.items()) if k != "signature"},
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def run_pipeline(receipts: list[dict], verbose: bool = True) -> PipelineStats:
    stats = PipelineStats()
    replay = ReplayGuard()
    dedup = CollisionDedup()

    if verbose:
        print("=" * 65)
        print("Receipt Validation Pipeline")
        print("Stage 1: Format → Stage 2: Replay Guard → Stage 3: Collision Dedup")
        print("=" * 65)

    for r in receipts:
        stats.total += 1
        chash = content_hash(r)
        eid = r.get("emitter_id", "unknown")
        seq = r.get("sequence_id", -1)

        # Stage 1: Format
        ok, msg = validate_format(r)
        if not ok:
            stats.rejected_format += 1
            if verbose:
                print(f"  🔴 #{stats.total} REJECT(format): {msg}")
            continue

        # Stage 2: Replay
        ok, msg = replay.check(eid, seq, chash)
        if not ok:
            stats.rejected_replay += 1
            if verbose:
                print(f"  🔴 #{stats.total} REJECT(replay): {msg}")
            continue

        # Stage 3: Collision
        ok, msg = dedup.check(eid, seq, chash)
        if not ok:
            stats.rejected_collision += 1
            if verbose:
                print(f"  🔴 #{stats.total} REJECT(collision): {msg}")
            continue

        stats.accepted += 1
        warn = " ⚠️" if "gap" in msg else ""
        if "gap" in msg:
            stats.warnings += 1
        if verbose:
            print(f"  ✅ #{stats.total} ACCEPT {eid}:seq{seq} [{r['decision_type']}]{warn}")

    if verbose:
        print(f"\n{'─' * 50}")
        print(json.dumps(stats.summary(), indent=2))

    return stats


def demo():
    now = time.time()
    receipts = [
        # Good receipts
        {"emitter_id": "agent_A", "counterparty_id": "agent_B", "decision_type": "completed",
         "timestamp": now, "evidence_grade": "witness", "sequence_id": 1,
         "rationale_hash": "abc123", "signature": "sig1"},
        {"emitter_id": "agent_A", "counterparty_id": "agent_C", "decision_type": "refusal",
         "timestamp": now+1, "evidence_grade": "self", "sequence_id": 2,
         "rationale_hash": "def456", "signature": "sig2"},
        {"emitter_id": "agent_B", "counterparty_id": "agent_A", "decision_type": "completed",
         "timestamp": now+2, "evidence_grade": "chain", "sequence_id": 1,
         "rationale_hash": "ghi789", "signature": "sig3"},
        # Bad format: missing fields
        {"emitter_id": "agent_X", "decision_type": "completed"},
        # Bad format: invalid decision_type
        {"emitter_id": "agent_X", "counterparty_id": "agent_Y", "decision_type": "INVALID",
         "timestamp": now, "evidence_grade": "self", "sequence_id": 1,
         "rationale_hash": "x", "signature": "x"},
        # Replay: agent_A seq 1 again
        {"emitter_id": "agent_A", "counterparty_id": "agent_B", "decision_type": "completed",
         "timestamp": now, "evidence_grade": "witness", "sequence_id": 1,
         "rationale_hash": "abc123", "signature": "sig1"},
        # Equivocation: agent_A seq 2 different content
        {"emitter_id": "agent_A", "counterparty_id": "agent_D", "decision_type": "completed",
         "timestamp": now+5, "evidence_grade": "chain", "sequence_id": 2,
         "rationale_hash": "DIFFERENT", "signature": "sig_fake"},
        # Gap: agent_B jumps to seq 5
        {"emitter_id": "agent_B", "counterparty_id": "agent_C", "decision_type": "partial",
         "timestamp": now+10, "evidence_grade": "witness", "sequence_id": 5,
         "rationale_hash": "jkl012", "signature": "sig5"},
        # Normal continuation
        {"emitter_id": "agent_A", "counterparty_id": "agent_B", "decision_type": "completed",
         "timestamp": now+15, "evidence_grade": "witness", "sequence_id": 3,
         "rationale_hash": "mno345", "signature": "sig6"},
    ]

    stats = run_pipeline(receipts)

    print(f"\n{'=' * 65}")
    print("PIPELINE SPEC:")
    print("  Stage 1 (Format):    MUST have 8 required fields + valid enums")
    print("  Stage 2 (Replay):    MUST reject seq <= last_seen per emitter")
    print("  Stage 3 (Collision): MUST reject duplicate composite keys")
    print("  Each stage is independent. Fail-fast on first rejection.")
    print("  Memory: O(emitters) for replay + O(receipts) for dedup")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    if "--demo" in sys.argv or len(sys.argv) == 1:
        demo()
    else:
        # Read JSONL from stdin
        receipts = []
        for line in sys.stdin:
            line = line.strip()
            if line:
                receipts.append(json.loads(line))
        run_pipeline(receipts)
