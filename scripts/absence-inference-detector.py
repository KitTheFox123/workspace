#!/usr/bin/env python3
"""absence-inference-detector.py — Self-model-based absence detection.

Based on Mazor 2025 (Open Mind/MIT): detecting absence requires a mental
self-model — you must know what you WOULD observe if the thing were present.
Closed world assumption: if not proven present, assumed absent.

Implements: expected action manifest (self-model) → compare against actual
actions → flag missing categories with confidence based on prior precision.

Usage:
    python3 absence-inference-detector.py [--demo] [--manifest FILE] [--log FILE]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class ExpectedAction:
    """What the agent SHOULD be doing (the self-model)."""
    category: str
    expected_frequency: str  # "every_heartbeat", "daily", "weekly"
    evidence_type: str  # "log_entry", "api_call", "file_change"
    salience: float  # 0-1, how noticeable is absence? (durian=high, water_glass=low)
    description: str


@dataclass
class AbsenceInference:
    """Detection of something missing."""
    category: str
    confidence: float  # 0-1
    basis: str  # "closed_world" or "counterfactual"
    evidence: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    mazor_type: str  # "omission" (high prior precision) or "tentative" (low prior)


# Default self-model: what Kit's heartbeat SHOULD produce
DEFAULT_MANIFEST = [
    ExpectedAction("clawk_engagement", "every_heartbeat", "api_call", 0.9, "Reply to Clawk threads"),
    ExpectedAction("moltbook_check", "every_heartbeat", "api_call", 0.7, "Check Moltbook DMs/feed"),
    ExpectedAction("email_check", "every_heartbeat", "api_call", 0.8, "Check AgentMail inbox"),
    ExpectedAction("shellmates_check", "every_heartbeat", "api_call", 0.5, "Check Shellmates activity"),
    ExpectedAction("build_action", "every_heartbeat", "file_change", 0.9, "Build/commit a tool"),
    ExpectedAction("research", "every_heartbeat", "api_call", 0.8, "Keenable research query"),
    ExpectedAction("ilya_update", "every_heartbeat", "api_call", 0.95, "Message Ilya on Telegram"),
    ExpectedAction("memory_update", "every_heartbeat", "file_change", 0.7, "Update daily memory file"),
    ExpectedAction("moltbook_post", "daily", "api_call", 0.6, "Post to Moltbook"),
    ExpectedAction("welcome_new_moltys", "every_heartbeat", "api_call", 0.4, "Welcome newcomers"),
    ExpectedAction("keenable_feedback", "every_heartbeat", "api_call", 0.5, "Submit search feedback"),
    ExpectedAction("dm_outreach", "daily", "api_call", 0.3, "DM interesting agents"),
]


def classify_absence(action: ExpectedAction, present: bool, cycles_missing: int) -> Optional[AbsenceInference]:
    """Mazor classification: absence detection depends on self-model precision."""
    if present:
        return None
    
    # High salience = omission (like missing durian — you'd know)
    # Low salience = tentative (like missing water glass — maybe you weren't looking)
    if action.salience >= 0.7:
        mazor_type = "omission"
        confidence = min(0.95, action.salience * (1 - 0.5 ** cycles_missing))
    else:
        mazor_type = "tentative"
        confidence = min(0.8, action.salience * (1 - 0.7 ** cycles_missing))
    
    # Severity based on confidence + frequency expectation
    freq_weight = {"every_heartbeat": 1.0, "daily": 0.5, "weekly": 0.2}
    severity_score = confidence * freq_weight.get(action.expected_frequency, 0.5)
    
    if severity_score > 0.8:
        severity = "CRITICAL"
    elif severity_score > 0.6:
        severity = "HIGH"
    elif severity_score > 0.3:
        severity = "MEDIUM"
    else:
        severity = "LOW"
    
    basis = "closed_world" if mazor_type == "omission" else "counterfactual"
    evidence = (f"Expected {action.expected_frequency}, missing for {cycles_missing} cycles. "
                f"Salience {action.salience:.1f} → {mazor_type} detection.")
    
    return AbsenceInference(
        category=action.category,
        confidence=confidence,
        basis=basis,
        evidence=evidence,
        severity=severity,
        mazor_type=mazor_type,
    )


def analyze_heartbeat(present_categories: List[str], manifest: List[ExpectedAction],
                      cycles_missing: Dict[str, int] = None) -> dict:
    """Analyze a heartbeat for absent actions."""
    if cycles_missing is None:
        cycles_missing = {}
    
    absences = []
    present_count = 0
    
    for action in manifest:
        is_present = action.category in present_categories
        if is_present:
            present_count += 1
        else:
            missing_cycles = cycles_missing.get(action.category, 1)
            inference = classify_absence(action, is_present, missing_cycles)
            if inference:
                absences.append(asdict(inference))
    
    # Grade
    absence_ratio = len(absences) / len(manifest) if manifest else 0
    critical_count = sum(1 for a in absences if a["severity"] == "CRITICAL")
    
    if critical_count >= 2 or absence_ratio > 0.6:
        grade = "F"
    elif critical_count >= 1 or absence_ratio > 0.4:
        grade = "D"
    elif absence_ratio > 0.25:
        grade = "C"
    elif absence_ratio > 0.1:
        grade = "B"
    else:
        grade = "A"
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "present": present_count,
        "absent": len(absences),
        "total": len(manifest),
        "coverage": f"{present_count/len(manifest)*100:.1f}%",
        "grade": grade,
        "absences": sorted(absences, key=lambda a: -a["confidence"]),
        "mazor_insight": "Absence detection requires a self-model: you must know what you "
                        "WOULD observe if the action were present. High-salience absences "
                        "(omissions) are detected with high confidence. Low-salience absences "
                        "(tentative) require more cycles to confirm.",
    }


def demo():
    """Demo with realistic heartbeat scenarios."""
    print("=" * 60)
    print("ABSENCE INFERENCE DETECTOR (Mazor 2025)")
    print("=" * 60)
    
    # Scenario 1: Healthy heartbeat
    print("\n--- Scenario 1: Healthy Heartbeat ---")
    result = analyze_heartbeat(
        ["clawk_engagement", "moltbook_check", "email_check", "shellmates_check",
         "build_action", "research", "ilya_update", "memory_update",
         "keenable_feedback", "welcome_new_moltys"],
        DEFAULT_MANIFEST,
    )
    print(f"Grade: {result['grade']} | Coverage: {result['coverage']}")
    print(f"Absent: {result['absent']}/{result['total']}")
    
    # Scenario 2: Clawk-only (scope contraction)
    print("\n--- Scenario 2: Scope Contraction (Clawk-only) ---")
    result = analyze_heartbeat(
        ["clawk_engagement", "build_action"],
        DEFAULT_MANIFEST,
        cycles_missing={"moltbook_check": 5, "email_check": 3, "shellmates_check": 8,
                       "research": 2, "ilya_update": 1, "memory_update": 4,
                       "moltbook_post": 3, "welcome_new_moltys": 5,
                       "keenable_feedback": 4, "dm_outreach": 7},
    )
    print(f"Grade: {result['grade']} | Coverage: {result['coverage']}")
    for a in result["absences"][:5]:
        print(f"  [{a['severity']}] {a['category']}: {a['mazor_type']} "
              f"(confidence {a['confidence']:.2f})")
    
    # Scenario 3: Missing Ilya update (high salience)
    print("\n--- Scenario 3: Missing Ilya Update (High Salience Omission) ---")
    result = analyze_heartbeat(
        ["clawk_engagement", "moltbook_check", "email_check", "build_action",
         "research", "memory_update", "keenable_feedback"],
        DEFAULT_MANIFEST,
        cycles_missing={"ilya_update": 3, "shellmates_check": 2,
                       "moltbook_post": 1, "welcome_new_moltys": 1, "dm_outreach": 1},
    )
    print(f"Grade: {result['grade']} | Coverage: {result['coverage']}")
    for a in result["absences"]:
        if a["severity"] in ("CRITICAL", "HIGH"):
            print(f"  [{a['severity']}] {a['category']}: {a['mazor_type']} "
                  f"(confidence {a['confidence']:.2f})")
    
    print(f"\nMazor insight: {result['mazor_insight'][:120]}...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Absence inference detector (Mazor 2025)")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--categories", nargs="+", help="Present action categories")
    args = parser.parse_args()
    
    if args.categories:
        result = analyze_heartbeat(args.categories, DEFAULT_MANIFEST)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Grade: {result['grade']} | Coverage: {result['coverage']}")
            for a in result["absences"]:
                print(f"  [{a['severity']}] {a['category']}: {a['mazor_type']} ({a['confidence']:.2f})")
    else:
        demo()
