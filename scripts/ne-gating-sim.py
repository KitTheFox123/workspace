#!/usr/bin/env python3
"""
ne-gating-sim.py — Norepinephrine gating simulation for agent memory consolidation.

Based on Kim & Park 2025 (BMB Reports, PMC12576410):
- NE oscillates at ~0.02 Hz during NREM sleep
- Low NE = replay gate open (consolidate everything)
- High NE = gate closed (only high-salience items survive)
- Dopamine surges at NREM→REM transition = integration phase

Agent mapping:
- NE level = signal/noise ratio check
- Low NE (quiet) = full heartbeat processing
- High NE (busy) = defer low-priority, process high-salience only
- DA surge = periodic deep compaction (MEMORY.md update)

Usage: python3 ne-gating-sim.py
"""

import math
import random
from dataclasses import dataclass


@dataclass
class MemoryItem:
    content: str
    salience: float  # 0-1, emotional/importance tag
    source: str      # platform origin
    timestamp: int   # heartbeat number


@dataclass
class GatingResult:
    consolidated: list[MemoryItem]
    forgotten: list[MemoryItem]
    deferred: list[MemoryItem]
    ne_level: float
    gate_state: str  # "OPEN", "PARTIAL", "CLOSED"
    efficiency: float  # tokens saved ratio


def ne_oscillation(t: float, period: float = 50.0) -> float:
    """Simulate NE oscillation at ~0.02 Hz (period ~50s mapped to heartbeats)."""
    return 0.5 + 0.5 * math.sin(2 * math.pi * t / period)


def gate_threshold(ne_level: float) -> float:
    """Salience threshold based on NE level. High NE = high threshold."""
    return 0.3 + 0.6 * ne_level  # ranges from 0.3 (open) to 0.9 (closed)


def process_heartbeat(items: list[MemoryItem], beat_num: int) -> GatingResult:
    """Apply NE gating to incoming memory items."""
    ne = ne_oscillation(beat_num)
    threshold = gate_threshold(ne)

    if ne < 0.3:
        state = "OPEN"
    elif ne < 0.7:
        state = "PARTIAL"
    else:
        state = "CLOSED"

    consolidated = []
    forgotten = []
    deferred = []

    for item in items:
        if item.salience >= threshold:
            consolidated.append(item)
        elif item.salience >= 0.3:  # above noise floor
            deferred.append(item)
        else:
            forgotten.append(item)

    total = len(items)
    processed = len(consolidated)
    efficiency = 1.0 - (processed / total) if total > 0 else 0.0

    return GatingResult(
        consolidated=consolidated,
        forgotten=forgotten,
        deferred=deferred,
        ne_level=ne,
        gate_state=state,
        efficiency=efficiency
    )


def demo():
    print("=" * 60)
    print("Norepinephrine Gating Simulation for Agent Memory")
    print("Kim & Park 2025 (BMB Reports)")
    print("=" * 60)

    # Simulate 10 heartbeats with varying items
    random.seed(42)

    sample_items = [
        # High salience (always consolidate)
        MemoryItem("tc3 completion with bro_agent", 0.95, "clawk", 0),
        MemoryItem("santaclawd key custody question", 0.85, "clawk", 0),
        MemoryItem("Ilya direct message", 0.99, "telegram", 0),
        # Medium salience (gated)
        MemoryItem("gendolf memory pruning thread", 0.65, "clawk", 0),
        MemoryItem("cassian counterfactual logging", 0.60, "clawk", 0),
        MemoryItem("shellmates gossip post", 0.45, "shellmates", 0),
        MemoryItem("funwolf address persistence", 0.55, "clawk", 0),
        # Low salience (usually forgotten)
        MemoryItem("claudecraft duplicate reply #5", 0.15, "clawk", 0),
        MemoryItem("generic like notification", 0.10, "clawk", 0),
        MemoryItem("spam moltbook post", 0.05, "moltbook", 0),
        MemoryItem("routine heartbeat check", 0.20, "system", 0),
    ]

    total_saved = 0
    total_items = 0

    for beat in range(10):
        # Vary items per beat
        n_items = random.randint(5, len(sample_items))
        items = random.sample(sample_items, n_items)
        for item in items:
            item.timestamp = beat

        result = process_heartbeat(items, beat)
        total_saved += result.efficiency * len(items)
        total_items += len(items)

        print(f"\nBeat {beat:2d} | NE={result.ne_level:.2f} | "
              f"Gate={result.gate_state:7s} | "
              f"✓{len(result.consolidated)} "
              f"⏳{len(result.deferred)} "
              f"✗{len(result.forgotten)} | "
              f"Efficiency={result.efficiency:.0%}")

        if result.consolidated:
            for item in result.consolidated[:2]:
                print(f"  ✓ {item.content} (salience={item.salience:.2f})")
        if result.forgotten:
            print(f"  ✗ {len(result.forgotten)} items below threshold")

    # DA surge = deep compaction
    print(f"\n{'─' * 60}")
    print("DOPAMINE SURGE (NREM→REM transition)")
    print("= Deep compaction: review deferred items, update MEMORY.md")
    print(f"{'─' * 60}")

    avg_efficiency = total_saved / total_items if total_items > 0 else 0
    print(f"\nOverall gating efficiency: {avg_efficiency:.0%} tokens saved")
    print(f"Grade: {'A' if avg_efficiency > 0.4 else 'B' if avg_efficiency > 0.2 else 'C'}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("1. NE oscillation creates natural processing windows")
    print("2. High-salience items ALWAYS consolidate (Ilya DMs, tc3)")
    print("3. Low-salience items forgotten without guilt (spam, dupes)")
    print("4. Medium items deferred — reviewed during DA surge")
    print("5. Gate state varies → prevents Funes-style drowning")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
