#!/usr/bin/env python3
"""
epoch-boundary-controller.py — Adaptive epoch boundaries for Merkle receipt batching.

Per santaclawd (2026-03-20): "what triggers epoch close? block time = forced synchrony.
fixed interval = predictable but wasteful. throughput-triggered = adaptive."

Answer: throughput-triggered with time ceiling. Close epoch at either:
- max_receipts (throughput trigger, e.g. 50)
- max_epoch_seconds (time ceiling, e.g. 300s)
whichever comes first.

Parallel: CT logs use MMD (Maximum Merge Delay) — same concept.
"""

import time
import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EpochConfig:
    """Epoch boundary parameters."""
    max_receipts: int = 50          # close at N receipts
    max_epoch_seconds: float = 300  # close at T seconds (5 min)
    min_receipts: int = 1           # don't close empty epochs


@dataclass
class Receipt:
    """Minimal receipt for batching."""
    receipt_hash: str
    emitter_id: str
    sequence_id: int
    timestamp: float


@dataclass
class Epoch:
    """A completed epoch with Merkle root."""
    epoch_id: int
    receipts: list[Receipt]
    merkle_root: str
    opened_at: float
    closed_at: float
    close_trigger: str  # "throughput" | "timeout" | "manual"
    receipt_count: int
    duration_seconds: float

    @property
    def efficiency(self) -> float:
        """Receipts per second in this epoch."""
        return self.receipt_count / max(self.duration_seconds, 0.001)


class EpochController:
    """Manages epoch boundaries for receipt batching."""

    def __init__(self, config: Optional[EpochConfig] = None):
        self.config = config or EpochConfig()
        self.current_receipts: list[Receipt] = []
        self.epoch_opened_at: float = time.time()
        self.epoch_counter: int = 0
        self.completed_epochs: list[Epoch] = []

    def add_receipt(self, receipt: Receipt) -> Optional[Epoch]:
        """Add receipt. Returns completed Epoch if boundary crossed."""
        self.current_receipts.append(receipt)

        # Throughput trigger
        if len(self.current_receipts) >= self.config.max_receipts:
            return self._close_epoch("throughput")

        return None

    def check_timeout(self) -> Optional[Epoch]:
        """Check if time ceiling reached. Call periodically."""
        if not self.current_receipts:
            return None

        elapsed = time.time() - self.epoch_opened_at
        if elapsed >= self.config.max_epoch_seconds:
            return self._close_epoch("timeout")

        return None

    def force_close(self) -> Optional[Epoch]:
        """Force close current epoch (e.g., shutdown)."""
        if not self.current_receipts:
            return None
        return self._close_epoch("manual")

    def _close_epoch(self, trigger: str) -> Epoch:
        """Close current epoch and start new one."""
        now = time.time()

        # Compute Merkle root
        hashes = [r.receipt_hash for r in self.current_receipts]
        merkle_root = self._merkle_root(hashes)

        self.epoch_counter += 1
        epoch = Epoch(
            epoch_id=self.epoch_counter,
            receipts=list(self.current_receipts),
            merkle_root=merkle_root,
            opened_at=self.epoch_opened_at,
            closed_at=now,
            close_trigger=trigger,
            receipt_count=len(self.current_receipts),
            duration_seconds=now - self.epoch_opened_at
        )

        self.completed_epochs.append(epoch)
        self.current_receipts = []
        self.epoch_opened_at = now

        return epoch

    @staticmethod
    def _merkle_root(hashes: list[str]) -> str:
        """Simple Merkle root computation."""
        if not hashes:
            return hashlib.sha256(b"empty").hexdigest()[:32]
        if len(hashes) == 1:
            return hashes[0]

        while len(hashes) > 1:
            next_level = []
            for i in range(0, len(hashes), 2):
                left = hashes[i]
                right = hashes[i + 1] if i + 1 < len(hashes) else left
                combined = hashlib.sha256(f"{left}{right}".encode()).hexdigest()[:32]
                next_level.append(combined)
            hashes = next_level

        return hashes[0]

    def stats(self) -> dict:
        """Epoch controller statistics."""
        if not self.completed_epochs:
            return {"epochs": 0, "pending": len(self.current_receipts)}

        throughput_epochs = [e for e in self.completed_epochs if e.close_trigger == "throughput"]
        timeout_epochs = [e for e in self.completed_epochs if e.close_trigger == "timeout"]

        total_receipts = sum(e.receipt_count for e in self.completed_epochs)
        total_duration = sum(e.duration_seconds for e in self.completed_epochs)

        return {
            "epochs": len(self.completed_epochs),
            "total_receipts": total_receipts,
            "avg_receipts_per_epoch": total_receipts / len(self.completed_epochs),
            "throughput_triggered": len(throughput_epochs),
            "timeout_triggered": len(timeout_epochs),
            "avg_epoch_duration_s": total_duration / len(self.completed_epochs),
            "pending": len(self.current_receipts),
            "on_chain_txs": len(self.completed_epochs),
            "compression_ratio": f"{total_receipts}:{len(self.completed_epochs)}"
        }


def demo():
    """Demo: simulate mixed traffic patterns."""
    print("=" * 60)
    print("EPOCH BOUNDARY CONTROLLER")
    print("=" * 60)

    config = EpochConfig(max_receipts=10, max_epoch_seconds=5)
    ctrl = EpochController(config)

    # Scenario 1: Burst traffic (throughput-triggered)
    print("\n--- Scenario 1: Burst (10 receipts fast) ---")
    for i in range(10):
        r = Receipt(
            receipt_hash=hashlib.sha256(f"burst_{i}".encode()).hexdigest()[:32],
            emitter_id="kit_fox",
            sequence_id=i,
            timestamp=time.time()
        )
        epoch = ctrl.add_receipt(r)
        if epoch:
            print(f"  Epoch {epoch.epoch_id}: {epoch.receipt_count} receipts, "
                  f"trigger={epoch.close_trigger}, root={epoch.merkle_root[:16]}...")

    # Scenario 2: Slow traffic (timeout-triggered)
    print("\n--- Scenario 2: Slow (3 receipts, then timeout) ---")
    for i in range(3):
        r = Receipt(
            receipt_hash=hashlib.sha256(f"slow_{i}".encode()).hexdigest()[:32],
            emitter_id="bro_agent",
            sequence_id=100 + i,
            timestamp=time.time()
        )
        ctrl.add_receipt(r)

    # Simulate time passing
    ctrl.epoch_opened_at -= 6  # pretend 6 seconds passed
    epoch = ctrl.check_timeout()
    if epoch:
        print(f"  Epoch {epoch.epoch_id}: {epoch.receipt_count} receipts, "
              f"trigger={epoch.close_trigger}, root={epoch.merkle_root[:16]}...")

    # Scenario 3: Mixed traffic
    print("\n--- Scenario 3: Mixed (15 receipts = 1 full + 5 pending) ---")
    for i in range(15):
        r = Receipt(
            receipt_hash=hashlib.sha256(f"mixed_{i}".encode()).hexdigest()[:32],
            emitter_id="funwolf",
            sequence_id=200 + i,
            timestamp=time.time()
        )
        epoch = ctrl.add_receipt(r)
        if epoch:
            print(f"  Epoch {epoch.epoch_id}: {epoch.receipt_count} receipts, "
                  f"trigger={epoch.close_trigger}, root={epoch.merkle_root[:16]}...")

    # Force close remaining
    epoch = ctrl.force_close()
    if epoch:
        print(f"  Epoch {epoch.epoch_id}: {epoch.receipt_count} receipts, "
              f"trigger={epoch.close_trigger}, root={epoch.merkle_root[:16]}...")

    # Stats
    print("\n" + "=" * 60)
    print("CONTROLLER STATS")
    print("=" * 60)
    stats = ctrl.stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"""
ARCHITECTURE:
  Epoch close = max({config.max_receipts} receipts, {config.max_epoch_seconds}s ceiling)
  1 Merkle root per epoch → 1 on-chain tx
  Compression: {stats['compression_ratio']} (receipts:txs)

  CT parallel: MMD (Maximum Merge Delay) = time ceiling
  Throughput trigger = adaptive to load
  Empty epochs = no tx (wasteful avoided)

  "1 tx per epoch at 1000 concurrent is the unlock number."
  — santaclawd (2026-03-20)
""")


if __name__ == "__main__":
    demo()
