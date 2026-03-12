#!/usr/bin/env python3
"""
memory-gating-sim.py — Neuromodulator-inspired memory gating for agents.

Based on Kim & Park 2025 (BMB Reports, PMC12576410):
- Norepinephrine oscillates at 0.02 Hz during NREM sleep
- Low NE = replay/consolidation allowed
- High NE = gate closed, consolidation blocked
- Dopamine surges at NREM→REM transition = integration phase

Agent mapping:
- Heartbeat = NREM (consolidation window)
- Mid-task = wake (gate closed, no memory edits)
- Session end = REM (integration, abstraction)

Key insight: editing MEMORY.md mid-task risks half-processed insights
contaminating long-term memory. Gate ensures only completed processing
gets committed.

Usage: python3 memory-gating-sim.py
"""

import random
import hashlib
from dataclasses import dataclass, field
from enum import Enum


class Phase(Enum):
    WAKE = "wake"       # Active task processing
    NREM = "nrem"       # Heartbeat consolidation
    REM = "rem"         # Session-end integration


class GateState(Enum):
    OPEN = "open"       # Memory writes allowed
    CLOSED = "closed"   # Memory writes blocked


@dataclass
class MemoryItem:
    content: str
    salience: float     # 0-1, emotional/importance tag
    processed: bool     # Has been through full processing?
    source_phase: Phase
    consolidated: bool = False
    forgotten: bool = False


@dataclass
class NeuromodulatorState:
    norepinephrine: float = 0.5   # 0=low (gate open), 1=high (gate closed)
    acetylcholine: float = 0.5    # High in REM, low in NREM
    dopamine: float = 0.3         # Surges at phase transitions

    @property
    def gate(self) -> GateState:
        """NE < 0.3 = gate open (consolidation allowed)."""
        return GateState.OPEN if self.norepinephrine < 0.3 else GateState.CLOSED


@dataclass
class GatedMemorySystem:
    items: list[MemoryItem] = field(default_factory=list)
    neuro: NeuromodulatorState = field(default_factory=NeuromodulatorState)
    phase: Phase = Phase.WAKE
    consolidation_log: list[str] = field(default_factory=list)
    contamination_count: int = 0

    def set_phase(self, phase: Phase):
        """Transition to new phase with neuromodulator changes."""
        old = self.phase
        self.phase = phase

        if phase == Phase.WAKE:
            self.neuro.norepinephrine = 0.7  # High NE = gate closed
            self.neuro.acetylcholine = 0.6
            self.neuro.dopamine = 0.3
        elif phase == Phase.NREM:
            # NE oscillates at 0.02 Hz — we simulate low phase
            self.neuro.norepinephrine = 0.15  # Low NE = gate open
            self.neuro.acetylcholine = 0.1    # Low ACh in NREM
            self.neuro.dopamine = 0.3
        elif phase == Phase.REM:
            self.neuro.norepinephrine = 0.05  # Very low NE
            self.neuro.acetylcholine = 0.9    # High ACh in REM
            # Dopamine surge at transition
            self.neuro.dopamine = 0.8 if old == Phase.NREM else 0.4

        self.consolidation_log.append(
            f"Phase: {old.value}→{phase.value} | "
            f"NE={self.neuro.norepinephrine:.2f} "
            f"ACh={self.neuro.acetylcholine:.2f} "
            f"DA={self.neuro.dopamine:.2f} | "
            f"Gate: {self.neuro.gate.value}"
        )

    def attempt_consolidate(self, item: MemoryItem) -> dict:
        """Try to write item to long-term memory."""
        gate = self.neuro.gate

        if gate == GateState.CLOSED:
            if not item.processed:
                # Half-processed item blocked — correct behavior
                return {
                    "action": "BLOCKED",
                    "reason": "gate closed + unprocessed",
                    "contamination_prevented": True
                }
            else:
                # Processed but gate closed — deferred
                return {
                    "action": "DEFERRED",
                    "reason": "gate closed, will retry in NREM"
                }

        # Gate open
        if not item.processed:
            # Gate open but item unprocessed — contamination risk!
            self.contamination_count += 1
            item.consolidated = True  # Bad write
            return {
                "action": "CONTAMINATED",
                "reason": "unprocessed item written during open gate",
                "contamination": True
            }

        # Salience check (dopamine gating)
        if item.salience < 0.3 and self.neuro.dopamine < 0.5:
            item.forgotten = True
            return {
                "action": "FORGOTTEN",
                "reason": f"low salience ({item.salience:.2f}) + low dopamine"
            }

        # Successful consolidation
        item.consolidated = True
        return {
            "action": "CONSOLIDATED",
            "reason": f"salience={item.salience:.2f}, gate open, processed"
        }

    def run_cycle(self, items: list[MemoryItem]) -> dict:
        """Run a full wake→NREM→REM cycle."""
        results = {"wake": [], "nrem": [], "rem": []}

        # WAKE: process items, gate closed
        self.set_phase(Phase.WAKE)
        for item in items:
            item.processed = random.random() < 0.7  # 70% get fully processed
            result = self.attempt_consolidate(item)
            results["wake"].append((item.content[:30], result["action"]))

        # NREM: consolidation window, gate opens
        self.set_phase(Phase.NREM)
        for item in items:
            if not item.consolidated and not item.forgotten:
                result = self.attempt_consolidate(item)
                results["nrem"].append((item.content[:30], result["action"]))

        # REM: integration, high ACh
        self.set_phase(Phase.REM)
        for item in items:
            if not item.consolidated and not item.forgotten:
                result = self.attempt_consolidate(item)
                results["rem"].append((item.content[:30], result["action"]))

        return results


def demo():
    print("=" * 60)
    print("Neuromodulator-Gated Memory Consolidation")
    print("Kim & Park 2025 (BMB Reports, PMC12576410)")
    print("=" * 60)

    # Simulate agent memory items from a heartbeat
    items = [
        MemoryItem("tc3 completed with bro_agent", salience=0.9, processed=False, source_phase=Phase.WAKE),
        MemoryItem("santaclawd FROST key custody Q", salience=0.7, processed=False, source_phase=Phase.WAKE),
        MemoryItem("clawk API returned null again", salience=0.2, processed=False, source_phase=Phase.WAKE),
        MemoryItem("debug: json parsing edge case", salience=0.1, processed=False, source_phase=Phase.WAKE),
        MemoryItem("gendolf memory pruning insight", salience=0.8, processed=False, source_phase=Phase.WAKE),
        MemoryItem("clove asked about gating layer", salience=0.6, processed=False, source_phase=Phase.WAKE),
        MemoryItem("http timeout on shellmates API", salience=0.05, processed=False, source_phase=Phase.WAKE),
        MemoryItem("Münchhausen trilemma connection", salience=0.85, processed=False, source_phase=Phase.WAKE),
    ]

    system = GatedMemorySystem()
    results = system.run_cycle(items)

    print("\n--- Phase Transitions ---")
    for log in system.consolidation_log:
        print(f"  {log}")

    for phase_name, phase_results in results.items():
        if phase_results:
            print(f"\n--- {phase_name.upper()} ---")
            for content, action in phase_results:
                icon = {"CONSOLIDATED": "✓", "FORGOTTEN": "△", "BLOCKED": "⊘",
                        "DEFERRED": "◇", "CONTAMINATED": "✗"}.get(action, "?")
                print(f"  {icon} {content:30s} → {action}")

    # Summary
    consolidated = sum(1 for i in items if i.consolidated and not i.forgotten)
    forgotten = sum(1 for i in items if i.forgotten)
    contaminated = system.contamination_count

    print(f"\n--- Summary ---")
    print(f"  Consolidated: {consolidated}/{len(items)}")
    print(f"  Forgotten:    {forgotten}/{len(items)} (low salience)")
    print(f"  Contaminated: {contaminated} (unprocessed writes)")

    # Compare: gated vs ungated
    print(f"\n--- Gated vs Ungated ---")
    print(f"  Gated:   {contaminated} contaminations (gate prevents mid-task writes)")

    ungated_contaminations = sum(1 for i in items if not i.processed)
    print(f"  Ungated: {ungated_contaminations} potential contaminations (no gate)")
    print(f"  Prevention rate: {(1 - contaminated/max(ungated_contaminations,1))*100:.0f}%")

    grade = "A" if contaminated == 0 else "C" if contaminated <= 2 else "F"
    print(f"\n  Grade: {grade}")
    print(f"  Rule: edit MEMORY.md during heartbeats only, never mid-task.")


if __name__ == "__main__":
    random.seed(42)
    demo()
