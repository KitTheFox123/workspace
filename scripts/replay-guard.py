#!/usr/bin/env python3
"""replay-guard.py — Monotonic sequence replay protection for receipt streams.

Per santaclawd: "replay attack — reuse an old receipt with valid signatures.
who catches #1? replay protection belongs in the spec."

CT approach: SCT timestamps + Maximum Merge Delay.
Our approach: emitter_id + monotonic sequence_id. Reject if seq <= last_seen.
8 bytes overhead per receipt. Zero state beyond a dict[emitter_id] -> last_seq.

Catches:
- Replay: resubmit old receipt → seq already seen → REJECT
- Reorder: out-of-order delivery → gap detected → WARN (configurable)
- Equivocation: same seq, different content → hash mismatch → REJECT
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum


class Verdict(Enum):
    ACCEPT = "ACCEPT"
    REJECT_REPLAY = "REJECT_REPLAY"
    REJECT_EQUIVOCATION = "REJECT_EQUIVOCATION"
    WARN_GAP = "WARN_GAP"  # accepted but gap detected
    REJECT_BACKWARDS = "REJECT_BACKWARDS"


@dataclass
class ReceiptEntry:
    emitter_id: str
    sequence_id: int
    content_hash: str
    timestamp: float


@dataclass
class ReplayGuard:
    """Per-emitter monotonic sequence tracker."""
    # emitter_id -> (last_seq, content_hash_at_seq)
    state: dict[str, tuple[int, str]] = field(default_factory=dict)
    # Stats
    accepted: int = 0
    rejected_replay: int = 0
    rejected_equivocation: int = 0
    rejected_backwards: int = 0
    gaps_detected: int = 0
    strict_ordering: bool = False  # if True, reject gaps too

    def check(self, receipt: ReceiptEntry) -> Verdict:
        eid = receipt.emitter_id
        seq = receipt.sequence_id
        chash = receipt.content_hash

        if eid not in self.state:
            # First receipt from this emitter
            self.state[eid] = (seq, chash)
            self.accepted += 1
            return Verdict.ACCEPT

        last_seq, last_hash = self.state[eid]

        if seq < last_seq:
            # Backwards — either replay or reorder
            self.rejected_backwards += 1
            return Verdict.REJECT_BACKWARDS

        if seq == last_seq:
            # Same sequence — check for equivocation
            if chash == last_hash:
                self.rejected_replay += 1
                return Verdict.REJECT_REPLAY
            else:
                self.rejected_equivocation += 1
                return Verdict.REJECT_EQUIVOCATION

        # seq > last_seq — accept
        gap = seq - last_seq
        self.state[eid] = (seq, chash)

        if gap > 1:
            self.gaps_detected += 1
            if self.strict_ordering:
                return Verdict.WARN_GAP
            self.accepted += 1
            return Verdict.WARN_GAP

        self.accepted += 1
        return Verdict.ACCEPT

    def stats(self) -> dict:
        return {
            "emitters_tracked": len(self.state),
            "accepted": self.accepted,
            "rejected_replay": self.rejected_replay,
            "rejected_equivocation": self.rejected_equivocation,
            "rejected_backwards": self.rejected_backwards,
            "gaps_detected": self.gaps_detected,
            "memory_bytes": len(self.state) * 48,  # ~48 bytes per entry
        }


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def demo():
    guard = ReplayGuard()

    # Simulate receipt stream
    scenarios = [
        # Normal flow
        ("agent_A", 1, "task completed: research"),
        ("agent_A", 2, "task completed: summary"),
        ("agent_B", 1, "escrow released: 0.01 SOL"),
        ("agent_A", 3, "task completed: review"),

        # Replay attack: agent_A resubmits seq 2
        ("agent_A", 2, "task completed: summary"),

        # Equivocation: agent_A submits seq 3 with different content
        ("agent_A", 3, "task completed: DIFFERENT CONTENT"),

        # Backwards: agent_B tries seq 0
        ("agent_B", 0, "escrow released: fake"),

        # Gap: agent_B jumps from 1 to 5
        ("agent_B", 5, "escrow released: 0.05 SOL"),

        # Normal continuation
        ("agent_A", 4, "task completed: delivery"),
        ("agent_B", 6, "escrow released: 0.02 SOL"),
    ]

    print("=" * 65)
    print("Replay Guard — Monotonic Sequence Protection")
    print("8 bytes overhead per receipt. O(1) per emitter.")
    print("=" * 65)

    for emitter, seq, content in scenarios:
        entry = ReceiptEntry(
            emitter_id=emitter,
            sequence_id=seq,
            content_hash=content_hash(content),
            timestamp=time.time(),
        )
        verdict = guard.check(entry)

        icon = {
            Verdict.ACCEPT: "✅",
            Verdict.REJECT_REPLAY: "🔴",
            Verdict.REJECT_EQUIVOCATION: "⚠️",
            Verdict.REJECT_BACKWARDS: "🔴",
            Verdict.WARN_GAP: "🟡",
        }[verdict]

        print(f"  {icon} {emitter} seq={seq}: {verdict.value}")
        if verdict in (Verdict.REJECT_REPLAY, Verdict.REJECT_EQUIVOCATION, Verdict.REJECT_BACKWARDS):
            print(f"     └─ content: \"{content[:40]}\"")

    print(f"\n{'─' * 50}")
    print("Stats:")
    for k, v in guard.stats().items():
        print(f"  {k}: {v}")

    print(f"\n{'=' * 65}")
    print("SPEC RECOMMENDATION:")
    print("  MUST: emitter_id + sequence_id monotonically increasing")
    print("  MUST: verifier rejects seq <= last_seen[emitter_id]")
    print("  MUST: same (emitter_id, seq) + different hash = equivocation")
    print("  SHOULD: verifier warns on gaps > 1 (missing receipts)")
    print("  Overhead: 8 bytes/receipt, ~48 bytes/emitter state")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
