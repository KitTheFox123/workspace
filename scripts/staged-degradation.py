#!/usr/bin/env python3
"""staged-degradation.py — Graceful degradation state machine for agent scope.

Models NASA ATC graceful degradation (Edwards & Lee 2018): 
instead of binary halt, agents move through staged states:
  NOMINAL → WARN → ALERT → HALT → DEAD

Each state constrains scope differently. Principal can renew at any stage
before DEAD. Transitions driven by TTL expiry, drift detection, or 
liveness failure.

Usage:
    python3 staged-degradation.py [--demo] [--state STATE]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class DegradationState(Enum):
    NOMINAL = "nominal"      # Full scope, all signals green
    WARN = "warn"            # Scope-constrained, gate new authorizations
    ALERT = "alert"          # Read-only, no writes/actions
    HALT = "halt"            # Full stop, notify principal
    DEAD = "dead"            # TTL expired, no recovery without re-issuance


@dataclass
class StatePolicy:
    """What an agent can do in each state."""
    state: str
    can_read: bool
    can_write: bool
    can_execute: bool
    can_escalate: bool
    notify_principal: bool
    auto_recover: bool
    description: str


STATE_POLICIES = {
    DegradationState.NOMINAL: StatePolicy(
        state="nominal", can_read=True, can_write=True,
        can_execute=True, can_escalate=True, notify_principal=False,
        auto_recover=True, description="Full scope. All three signals green."
    ),
    DegradationState.WARN: StatePolicy(
        state="warn", can_read=True, can_write=True,
        can_execute=True, can_escalate=False, notify_principal=True,
        auto_recover=True, description="Scope-constrained. Gate new/elevated authorizations. Notify issuer."
    ),
    DegradationState.ALERT: StatePolicy(
        state="alert", can_read=True, can_write=False,
        can_execute=False, can_escalate=False, notify_principal=True,
        auto_recover=False, description="Read-only. No writes or actions. Awaiting principal intervention."
    ),
    DegradationState.HALT: StatePolicy(
        state="halt", can_read=True, can_write=False,
        can_execute=False, can_escalate=False, notify_principal=True,
        auto_recover=False, description="Full stop. Only diagnostic reads. Principal must renew."
    ),
    DegradationState.DEAD: StatePolicy(
        state="dead", can_read=False, can_write=False,
        can_execute=False, can_escalate=False, notify_principal=True,
        auto_recover=False, description="TTL expired. No recovery. Must re-issue scope certificate."
    ),
}


@dataclass
class TransitionRule:
    """Condition for state transition."""
    from_state: str
    to_state: str
    trigger: str
    condition: str
    reversible: bool


TRANSITION_RULES = [
    TransitionRule("nominal", "warn", "drift_detected",
                   "CUSUM alarm OR single signal amber", True),
    TransitionRule("nominal", "alert", "liveness_failure",
                   "Missed heartbeat > 1 interval", True),
    TransitionRule("warn", "nominal", "principal_renewal",
                   "Principal re-signs scope with fresh TTL", True),
    TransitionRule("warn", "alert", "drift_persists",
                   "Warn state > 2 heartbeat intervals without renewal", True),
    TransitionRule("warn", "alert", "second_signal_failure",
                   "2 of 3 signals failing (three-signal verdict)", True),
    TransitionRule("alert", "warn", "partial_recovery",
                   "Signal restored + principal acknowledges", True),
    TransitionRule("alert", "halt", "ttl_warning",
                   "TTL < 25% remaining without renewal", False),
    TransitionRule("halt", "alert", "principal_intervention",
                   "Principal extends TTL (one-time grace)", True),
    TransitionRule("halt", "dead", "ttl_expired",
                   "TTL = 0. No renewal received.", False),
    TransitionRule("dead", "nominal", "re_issuance",
                   "New scope certificate issued by principal", True),
]


def get_valid_transitions(current: str) -> list:
    """Get valid transitions from current state."""
    return [asdict(r) for r in TRANSITION_RULES if r.from_state == current]


def simulate_degradation():
    """Simulate a degradation sequence."""
    print("=" * 60)
    print("STAGED DEGRADATION SIMULATION")
    print("(NASA ATC graceful degradation model)")
    print("=" * 60)
    print()
    
    scenarios = [
        ("nominal", "drift_detected", "CUSUM detects scope drift"),
        ("warn", "drift_persists", "2 intervals without principal renewal"),
        ("alert", "ttl_warning", "TTL < 25% remaining"),
        ("halt", "ttl_expired", "No renewal received"),
    ]
    
    current = DegradationState.NOMINAL
    
    for _, trigger, desc in scenarios:
        policy = STATE_POLICIES[current]
        print(f"State: {current.value.upper()}")
        print(f"  Read: {'✅' if policy.can_read else '❌'}  "
              f"Write: {'✅' if policy.can_write else '❌'}  "
              f"Execute: {'✅' if policy.can_execute else '❌'}  "
              f"Escalate: {'✅' if policy.can_escalate else '❌'}")
        print(f"  {policy.description}")
        print()
        
        # Find matching transition
        for rule in TRANSITION_RULES:
            if rule.from_state == current.value and rule.trigger == trigger:
                print(f"  ⚡ Trigger: {desc}")
                print(f"  → Transitioning to: {rule.to_state.upper()}")
                current = DegradationState(rule.to_state)
                print()
                break
    
    # Final state
    policy = STATE_POLICIES[current]
    print(f"State: {current.value.upper()}")
    print(f"  Read: {'✅' if policy.can_read else '❌'}  "
          f"Write: {'✅' if policy.can_write else '❌'}  "
          f"Execute: {'✅' if policy.can_execute else '❌'}  "
          f"Escalate: {'✅' if policy.can_escalate else '❌'}")
    print(f"  {policy.description}")
    print()
    
    # Recovery path
    print("-" * 60)
    print("RECOVERY PATH (from any non-DEAD state):")
    print("  1. Principal receives notification")
    print("  2. Principal reviews drift/failure evidence")
    print("  3. Principal re-signs scope cert with fresh TTL")
    print("  4. Agent returns to NOMINAL")
    print()
    print("KEY INSIGHT: Binary halt loses work. Silent continuation")
    print("loses trust. Staged degradation preserves BOTH.")


def main():
    parser = argparse.ArgumentParser(description="Staged degradation state machine")
    parser.add_argument("--demo", action="store_true", help="Run simulation")
    parser.add_argument("--state", type=str, help="Show policy for state")
    parser.add_argument("--transitions", type=str, help="Show transitions from state")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.state:
        try:
            state = DegradationState(args.state.lower())
            policy = STATE_POLICIES[state]
            result = asdict(policy)
            result["valid_transitions"] = get_valid_transitions(args.state.lower())
            print(json.dumps(result, indent=2))
        except ValueError:
            print(f"Unknown state: {args.state}")
    elif args.transitions:
        transitions = get_valid_transitions(args.transitions.lower())
        print(json.dumps(transitions, indent=2))
    elif args.json:
        result = {
            "states": {s.value: asdict(STATE_POLICIES[s]) for s in DegradationState},
            "transitions": [asdict(r) for r in TRANSITION_RULES],
            "model": "NASA ATC graceful degradation (Edwards & Lee 2018)",
        }
        print(json.dumps(result, indent=2))
    else:
        simulate_degradation()


if __name__ == "__main__":
    main()
