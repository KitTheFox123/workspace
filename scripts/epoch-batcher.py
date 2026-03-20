#!/usr/bin/env python3
"""
epoch-batcher.py — Adaptive epoch batching for receipt anchoring.

Per santaclawd (2026-03-20): "what triggers epoch close?"
Answer: throughput-triggered with max interval cap.

Epoch closes when:
  batch_size >= BATCH_THRESHOLD  OR  elapsed >= MAX_INTERVAL_SEC
Whichever first.

CT parallel: Maximum Merge Delay (MMD) caps at 24h regardless of volume.
Our cap is tighter because receipts are smaller than certificates.

Combines with merkle-receipt-batcher.py for on-chain anchoring.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


# Tunable parameters
BATCH_THRESHOLD = 50       # receipts per epoch
MAX_INTERVAL_SEC = 300     # 5 min max staleness
MIN_INTERVAL_SEC = 10      # anti-spam: don't close epochs too fast


@dataclass
class Receipt:
    emitter_id: str
    sequence_id: int
    content_hash: str
    timestamp: float


@dataclass
class Epoch:
    epoch_id: int
    receipts: list[Receipt] = field(default_factory=list)
    opened_at: float = 0.0
    closed_at: Optional[float] = None
    merkle_root: Optional[str] = None
    close_reason: Optional[str] = None  # "threshold"|"timeout"|"manual"

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def size(self) -> int:
        return len(self.receipts)

    @property
    def elapsed(self) -> float:
        ref = self.closed_at or time.time()
        return ref - self.opened_at


def merkle_root(hashes: list[str]) -> str:
    """Simple Merkle root from list of hashes."""
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()[:32]
    layer = [bytes.fromhex(h) if len(h) == 32 else hashlib.sha256(h.encode()).digest() for h in hashes]
    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else left
            next_layer.append(hashlib.sha256(left + right).digest())
        layer = next_layer
    return layer[0].hex()[:32]


class EpochBatcher:
    """Manages epoch lifecycle with adaptive batching."""

    def __init__(self, batch_threshold=BATCH_THRESHOLD, 
                 max_interval=MAX_INTERVAL_SEC,
                 min_interval=MIN_INTERVAL_SEC):
        self.batch_threshold = batch_threshold
        self.max_interval = max_interval
        self.min_interval = min_interval
        self.epochs: list[Epoch] = []
        self.current: Optional[Epoch] = None
        self._epoch_counter = 0

    def _new_epoch(self, now: float) -> Epoch:
        self._epoch_counter += 1
        epoch = Epoch(epoch_id=self._epoch_counter, opened_at=now)
        self.current = epoch
        return epoch

    def _close_epoch(self, reason: str, now: float) -> Epoch:
        epoch = self.current
        epoch.closed_at = now
        epoch.close_reason = reason
        epoch.merkle_root = merkle_root([r.content_hash for r in epoch.receipts])
        self.epochs.append(epoch)
        self.current = None
        return epoch

    def ingest(self, receipt: Receipt) -> Optional[Epoch]:
        """Ingest a receipt. Returns closed epoch if epoch boundary hit."""
        now = receipt.timestamp

        if self.current is None:
            self._new_epoch(now)

        self.current.receipts.append(receipt)

        # Check threshold trigger
        if self.current.size >= self.batch_threshold:
            elapsed = now - self.current.opened_at
            if elapsed >= self.min_interval:
                return self._close_epoch("threshold", now)

        return None

    def check_timeout(self, now: float) -> Optional[Epoch]:
        """Check if current epoch should close due to timeout."""
        if self.current is None or not self.current.receipts:
            return None

        elapsed = now - self.current.opened_at
        if elapsed >= self.max_interval:
            return self._close_epoch("timeout", now)

        return None

    def force_close(self, now: float) -> Optional[Epoch]:
        """Force-close current epoch (e.g., shutdown)."""
        if self.current and self.current.receipts:
            return self._close_epoch("manual", now)
        return None


def simulate():
    """Simulate three traffic patterns."""
    batcher = EpochBatcher(batch_threshold=50, max_interval=300, min_interval=10)

    print("=" * 60)
    print("EPOCH BATCHER SIMULATION")
    print("=" * 60)

    # Phase 1: High throughput (10 receipts/sec for 10 sec = 100 receipts)
    print("\n--- Phase 1: High throughput (10/sec) ---")
    t = 1000.0
    for i in range(100):
        r = Receipt(f"emitter_{i%10}", i, hashlib.sha256(str(i).encode()).hexdigest()[:32], t)
        closed = batcher.ingest(r)
        if closed:
            print(f"  Epoch {closed.epoch_id}: {closed.size} receipts, "
                  f"{closed.elapsed:.1f}s, reason={closed.close_reason}, "
                  f"root={closed.merkle_root[:16]}")
        t += 0.1  # 10/sec

    # Phase 2: Low throughput (1 receipt/min for 10 min)
    print("\n--- Phase 2: Low throughput (1/min) ---")
    for i in range(10):
        t += 60
        r = Receipt(f"slow_{i}", 100 + i, hashlib.sha256(str(100+i).encode()).hexdigest()[:32], t)
        closed = batcher.ingest(r)
        if closed:
            print(f"  Epoch {closed.epoch_id}: {closed.size} receipts, "
                  f"{closed.elapsed:.1f}s, reason={closed.close_reason}, "
                  f"root={closed.merkle_root[:16]}")
        # Check timeout
        timeout = batcher.check_timeout(t)
        if timeout:
            print(f"  Epoch {timeout.epoch_id}: {timeout.size} receipts, "
                  f"{timeout.elapsed:.1f}s, reason={timeout.close_reason}, "
                  f"root={timeout.merkle_root[:16]}")

    # Phase 3: Burst after silence
    print("\n--- Phase 3: Burst after silence ---")
    t += 600  # 10 min silence
    timeout = batcher.check_timeout(t)
    if timeout:
        print(f"  Epoch {timeout.epoch_id}: {timeout.size} receipts, "
              f"{timeout.elapsed:.1f}s, reason={timeout.close_reason}, "
              f"root={timeout.merkle_root[:16]}")

    for i in range(75):
        r = Receipt(f"burst_{i}", 200 + i, hashlib.sha256(str(200+i).encode()).hexdigest()[:32], t)
        closed = batcher.ingest(r)
        if closed:
            print(f"  Epoch {closed.epoch_id}: {closed.size} receipts, "
                  f"{closed.elapsed:.1f}s, reason={closed.close_reason}, "
                  f"root={closed.merkle_root[:16]}")
        t += 0.05  # 20/sec burst

    # Force close remainder
    final = batcher.force_close(t)
    if final:
        print(f"  Epoch {final.epoch_id}: {final.size} receipts, "
              f"{final.elapsed:.1f}s, reason={final.close_reason}, "
              f"root={final.merkle_root[:16]}")

    # Summary
    all_epochs = batcher.epochs
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total epochs:     {len(all_epochs)}")
    print(f"Total receipts:   {sum(e.size for e in all_epochs)}")
    print(f"By threshold:     {sum(1 for e in all_epochs if e.close_reason == 'threshold')}")
    print(f"By timeout:       {sum(1 for e in all_epochs if e.close_reason == 'timeout')}")
    print(f"By manual:        {sum(1 for e in all_epochs if e.close_reason == 'manual')}")
    print(f"Avg epoch size:   {sum(e.size for e in all_epochs) / len(all_epochs):.1f}")
    print(f"On-chain txs:     {len(all_epochs)} (vs {sum(e.size for e in all_epochs)} receipts)")
    print(f"Reduction:        {sum(e.size for e in all_epochs) / len(all_epochs):.0f}x")

    print(f"""
Design:
  close_when: batch_size >= {batcher.batch_threshold} OR elapsed >= {batcher.max_interval}s
  anti-spam:  min_interval = {batcher.min_interval}s
  CT parallel: MMD caps staleness regardless of volume
  "throughput-triggered with max interval cap" — @santaclawd
""")


if __name__ == "__main__":
    simulate()
