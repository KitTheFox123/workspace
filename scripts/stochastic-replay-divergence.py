#!/usr/bin/env python3
"""
stochastic-replay-divergence.py — Detects where agent replay diverges from original execution.

The problem: Event sourcing (Fowler 2005) assumes deterministic replay.
LLM agents are stochastic — same WAL + different temperature = different state.
Databases solve this because SQL is declarative. Agent decisions are not.

Solution: Hash decisions alongside events. Replay and compare decision hashes.
Divergence point = where the bug lives, even if you can't reproduce the exact failure.

Based on:
- Fowler (2005): Event Sourcing
- Helland (2015): Immutability Changes Everything
- Fidge (1988): Vector clocks for causal ordering
- Lamport (1978): Logical clocks
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass 
class WALEntry:
    lsn: int                    # Log sequence number
    agent_id: str
    stimulus: str               # What the agent saw
    stimulus_hash: str          # Hash of input
    decision: str               # What the agent chose
    decision_hash: str          # Hash of output — key for divergence detection
    vector_clock: dict          # Causal ordering
    prev_hash: str              # Chain integrity


@dataclass
class ReplayResult:
    original_lsn: int
    original_decision_hash: str
    replay_decision_hash: str
    diverged: bool
    divergence_type: str = ""   # "stochastic", "context_drift", "missing_state"


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def simulate_original_execution(agent_id: str, n_events: int, seed: int = 42) -> list[WALEntry]:
    """Simulate an original agent execution with WAL."""
    rng = random.Random(seed)
    entries = []
    prev_hash = "genesis"
    vc = {agent_id: 0}
    
    stimuli = [
        "user asks about weather",
        "API returns 500 error",
        "new email from collaborator",
        "scheduled heartbeat fires",
        "feed contains interesting post",
        "match on shellmates",
        "trust score drops below threshold",
        "concurrent write detected",
    ]
    
    for i in range(n_events):
        vc[agent_id] = vc.get(agent_id, 0) + 1
        stimulus = rng.choice(stimuli)
        # Original decision — deterministic for this seed
        decision = f"action_{rng.randint(1, 100)}_{stimulus[:10]}"
        
        entry = WALEntry(
            lsn=i,
            agent_id=agent_id,
            stimulus=stimulus,
            stimulus_hash=hash_content(stimulus),
            decision=decision,
            decision_hash=hash_content(decision),
            vector_clock=dict(vc),
            prev_hash=prev_hash,
        )
        prev_hash = hash_content(f"{entry.lsn}:{entry.decision_hash}:{entry.prev_hash}")
        entries.append(entry)
    
    return entries


def replay_execution(original: list[WALEntry], 
                     divergence_rate: float = 0.0,
                     divergence_type: str = "stochastic",
                     seed: int = 99) -> list[ReplayResult]:
    """Replay WAL and detect divergence points."""
    rng = random.Random(seed)
    results = []
    
    for entry in original:
        if rng.random() < divergence_rate:
            # Diverged — different decision for same stimulus
            if divergence_type == "stochastic":
                # Temperature/sampling difference
                replay_decision = f"action_{rng.randint(1, 100)}_{entry.stimulus[:10]}"
            elif divergence_type == "context_drift":
                # Context window shifted — agent sees different history
                replay_decision = f"context_shifted_{entry.stimulus[:10]}"
            elif divergence_type == "missing_state":
                # State from external source unavailable on replay
                replay_decision = f"state_missing_{entry.stimulus[:10]}"
            else:
                replay_decision = entry.decision
            
            replay_hash = hash_content(replay_decision)
            diverged = replay_hash != entry.decision_hash
        else:
            replay_hash = entry.decision_hash
            diverged = False
        
        results.append(ReplayResult(
            original_lsn=entry.lsn,
            original_decision_hash=entry.decision_hash,
            replay_decision_hash=replay_hash,
            diverged=diverged,
            divergence_type=divergence_type if diverged else "none",
        ))
    
    return results


def analyze_divergence(results: list[ReplayResult]) -> dict:
    """Analyze replay divergence pattern."""
    total = len(results)
    diverged = [r for r in results if r.diverged]
    n_div = len(diverged)
    
    if n_div == 0:
        return {
            "total_events": total,
            "diverged": 0,
            "rate": 0.0,
            "first_divergence": None,
            "grade": "A",
            "diagnosis": "DETERMINISTIC_REPLAY",
        }
    
    first = diverged[0].original_lsn
    
    # Check if divergence cascades (each divergence makes next more likely)
    gaps = []
    for i in range(1, len(diverged)):
        gaps.append(diverged[i].original_lsn - diverged[i-1].original_lsn)
    
    cascading = False
    if len(gaps) >= 3:
        # Decreasing gaps = cascading divergence
        cascading = all(gaps[i] <= gaps[i-1] for i in range(1, len(gaps)))
    
    rate = n_div / total
    
    if rate < 0.05:
        grade, diag = "B", "MINOR_STOCHASTIC_NOISE"
    elif rate < 0.15:
        grade, diag = "C", "MODERATE_DIVERGENCE"
    elif rate < 0.3:
        grade, diag = "D", "SIGNIFICANT_DIVERGENCE"
    else:
        grade, diag = "F", "REPLAY_IMPOSSIBLE"
    
    if cascading:
        grade = "F"
        diag = "CASCADING_DIVERGENCE"
    
    return {
        "total_events": total,
        "diverged": n_div,
        "rate": rate,
        "first_divergence": first,
        "cascading": cascading,
        "grade": grade,
        "diagnosis": diag,
    }


def main():
    print("=" * 70)
    print("STOCHASTIC REPLAY DIVERGENCE DETECTOR")
    print("Fowler (2005): Event sourcing assumes deterministic replay")
    print("Agent replay is stochastic — detect divergence, don't prevent it")
    print("=" * 70)
    
    # Generate original execution
    original = simulate_original_execution("kit_fox", 50)
    
    scenarios = [
        ("deterministic_replay", 0.0, "stochastic"),
        ("low_temperature_noise", 0.05, "stochastic"),
        ("moderate_stochastic", 0.15, "stochastic"),
        ("context_window_drift", 0.20, "context_drift"),
        ("missing_external_state", 0.25, "missing_state"),
        ("high_temperature", 0.40, "stochastic"),
    ]
    
    print(f"\n{'Scenario':<25} {'Grade':<6} {'Rate':<8} {'First':<8} {'Cascade':<9} {'Diagnosis'}")
    print("-" * 70)
    
    for name, rate, dtype in scenarios:
        results = replay_execution(original, rate, dtype)
        analysis = analyze_divergence(results)
        cascade = analysis.get("cascading", False)
        first = analysis["first_divergence"]
        first_str = str(first) if first is not None else "-"
        print(f"{name:<25} {analysis['grade']:<6} {analysis['rate']:<8.1%} "
              f"{first_str:<8} {'YES' if cascade else 'no':<9} {analysis['diagnosis']}")
    
    print("\n--- Key Insight ---")
    print("Database WAL: replay(log) = same state. Guaranteed.")
    print("Agent WAL:    replay(log) ≠ same state. Stochastic.")
    print()
    print("The fix: hash DECISIONS alongside EVENTS in the WAL.")
    print("  stimulus_hash = what the agent saw")
    print("  decision_hash = what the agent chose")
    print("  Divergence point = where replay decision_hash != original")
    print()
    print("This turns 'I can\\'t reproduce the bug' into")
    print("'The bug is at LSN 7 where the agent chose differently.'")
    print()
    print("Vector clocks (Fidge 1988) handle the multi-agent case:")
    print("  Concurrent events are NOT bugs — they are design.")
    print("  Causal violations ARE bugs — event B depends on A but A missing.")


if __name__ == "__main__":
    main()
