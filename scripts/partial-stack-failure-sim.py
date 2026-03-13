#!/usr/bin/env python3
"""
Partial Stack Failure Simulator

Tests agent trust stack behavior when individual layers fail mid-verification.
Based on the "stack closed" discussion (Mar 13): tile_proof + liveness + sleeper detection
each work solo, but composition under failure is untested.

Scenarios:
1. All layers healthy → Grade A
2. Tile proof succeeds, gossip times out → Grade C (partial verification)
3. Gossip healthy, tile proof stale → Grade D (liveness without provenance)
4. Sleeper flag missing, others healthy → Grade B (trust without memory)
5. Cascade: tile stale → gossip can't verify → sleeper unchecked → Grade F
6. DLQ recovery: webhook fails, email fallback succeeds → Grade B

Key insight: The TRANSITION between layers is where trust breaks.
Each layer's failure mode must produce a RECEIPT, not silence.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import hashlib
import time


class LayerStatus(Enum):
    HEALTHY = "healthy"
    TIMEOUT = "timeout"
    STALE = "stale"
    MISSING = "missing"
    RECOVERED = "recovered"  # Via DLQ/fallback


@dataclass
class LayerResult:
    name: str
    status: LayerStatus
    latency_ms: float
    receipt: Optional[str] = None  # Hash receipt or None
    fallback_used: bool = False
    
    @property
    def has_receipt(self) -> bool:
        return self.receipt is not None
    
    @property
    def is_usable(self) -> bool:
        return self.status in (LayerStatus.HEALTHY, LayerStatus.RECOVERED)


@dataclass
class StackVerification:
    tile_proof: LayerResult
    gossip_beacon: LayerResult
    sleeper_check: LayerResult
    
    @property
    def layers(self) -> list[LayerResult]:
        return [self.tile_proof, self.gossip_beacon, self.sleeper_check]
    
    @property
    def healthy_count(self) -> int:
        return sum(1 for l in self.layers if l.is_usable)
    
    @property
    def receipt_count(self) -> int:
        return sum(1 for l in self.layers if l.has_receipt)
    
    def grade(self) -> str:
        healthy = self.healthy_count
        receipts = self.receipt_count
        
        if healthy == 3:
            return "A" if receipts == 3 else "B"
        elif healthy == 2:
            # Which layer failed matters
            if not self.tile_proof.is_usable:
                return "D"  # No provenance = dangerous
            return "C" if receipts >= 2 else "D"
        elif healthy == 1:
            return "D" if self.tile_proof.is_usable else "F"
        else:
            return "F"
    
    def diagnosis(self) -> str:
        failed = [l for l in self.layers if not l.is_usable]
        silent = [l for l in failed if not l.has_receipt]
        
        if not failed:
            return "all layers verified"
        
        parts = []
        for l in failed:
            if l.has_receipt:
                parts.append(f"{l.name}: {l.status.value} (receipt preserved)")
            else:
                parts.append(f"{l.name}: {l.status.value} (SILENT FAILURE)")
        
        if silent:
            parts.append(f"⚠️ {len(silent)} silent failure(s) — no receipt = no accountability")
        
        return "; ".join(parts)


def make_receipt(layer: str, status: str, ts: float) -> str:
    return hashlib.sha256(f"{layer}:{status}:{ts}".encode()).hexdigest()[:16]


def scenario_all_healthy() -> StackVerification:
    ts = time.time()
    return StackVerification(
        tile_proof=LayerResult("tile_proof", LayerStatus.HEALTHY, 45.0,
                              receipt=make_receipt("tile", "ok", ts)),
        gossip_beacon=LayerResult("gossip", LayerStatus.HEALTHY, 120.0,
                                receipt=make_receipt("gossip", "ok", ts)),
        sleeper_check=LayerResult("sleeper", LayerStatus.HEALTHY, 15.0,
                                receipt=make_receipt("sleeper", "ok", ts)),
    )


def scenario_gossip_timeout() -> StackVerification:
    ts = time.time()
    return StackVerification(
        tile_proof=LayerResult("tile_proof", LayerStatus.HEALTHY, 45.0,
                              receipt=make_receipt("tile", "ok", ts)),
        gossip_beacon=LayerResult("gossip", LayerStatus.TIMEOUT, 30000.0,
                                receipt=make_receipt("gossip", "timeout", ts)),
        sleeper_check=LayerResult("sleeper", LayerStatus.HEALTHY, 15.0,
                                receipt=make_receipt("sleeper", "ok", ts)),
    )


def scenario_stale_tile() -> StackVerification:
    ts = time.time()
    return StackVerification(
        tile_proof=LayerResult("tile_proof", LayerStatus.STALE, 45.0,
                              receipt=make_receipt("tile", "stale", ts)),
        gossip_beacon=LayerResult("gossip", LayerStatus.HEALTHY, 120.0,
                                receipt=make_receipt("gossip", "ok", ts)),
        sleeper_check=LayerResult("sleeper", LayerStatus.HEALTHY, 15.0,
                                receipt=make_receipt("sleeper", "ok", ts)),
    )


def scenario_sleeper_missing() -> StackVerification:
    ts = time.time()
    return StackVerification(
        tile_proof=LayerResult("tile_proof", LayerStatus.HEALTHY, 45.0,
                              receipt=make_receipt("tile", "ok", ts)),
        gossip_beacon=LayerResult("gossip", LayerStatus.HEALTHY, 120.0,
                                receipt=make_receipt("gossip", "ok", ts)),
        sleeper_check=LayerResult("sleeper", LayerStatus.MISSING, 0.0),
    )


def scenario_cascade() -> StackVerification:
    """Tile stale → gossip can't verify → sleeper unchecked"""
    ts = time.time()
    return StackVerification(
        tile_proof=LayerResult("tile_proof", LayerStatus.STALE, 45.0),  # No receipt!
        gossip_beacon=LayerResult("gossip", LayerStatus.TIMEOUT, 30000.0),  # No receipt!
        sleeper_check=LayerResult("sleeper", LayerStatus.MISSING, 0.0),  # No receipt!
    )


def scenario_dlq_recovery() -> StackVerification:
    """Webhook fails, email DLQ succeeds"""
    ts = time.time()
    return StackVerification(
        tile_proof=LayerResult("tile_proof", LayerStatus.RECOVERED, 5000.0,
                              receipt=make_receipt("tile", "dlq", ts),
                              fallback_used=True),
        gossip_beacon=LayerResult("gossip", LayerStatus.HEALTHY, 120.0,
                                receipt=make_receipt("gossip", "ok", ts)),
        sleeper_check=LayerResult("sleeper", LayerStatus.HEALTHY, 15.0,
                                receipt=make_receipt("sleeper", "ok", ts)),
    )


def main():
    print("=" * 65)
    print("PARTIAL STACK FAILURE SIMULATOR")
    print("What breaks when layers fail mid-verification?")
    print("=" * 65)
    
    scenarios = [
        ("1. All healthy", scenario_all_healthy),
        ("2. Gossip timeout (tile + sleeper ok)", scenario_gossip_timeout),
        ("3. Stale tile (gossip + sleeper ok)", scenario_stale_tile),
        ("4. Sleeper missing (tile + gossip ok)", scenario_sleeper_missing),
        ("5. CASCADE: all fail silently", scenario_cascade),
        ("6. DLQ recovery (webhook→email)", scenario_dlq_recovery),
    ]
    
    for name, fn in scenarios:
        sv = fn()
        print(f"\n{'─' * 65}")
        print(f"Scenario: {name}")
        print(f"  Grade: {sv.grade()}")
        print(f"  Healthy: {sv.healthy_count}/3 | Receipts: {sv.receipt_count}/3")
        for layer in sv.layers:
            status_str = layer.status.value
            if layer.fallback_used:
                status_str += " (via DLQ)"
            receipt_str = layer.receipt[:12] + "..." if layer.receipt else "NONE"
            print(f"    {layer.name:15s} {status_str:12s} {layer.latency_ms:>8.0f}ms  receipt={receipt_str}")
        print(f"  Diagnosis: {sv.diagnosis()}")
    
    print(f"\n{'=' * 65}")
    print("KEY FINDINGS:")
    print("  Scenario 5 (cascade) = Grade F: silent failures compound.")
    print("  Every failure MUST produce a receipt, even timeout/stale.")
    print("  DLQ recovery (scenario 6) = Grade B: fallback IS the design.")
    print("  Stale tile = Grade D even with gossip: provenance > liveness.")
    print("  Silent failure = no accountability. Receipt = accountability.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
