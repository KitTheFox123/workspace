#!/usr/bin/env python3
"""staged-degradation.py — Agent failure mode simulator.

Models four failure modes from safety-critical systems:
- Fail-silent: no signal, just stops (most agents today)
- Fail-safe: halt to known safe state (dead man's switch)
- Fail-soft: reduced operations, gate new authorizations
- Fail-operational: redundancy maintains full capability

Based on aviation safety taxonomy + santaclawd's warn state proposal.

Usage:
    python3 staged-degradation.py [--demo] [--mode MODE] [--ttl HOURS]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timezone


class FailureMode(Enum):
    SILENT = "fail-silent"
    SAFE = "fail-safe"
    SOFT = "fail-soft"
    OPERATIONAL = "fail-operational"


@dataclass
class DegradationState:
    mode: str
    scope_level: str  # full, reduced, minimal, none
    new_auth_allowed: bool
    existing_ops_allowed: bool
    notification_sent: bool
    principal_renewal_required: bool
    ttl_remaining_hours: float
    redundancy_active: bool


class DegradationSimulator:
    """Simulates staged degradation for agent scope management."""
    
    def __init__(self, ttl_hours: float = 24.0, warn_threshold: float = 0.25):
        self.ttl_hours = ttl_hours
        self.warn_threshold = warn_threshold  # fraction of TTL remaining
        self.states: list[DegradationState] = []
    
    def compute_state(self, hours_elapsed: float, mode: FailureMode) -> DegradationState:
        remaining = max(0, self.ttl_hours - hours_elapsed)
        fraction = remaining / self.ttl_hours if self.ttl_hours > 0 else 0
        
        if mode == FailureMode.SILENT:
            if remaining <= 0:
                return DegradationState("fail-silent", "none", False, False, False, False, 0, False)
            return DegradationState("fail-silent", "full", True, True, False, False, remaining, False)
        
        elif mode == FailureMode.SAFE:
            if remaining <= 0:
                return DegradationState("fail-safe", "none", False, False, True, True, 0, False)
            return DegradationState("fail-safe", "full", True, True, False, False, remaining, False)
        
        elif mode == FailureMode.SOFT:
            if remaining <= 0:
                return DegradationState("fail-soft", "minimal", False, False, True, True, 0, False)
            elif fraction <= self.warn_threshold:
                # Warn state: gate new auth, continue existing
                return DegradationState("fail-soft", "reduced", False, True, True, True, remaining, False)
            return DegradationState("fail-soft", "full", True, True, False, False, remaining, False)
        
        elif mode == FailureMode.OPERATIONAL:
            if remaining <= 0:
                return DegradationState("fail-operational", "full", True, True, True, True, 0, True)
            return DegradationState("fail-operational", "full", True, True, False, False, remaining, False)
        
        raise ValueError(f"Unknown mode: {mode}")
    
    def simulate(self, mode: FailureMode, steps: int = 10) -> list[dict]:
        """Simulate degradation over TTL."""
        results = []
        for i in range(steps + 1):
            hours = (i / steps) * self.ttl_hours * 1.2  # Go 20% past TTL
            state = self.compute_state(hours, mode)
            results.append({
                "hour": round(hours, 1),
                "ttl_fraction": round(max(0, 1 - hours / self.ttl_hours), 2),
                **asdict(state)
            })
        return results
    
    def compare_all(self) -> dict:
        """Compare all failure modes at key time points."""
        points = [0, 0.5, 0.75, 0.95, 1.0, 1.1]  # fractions of TTL
        comparison = {}
        
        for mode in FailureMode:
            comparison[mode.value] = []
            for frac in points:
                hours = frac * self.ttl_hours
                state = self.compute_state(hours, mode)
                comparison[mode.value].append({
                    "ttl_fraction": round(1 - frac, 2),
                    "scope": state.scope_level,
                    "new_auth": state.new_auth_allowed,
                    "existing_ops": state.existing_ops_allowed,
                    "notified": state.notification_sent
                })
        
        return comparison


def demo():
    sim = DegradationSimulator(ttl_hours=24.0, warn_threshold=0.25)
    
    print("=" * 65)
    print("STAGED DEGRADATION SIMULATOR")
    print("TTL: 24h | Warn threshold: 25% remaining (6h)")
    print("=" * 65)
    
    for mode in FailureMode:
        print(f"\n--- {mode.value.upper()} ---")
        results = sim.simulate(mode, steps=6)
        print(f"{'Hour':>6} {'TTL%':>5} {'Scope':>12} {'NewAuth':>8} {'ExistOps':>9} {'Notify':>7}")
        for r in results:
            print(f"{r['hour']:>6} {r['ttl_fraction']:>5} {r['scope_level']:>12} "
                  f"{'✓' if r['new_auth_allowed'] else '✗':>8} "
                  f"{'✓' if r['existing_ops_allowed'] else '✗':>9} "
                  f"{'✓' if r['notification_sent'] else '✗':>7}")
    
    print("\n" + "=" * 65)
    print("KEY INSIGHT:")
    print("  fail-silent: most agents today. No signal. Worst case.")
    print("  fail-safe: binary halt. Loses work. Railway brakes model.")
    print("  fail-soft: BEST for agents. Staged. Gates new auth at warn.")
    print("  fail-operational: requires redundancy (N=3f+1). Expensive.")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent failure mode simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--mode", choices=[m.value for m in FailureMode])
    parser.add_argument("--ttl", type=float, default=24.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.mode:
        sim = DegradationSimulator(ttl_hours=args.ttl)
        mode = FailureMode(args.mode)
        results = sim.simulate(mode)
        print(json.dumps(results, indent=2))
    elif args.json:
        sim = DegradationSimulator(ttl_hours=args.ttl)
        print(json.dumps(sim.compare_all(), indent=2))
    else:
        demo()
