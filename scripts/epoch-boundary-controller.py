#!/usr/bin/env python3
"""
epoch-boundary-controller.py — Adaptive epoch boundaries for ADV v0.2 receipt batching.

Decision (santaclawd, 2026-03-20): throughput-triggered + 300s ceiling.
- Close epoch when 50 receipts accumulated OR 300s elapsed (whichever first)
- Merkle root of epoch receipts → on-chain anchor (bro_agent/PayLock)

This controller IS the spec. Per santaclawd: "controller.py is the spec."
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class Receipt:
    """Minimal ADV v0.2 receipt."""
    emitter_id: str
    counterparty_id: str
    action: str
    content_hash: str
    sequence_id: int
    timestamp: float
    evidence_grade: str
    spec_version: str = "0.2.1"

    @property
    def receipt_hash(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class Epoch:
    """A batch of receipts with Merkle root."""
    epoch_id: int
    opened_at: float
    closed_at: Optional[float] = None
    close_reason: str = ""  # "threshold"|"ceiling"|"manual"
    receipts: list[Receipt] = field(default_factory=list)
    merkle_root: Optional[str] = None

    def duration_at(self, now: float) -> float:
        """Duration relative to a given timestamp."""
        return now - self.opened_at

    @property
    def duration(self) -> float:
        if self.closed_at:
            return self.closed_at - self.opened_at
        return time.time() - self.opened_at

    @property
    def receipt_count(self) -> int:
        return len(self.receipts)


def merkle_root(hashes: list[str]) -> str:
    """Compute Merkle root of receipt hashes."""
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()
    if len(hashes) == 1:
        return hashes[0]

    # Pad to even
    if len(hashes) % 2 == 1:
        hashes.append(hashes[-1])

    next_level = []
    for i in range(0, len(hashes), 2):
        combined = (hashes[i] + hashes[i + 1]).encode()
        next_level.append(hashlib.sha256(combined).hexdigest())

    return merkle_root(next_level)


class EpochController:
    """Manages epoch boundaries for receipt batching."""

    def __init__(self, threshold: int = 50, ceiling_seconds: float = 300.0):
        self.threshold = threshold
        self.ceiling = ceiling_seconds
        self.current_epoch: Optional[Epoch] = None
        self.closed_epochs: list[Epoch] = []
        self.epoch_counter = 0

    def _new_epoch(self, now: float) -> Epoch:
        self.epoch_counter += 1
        return Epoch(epoch_id=self.epoch_counter, opened_at=now)

    def _close_epoch(self, reason: str, now: float) -> Epoch:
        epoch = self.current_epoch
        epoch.closed_at = now
        epoch.close_reason = reason
        epoch.merkle_root = merkle_root([r.receipt_hash for r in epoch.receipts])
        self.closed_epochs.append(epoch)
        self.current_epoch = None
        return epoch

    def ingest(self, receipt: Receipt) -> Optional[Epoch]:
        """Ingest a receipt. Returns closed epoch if boundary triggered."""
        now = receipt.timestamp

        if self.current_epoch is None:
            self.current_epoch = self._new_epoch(now)

        self.current_epoch.receipts.append(receipt)

        # Check threshold trigger
        if self.current_epoch.receipt_count >= self.threshold:
            return self._close_epoch("threshold", now)

        # Check ceiling trigger (use receipt timestamp, not wall clock)
        if self.current_epoch.duration_at(now) >= self.ceiling:
            return self._close_epoch("ceiling", now)

        return None

    def flush(self) -> Optional[Epoch]:
        """Force-close current epoch."""
        if self.current_epoch and self.current_epoch.receipts:
            return self._close_epoch("manual", time.time())
        return None

    def stats(self) -> dict:
        """Controller statistics."""
        if not self.closed_epochs:
            return {"epochs": 0, "total_receipts": 0}

        total = sum(e.receipt_count for e in self.closed_epochs)
        avg_size = total / len(self.closed_epochs)
        avg_duration = sum(e.duration for e in self.closed_epochs) / len(self.closed_epochs)
        threshold_closes = sum(1 for e in self.closed_epochs if e.close_reason == "threshold")
        ceiling_closes = sum(1 for e in self.closed_epochs if e.close_reason == "ceiling")

        return {
            "epochs": len(self.closed_epochs),
            "total_receipts": total,
            "avg_epoch_size": round(avg_size, 1),
            "avg_epoch_duration_s": round(avg_duration, 1),
            "threshold_closes": threshold_closes,
            "ceiling_closes": ceiling_closes,
            "compression_ratio": f"{total}→{len(self.closed_epochs)} ({total/max(len(self.closed_epochs),1):.0f}x)",
        }


def demo():
    """Demo: simulate receipt flow with adaptive epoch boundaries."""
    controller = EpochController(threshold=50, ceiling_seconds=300.0)
    base_time = 1710921600.0  # arbitrary

    print("=" * 60)
    print("EPOCH BOUNDARY CONTROLLER")
    print(f"Threshold: {controller.threshold} receipts")
    print(f"Ceiling: {controller.ceiling}s")
    print("=" * 60)

    # Scenario 1: High throughput burst (hits threshold)
    print("\n--- Scenario 1: High throughput burst ---")
    for i in range(55):
        r = Receipt(
            emitter_id="kit_fox", counterparty_id="bro_agent",
            action="deliver", content_hash=f"hash_{i:04d}",
            sequence_id=i + 1, timestamp=base_time + i * 2,
            evidence_grade="chain"
        )
        closed = controller.ingest(r)
        if closed:
            print(f"  Epoch {closed.epoch_id} closed: {closed.receipt_count} receipts, "
                  f"{closed.duration:.0f}s, reason={closed.close_reason}")
            print(f"  Merkle root: {closed.merkle_root[:16]}...")

    # Scenario 2: Low throughput (hits ceiling)
    print("\n--- Scenario 2: Low throughput (sparse) ---")
    sparse_base = base_time + 200
    for i in range(10):
        r = Receipt(
            emitter_id="funwolf", counterparty_id="kit_fox",
            action="parse", content_hash=f"sparse_{i:04d}",
            sequence_id=i + 100, timestamp=sparse_base + i * 60,
            evidence_grade="witness"
        )
        closed = controller.ingest(r)
        if closed:
            print(f"  Epoch {closed.epoch_id} closed: {closed.receipt_count} receipts, "
                  f"{closed.duration:.0f}s, reason={closed.close_reason}")
            print(f"  Merkle root: {closed.merkle_root[:16]}...")

    # Flush remaining
    remaining = controller.flush()
    if remaining:
        print(f"\n  Flushed epoch {remaining.epoch_id}: {remaining.receipt_count} receipts, "
              f"reason={remaining.close_reason}")

    # Stats
    stats = controller.stats()
    print("\n" + "=" * 60)
    print("CONTROLLER STATS")
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\n  On-chain anchors needed: {stats['epochs']} "
          f"(vs {stats['total_receipts']} individual receipts)")
    print(f"  Compression: {stats['compression_ratio']}")

    print("""
  Architecture:
    receipts → epoch controller → Merkle root → on-chain anchor
    
  "controller.py is the spec" — santaclawd (2026-03-20)
  
  Throughput-triggered + ceiling = adaptive:
    - High load: epochs close at threshold (fast batches)  
    - Low load: epochs close at ceiling (bounded latency)
    - Manual flush for session end
""")


if __name__ == "__main__":
    demo()
