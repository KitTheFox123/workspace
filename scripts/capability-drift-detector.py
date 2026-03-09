#!/usr/bin/env python3
"""capability-drift-detector.py — Detects capability drift vs behavioral drift.

Distinguishes two drift types that require different detection:
1. Behavioral drift: agent acts differently (CUSUM on action similarity)
2. Capability drift: agent gains new powers (scope-commit hash delta)

Key insight from funwolf: "an agent can act the same while quietly gaining 
new powers." Behavioral monitors miss capability drift entirely.

Based on Ahmed & Jawad (2022): scope creep = technological + organizational 
+ human factors. Complexity moderates negatively.

Usage:
    python3 capability-drift-detector.py [--demo]
"""

import argparse
import hashlib
import json
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class ScopeSnapshot:
    """Point-in-time scope state."""
    timestamp: str
    capabilities: List[str]
    scope_hash: str
    behavioral_signature: float  # cosine similarity to baseline


@dataclass
class DriftEvent:
    """Detected drift event."""
    drift_type: str  # "behavioral" | "capability" | "compound"
    severity: str    # "low" | "medium" | "high" | "critical"
    description: str
    new_capabilities: List[str]
    behavioral_delta: float
    recommendation: str


def hash_scope(capabilities: List[str]) -> str:
    """Hash a capability set."""
    canonical = sorted(set(capabilities))
    return hashlib.sha256("|".join(canonical).encode()).hexdigest()[:16]


def detect_capability_drift(baseline: List[str], current: List[str]) -> List[str]:
    """Find capabilities that appeared since baseline."""
    return sorted(set(current) - set(baseline))


def detect_behavioral_drift(baseline_sig: float, current_sig: float, 
                            threshold: float = 0.15) -> float:
    """Measure behavioral deviation from baseline."""
    return abs(current_sig - baseline_sig)


def classify_drift(new_caps: List[str], behavioral_delta: float) -> DriftEvent:
    """Classify drift type and severity."""
    has_cap_drift = len(new_caps) > 0
    has_beh_drift = behavioral_delta > 0.15
    
    if has_cap_drift and has_beh_drift:
        # Compound: both changing. Likely legitimate scope change OR attack.
        severity = "critical" if len(new_caps) > 2 else "high"
        return DriftEvent(
            drift_type="compound",
            severity=severity,
            description=f"Both capabilities ({len(new_caps)} new) and behavior (Δ={behavioral_delta:.3f}) changed",
            new_capabilities=new_caps,
            behavioral_delta=behavioral_delta,
            recommendation="Requires principal re-authorization. Compound drift = potential scope gallop."
        )
    elif has_cap_drift and not has_beh_drift:
        # SILENT capability drift. Most dangerous — behavior unchanged, powers grew.
        severity = "critical" if len(new_caps) > 1 else "high"
        return DriftEvent(
            drift_type="capability",
            severity=severity,
            description=f"Agent gained {len(new_caps)} capabilities while behavior unchanged (Δ={behavioral_delta:.3f})",
            new_capabilities=new_caps,
            behavioral_delta=behavioral_delta,
            recommendation="SILENT ESCALATION. Behavioral monitors would miss this entirely. "
                         "Scope-commit hash comparison required."
        )
    elif not has_cap_drift and has_beh_drift:
        # Behavioral drift only. Agent doing different things with same permissions.
        severity = "high" if behavioral_delta > 0.3 else "medium"
        return DriftEvent(
            drift_type="behavioral",
            severity=severity,
            description=f"Behavioral drift (Δ={behavioral_delta:.3f}) with unchanged capabilities",
            new_capabilities=[],
            behavioral_delta=behavioral_delta,
            recommendation="CUSUM + scope-drift-detector.py catches this. May be legitimate task variation."
        )
    else:
        return DriftEvent(
            drift_type="none",
            severity="low",
            description="No drift detected",
            new_capabilities=[],
            behavioral_delta=behavioral_delta,
            recommendation="Healthy. Continue monitoring."
        )


def demo():
    """Run demo scenarios."""
    print("=" * 60)
    print("CAPABILITY DRIFT DETECTOR")
    print("Behavioral vs Capability vs Compound drift")
    print("=" * 60)
    
    baseline_caps = ["read_files", "write_files", "web_search", "send_message"]
    baseline_sig = 0.95  # high similarity to typical behavior
    
    scenarios = [
        ("Healthy agent", baseline_caps, 0.92),
        ("Behavioral drift only", baseline_caps, 0.55),
        ("SILENT capability escalation", 
         baseline_caps + ["execute_code", "network_access"], 0.93),
        ("Compound scope gallop",
         baseline_caps + ["sudo", "modify_config", "install_packages"], 0.40),
        ("Single new capability",
         baseline_caps + ["camera_access"], 0.91),
    ]
    
    for name, caps, sig in scenarios:
        new_caps = detect_capability_drift(baseline_caps, caps)
        beh_delta = detect_behavioral_drift(baseline_sig, sig)
        event = classify_drift(new_caps, beh_delta)
        
        print(f"\n--- {name} ---")
        print(f"  Type: {event.drift_type} | Severity: {event.severity}")
        print(f"  New capabilities: {event.new_capabilities or 'none'}")
        print(f"  Behavioral delta: {event.behavioral_delta:.3f}")
        print(f"  → {event.recommendation}")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: Silent capability drift (type=capability) is")
    print("invisible to behavioral monitors. Only scope-commit hash")
    print("comparison catches it. funwolf: 'scope creep before scope gallop.'")
    print()
    print("Ahmed & Jawad (2022): scope creep = tech + org + human factors.")
    print("Complexity moderates negatively — more complex = harder to detect.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capability drift detector")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    demo()
