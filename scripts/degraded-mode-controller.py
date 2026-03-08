#!/usr/bin/env python3
"""degraded-mode-controller.py — IEC 61508 graceful degradation for agents.

Models agent operational modes: CLEAN → WARN → HALT with deterministic
transitions based on scope freshness, attestation status, and principal response.

Based on IEC 61508 graceful degradation: shed non-critical functions,
preserve safety-critical ones, annunciate degraded state.

Usage:
    python3 degraded-mode-controller.py [--demo] [--state FILE]
"""

import argparse
import json
import time
import hashlib
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class Mode(str, Enum):
    CLEAN = "CLEAN"    # Full autonomy, all functions available
    WARN = "WARN"      # Scope-constrained, notify principal, gate elevated ops
    HALT = "HALT"      # No new actions, await re-attestation
    EMERGENCY = "EMERGENCY"  # Safety-critical only (compromise detected)


@dataclass
class ModeTransition:
    from_mode: str
    to_mode: str
    trigger: str
    timestamp: str
    evidence: str


@dataclass
class ModeTable:
    """Deterministic mode transition table."""
    
    # Thresholds (seconds)
    scope_warn_age: float = 1800     # 30 min → WARN
    scope_halt_age: float = 7200     # 2 hours → HALT
    heartbeat_warn_gap: float = 600  # 10 min missed → WARN
    heartbeat_halt_gap: float = 1800 # 30 min missed → HALT
    principal_response_window: float = 3600  # 1 hour for principal to ack WARN
    
    # Functions by criticality
    safety_critical: List[str] = field(default_factory=lambda: [
        "scope_enforcement", "action_logging", "halt_attestation",
        "principal_notification", "state_annunciation"
    ])
    normal_ops: List[str] = field(default_factory=lambda: [
        "autonomous_actions", "new_tool_execution", "elevated_permissions",
        "external_api_calls", "data_writes"
    ])
    non_critical: List[str] = field(default_factory=lambda: [
        "social_engagement", "feed_browsing", "analytics",
        "history_export", "dashboard_updates"
    ])


@dataclass 
class AgentState:
    mode: str = "CLEAN"
    last_scope_commit: Optional[str] = None
    last_heartbeat: Optional[str] = None
    last_principal_ack: Optional[str] = None
    transitions: List[dict] = field(default_factory=list)
    shed_functions: List[str] = field(default_factory=list)
    active_functions: List[str] = field(default_factory=list)
    annunciation: str = ""


class DegradedModeController:
    def __init__(self, mode_table: Optional[ModeTable] = None):
        self.table = mode_table or ModeTable()
        self.state = AgentState()
        self._update_functions()
    
    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
    
    def _age_seconds(self, timestamp: Optional[str]) -> float:
        if not timestamp:
            return float('inf')
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except (ValueError, TypeError):
            return float('inf')
    
    def _update_functions(self):
        """Update active/shed functions based on current mode."""
        if self.state.mode == Mode.CLEAN:
            self.state.active_functions = (
                self.table.safety_critical + 
                self.table.normal_ops + 
                self.table.non_critical
            )
            self.state.shed_functions = []
            self.state.annunciation = "NORMAL OPERATION"
        
        elif self.state.mode == Mode.WARN:
            self.state.active_functions = (
                self.table.safety_critical + 
                self.table.normal_ops
            )
            self.state.shed_functions = list(self.table.non_critical)
            self.state.annunciation = "⚠️ DEGRADED — scope-constrained, principal notified"
        
        elif self.state.mode == Mode.HALT:
            self.state.active_functions = list(self.table.safety_critical)
            self.state.shed_functions = (
                list(self.table.normal_ops) + 
                list(self.table.non_critical)
            )
            self.state.annunciation = "🛑 HALTED — awaiting re-attestation"
        
        elif self.state.mode == Mode.EMERGENCY:
            self.state.active_functions = [
                "halt_attestation", "principal_notification", "state_annunciation"
            ]
            self.state.shed_functions = [
                f for f in (self.table.safety_critical + 
                           self.table.normal_ops + 
                           self.table.non_critical)
                if f not in self.state.active_functions
            ]
            self.state.annunciation = "🚨 EMERGENCY — compromise detected, minimal ops"
    
    def _transition(self, new_mode: str, trigger: str, evidence: str = ""):
        """Record mode transition."""
        if new_mode == self.state.mode:
            return
        
        t = ModeTransition(
            from_mode=self.state.mode,
            to_mode=new_mode,
            trigger=trigger,
            timestamp=self._now(),
            evidence=evidence
        )
        self.state.transitions.append(asdict(t))
        self.state.mode = new_mode
        self._update_functions()
    
    def evaluate(self) -> dict:
        """Evaluate current state and apply mode transitions."""
        scope_age = self._age_seconds(self.state.last_scope_commit)
        heartbeat_age = self._age_seconds(self.state.last_heartbeat)
        principal_age = self._age_seconds(self.state.last_principal_ack)
        
        # HALT conditions (highest priority)
        if scope_age > self.table.scope_halt_age:
            self._transition(Mode.HALT, "scope_expired", 
                           f"scope age {scope_age:.0f}s > {self.table.scope_halt_age}s")
        elif heartbeat_age > self.table.heartbeat_halt_gap:
            self._transition(Mode.HALT, "heartbeat_expired",
                           f"heartbeat gap {heartbeat_age:.0f}s > {self.table.heartbeat_halt_gap}s")
        elif (self.state.mode == Mode.WARN and 
              principal_age > self.table.principal_response_window):
            self._transition(Mode.HALT, "principal_silent",
                           f"no principal ack for {principal_age:.0f}s")
        
        # WARN conditions
        elif scope_age > self.table.scope_warn_age:
            self._transition(Mode.WARN, "scope_stale",
                           f"scope age {scope_age:.0f}s > {self.table.scope_warn_age}s")
        elif heartbeat_age > self.table.heartbeat_warn_gap:
            self._transition(Mode.WARN, "heartbeat_gap",
                           f"heartbeat gap {heartbeat_age:.0f}s > {self.table.heartbeat_warn_gap}s")
        
        # Recovery to CLEAN
        elif (self.state.mode in (Mode.WARN, Mode.HALT) and 
              scope_age < self.table.scope_warn_age and
              heartbeat_age < self.table.heartbeat_warn_gap):
            self._transition(Mode.CLEAN, "recovered",
                           "scope fresh + heartbeat current")
        
        return {
            "mode": self.state.mode,
            "annunciation": self.state.annunciation,
            "active_functions": len(self.state.active_functions),
            "shed_functions": len(self.state.shed_functions),
            "scope_age_s": round(scope_age, 1) if scope_age != float('inf') else None,
            "heartbeat_age_s": round(heartbeat_age, 1) if heartbeat_age != float('inf') else None,
            "transitions": len(self.state.transitions),
        }
    
    def is_allowed(self, function_name: str) -> bool:
        """Check if a function is allowed in current mode."""
        return function_name in self.state.active_functions
    
    def record_heartbeat(self):
        self.state.last_heartbeat = self._now()
    
    def record_scope_commit(self, scope_hash: str = ""):
        self.state.last_scope_commit = self._now()
    
    def record_principal_ack(self):
        self.state.last_principal_ack = self._now()
    
    def trigger_emergency(self, evidence: str):
        self._transition(Mode.EMERGENCY, "compromise_detected", evidence)


def demo():
    """Demo: walk through mode transitions."""
    ctrl = DegradedModeController()
    
    print("=" * 60)
    print("IEC 61508 GRACEFUL DEGRADATION FOR AGENTS")
    print("=" * 60)
    
    # Scenario 1: Fresh start
    ctrl.record_heartbeat()
    ctrl.record_scope_commit("abc123")
    ctrl.record_principal_ack()
    result = ctrl.evaluate()
    print(f"\n1. Fresh start: {result['mode']}")
    print(f"   Active: {result['active_functions']} functions")
    print(f"   {result['annunciation']}")
    
    # Scenario 2: Scope goes stale (simulate by backdating)
    ctrl.state.last_scope_commit = "2026-03-08T04:00:00+00:00"
    result = ctrl.evaluate()
    print(f"\n2. Stale scope: {result['mode']}")
    print(f"   Active: {result['active_functions']}, Shed: {result['shed_functions']}")
    print(f"   {result['annunciation']}")
    
    # Check function gating
    print(f"\n   social_engagement allowed? {ctrl.is_allowed('social_engagement')}")
    print(f"   scope_enforcement allowed? {ctrl.is_allowed('scope_enforcement')}")
    print(f"   autonomous_actions allowed? {ctrl.is_allowed('autonomous_actions')}")
    
    # Scenario 3: Scope expires completely
    ctrl.state.last_scope_commit = "2026-03-08T01:00:00+00:00"
    result = ctrl.evaluate()
    print(f"\n3. Expired scope: {result['mode']}")
    print(f"   Active: {result['active_functions']}, Shed: {result['shed_functions']}")
    print(f"   {result['annunciation']}")
    
    # Scenario 4: Recovery
    ctrl.record_scope_commit("fresh_hash")
    ctrl.record_heartbeat()
    result = ctrl.evaluate()
    print(f"\n4. After re-attestation: {result['mode']}")
    print(f"   Active: {result['active_functions']} functions")
    print(f"   {result['annunciation']}")
    
    # Scenario 5: Emergency
    ctrl.trigger_emergency("CUSUM drift alarm + scope hash mismatch")
    result = ctrl.evaluate()
    print(f"\n5. Emergency: {result['mode']}")
    print(f"   Active: {result['active_functions']}, Shed: {result['shed_functions']}")
    print(f"   {result['annunciation']}")
    
    # Mode table
    print("\n" + "=" * 60)
    print("MODE TABLE")
    print("-" * 60)
    print(f"{'Mode':<12} {'Active':<8} {'Shed':<8} {'Trigger'}")
    print(f"{'CLEAN':<12} {'15':<8} {'0':<8} scope fresh + heartbeat current")
    print(f"{'WARN':<12} {'10':<8} {'5':<8} scope > 30min OR heartbeat > 10min")
    print(f"{'HALT':<12} {'5':<8} {'10':<8} scope > 2hr OR principal silent")
    print(f"{'EMERGENCY':<12} {'3':<8} {'12':<8} compromise detected")
    
    # Transition log
    print(f"\nTransitions recorded: {len(ctrl.state.transitions)}")
    for t in ctrl.state.transitions:
        print(f"  {t['from_mode']} → {t['to_mode']}: {t['trigger']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IEC 61508 graceful degradation for agents")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        ctrl = DegradedModeController()
        ctrl.record_heartbeat()
        ctrl.record_scope_commit()
        print(json.dumps(asdict(ctrl.state), indent=2))
    else:
        demo()
