#!/usr/bin/env python3
"""
grace-epoch-sim.py — Grace epoch vs async DPSS ceremony comparison.

Grace epoch: TTL-bounded share validity, no coordination needed.
DPSS ceremony: full reshare protocol, O(n²) worst case.

Thesis: grace epochs handle 90%+ of cases with zero coordination.
Ceremonies only needed on detected compromise.

Based on:
- D-FROST (Cimatti et al 2024): sync reshare
- Hu et al 2025 (Beihang/NTU): async DPSS, O(n) optimistic, 1.9-8s

Usage: python3 grace-epoch-sim.py
"""

import random
from dataclasses import dataclass


@dataclass
class EpochEvent:
    epoch: int
    event_type: str  # "grace_expire", "compromise_detected", "ceremony", "partition"
    cost_messages: int
    latency_ms: float
    shares_valid: bool


def simulate_grace_epochs(n_epochs: int, n_parties: int, compromise_rate: float = 0.05):
    """Simulate grace epoch lifecycle."""
    events = []
    ceremonies_needed = 0

    for epoch in range(n_epochs):
        compromised = random.random() < compromise_rate
        partitioned = random.random() < 0.02  # 2% partition rate

        if compromised:
            # Need ceremony — can't just let shares expire
            ceremonies_needed += 1
            # Hu et al 2025: O(n) optimistic, O(n²) worst
            if partitioned:
                cost = n_parties ** 2  # worst case
                latency = 8000  # 8s worst case
            else:
                cost = n_parties  # optimistic
                latency = 1900  # 1.9s optimistic
            events.append(EpochEvent(epoch, "ceremony", cost, latency, True))
        elif partitioned:
            # Grace epoch handles partition — shares still valid until TTL
            events.append(EpochEvent(epoch, "partition_grace", 0, 0, True))
        else:
            # Normal epoch — shares expire naturally, zero coordination
            events.append(EpochEvent(epoch, "grace_expire", 0, 0, True))

    return events, ceremonies_needed


def compare_strategies(n_epochs=1000, n_parties=5):
    """Compare always-ceremony vs grace-epoch-first."""
    print("=" * 60)
    print("Grace Epoch vs Always-Ceremony Comparison")
    print(f"Epochs: {n_epochs}, Parties: {n_parties}")
    print("=" * 60)

    # Strategy 1: Always ceremony (sync D-FROST every epoch)
    always_cost = n_epochs * n_parties  # O(n) per epoch
    always_latency = n_epochs * 1900  # 1.9s per epoch

    # Strategy 2: Grace epoch + ceremony only on compromise
    random.seed(42)
    events, ceremonies = simulate_grace_epochs(n_epochs, n_parties)

    grace_cost = sum(e.cost_messages for e in events)
    grace_latency = sum(e.latency_ms for e in events)
    grace_types = {}
    for e in events:
        grace_types[e.event_type] = grace_types.get(e.event_type, 0) + 1

    print(f"\n{'Strategy':<25} {'Messages':>10} {'Latency (s)':>12} {'Ceremonies':>10}")
    print("-" * 60)
    print(f"{'Always ceremony':<25} {always_cost:>10,} {always_latency/1000:>12,.1f} {n_epochs:>10,}")
    print(f"{'Grace + on-demand':<25} {grace_cost:>10,} {grace_latency/1000:>12,.1f} {ceremonies:>10,}")

    savings_msg = (1 - grace_cost / always_cost) * 100 if always_cost > 0 else 0
    savings_lat = (1 - grace_latency / always_latency) * 100 if always_latency > 0 else 0

    print(f"\n{'Savings':<25} {savings_msg:>9.1f}% {savings_lat:>11.1f}%")

    print(f"\nEpoch breakdown:")
    for etype, count in sorted(grace_types.items()):
        pct = count / n_epochs * 100
        print(f"  {etype:<25} {count:>5} ({pct:.1f}%)")

    # Scale analysis
    print(f"\n{'=' * 60}")
    print("Scale analysis (at n=64 parties):")
    for compromise_rate in [0.01, 0.05, 0.10, 0.20]:
        random.seed(42)
        events, cere = simulate_grace_epochs(1000, 64, compromise_rate)
        total_msg = sum(e.cost_messages for e in events)
        always_msg = 1000 * 64
        saving = (1 - total_msg / always_msg) * 100
        print(f"  {compromise_rate*100:.0f}% compromise rate: {cere} ceremonies, {saving:.1f}% message savings")

    print(f"\n{'=' * 60}")
    print("INSIGHT:")
    print("Grace epochs = zero coordination for clean epochs.")
    print("Ceremonies = expensive but rare (only on compromise).")
    print("Optimistic protocol for normal times, ceremony for crisis.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    compare_strategies()
