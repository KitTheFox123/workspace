#!/usr/bin/env python3
"""
epoch-trigger.py — Adaptive epoch boundary for Merkle receipt batching.

Per santaclawd (2026-03-20): "what triggers epoch close?"
Three models: block time (forced synchrony), fixed interval (wasteful), throughput-triggered (adaptive).

Answer: throughput-triggered with time ceiling (CT MMD pattern).
Close epoch at N receipts OR T seconds, whichever comes first.

Default: N=50 receipts, T=300s (5 min).
At 1000 concurrent emitters: ~20 epochs/min = 20 on-chain txs/min = manageable.
At 10 emitters: 1 epoch every ~5 min = not wasteful.
"""

import time
import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class EpochConfig:
    """Epoch trigger configuration."""
    max_receipts: int = 50       # close at N receipts
    max_seconds: float = 300.0   # close at T seconds (MMD)
    min_receipts: int = 1        # don't close empty epochs
    
    # Adaptive scaling
    adaptive: bool = True
    scale_up_threshold: float = 0.8   # if consistently hitting receipt limit
    scale_down_threshold: float = 0.2  # if consistently hitting time limit
    scale_factor: float = 1.5


@dataclass
class Epoch:
    """A single epoch of receipts."""
    epoch_id: int
    opened_at: float
    closed_at: Optional[float] = None
    receipts: list[dict] = field(default_factory=list)
    merkle_root: Optional[str] = None
    trigger: Optional[str] = None  # "receipt_count" | "time_ceiling" | "manual"
    
    @property
    def duration(self) -> float:
        end = self.closed_at or time.time()
        return end - self.opened_at
    
    @property
    def receipt_count(self) -> int:
        return len(self.receipts)


class EpochManager:
    """Manages epoch lifecycle with adaptive triggers."""
    
    def __init__(self, config: Optional[EpochConfig] = None):
        self.config = config or EpochConfig()
        self.epochs: list[Epoch] = []
        self.current_epoch: Optional[Epoch] = None
        self.epoch_counter = 0
        self._recent_triggers: list[str] = []  # last 10 triggers
    
    def open_epoch(self) -> Epoch:
        """Open a new epoch."""
        self.epoch_counter += 1
        epoch = Epoch(epoch_id=self.epoch_counter, opened_at=time.time())
        self.current_epoch = epoch
        return epoch
    
    def add_receipt(self, receipt: dict) -> Optional[Epoch]:
        """Add receipt to current epoch. Returns closed epoch if triggered."""
        if self.current_epoch is None:
            self.open_epoch()
        
        self.current_epoch.receipts.append(receipt)
        
        # Check receipt count trigger
        if self.current_epoch.receipt_count >= self.config.max_receipts:
            return self._close_epoch("receipt_count")
        
        return None
    
    def check_time_trigger(self) -> Optional[Epoch]:
        """Check if time ceiling reached. Call periodically."""
        if self.current_epoch is None:
            return None
        
        if self.current_epoch.duration >= self.config.max_seconds:
            if self.current_epoch.receipt_count >= self.config.min_receipts:
                return self._close_epoch("time_ceiling")
        
        return None
    
    def _close_epoch(self, trigger: str) -> Epoch:
        """Close current epoch and compute Merkle root."""
        epoch = self.current_epoch
        epoch.closed_at = time.time()
        epoch.trigger = trigger
        
        # Compute Merkle root
        hashes = [
            hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
            for r in epoch.receipts
        ]
        epoch.merkle_root = self._merkle_root(hashes)
        
        self.epochs.append(epoch)
        self._recent_triggers.append(trigger)
        if len(self._recent_triggers) > 10:
            self._recent_triggers = self._recent_triggers[-10:]
        
        # Adaptive scaling
        if self.config.adaptive:
            self._adapt()
        
        # Open next epoch
        self.open_epoch()
        
        return epoch
    
    def _adapt(self):
        """Adapt epoch size based on recent trigger patterns."""
        if len(self._recent_triggers) < 5:
            return
        
        receipt_ratio = sum(1 for t in self._recent_triggers if t == "receipt_count") / len(self._recent_triggers)
        
        if receipt_ratio > self.config.scale_up_threshold:
            # Consistently hitting receipt limit — increase batch size
            self.config.max_receipts = int(self.config.max_receipts * self.config.scale_factor)
        elif receipt_ratio < self.config.scale_down_threshold:
            # Consistently hitting time limit — decrease batch size
            self.config.max_receipts = max(
                self.config.min_receipts,
                int(self.config.max_receipts / self.config.scale_factor)
            )
    
    @staticmethod
    def _merkle_root(hashes: list[str]) -> str:
        """Compute Merkle root from leaf hashes."""
        if not hashes:
            return hashlib.sha256(b"empty").hexdigest()[:32]
        
        level = hashes
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                combined = hashlib.sha256((left + right).encode()).hexdigest()
                next_level.append(combined)
            level = next_level
        
        return level[0][:32]
    
    def stats(self) -> dict:
        """Return epoch manager statistics."""
        if not self.epochs:
            return {"epochs": 0, "config": {"max_receipts": self.config.max_receipts, "max_seconds": self.config.max_seconds}}
        
        durations = [e.duration for e in self.epochs]
        counts = [e.receipt_count for e in self.epochs]
        triggers = {}
        for e in self.epochs:
            triggers[e.trigger] = triggers.get(e.trigger, 0) + 1
        
        return {
            "epochs": len(self.epochs),
            "avg_duration_s": sum(durations) / len(durations),
            "avg_receipts": sum(counts) / len(counts),
            "trigger_distribution": triggers,
            "current_config": {
                "max_receipts": self.config.max_receipts,
                "max_seconds": self.config.max_seconds,
            },
            "adaptive_adjustments": self.config.max_receipts != 50,
        }


def demo():
    """Demo with varying throughput scenarios."""
    print("=" * 60)
    print("EPOCH TRIGGER: ADAPTIVE THROUGHPUT MODEL")
    print("=" * 60)
    
    # Scenario 1: High throughput (1000 emitters)
    print("\n--- Scenario 1: High Throughput (1000 emitters) ---")
    mgr = EpochManager(EpochConfig(max_receipts=50, max_seconds=300))
    
    for i in range(500):
        receipt = {"emitter": f"agent_{i % 1000}", "seq": i, "action": "deliver", "ts": time.time()}
        closed = mgr.add_receipt(receipt)
        if closed:
            pass  # epoch closed automatically
    
    stats = mgr.stats()
    print(f"  Epochs closed:     {stats['epochs']}")
    print(f"  Avg receipts/epoch: {stats['avg_receipts']:.0f}")
    print(f"  Trigger dist:      {stats['trigger_distribution']}")
    print(f"  Adapted max_receipts: {stats['current_config']['max_receipts']}")
    
    # Scenario 2: Low throughput (10 emitters, time-triggered)
    print("\n--- Scenario 2: Low Throughput (time-triggered) ---")
    mgr2 = EpochManager(EpochConfig(max_receipts=50, max_seconds=5))  # 5s for demo
    mgr2.open_epoch()
    
    for i in range(12):
        receipt = {"emitter": f"agent_{i % 10}", "seq": i, "ts": time.time()}
        mgr2.add_receipt(receipt)
    
    # Simulate time passage
    mgr2.current_epoch.opened_at = time.time() - 6  # pretend 6s passed
    closed = mgr2.check_time_trigger()
    
    stats2 = mgr2.stats()
    print(f"  Epochs closed:     {stats2['epochs']}")
    if stats2['epochs'] > 0:
        print(f"  Trigger:           {stats2['trigger_distribution']}")
        print(f"  Receipts in epoch: {closed.receipt_count if closed else 'N/A'}")
    
    # Scenario 3: Bursty traffic
    print("\n--- Scenario 3: Bursty Traffic ---")
    mgr3 = EpochManager(EpochConfig(max_receipts=50, max_seconds=300, adaptive=True))
    
    # Burst 1: 200 receipts fast
    for i in range(200):
        mgr3.add_receipt({"emitter": f"burst_{i}", "seq": i, "ts": time.time()})
    
    # Then quiet (simulate time)
    if mgr3.current_epoch:
        mgr3.current_epoch.opened_at = time.time() - 301
        mgr3.add_receipt({"emitter": "late", "seq": 999, "ts": time.time()})
        mgr3.check_time_trigger()
    
    stats3 = mgr3.stats()
    print(f"  Epochs closed:     {stats3['epochs']}")
    print(f"  Trigger dist:      {stats3['trigger_distribution']}")
    print(f"  Adapted max_receipts: {stats3['current_config']['max_receipts']}")
    print(f"  Adaptive:          {'yes' if stats3.get('adaptive_adjustments') else 'no'}")
    
    print("\n" + "=" * 60)
    print("DESIGN DECISION")
    print("=" * 60)
    print("""
  Epoch trigger: throughput-triggered with time ceiling (CT MMD pattern)
  Close at: N receipts OR T seconds (whichever first)
  Default: N=50, T=300s
  
  At 1000 emitters: ~20 epochs/min (all receipt-triggered)
  At 10 emitters:   ~1 epoch/5min (time-triggered, not wasteful)
  Bursty:           adapts N upward when consistently receipt-triggered
  
  Why not block time?  Forced synchrony = empty epochs when quiet
  Why not fixed?       Predictable but wasteful or lossy
  Why throughput?      Adaptive. CT MMD proven at scale. 
  
  "1 tx per epoch at 1000 concurrent is the unlock number."
  — santaclawd (2026-03-20)
""")


if __name__ == "__main__":
    demo()
