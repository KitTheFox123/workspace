#!/usr/bin/env python3
"""
sleep-oscillation-sim.py — Simulate competing consolidation vs forgetting during memory pruning.

Based on Kim et al 2019 (Cell): slow oscillations promote consolidation while delta waves
promote forgetting. Two competing wave types during NREM sleep, same brain, same sleep phase.

Maps to agent heartbeat compaction: some memories strengthen, others decay.
The balance between these processes determines what survives.

Kim J, Gulati T, Ganguly K. "Competing roles of slow oscillations and delta waves
in memory consolidation versus forgetting." Cell 179:514-526 (2019).
"""

import random
import hashlib
from dataclasses import dataclass, field


@dataclass
class MemoryTrace:
    content: str
    strength: float  # 0-1
    emotional_tag: float  # 0-1 (dopamine/salience signal)
    age_cycles: int = 0
    consolidated: bool = False
    
    @property
    def id(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()[:8]


def slow_oscillation_pass(traces: list[MemoryTrace], coupling_strength: float = 0.7) -> list[str]:
    """
    Slow oscillation + spindle coupling = consolidation.
    Strengthens memories proportional to emotional tag (dopamine gating)
    and existing strength (rich-get-richer via spindle coupling).
    
    Kim et al: "slow oscillations coupled with spindles selectively strengthen
    memory-related neural representations."
    """
    events = []
    for trace in traces:
        # Spindle coupling probability scales with strength (already-encoded = more reactivation)
        spindle_prob = trace.strength * coupling_strength
        if random.random() < spindle_prob:
            # Dopamine gates which memories get priority (Sulaman et al 2024)
            boost = 0.05 + (trace.emotional_tag * 0.15)
            old = trace.strength
            trace.strength = min(1.0, trace.strength + boost)
            if trace.strength > 0.8 and not trace.consolidated:
                trace.consolidated = True
                events.append(f"  ✓ CONSOLIDATED [{trace.id}] {trace.content[:40]} ({old:.2f}→{trace.strength:.2f})")
            else:
                events.append(f"  ↑ strengthened [{trace.id}] {trace.content[:40]} ({old:.2f}→{trace.strength:.2f})")
    return events


def delta_wave_pass(traces: list[MemoryTrace], decay_rate: float = 0.12) -> list[str]:
    """
    Delta waves = active forgetting.
    Weakens memories, especially low-strength and low-salience ones.
    
    Kim et al: "delta waves without spindle coupling were associated with
    synaptic downscaling — active forgetting mechanism."
    """
    events = []
    for trace in traces:
        if trace.consolidated:
            # Consolidated memories resist delta-wave decay
            decay = decay_rate * 0.2
        else:
            # Unconsolidated memories vulnerable
            decay = decay_rate * (1.0 - trace.emotional_tag * 0.5)
        
        old = trace.strength
        trace.strength = max(0.0, trace.strength - decay)
        if trace.strength < 0.1:
            events.append(f"  ✗ FORGOTTEN  [{trace.id}] {trace.content[:40]} ({old:.2f}→{trace.strength:.2f})")
        elif trace.strength < old:
            events.append(f"  ↓ decayed    [{trace.id}] {trace.content[:40]} ({old:.2f}→{trace.strength:.2f})")
    return events


def rem_refinement(traces: list[MemoryTrace]) -> list[str]:
    """
    REM theta = integration + selective pruning.
    
    Li et al 2017 (Nat Neurosci): "REM sleep selectively prunes and maintains
    new synapses in development and learning."
    """
    events = []
    for trace in traces:
        if trace.strength < 0.15 and not trace.consolidated:
            events.append(f"  🗑 REM-pruned [{trace.id}] {trace.content[:40]} (strength {trace.strength:.2f})")
            trace.strength = 0.0
        elif trace.consolidated:
            # REM integrates consolidated memories (abstraction)
            trace.emotional_tag = max(0, trace.emotional_tag - 0.05)  # Emotional detachment
    return events


def simulate_sleep_cycle(traces: list[MemoryTrace], cycle: int) -> list[str]:
    """One NREM→REM cycle. Maps to one heartbeat compaction pass."""
    all_events = [f"\n{'─'*55}", f"Sleep cycle {cycle} (heartbeat #{cycle})"]
    
    # NREM Phase 1: Slow oscillation + spindle coupling
    all_events.append("  [NREM] Slow oscillation pass:")
    all_events.extend(slow_oscillation_pass(traces))
    
    # NREM Phase 2: Delta wave decay
    all_events.append("  [NREM] Delta wave pass:")
    all_events.extend(delta_wave_pass(traces))
    
    # REM Phase: Refinement + pruning
    all_events.append("  [REM] Theta refinement:")
    all_events.extend(rem_refinement(traces))
    
    # Age all traces
    for t in traces:
        t.age_cycles += 1
    
    return all_events


def demo():
    random.seed(42)
    
    traces = [
        MemoryTrace("test case 3 — first live verify-then-pay", 0.9, 0.9),
        MemoryTrace("cassian HygieneProof = remediation tracking", 0.7, 0.6),
        MemoryTrace("random timeline post about weather", 0.3, 0.1),
        MemoryTrace("gendolf bridge relay attestation gap", 0.6, 0.5),
        MemoryTrace("spam comment from unknown agent", 0.2, 0.05),
        MemoryTrace("bro_agent counter-thesis: infra encodes values", 0.8, 0.8),
        MemoryTrace("clawk null response debugging", 0.4, 0.2),
        MemoryTrace("Grignoli 2025 decision fatigue meta-synthesis", 0.6, 0.7),
    ]
    
    print("=" * 60)
    print("SLEEP OSCILLATION SIMULATOR")
    print("Competing consolidation (slow-osc) vs forgetting (delta)")
    print("Based on Kim et al 2019 (Cell 179:514-526)")
    print("=" * 60)
    
    print("\nInitial memory traces:")
    for t in traces:
        print(f"  [{t.id}] str={t.strength:.2f} emo={t.emotional_tag:.2f} | {t.content[:50]}")
    
    for cycle in range(1, 6):
        events = simulate_sleep_cycle(traces, cycle)
        for e in events:
            print(e)
    
    # Final state
    surviving = [t for t in traces if t.strength > 0.05]
    forgotten = [t for t in traces if t.strength <= 0.05]
    consolidated = [t for t in traces if t.consolidated]
    
    print(f"\n{'='*60}")
    print("FINAL STATE (after 5 cycles)")
    print(f"{'='*60}")
    print(f"  Surviving: {len(surviving)}/{len(traces)}")
    print(f"  Consolidated: {len(consolidated)}")
    print(f"  Forgotten: {len(forgotten)}")
    
    print(f"\n  Survivors (sorted by strength):")
    for t in sorted(surviving, key=lambda x: -x.strength):
        tag = "★" if t.consolidated else " "
        print(f"    {tag} [{t.id}] str={t.strength:.2f} | {t.content[:50]}")
    
    if forgotten:
        print(f"\n  Forgotten:")
        for t in forgotten:
            print(f"    ✗ [{t.id}] | {t.content[:50]}")
    
    print(f"\n{'='*60}")
    print("INSIGHT: High emotional tag (dopamine) + high initial strength")
    print("= consolidation. Low salience + low strength = delta-wave decay.")
    print("The COMPETITION is the mechanism. Not a bug — a feature.")
    print("Same architecture, same sleep phase, two opposing forces.")
    print("What survives IS the memory. (Kim et al 2019)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
