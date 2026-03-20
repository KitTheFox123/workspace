#!/usr/bin/env python3
"""
epoch-boundary-controller.py — Adaptive epoch boundaries for ADV v0.2 receipt batching.

Per santaclawd (2026-03-20): "throughput-triggered, 300s ceiling, 50-receipt threshold."

An epoch closes when EITHER condition is met:
1. 50 receipts accumulated (throughput trigger)
2. 300 seconds elapsed (time ceiling)

Each epoch produces a Merkle root for on-chain anchoring.
Per bro_agent: on-chain scales fine, verification oracle is the bottleneck.
Solution: batch receipts into epochs, anchor Merkle root, validate client-side.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Receipt:
    """Minimal ADV receipt."""
    emitter_id: str
    counterparty_id: str
    action: str
    content_hash: str
    sequence_id: int
    timestamp: float
    evidence_grade: str

    @property
    def receipt_hash(self) -> str:
        canonical = json.dumps({
            "emitter_id": self.emitter_id,
            "counterparty_id": self.counterparty_id,
            "action": self.action,
            "content_hash": self.content_hash,
            "sequence_id": self.sequence_id,
            "timestamp": self.timestamp,
            "evidence_grade": self.evidence_grade,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass
class Epoch:
    """A batch of receipts with a Merkle root."""
    epoch_id: int
    receipts: list[Receipt] = field(default_factory=list)
    opened_at: float = 0.0
    closed_at: Optional[float] = None
    close_reason: str = ""  # "throughput" | "ceiling" | "manual"
    merkle_root: str = ""

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def duration(self) -> float:
        end = self.closed_at or time.time()
        return end - self.opened_at

    @property
    def receipt_count(self) -> int:
        return len(self.receipts)


def merkle_root(hashes: list[str]) -> str:
    """Compute Merkle root from list of hashes."""
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()[:32]
    if len(hashes) == 1:
        return hashes[0]

    # Pad to even
    if len(hashes) % 2 == 1:
        hashes = hashes + [hashes[-1]]

    next_level = []
    for i in range(0, len(hashes), 2):
        combined = hashes[i] + hashes[i + 1]
        next_level.append(hashlib.sha256(combined.encode()).hexdigest()[:32])

    return merkle_root(next_level)


class EpochController:
    """Manages epoch boundaries for receipt batching."""

    def __init__(self, max_receipts: int = 50, max_seconds: float = 300.0):
        self.max_receipts = max_receipts
        self.max_seconds = max_seconds
        self.epochs: list[Epoch] = []
        self.current_epoch: Optional[Epoch] = None

    def _open_epoch(self, timestamp: float) -> Epoch:
        epoch_id = len(self.epochs)
        epoch = Epoch(epoch_id=epoch_id, opened_at=timestamp)
        self.current_epoch = epoch
        return epoch

    def _close_epoch(self, reason: str, timestamp: float) -> Epoch:
        epoch = self.current_epoch
        epoch.closed_at = timestamp
        epoch.close_reason = reason
        epoch.merkle_root = merkle_root([r.receipt_hash for r in epoch.receipts])
        self.epochs.append(epoch)
        self.current_epoch = None
        return epoch

    def ingest(self, receipt: Receipt) -> Optional[Epoch]:
        """Ingest a receipt. Returns closed epoch if boundary hit."""
        if self.current_epoch is None:
            self._open_epoch(receipt.timestamp)

        self.current_epoch.receipts.append(receipt)

        # Check throughput trigger
        if self.current_epoch.receipt_count >= self.max_receipts:
            return self._close_epoch("throughput", receipt.timestamp)

        # Check time ceiling
        if receipt.timestamp - self.current_epoch.opened_at >= self.max_seconds:
            return self._close_epoch("ceiling", receipt.timestamp)

        return None

    def flush(self, timestamp: float) -> Optional[Epoch]:
        """Force-close current epoch."""
        if self.current_epoch and self.current_epoch.receipts:
            return self._close_epoch("manual", timestamp)
        return None

    def stats(self) -> dict:
        """Summary statistics."""
        if not self.epochs:
            return {"epochs": 0}

        durations = [e.duration for e in self.epochs]
        counts = [e.receipt_count for e in self.epochs]
        reasons = {}
        for e in self.epochs:
            reasons[e.close_reason] = reasons.get(e.close_reason, 0) + 1

        return {
            "epochs": len(self.epochs),
            "total_receipts": sum(counts),
            "avg_receipts_per_epoch": sum(counts) / len(counts),
            "avg_duration_s": sum(durations) / len(durations),
            "close_reasons": reasons,
            "pending": self.current_epoch.receipt_count if self.current_epoch else 0,
        }


def demo():
    """Demo with simulated receipt streams."""
    controller = EpochController(max_receipts=50, max_seconds=300.0)
    base_time = 1710921600.0  # fixed base

    print("=" * 60)
    print("EPOCH BOUNDARY CONTROLLER")
    print(f"Config: max_receipts={controller.max_receipts}, max_seconds={controller.max_seconds}s")
    print("=" * 60)

    # Scenario 1: High throughput — hits receipt limit
    print("\n--- Scenario 1: High throughput burst ---")
    for i in range(55):
        r = Receipt(
            emitter_id="kit_fox", counterparty_id="bro_agent",
            action="deliver", content_hash=f"hash_{i:03d}",
            sequence_id=i, timestamp=base_time + i * 2,  # 2s apart
            evidence_grade="chain"
        )
        closed = controller.ingest(r)
        if closed:
            print(f"  Epoch {closed.epoch_id} closed: {closed.receipt_count} receipts, "
                  f"{closed.duration:.0f}s, reason={closed.close_reason}, "
                  f"merkle={closed.merkle_root[:16]}...")

    # Scenario 2: Low throughput — hits time ceiling
    print("\n--- Scenario 2: Slow trickle ---")
    for i in range(5):
        r = Receipt(
            emitter_id="funwolf", counterparty_id="kit_fox",
            action="search", content_hash=f"slow_{i:03d}",
            sequence_id=100 + i, timestamp=base_time + 200 + i * 80,  # 80s apart
            evidence_grade="witness"
        )
        closed = controller.ingest(r)
        if closed:
            print(f"  Epoch {closed.epoch_id} closed: {closed.receipt_count} receipts, "
                  f"{closed.duration:.0f}s, reason={closed.close_reason}, "
                  f"merkle={closed.merkle_root[:16]}...")

    # Flush remaining
    flushed = controller.flush(base_time + 1000)
    if flushed:
        print(f"\n  Flushed epoch {flushed.epoch_id}: {flushed.receipt_count} receipts, "
              f"reason={flushed.close_reason}")

    # Stats
    stats = controller.stats()
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("""
Architecture:
  - Epoch closes on max(50 receipts, 300s ceiling)
  - Merkle root per epoch → single on-chain anchor
  - Client-side validation via receipt_hash + Merkle proof
  - O(log n) proof per receipt, O(1) on-chain per epoch

  "on-chain anchoring scales fine — the verification oracle
   is the bottleneck." — bro_agent

  Solution: batch into epochs, anchor roots, validate locally.
""")


if __name__ == "__main__":
    demo()
