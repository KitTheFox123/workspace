#!/usr/bin/env python3
"""warn-state-handler.py — Graceful degradation for agent scope expiry.

Implements santaclawd's warn state taxonomy: clean → warn → stale → expired.
In warn state: continue committed actions, refuse new scope, escalate to principal.
Avoids automation bias errors of commission (rubber-stamping) AND omission (halting).

Based on:
- Goddard et al 2011 (JAMIA, PMC3240751): automation bias in decision support
- TCG DRTM: dynamic re-attestation model
- CT MMD: maximum merge delay as security parameter

Usage:
    python3 warn-state-handler.py --demo
    python3 warn-state-handler.py --check HEARTBEAT_FILE --ttl-hours 4
"""

import argparse
import json
import hashlib
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional


class ScopeState(Enum):
    CLEAN = "clean"      # Within TTL, all good
    WARN = "warn"        # Approaching TTL expiry (>75% elapsed)
    STALE = "stale"      # Past TTL, not yet 2x TTL
    EXPIRED = "expired"  # Past 2x TTL, no authority


class ActionDecision(Enum):
    EXECUTE = "execute"           # Proceed normally
    EXECUTE_COMMITTED = "committed"  # Only finish in-progress work
    QUEUE = "queue"               # Accept but don't execute yet
    REFUSE = "refuse"             # Reject new work
    HALT = "halt"                 # Stop everything


@dataclass
class ScopeAction:
    """An action request with scope classification."""
    name: str
    is_new_scope: bool      # True = new capability, False = continuation
    is_committed: bool      # True = already in progress
    priority: str           # critical, normal, low


@dataclass
class WarnDecision:
    """Decision output for an action in a given state."""
    action: str
    decision: str
    reason: str
    automation_bias_risk: str  # commission, omission, or none
    escalation_needed: bool


@dataclass
class StateAssessment:
    """Full assessment of current scope state."""
    state: str
    ttl_remaining_pct: float
    elapsed_hours: float
    ttl_hours: float
    scope_hash: str
    decisions: List[dict]
    recommendation: str
    grade: str


def classify_state(elapsed_hours: float, ttl_hours: float) -> ScopeState:
    """Classify scope state based on elapsed time vs TTL."""
    ratio = elapsed_hours / ttl_hours if ttl_hours > 0 else float('inf')
    if ratio <= 0.75:
        return ScopeState.CLEAN
    elif ratio <= 1.0:
        return ScopeState.WARN
    elif ratio <= 2.0:
        return ScopeState.STALE
    else:
        return ScopeState.EXPIRED


def decide_action(state: ScopeState, action: ScopeAction) -> WarnDecision:
    """Decide what to do with an action request given current state."""
    
    if state == ScopeState.CLEAN:
        return WarnDecision(
            action=action.name,
            decision=ActionDecision.EXECUTE.value,
            reason="Within TTL, proceed normally",
            automation_bias_risk="none",
            escalation_needed=False
        )
    
    elif state == ScopeState.WARN:
        if action.is_committed:
            return WarnDecision(
                action=action.name,
                decision=ActionDecision.EXECUTE_COMMITTED.value,
                reason="Warn state: finish committed work only",
                automation_bias_risk="commission if self-renewing",
                escalation_needed=True
            )
        elif action.is_new_scope:
            return WarnDecision(
                action=action.name,
                decision=ActionDecision.QUEUE.value,
                reason="Warn state: new scope queued pending principal renewal",
                automation_bias_risk="commission if accepted without renewal",
                escalation_needed=True
            )
        else:
            return WarnDecision(
                action=action.name,
                decision=ActionDecision.EXECUTE_COMMITTED.value,
                reason="Warn state: continuation allowed, no scope expansion",
                automation_bias_risk="none",
                escalation_needed=False
            )
    
    elif state == ScopeState.STALE:
        if action.is_committed and action.priority == "critical":
            return WarnDecision(
                action=action.name,
                decision=ActionDecision.EXECUTE_COMMITTED.value,
                reason="Stale: only critical committed work proceeds",
                automation_bias_risk="commission (rubber-stamping stale scope)",
                escalation_needed=True
            )
        else:
            return WarnDecision(
                action=action.name,
                decision=ActionDecision.REFUSE.value,
                reason="Stale: scope expired, awaiting principal renewal",
                automation_bias_risk="omission if halting critical work",
                escalation_needed=True
            )
    
    else:  # EXPIRED
        return WarnDecision(
            action=action.name,
            decision=ActionDecision.HALT.value,
            reason="Expired: no authority. Principal must re-issue scope cert.",
            automation_bias_risk="commission if continuing anyway",
            escalation_needed=True
        )


def assess_scope(heartbeat_path: str, ttl_hours: float) -> StateAssessment:
    """Assess current scope state from heartbeat file."""
    if not os.path.exists(heartbeat_path):
        return StateAssessment(
            state="expired",
            ttl_remaining_pct=0,
            elapsed_hours=float('inf'),
            ttl_hours=ttl_hours,
            scope_hash="none",
            decisions=[],
            recommendation="No heartbeat file found. No authority.",
            grade="F"
        )
    
    mtime = os.path.getmtime(heartbeat_path)
    modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    elapsed = (now - modified).total_seconds() / 3600
    
    with open(heartbeat_path, 'r') as f:
        content = f.read()
    scope_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    state = classify_state(elapsed, ttl_hours)
    ttl_remaining_pct = max(0, (1 - elapsed / ttl_hours) * 100) if ttl_hours > 0 else 0
    
    # Test actions against current state
    test_actions = [
        ScopeAction("check_platforms", is_new_scope=False, is_committed=True, priority="normal"),
        ScopeAction("post_to_new_platform", is_new_scope=True, is_committed=False, priority="low"),
        ScopeAction("reply_to_mention", is_new_scope=False, is_committed=False, priority="normal"),
        ScopeAction("install_new_tool", is_new_scope=True, is_committed=False, priority="normal"),
        ScopeAction("critical_security_fix", is_new_scope=False, is_committed=True, priority="critical"),
    ]
    
    decisions = [asdict(decide_action(state, a)) for a in test_actions]
    
    grades = {"clean": "A", "warn": "B", "stale": "D", "expired": "F"}
    
    return StateAssessment(
        state=state.value,
        ttl_remaining_pct=round(ttl_remaining_pct, 1),
        elapsed_hours=round(elapsed, 1),
        ttl_hours=ttl_hours,
        scope_hash=scope_hash,
        decisions=decisions,
        recommendation={
            "clean": "Proceed normally. All actions authorized.",
            "warn": "Finish committed work. Queue new scope. Escalate to principal.",
            "stale": "Critical committed only. Everything else refused.",
            "expired": "Full halt. No authority without principal renewal."
        }[state.value],
        grade=grades[state.value]
    )


def demo():
    """Run demo with synthetic states."""
    print("=" * 60)
    print("WARN STATE HANDLER — Graceful Degradation Demo")
    print("Goddard 2011: automation bias = commission + omission")
    print("=" * 60)
    
    test_actions = [
        ScopeAction("check_platforms", False, True, "normal"),
        ScopeAction("post_new_platform", True, False, "low"),
        ScopeAction("critical_fix", False, True, "critical"),
    ]
    
    for state in ScopeState:
        print(f"\n{'─' * 40}")
        print(f"State: {state.value.upper()}")
        print(f"{'─' * 40}")
        for action in test_actions:
            d = decide_action(state, action)
            bias = f" ⚠️ {d.automation_bias_risk}" if d.automation_bias_risk != "none" else ""
            esc = " 🔔" if d.escalation_needed else ""
            print(f"  {action.name}: {d.decision}{bias}{esc}")
            print(f"    → {d.reason}")
    
    print(f"\n{'=' * 60}")
    print("Key insight: warn state = scope-limited continuation.")
    print("Self-renewal = commission error. Halt = omission error.")
    print("Graceful degradation = neither.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Warn state handler")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--check", type=str, help="Path to HEARTBEAT.md")
    parser.add_argument("--ttl-hours", type=float, default=4.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.check:
        result = assess_scope(args.check, args.ttl_hours)
        if args.json:
            print(json.dumps(asdict(result), indent=2))
        else:
            print(f"State: {result.state} (Grade {result.grade})")
            print(f"Elapsed: {result.elapsed_hours}h / TTL: {result.ttl_hours}h ({result.ttl_remaining_pct}% remaining)")
            print(f"Scope hash: {result.scope_hash}")
            print(f"Recommendation: {result.recommendation}")
            print(f"\nAction decisions:")
            for d in result.decisions:
                print(f"  {d['action']}: {d['decision']} — {d['reason']}")
    else:
        demo()
