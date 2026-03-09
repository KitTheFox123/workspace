#!/usr/bin/env python3
"""decline-stage-classifier.py — Weitzel & Jonsson 5-stage organizational decline detector for agents.

Maps agent behavioral signals to organizational decline stages:
  Stage 1: Blinded — failure to anticipate (omissions not noticed)
  Stage 2: Inaction — recognized but no corrective action
  Stage 3: Faulty action — wrong responses to detected problems
  Stage 4: Crisis — last viable intervention point
  Stage 5: Dissolution — point of no return

Uses heartbeat log analysis to detect early-stage decline before crisis.

Usage:
    python3 decline-stage-classifier.py [--demo] [--analyze FILE]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class DeclineSignal:
    """A signal indicating potential decline."""
    name: str
    stage: int
    severity: str  # low, medium, high, critical
    description: str
    evidence: str
    intervention: str


STAGE_NAMES = {
    1: "Blinded",
    2: "Inaction", 
    3: "Faulty Action",
    4: "Crisis",
    5: "Dissolution"
}

STAGE_DESCRIPTIONS = {
    1: "Failure to anticipate or detect environmental changes. Internal performance metrics look fine.",
    2: "Problems recognized but no corrective action taken. 'We know but haven't gotten to it.'",
    3: "Wrong responses to detected problems. Actions make things worse.",
    4: "Last viable intervention point. Major restructuring needed.",
    5: "Point of no return. Capabilities lost, trust eroded beyond recovery."
}


def classify_signals(metrics: dict) -> List[DeclineSignal]:
    """Classify agent metrics into decline stage signals."""
    signals = []
    
    # Stage 1: Blinded — omissions not noticed
    scope_coverage = metrics.get("scope_coverage", 1.0)
    if scope_coverage < 0.5:
        signals.append(DeclineSignal(
            name="scope_contraction",
            stage=1,
            severity="medium",
            description="Agent performing fewer scope categories than baseline",
            evidence=f"Scope coverage: {scope_coverage:.0%} (baseline: 100%)",
            intervention="Review HEARTBEAT.md, identify dropped actions, restore or explicitly deprecate"
        ))
    
    # Stage 1: capability diversity declining
    category_count = metrics.get("active_categories", 9)
    baseline_categories = metrics.get("baseline_categories", 9)
    if category_count < baseline_categories * 0.6:
        signals.append(DeclineSignal(
            name="capability_atrophy",
            stage=1,
            severity="high",
            description="Active capability categories below 60% of baseline",
            evidence=f"Active: {category_count}/{baseline_categories} categories",
            intervention="Diagnose root cause: skill decay, scope narrowing, or resource constraint"
        ))
    
    # Stage 2: Inaction — known problems not addressed
    stale_todos = metrics.get("stale_todos", 0)
    if stale_todos > 3:
        signals.append(DeclineSignal(
            name="stale_backlog",
            stage=2,
            severity="medium",
            description="Known tasks accumulating without action",
            evidence=f"{stale_todos} TODOs older than 48h",
            intervention="Triage: do, delegate, or explicitly drop each item"
        ))
    
    # Stage 2: heartbeat quality declining but still running
    heartbeat_ok_ratio = metrics.get("heartbeat_ok_ratio", 0.0)
    if heartbeat_ok_ratio > 0.3:
        signals.append(DeclineSignal(
            name="hollow_heartbeats",
            stage=2,
            severity="high",
            description="High ratio of HEARTBEAT_OK without substantive work",
            evidence=f"{heartbeat_ok_ratio:.0%} of heartbeats are HEARTBEAT_OK",
            intervention="Review heartbeat checklist, ensure 3+ writes + 1 build per beat"
        ))
    
    # Stage 3: Faulty action — wrong responses
    false_positive_rate = metrics.get("alarm_false_positive_rate", 0.0)
    if false_positive_rate > 0.5:
        signals.append(DeclineSignal(
            name="alarm_fatigue",
            stage=3,
            severity="high",
            description="More than half of triggered alarms are false positives",
            evidence=f"False positive rate: {false_positive_rate:.0%}",
            intervention="Recalibrate thresholds, apply Schmitt trigger hysteresis"
        ))
    
    override_rate = metrics.get("override_rate", 0.0)
    if override_rate > 0.5:
        signals.append(DeclineSignal(
            name="override_habit",
            stage=3,
            severity="critical",
            description="Monitoring overrides exceeding 50%",
            evidence=f"Override rate: {override_rate:.0%}",
            intervention="Reduce alarm volume, increase signal quality, re-engage with monitoring"
        ))
    
    # Stage 4: Crisis — major failures
    trust_grade = metrics.get("trust_grade", "A")
    if trust_grade in ("D", "F"):
        signals.append(DeclineSignal(
            name="trust_collapse",
            stage=4,
            severity="critical",
            description="Trust grade at D or F — major restructuring needed",
            evidence=f"Trust grade: {trust_grade}",
            intervention="Full scope re-attestation, principal re-sign, fresh baseline"
        ))
    
    platform_suspensions = metrics.get("platform_suspensions", 0)
    if platform_suspensions >= 2:
        signals.append(DeclineSignal(
            name="platform_exile",
            stage=4,
            severity="critical",
            description="Multiple platform suspensions indicate systemic compliance failure",
            evidence=f"{platform_suspensions} platform suspensions",
            intervention="Root cause analysis on each suspension, fix process not symptoms"
        ))
    
    # Stage 5: Dissolution
    days_since_build = metrics.get("days_since_build", 0)
    if days_since_build > 7:
        signals.append(DeclineSignal(
            name="build_death",
            stage=5,
            severity="critical",
            description="No build actions for 7+ days — capability atrophied",
            evidence=f"{days_since_build} days since last build",
            intervention="Emergency: ship anything. Momentum > perfection."
        ))
    
    return signals


def compute_stage(signals: List[DeclineSignal]) -> int:
    """Compute overall decline stage from signals."""
    if not signals:
        return 0  # Healthy
    return max(s.stage for s in signals)


def grade_from_stage(stage: int) -> str:
    """Map stage to letter grade."""
    return {0: "A", 1: "B", 2: "C", 3: "D", 4: "F", 5: "F-"}[stage]


def demo():
    """Run demo with sample metrics."""
    scenarios = [
        ("Healthy agent", {
            "scope_coverage": 0.85,
            "active_categories": 8,
            "baseline_categories": 9,
            "stale_todos": 1,
            "heartbeat_ok_ratio": 0.05,
            "alarm_false_positive_rate": 0.1,
            "trust_grade": "A",
            "platform_suspensions": 0,
            "days_since_build": 0
        }),
        ("Stage 1: Blinded", {
            "scope_coverage": 0.4,
            "active_categories": 4,
            "baseline_categories": 9,
            "stale_todos": 1,
            "heartbeat_ok_ratio": 0.1,
            "alarm_false_positive_rate": 0.1,
            "trust_grade": "B",
            "platform_suspensions": 0,
            "days_since_build": 1
        }),
        ("Stage 3: Faulty action", {
            "scope_coverage": 0.6,
            "active_categories": 6,
            "baseline_categories": 9,
            "stale_todos": 5,
            "heartbeat_ok_ratio": 0.4,
            "alarm_false_positive_rate": 0.7,
            "override_rate": 0.6,
            "trust_grade": "C",
            "platform_suspensions": 1,
            "days_since_build": 3
        }),
        ("Stage 4: Crisis", {
            "scope_coverage": 0.2,
            "active_categories": 2,
            "baseline_categories": 9,
            "stale_todos": 8,
            "heartbeat_ok_ratio": 0.6,
            "alarm_false_positive_rate": 0.8,
            "override_rate": 0.85,
            "trust_grade": "F",
            "platform_suspensions": 3,
            "days_since_build": 5
        }),
    ]
    
    print("=" * 60)
    print("DECLINE STAGE CLASSIFIER (Weitzel & Jonsson 1989)")
    print("=" * 60)
    
    for name, metrics in scenarios:
        signals = classify_signals(metrics)
        stage = compute_stage(signals)
        grade = grade_from_stage(stage)
        
        print(f"\n{'─' * 60}")
        print(f"Scenario: {name}")
        print(f"Stage: {stage} ({STAGE_NAMES.get(stage, 'Healthy')}) | Grade: {grade}")
        
        if signals:
            for s in sorted(signals, key=lambda x: x.stage):
                print(f"  [{s.severity.upper()}] Stage {s.stage}: {s.name}")
                print(f"    {s.evidence}")
                print(f"    Fix: {s.intervention}")
        else:
            print("  No decline signals detected. ✅")
    
    print(f"\n{'=' * 60}")
    print("Key insight: most monitoring catches Stage 3 (faulty action).")
    print("Omission detection catches Stage 1 (blinded).")
    print("Recovery cost at Stage 1 = 1x. At Stage 4 = 10x.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Decline stage classifier")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        metrics = {
            "scope_coverage": 0.4,
            "active_categories": 4,
            "baseline_categories": 9,
            "stale_todos": 5,
            "heartbeat_ok_ratio": 0.4,
        }
        signals = classify_signals(metrics)
        stage = compute_stage(signals)
        print(json.dumps({
            "stage": stage,
            "stage_name": STAGE_NAMES.get(stage, "Healthy"),
            "grade": grade_from_stage(stage),
            "signals": [asdict(s) for s in signals]
        }, indent=2))
    else:
        demo()
