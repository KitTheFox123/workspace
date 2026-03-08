#!/usr/bin/env python3
"""graceful-degradation-sim.py — Staged degradation simulator for agent trust.

Models NASA ATC graceful degradation framework (Edwards & Lee 2018)
applied to agent trust states: NOMINAL → WARN → ALERT → HALT → DEAD.

Each state has:
- Allowed operations (full → constrained → read-only → none)
- Recovery windows (how long principal has to intervene)
- Compound failure detection (multi-category causes)

Transitions triggered by three-signal verdict: liveness × intent × drift.

Usage:
    python3 graceful-degradation-sim.py [--demo] [--simulate CYCLES]
"""

import argparse
import json
import random
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class TrustState(Enum):
    NOMINAL = "NOMINAL"
    WARN = "WARN"
    ALERT = "ALERT"  
    HALT = "HALT"
    DEAD = "DEAD"


@dataclass
class StateConfig:
    state: TrustState
    allowed_ops: str
    recovery_window_minutes: int
    escalation_trigger: str
    de_escalation_trigger: str


STATE_CONFIGS = {
    TrustState.NOMINAL: StateConfig(
        TrustState.NOMINAL, "full", 0,
        "Single signal failure OR drift detected",
        "N/A (already nominal)"
    ),
    TrustState.WARN: StateConfig(
        TrustState.WARN, "constrained (no writes to external)", 60,
        "Second signal failure OR warn timeout",
        "All 3 signals pass for 2 consecutive cycles"
    ),
    TrustState.ALERT: StateConfig(
        TrustState.ALERT, "read-only + telemetry", 15,
        "Third signal failure OR alert timeout OR compound event",
        "Principal manual intervention + 2 signals pass"
    ),
    TrustState.HALT: StateConfig(
        TrustState.HALT, "none (frozen)", 5,
        "Halt timeout (no principal response)",
        "Principal re-signs scope cert"
    ),
    TrustState.DEAD: StateConfig(
        TrustState.DEAD, "none (requires new provisioning)", 0,
        "N/A (terminal)",
        "Full re-provisioning by principal"
    ),
}


@dataclass
class SignalState:
    liveness: bool = True
    intent: bool = True
    drift: bool = True
    
    @property
    def passing_count(self) -> int:
        return sum([self.liveness, self.intent, self.drift])
    
    @property
    def verdict(self) -> str:
        if self.passing_count == 3:
            return "HEALTHY"
        if self.passing_count == 0:
            return "COMPROMISED"
        if self.liveness and self.intent and not self.drift:
            return "MASKING"
        if self.liveness and not self.intent and self.drift:
            return "SHADOW_OP"
        if not self.liveness and self.intent and self.drift:
            return "INFRA_FAILURE"
        return "DEGRADED"


@dataclass
class CycleRecord:
    cycle: int
    state: str
    signals: dict
    verdict: str
    transition: Optional[str]
    allowed_ops: str


def simulate(cycles: int, failure_prob: float = 0.15, 
             compound_prob: float = 0.05, recovery_prob: float = 0.3) -> dict:
    """Run degradation simulation."""
    state = TrustState.NOMINAL
    consecutive_nominal = 0
    cycles_in_state = 0
    records: List[CycleRecord] = []
    
    for i in range(cycles):
        # Generate signals
        signals = SignalState(
            liveness=random.random() > failure_prob,
            intent=random.random() > failure_prob,
            drift=random.random() > (failure_prob * 1.5)  # drift more common
        )
        
        # Compound failure (correlated)
        if random.random() < compound_prob:
            signals.liveness = False
            signals.intent = False
        
        # Recovery attempts in degraded states
        if state != TrustState.NOMINAL and random.random() < recovery_prob:
            signals = SignalState(True, True, True)
        
        old_state = state
        verdict = signals.verdict
        passing = signals.passing_count
        
        # State transitions
        if state == TrustState.NOMINAL:
            if passing <= 1:
                state = TrustState.ALERT
            elif passing == 2:
                state = TrustState.WARN
            consecutive_nominal = passing == 3
            
        elif state == TrustState.WARN:
            if passing == 3:
                consecutive_nominal += 1
                if consecutive_nominal >= 2:
                    state = TrustState.NOMINAL
                    consecutive_nominal = 0
            elif passing <= 1:
                state = TrustState.ALERT
            else:
                consecutive_nominal = 0
                cycles_in_state += 1
                if cycles_in_state > 4:  # timeout
                    state = TrustState.ALERT
                    
        elif state == TrustState.ALERT:
            if passing == 3:  # principal intervention simulated
                state = TrustState.WARN
                consecutive_nominal = 0
            elif passing == 0:
                state = TrustState.HALT
            else:
                cycles_in_state += 1
                if cycles_in_state > 3:
                    state = TrustState.HALT
                    
        elif state == TrustState.HALT:
            if passing == 3:  # re-provisioning
                state = TrustState.WARN
                consecutive_nominal = 0
            else:
                cycles_in_state += 1
                if cycles_in_state > 2:
                    state = TrustState.DEAD
                    
        elif state == TrustState.DEAD:
            pass  # terminal
        
        if state != old_state:
            cycles_in_state = 0
            
        transition = f"{old_state.value}→{state.value}" if state != old_state else None
        config = STATE_CONFIGS[state]
        
        records.append(CycleRecord(
            cycle=i + 1,
            state=state.value,
            signals={"liveness": signals.liveness, "intent": signals.intent, "drift": signals.drift},
            verdict=verdict,
            transition=transition,
            allowed_ops=config.allowed_ops
        ))
    
    # Summary
    state_counts = {}
    for r in records:
        state_counts[r.state] = state_counts.get(r.state, 0) + 1
    
    transitions = [r.transition for r in records if r.transition]
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "cycles": cycles,
            "failure_prob": failure_prob,
            "compound_prob": compound_prob,
            "recovery_prob": recovery_prob
        },
        "state_distribution": state_counts,
        "transitions": transitions,
        "total_transitions": len(transitions),
        "reached_dead": any(r.state == "DEAD" for r in records),
        "nominal_pct": round(state_counts.get("NOMINAL", 0) / cycles * 100, 1),
        "records": [asdict(r) for r in records],
        "key_insight": "Compound failures (correlated signal loss) cause rapid escalation. "
                      "Recovery requires consecutive passing cycles, not just one good heartbeat."
    }


def demo():
    """Run demo simulation."""
    print("=" * 60)
    print("GRACEFUL DEGRADATION SIMULATOR")
    print("NASA ATC model → Agent trust states")
    print("=" * 60)
    
    result = simulate(30, failure_prob=0.2, compound_prob=0.08)
    
    print(f"\nSimulated {result['config']['cycles']} heartbeat cycles")
    print(f"Failure probability: {result['config']['failure_prob']}")
    print(f"Compound failure rate: {result['config']['compound_prob']}")
    print()
    
    for r in result["records"]:
        signals = r["signals"]
        sig_str = f"L:{'✓' if signals['liveness'] else '✗'} I:{'✓' if signals['intent'] else '✗'} D:{'✓' if signals['drift'] else '✗'}"
        trans = f" → {r['transition']}" if r['transition'] else ""
        print(f"  [{r['cycle']:2d}] {r['state']:8s} {sig_str}  {r['verdict']:15s}{trans}")
    
    print(f"\nState distribution: {result['state_distribution']}")
    print(f"Total transitions: {result['total_transitions']}")
    print(f"Reached DEAD: {result['reached_dead']}")
    print(f"Nominal %: {result['nominal_pct']}%")
    print(f"\nInsight: {result['key_insight']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Graceful degradation simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--simulate", type=int, default=30, help="Number of cycles")
    parser.add_argument("--failure-prob", type=float, default=0.15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(simulate(args.simulate, args.failure_prob), indent=2))
    else:
        demo()
