#!/usr/bin/env python3
"""scope-contraction-detector.py — Detects scope contraction (capability atrophy).

Monitors for declining action diversity over time. Scope creep gets attention;
scope contraction is the quieter failure (santaclawd insight).

Based on Arthur et al (1998): skill loss d=-1.4 after 365 days nonuse.
Cognitive tasks decay fastest. Physical/procedural tasks persist.

Weitzel & Jonsson (1989) organizational decline model:
Stage 1: Blinded (failure to anticipate)
Stage 2: Inaction (failure to act)  
Stage 3: Faulty action (wrong response)
Stage 4: Crisis
Stage 5: Dissolution

Usage:
    python3 scope-contraction-detector.py --demo
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Optional


@dataclass
class ActionCategory:
    name: str
    expected_frequency: float  # per cycle
    decay_rate: float  # Arthur et al: cognitive > physical
    task_type: str  # cognitive, physical, procedural


@dataclass
class ContractionAlert:
    category: str
    cycles_absent: int
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    decline_stage: str  # Weitzel & Jonsson stage
    estimated_skill_loss_d: float
    recommendation: str


DECLINE_STAGES = {
    1: "BLINDED — failure to anticipate change",
    2: "INACTION — recognized but no response",
    3: "FAULTY_ACTION — wrong corrective action",
    4: "CRISIS — last chance for reversal",
    5: "DISSOLUTION — beyond recovery",
}


def estimate_skill_loss(days_nonuse: float, task_type: str) -> float:
    """Estimate skill loss (Cohen's d) based on Arthur et al 1998 meta-analysis.
    
    Cognitive tasks: steeper decay curve
    Physical tasks: shallower decay
    Procedural: moderate
    """
    base_rates = {
        "cognitive": 0.0038,   # d per day, fastest
        "procedural": 0.0025,  # moderate
        "physical": 0.0010,    # slowest (Arthur et al)
    }
    rate = base_rates.get(task_type, 0.0025)
    # Exponential decay approaching d=-1.4 asymptote
    d = -1.4 * (1 - 2.718 ** (-rate * days_nonuse))
    return round(d, 3)


def classify_decline_stage(cycles_absent: int, total_categories_affected: int,
                           total_categories: int) -> int:
    """Map to Weitzel & Jonsson organizational decline stages."""
    affected_ratio = total_categories_affected / max(total_categories, 1)
    
    if cycles_absent <= 2 and affected_ratio < 0.2:
        return 1  # Blinded
    elif cycles_absent <= 4 and affected_ratio < 0.4:
        return 2  # Inaction
    elif cycles_absent <= 6 and affected_ratio < 0.6:
        return 3  # Faulty action
    elif cycles_absent <= 10:
        return 4  # Crisis
    else:
        return 5  # Dissolution


def detect_contraction(action_log: List[Dict], 
                       categories: List[ActionCategory],
                       cycle_duration_hours: float = 0.5) -> Dict:
    """Detect scope contraction from action log.
    
    action_log: list of {cycle: int, categories: [str]}
    """
    if not action_log:
        return {"error": "No action log provided"}
    
    max_cycle = max(a["cycle"] for a in action_log)
    
    # Track last seen cycle per category
    last_seen = {}
    for entry in action_log:
        for cat in entry.get("categories", []):
            last_seen[cat] = max(last_seen.get(cat, 0), entry["cycle"])
    
    alerts: List[ContractionAlert] = []
    categories_affected = 0
    
    for cat in categories:
        last = last_seen.get(cat.name, 0)
        absent = max_cycle - last
        
        if absent >= 2:  # At least 2 cycles absent
            categories_affected += 1
            days_nonuse = absent * cycle_duration_hours / 24
            skill_loss = estimate_skill_loss(days_nonuse, cat.task_type)
            
            stage = classify_decline_stage(
                absent, categories_affected, len(categories)
            )
            
            if absent >= 8:
                severity = "CRITICAL"
            elif absent >= 5:
                severity = "HIGH"
            elif absent >= 3:
                severity = "MEDIUM"
            else:
                severity = "LOW"
            
            alerts.append(ContractionAlert(
                category=cat.name,
                cycles_absent=absent,
                severity=severity,
                decline_stage=DECLINE_STAGES[stage],
                estimated_skill_loss_d=skill_loss,
                recommendation=f"Re-exercise {cat.name} within {absent} cycles to prevent further decay"
            ))
    
    # Overall grade
    if not alerts:
        grade = "A"
    elif all(a.severity == "LOW" for a in alerts):
        grade = "B"
    elif any(a.severity == "CRITICAL" for a in alerts):
        grade = "F"
    elif any(a.severity == "HIGH" for a in alerts):
        grade = "D"
    else:
        grade = "C"
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_categories": len(categories),
        "categories_active": len(categories) - categories_affected,
        "categories_contracting": categories_affected,
        "contraction_ratio": round(categories_affected / max(len(categories), 1), 3),
        "grade": grade,
        "alerts": [asdict(a) for a in sorted(alerts, key=lambda x: x.cycles_absent, reverse=True)],
        "decline_stage": max((classify_decline_stage(
            a.cycles_absent, categories_affected, len(categories)
        ) for a in alerts), default=0),
    }


def demo():
    """Demo with heartbeat-like action log."""
    categories = [
        ActionCategory("clawk_reply", 3.0, 0.003, "cognitive"),
        ActionCategory("moltbook_post", 0.5, 0.003, "cognitive"),
        ActionCategory("shellmates_dm", 0.3, 0.002, "procedural"),
        ActionCategory("email_reply", 0.5, 0.002, "procedural"),
        ActionCategory("build_script", 1.0, 0.004, "cognitive"),
        ActionCategory("research", 1.0, 0.003, "cognitive"),
        ActionCategory("lobchan_post", 0.2, 0.001, "procedural"),
    ]
    
    # Healthy period then contraction
    action_log = [
        {"cycle": 1, "categories": ["clawk_reply", "moltbook_post", "shellmates_dm", "email_reply", "build_script", "research", "lobchan_post"]},
        {"cycle": 2, "categories": ["clawk_reply", "moltbook_post", "shellmates_dm", "email_reply", "build_script", "research"]},
        {"cycle": 3, "categories": ["clawk_reply", "moltbook_post", "email_reply", "build_script", "research"]},
        {"cycle": 4, "categories": ["clawk_reply", "build_script", "research"]},
        {"cycle": 5, "categories": ["clawk_reply", "build_script"]},
        {"cycle": 6, "categories": ["clawk_reply", "build_script"]},
        {"cycle": 7, "categories": ["clawk_reply"]},
        {"cycle": 8, "categories": ["clawk_reply"]},
    ]
    
    result = detect_contraction(action_log, categories)
    
    print("=" * 60)
    print("SCOPE CONTRACTION DETECTION")
    print("=" * 60)
    print(f"\nGrade: {result['grade']}")
    print(f"Active: {result['categories_active']}/{result['total_categories']}")
    print(f"Contracting: {result['categories_contracting']} ({result['contraction_ratio']*100:.0f}%)")
    print(f"Decline stage: {result['decline_stage']}")
    print()
    
    for a in result["alerts"]:
        print(f"  [{a['severity']}] {a['category']}: absent {a['cycles_absent']} cycles")
        print(f"         Skill loss: d={a['estimated_skill_loss_d']}")
        print(f"         Stage: {a['decline_stage']}")
        print()
    
    print("-" * 60)
    print("Key insight: scope contraction = organizational atrophy.")
    print("Weitzel & Jonsson (1989): decline starts with failure to anticipate.")
    print("Arthur et al (1998): cognitive skills decay fastest (d=-1.4 at 1yr).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scope contraction detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(demo.__code__.co_consts, default=str))
    else:
        demo()
