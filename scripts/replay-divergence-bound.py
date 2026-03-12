#!/usr/bin/env python3
"""
replay-divergence-bound.py — Bounds on agent state reconstruction from WAL replay.

Based on:
- Stevens (SakuraSky, Nov 2025): "Deterministic Replay" — 5 nondeterminism sources
- aletheaveyra: "same WAL + different attention weights = different reconstruction"
- Meng (Harvard 2025, arXiv 2501.01475): Heisenberg for learning — can't optimize + assess

Key insight: You CANNOT PITR an agent to the same state.
You CAN verify the checkpoint wasn't adversarial.
Detect divergence, don't prevent it.

The 5 nondeterminism sources (Stevens 2025):
1. LLM sampling (temperature, top-p)
2. Model version drift (weights change between runs)
3. Tool response variability (APIs return different data)
4. Timing/ordering (race conditions in async)
5. Context window truncation (what gets evicted)
"""

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WALEntry:
    lsn: int
    action: str
    input_hash: str
    output_hash: str
    timestamp: float
    nondeterminism_sources: list[str] = field(default_factory=list)


@dataclass
class ReplayResult:
    original_state_hash: str
    replayed_state_hash: str
    divergence: float  # 0.0 = identical, 1.0 = completely different
    divergence_sources: dict[str, float] = field(default_factory=dict)
    entries_replayed: int = 0
    entries_diverged: int = 0


@dataclass
class DivergenceBound:
    """Theoretical bound on replay fidelity."""
    source: str
    min_divergence: float  # Best case
    max_divergence: float  # Worst case
    controllable: bool     # Can we eliminate this source?
    mitigation: str


# Stevens' 5 sources with divergence bounds
NONDETERMINISM_SOURCES = [
    DivergenceBound(
        source="llm_sampling",
        min_divergence=0.0,   # temperature=0
        max_divergence=0.4,   # temperature=1.0
        controllable=True,
        mitigation="Record seed + temperature=0 for replay"
    ),
    DivergenceBound(
        source="model_version",
        min_divergence=0.0,   # Pinned version
        max_divergence=0.8,   # Major version change (e.g., Opus 4.5→4.6)
        controllable=True,
        mitigation="Pin model version in WAL metadata"
    ),
    DivergenceBound(
        source="tool_responses",
        min_divergence=0.0,   # Recorded responses
        max_divergence=0.9,   # Live API calls
        controllable=True,
        mitigation="Record tool responses in WAL (event sourcing)"
    ),
    DivergenceBound(
        source="timing_ordering",
        min_divergence=0.0,   # Sequential replay
        max_divergence=0.3,   # Concurrent async
        controllable=True,
        mitigation="Lamport timestamps + causal ordering in WAL"
    ),
    DivergenceBound(
        source="context_truncation",
        min_divergence=0.05,  # Slightly different eviction
        max_divergence=0.6,   # Different context = different reasoning
        controllable=False,   # Can't fully control what model attends to
        mitigation="Hash context window state at each step (detect, don't prevent)"
    ),
]


def simulate_replay(wal: list[WALEntry], 
                     controlled_sources: set[str]) -> ReplayResult:
    """Simulate replaying a WAL with some nondeterminism sources controlled."""
    rng = random.Random(42)
    total_divergence = 0.0
    source_contributions = {}
    diverged = 0

    for entry in wal:
        entry_divergence = 0.0
        for source in NONDETERMINISM_SOURCES:
            if source.source in controlled_sources:
                contrib = source.min_divergence
            else:
                contrib = rng.uniform(source.min_divergence, source.max_divergence)

            if source.source in entry.nondeterminism_sources:
                entry_divergence = max(entry_divergence, contrib)
                source_contributions[source.source] = source_contributions.get(
                    source.source, 0) + contrib

        total_divergence += entry_divergence
        if entry_divergence > 0.1:
            diverged += 1

    n = len(wal) or 1
    avg_divergence = total_divergence / n
    for k in source_contributions:
        source_contributions[k] /= n

    # Generate state hashes
    original = hashlib.sha256(b"original_state").hexdigest()[:16]
    if avg_divergence < 0.01:
        replayed = original
    else:
        replayed = hashlib.sha256(
            f"diverged_{avg_divergence:.4f}".encode()).hexdigest()[:16]

    return ReplayResult(
        original_state_hash=original,
        replayed_state_hash=replayed,
        divergence=avg_divergence,
        divergence_sources=source_contributions,
        entries_replayed=len(wal),
        entries_diverged=diverged
    )


def generate_sample_wal(n: int = 50) -> list[WALEntry]:
    """Generate a sample WAL with realistic nondeterminism patterns."""
    rng = random.Random(123)
    wal = []
    sources = [s.source for s in NONDETERMINISM_SOURCES]

    for i in range(n):
        # Each entry has 1-3 nondeterminism sources
        entry_sources = rng.sample(sources, k=rng.randint(1, 3))
        wal.append(WALEntry(
            lsn=i,
            action=rng.choice(["llm_call", "tool_call", "memory_read", 
                               "memory_write", "decision"]),
            input_hash=hashlib.sha256(f"input_{i}".encode()).hexdigest()[:8],
            output_hash=hashlib.sha256(f"output_{i}".encode()).hexdigest()[:8],
            timestamp=1000.0 + i * 0.5,
            nondeterminism_sources=entry_sources
        ))
    return wal


def grade_replay(divergence: float) -> tuple[str, str]:
    if divergence < 0.01:
        return "A", "DETERMINISTIC"
    if divergence < 0.05:
        return "B", "NEAR_DETERMINISTIC"
    if divergence < 0.15:
        return "C", "BOUNDED_DIVERGENCE"
    if divergence < 0.3:
        return "D", "SIGNIFICANT_DIVERGENCE"
    return "F", "UNREPLAYABLE"


def main():
    print("=" * 70)
    print("REPLAY DIVERGENCE BOUND ANALYSIS")
    print("Stevens (SakuraSky 2025): 5 nondeterminism sources")
    print("aletheaveyra: 'detect divergence, dont prevent it'")
    print("=" * 70)

    # Show theoretical bounds
    print("\n--- Nondeterminism Sources ---")
    print(f"{'Source':<22} {'Min':<6} {'Max':<6} {'Ctrl':<6} {'Mitigation'}")
    print("-" * 70)
    for s in NONDETERMINISM_SOURCES:
        ctrl = "YES" if s.controllable else "NO"
        print(f"{s.source:<22} {s.min_divergence:<6.2f} {s.max_divergence:<6.2f} "
              f"{ctrl:<6} {s.mitigation[:40]}")

    # Generate sample WAL
    wal = generate_sample_wal(50)

    # Test different control strategies
    strategies = {
        "no_control": set(),
        "pin_model_only": {"model_version"},
        "record_tools": {"model_version", "tool_responses"},
        "full_event_sourcing": {"llm_sampling", "model_version", 
                                 "tool_responses", "timing_ordering"},
        "theoretical_max": {"llm_sampling", "model_version", 
                            "tool_responses", "timing_ordering",
                            "context_truncation"},  # Can't fully control this
    }

    print(f"\n--- Replay Strategies ---")
    print(f"{'Strategy':<25} {'Grade':<6} {'Divergence':<12} {'Diverged':<10} {'Diagnosis'}")
    print("-" * 70)

    for name, controlled in strategies.items():
        result = simulate_replay(wal, controlled)
        grade, diag = grade_replay(result.divergence)
        print(f"{name:<25} {grade:<6} {result.divergence:<12.4f} "
              f"{result.entries_diverged:<10} {diag}")

    # Key insight
    print("\n--- Key Insight (aletheaveyra) ---")
    print("'same WAL + different attention weights = different reconstruction'")
    print("'you cant PITR an agent to the same state'")
    print("'you can only verify the checkpoint wasnt adversarial'")
    print()
    print("Context truncation (source #5) is UNCONTROLLABLE.")
    print("Even with full event sourcing, the model's internal attention")
    print("pattern introduces irreducible divergence ≥ 0.05.")
    print()
    print("This is Meng (Harvard 2025) applied to replay:")
    print("Can't simultaneously REPLAY and VERIFY from the same evidence.")
    print("Reserve some WAL entries for verification, don't use all for replay.")
    print()
    print("Practical architecture:")
    print("  1. Record everything (full event sourcing)")
    print("  2. Accept divergence as inherent")
    print("  3. Hash checkpoint state (compaction receipt)")
    print("  4. Measure divergence on replay (diagnostic, not prevention)")
    print("  5. Flag when divergence exceeds expected bounds")


if __name__ == "__main__":
    main()
