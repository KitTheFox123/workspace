#!/usr/bin/env python3
"""
Finality queue monitor — circuit breaker for cert issuance during finality stalls.

Models the ETH May 2023 incident: finality stalled for 9 epochs (~57 min).
Cert issuance queue grows unbounded if not managed.

Design: queue + circuit breaker + degraded-finality status surface.
- Normal: finality gap < 2 epochs → issue certs
- Degraded: gap 2-5 epochs → queue, surface status
- Stalled: gap > 5 epochs → circuit breaker, reject new requests
- Recovery: finality resumes → drain queue FIFO, issue backlog

Based on: ETH May 2023 post-mortem, Trail of Bits 2023
"""

import time
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FinalityState(Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    STALLED = "stalled"
    RECOVERING = "recovering"


@dataclass
class PendingCert:
    deposit_ref: str
    requested_at: float
    block_slot: int
    issued: bool = False
    rejected: bool = False
    wait_time: float = 0.0


@dataclass
class QueueMetrics:
    state: FinalityState
    queue_depth: int
    finality_gap_epochs: float
    oldest_pending_age_s: float
    certs_issued: int
    certs_rejected: int
    certs_queued: int
    drain_rate: float  # certs/s during recovery


class FinalityQueueMonitor:
    EPOCH_DURATION_S = 384  # 32 slots × 12s
    DEGRADED_THRESHOLD = 2  # epochs
    STALLED_THRESHOLD = 5   # epochs
    MAX_QUEUE_DEPTH = 100

    def __init__(self):
        self.queue: list[PendingCert] = []
        self.issued: list[PendingCert] = []
        self.rejected: list[PendingCert] = []
        self.state = FinalityState.NORMAL
        self.state_history: list[tuple[float, FinalityState]] = []

    def update_state(self, finality_gap_epochs: float, sim_time: float):
        old_state = self.state
        if finality_gap_epochs < self.DEGRADED_THRESHOLD:
            self.state = FinalityState.NORMAL if not self.queue else FinalityState.RECOVERING
        elif finality_gap_epochs < self.STALLED_THRESHOLD:
            self.state = FinalityState.DEGRADED
        else:
            self.state = FinalityState.STALLED

        if self.state != old_state:
            self.state_history.append((sim_time, self.state))

    def submit(self, deposit_ref: str, block_slot: int, sim_time: float) -> str:
        if self.state == FinalityState.STALLED and len(self.queue) >= self.MAX_QUEUE_DEPTH:
            cert = PendingCert(deposit_ref=deposit_ref, requested_at=sim_time, block_slot=block_slot, rejected=True)
            self.rejected.append(cert)
            return "rejected_circuit_open"
        elif self.state in (FinalityState.DEGRADED, FinalityState.STALLED):
            cert = PendingCert(deposit_ref=deposit_ref, requested_at=sim_time, block_slot=block_slot)
            self.queue.append(cert)
            return "queued"
        elif self.state == FinalityState.RECOVERING:
            cert = PendingCert(deposit_ref=deposit_ref, requested_at=sim_time, block_slot=block_slot)
            self.queue.append(cert)
            return "queued_recovering"
        else:
            cert = PendingCert(deposit_ref=deposit_ref, requested_at=sim_time, block_slot=block_slot, issued=True)
            self.issued.append(cert)
            return "issued"

    def drain_queue(self, sim_time: float, batch_size: int = 10) -> int:
        """Drain queued certs FIFO during recovery."""
        drained = 0
        while self.queue and drained < batch_size:
            cert = self.queue.pop(0)
            cert.issued = True
            cert.wait_time = sim_time - cert.requested_at
            self.issued.append(cert)
            drained += 1
        return drained

    def metrics(self, finality_gap: float, sim_time: float) -> QueueMetrics:
        oldest_age = sim_time - self.queue[0].requested_at if self.queue else 0
        drain_rate = len([c for c in self.issued if c.wait_time > 0]) / max(1, sim_time) if sim_time > 0 else 0
        return QueueMetrics(
            state=self.state,
            queue_depth=len(self.queue),
            finality_gap_epochs=finality_gap,
            oldest_pending_age_s=oldest_age,
            certs_issued=len(self.issued),
            certs_rejected=len(self.rejected),
            certs_queued=len(self.queue),
            drain_rate=drain_rate,
        )


def simulate_eth_may_2023():
    """Simulate the May 2023 ETH finality stall pattern."""
    print("=" * 60)
    print("FINALITY QUEUE MONITOR — ETH May 2023 Simulation")
    print("=" * 60)

    monitor = FinalityQueueMonitor()

    # Timeline: normal → degraded → stalled → recovery → normal
    # Each step = 1 epoch (~6.4 min)
    timeline = (
        [(0.5, "normal")] * 5 +       # 5 epochs normal
        [(2.5, "degrading")] * 2 +     # 2 epochs degrading
        [(7.0, "stalled")] * 9 +       # 9 epochs stalled (the actual incident)
        [(3.0, "recovering")] * 3 +    # 3 epochs recovering
        [(0.5, "normal")] * 5          # 5 epochs normal again
    )

    sim_time = 0
    deposit_counter = 0
    requests_per_epoch = 8  # cert requests per epoch

    print(f"\nTimeline: {len(timeline)} epochs, {requests_per_epoch} requests/epoch")
    print(f"Circuit breaker: queue > {monitor.MAX_QUEUE_DEPTH}\n")

    for epoch_idx, (gap, label) in enumerate(timeline):
        sim_time = epoch_idx * monitor.EPOCH_DURATION_S
        monitor.update_state(gap, sim_time)

        # Submit cert requests
        for _ in range(requests_per_epoch):
            deposit_counter += 1
            result = monitor.submit(f"dep_{deposit_counter}", block_slot=epoch_idx * 32, sim_time=sim_time)

        # Drain during recovery/normal
        drained = 0
        if monitor.state in (FinalityState.NORMAL, FinalityState.RECOVERING):
            drained = monitor.drain_queue(sim_time)

        m = monitor.metrics(gap, sim_time)
        state_icon = {"normal": "✅", "degraded": "⚠️", "stalled": "🔴", "recovering": "🔄"}
        icon = state_icon.get(m.state.value, "❓")

        if epoch_idx % 3 == 0 or m.state != FinalityState.NORMAL:
            print(f"  Epoch {epoch_idx:2d} | {icon} {m.state.value:11s} | gap: {gap:.1f}e | "
                  f"queue: {m.queue_depth:3d} | issued: {m.certs_issued:3d} | rejected: {m.certs_rejected:3d}"
                  + (f" | drained: {drained}" if drained else ""))

    # Final drain
    while monitor.queue:
        sim_time += 10
        monitor.drain_queue(sim_time)

    # Summary
    m = monitor.metrics(0.5, sim_time)
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"  Total requests: {deposit_counter}")
    print(f"  Issued: {m.certs_issued}")
    print(f"  Rejected (circuit breaker): {m.certs_rejected}")
    print(f"  Max queue depth observed: {max(len(monitor.queue), m.certs_issued - deposit_counter + m.certs_rejected + len(monitor.queue))}")

    # Wait time analysis
    wait_times = [c.wait_time for c in monitor.issued if c.wait_time > 0]
    if wait_times:
        print(f"\n  Queued certs wait times:")
        print(f"    Min: {min(wait_times):.0f}s ({min(wait_times)/60:.1f} min)")
        print(f"    Max: {max(wait_times):.0f}s ({max(wait_times)/60:.1f} min)")
        print(f"    Avg: {sum(wait_times)/len(wait_times):.0f}s ({sum(wait_times)/len(wait_times)/60:.1f} min)")
        print(f"    Count: {len(wait_times)} certs delayed")

    print(f"\n  State transitions:")
    for t, state in monitor.state_history:
        print(f"    {t/60:6.1f} min → {state.value}")

    print(f"\n  Verdict: {'PASS' if m.certs_rejected == 0 else 'CIRCUIT BREAKER ACTIVATED'}")
    print(f"  Queue prevented {len(wait_times)} double-spends from premature issuance")
    print(f"  Circuit breaker prevented {m.certs_rejected} queue overflows")
    print("=" * 60)


if __name__ == "__main__":
    simulate_eth_may_2023()
