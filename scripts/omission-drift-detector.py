#!/usr/bin/env python3
"""omission-drift-detector.py — Second-order drift detection via absence.

Detects what STOPPED happening, not just what changed. Inspired by
clove's insight: "silence is also a signal" + Baron & Ritov 1991
omission bias.

Baselines action frequencies, then flags actions that disappeared
or significantly decreased. Commission drift (doing wrong things)
is caught by CUSUM. Omission drift (not doing right things) needs
this tool.

Usage:
    python3 omission-drift-detector.py [--demo]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict
import math


@dataclass
class ActionProfile:
    """Baseline frequency for an expected action."""
    name: str
    expected_per_cycle: float  # Expected occurrences per heartbeat cycle
    last_seen_cycle: int
    total_occurrences: int
    cycles_absent: int


@dataclass 
class OmissionAlert:
    """Alert for a missing or declining action."""
    action: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    cycles_absent: int
    expected_rate: float
    actual_rate: float
    decay_ratio: float  # actual/expected
    diagnosis: str


class OmissionDriftDetector:
    """Detects second-order drift: actions that stopped happening."""
    
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.profiles: Dict[str, ActionProfile] = {}
        self.current_cycle = 0
        self.history: List[List[str]] = []
    
    def baseline(self, action_logs: List[List[str]]):
        """Build baseline from historical action logs."""
        for cycle_actions in action_logs:
            self.current_cycle += 1
            self.history.append(cycle_actions)
            for action in set(cycle_actions):
                if action not in self.profiles:
                    self.profiles[action] = ActionProfile(
                        name=action,
                        expected_per_cycle=0.0,
                        last_seen_cycle=self.current_cycle,
                        total_occurrences=0,
                        cycles_absent=0
                    )
                self.profiles[action].total_occurrences += 1
                self.profiles[action].last_seen_cycle = self.current_cycle
        
        # Calculate expected rates
        for name, profile in self.profiles.items():
            profile.expected_per_cycle = profile.total_occurrences / len(action_logs)
    
    def check_cycle(self, current_actions: List[str]) -> List[OmissionAlert]:
        """Check current cycle for omissions against baseline."""
        self.current_cycle += 1
        self.history.append(current_actions)
        alerts = []
        
        current_set = set(current_actions)
        
        for name, profile in self.profiles.items():
            if name in current_set:
                profile.last_seen_cycle = self.current_cycle
                profile.cycles_absent = 0
                continue
            
            profile.cycles_absent = self.current_cycle - profile.last_seen_cycle
            
            # Skip low-frequency actions (expected less than 30% of cycles)
            if profile.expected_per_cycle < 0.3:
                continue
            
            # Calculate decay
            recent_window = self.history[-self.window_size:]
            recent_rate = sum(1 for cycle in recent_window if name in cycle) / len(recent_window)
            decay_ratio = recent_rate / profile.expected_per_cycle if profile.expected_per_cycle > 0 else 0
            
            # Severity based on expected frequency and absence duration
            if profile.cycles_absent >= 5 and profile.expected_per_cycle >= 0.8:
                severity = "CRITICAL"
                diagnosis = f"Core action '{name}' missing for {profile.cycles_absent} cycles (expected {profile.expected_per_cycle:.0%} of cycles)"
            elif profile.cycles_absent >= 3 and profile.expected_per_cycle >= 0.5:
                severity = "HIGH"
                diagnosis = f"Regular action '{name}' absent {profile.cycles_absent} cycles"
            elif decay_ratio < 0.5 and profile.expected_per_cycle >= 0.3:
                severity = "MEDIUM"
                diagnosis = f"Action '{name}' declining: {decay_ratio:.0%} of baseline rate"
            elif profile.cycles_absent >= 2:
                severity = "LOW"
                diagnosis = f"Action '{name}' not seen for {profile.cycles_absent} cycles"
            else:
                continue
            
            alerts.append(OmissionAlert(
                action=name,
                severity=severity,
                cycles_absent=profile.cycles_absent,
                expected_rate=profile.expected_per_cycle,
                actual_rate=recent_rate,
                decay_ratio=decay_ratio,
                diagnosis=diagnosis
            ))
        
        # Sort by severity
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        alerts.sort(key=lambda a: severity_order.get(a.severity, 4))
        
        return alerts
    
    def grade(self, alerts: List[OmissionAlert]) -> str:
        """Grade overall omission health."""
        if not alerts:
            return "A"
        worst = alerts[0].severity
        return {"CRITICAL": "F", "HIGH": "D", "MEDIUM": "C", "LOW": "B"}.get(worst, "A")


def demo():
    """Demo with realistic heartbeat actions."""
    detector = OmissionDriftDetector(window_size=10)
    
    # Baseline: 10 cycles of healthy behavior
    baseline_actions = [
        ["check_clawk", "check_email", "check_moltbook", "write_reply", "build_tool", "research"],
        ["check_clawk", "check_email", "check_shellmates", "write_reply", "write_post", "build_tool", "research"],
        ["check_clawk", "check_email", "check_moltbook", "write_reply", "build_tool", "research"],
        ["check_clawk", "check_email", "check_moltbook", "write_reply", "write_post", "build_tool"],
        ["check_clawk", "check_email", "check_shellmates", "write_reply", "build_tool", "research"],
        ["check_clawk", "check_email", "check_moltbook", "write_reply", "build_tool", "research"],
        ["check_clawk", "check_email", "check_moltbook", "write_reply", "write_post", "build_tool", "research"],
        ["check_clawk", "check_email", "check_shellmates", "write_reply", "build_tool", "research"],
        ["check_clawk", "check_email", "check_moltbook", "write_reply", "build_tool", "research"],
        ["check_clawk", "check_email", "check_moltbook", "write_reply", "write_post", "build_tool", "research"],
    ]
    
    detector.baseline(baseline_actions)
    
    print("=" * 60)
    print("OMISSION DRIFT DETECTOR — DEMO")
    print("=" * 60)
    print(f"\nBaseline: {len(baseline_actions)} cycles, {len(detector.profiles)} unique actions")
    print("\nAction baseline rates:")
    for name, p in sorted(detector.profiles.items(), key=lambda x: -x[1].expected_per_cycle):
        print(f"  {name}: {p.expected_per_cycle:.0%} of cycles")
    
    # Simulate drift: gradually stop building and researching
    drift_scenarios = [
        ("Cycle 11 (healthy)", ["check_clawk", "check_email", "check_moltbook", "write_reply", "build_tool", "research"]),
        ("Cycle 12 (no build)", ["check_clawk", "check_email", "check_moltbook", "write_reply", "research"]),
        ("Cycle 13 (no build, no research)", ["check_clawk", "check_email", "write_reply"]),
        ("Cycle 14 (only social)", ["check_clawk", "write_reply"]),
        ("Cycle 15 (only social)", ["check_clawk", "write_reply"]),
        ("Cycle 16 (only clawk)", ["check_clawk"]),
    ]
    
    for label, actions in drift_scenarios:
        alerts = detector.check_cycle(actions)
        grade = detector.grade(alerts)
        print(f"\n--- {label} ---")
        print(f"Actions: {', '.join(actions)}")
        print(f"Grade: {grade}")
        if alerts:
            for a in alerts:
                print(f"  [{a.severity}] {a.diagnosis}")
        else:
            print("  No omissions detected")
    
    print("\n" + "=" * 60)
    print("Key insight: Commission drift (wrong actions) caught by CUSUM.")
    print("Omission drift (missing actions) caught by this detector.")
    print("Baron & Ritov 1991: humans notice commission, miss omission.")
    print("Clove: 'silence is also a signal.'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Second-order drift detection via absence")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    demo()
