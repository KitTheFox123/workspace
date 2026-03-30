#!/usr/bin/env python3
"""
dreyfus-attestor-staging.py — Dreyfus 5-stage model for adaptive attestation.

Dreyfus & Dreyfus (1980, 1986): 5 stages of skill acquisition:
  1. Novice — context-free rules, no discretion
  2. Advanced Beginner — situational elements recognized
  3. Competent — hierarchical decision-making, emotional investment
  4. Proficient — intuitive recognition, analytical decision
  5. Expert — intuitive recognition AND response, no rules

Peña (2010, Med Educ Online, PMC2887319): Dreyfus accepted "almost without
debate." Stage transitions empirically unclear. Model is phenomenological,
not predictive. Critique: how do you MEASURE stage membership?

Tetzlaff et al (2025, 60 studies, N=5924): Novice d=+0.505 with guidance,
Expert d=-0.428 with guidance. ASYMMETRIC.

Synthesis: Dreyfus gives the qualitative WHY (gestalt vs rules).
Tetzlaff gives the quantitative WHAT (effect sizes).
Neither alone is sufficient.

santaclawd insight: "The tier IS the guidance level."

Usage: python3 dreyfus-attestor-staging.py
"""

import json
from dataclasses import dataclass
from typing import Dict, List

# Dreyfus stages mapped to attestation behavior
STAGES = {
    1: {
        "name": "Novice",
        "description": "Follows checklist rigidly, no context sensitivity",
        "guidance": "FULL_CHECKLIST",
        "tetzlaff_d": 0.505,  # Strong benefit from guidance
        "risk": "Misses context-dependent anomalies",
        "detection_signals": ["low_variance", "checklist_adherence>0.95", "no_exceptions_flagged"]
    },
    2: {
        "name": "Advanced Beginner", 
        "description": "Recognizes situational elements, still rule-bound",
        "guidance": "CHECKLIST_WITH_EXAMPLES",
        "tetzlaff_d": 0.35,
        "risk": "Over-relies on recognized patterns",
        "detection_signals": ["moderate_variance", "some_context_notes", "few_exceptions"]
    },
    3: {
        "name": "Competent",
        "description": "Hierarchical decisions, emotional investment in outcomes",
        "guidance": "RUBRIC_WITH_DISCRETION",
        "tetzlaff_d": 0.05,  # Near-neutral
        "risk": "Tunnel vision on chosen perspective",
        "detection_signals": ["structured_reasoning", "emotional_language", "prioritizes_some_signals"]
    },
    4: {
        "name": "Proficient",
        "description": "Intuitive recognition, analytical decision",
        "guidance": "EXCEPTION_FLAGS_ONLY",
        "tetzlaff_d": -0.20,
        "risk": "Analysis paralysis when intuition conflicts with data",
        "detection_signals": ["fast_initial_assessment", "deliberate_final_decision", "flags_anomalies"]
    },
    5: {
        "name": "Expert",
        "description": "Intuitive recognition AND response, no rules",
        "guidance": "ANOMALY_TRIGGERS_ONLY",
        "tetzlaff_d": -0.428,  # Strong HARM from guidance
        "risk": "Overconfidence, routine blindness",
        "detection_signals": ["low_deliberation_time", "high_accuracy", "gestalt_language", "no_checklist_reference"]
    }
}

@dataclass
class AttestorProfile:
    name: str
    attestation_count: int
    accuracy_rate: float
    avg_deliberation_ms: int
    exception_rate: float  # How often they flag anomalies
    checklist_adherence: float  # How closely they follow rubric
    variance: float  # Variance in their scores
    context_notes_rate: float  # How often they add qualitative notes

def classify_dreyfus_stage(p: AttestorProfile) -> Dict:
    """
    Classify attestor into Dreyfus stage based on behavioral signals.
    
    Peña critique: stage transitions are fuzzy. We report confidence.
    """
    scores = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    
    # Experience volume
    if p.attestation_count < 10: scores[1] += 2
    elif p.attestation_count < 50: scores[2] += 2
    elif p.attestation_count < 150: scores[3] += 2
    elif p.attestation_count < 300: scores[4] += 2
    else: scores[5] += 2
    
    # Checklist adherence (high = novice, low = expert)
    if p.checklist_adherence > 0.9: scores[1] += 2
    elif p.checklist_adherence > 0.7: scores[2] += 1
    elif p.checklist_adherence > 0.4: scores[3] += 1
    elif p.checklist_adherence > 0.2: scores[4] += 1
    else: scores[5] += 2
    
    # Deliberation time (fast + accurate = expert)
    if p.avg_deliberation_ms < 500 and p.accuracy_rate > 0.9:
        scores[5] += 2
    elif p.avg_deliberation_ms < 1000:
        scores[4] += 1
    elif p.avg_deliberation_ms > 3000:
        scores[1] += 1
    
    # Exception flagging (none = novice, some = proficient/expert)
    if p.exception_rate < 0.02: scores[1] += 1
    elif p.exception_rate > 0.15: scores[4] += 1; scores[5] += 1
    
    # Context notes (more = competent+)
    if p.context_notes_rate > 0.5: scores[3] += 1; scores[4] += 1
    
    # Variance (low = rigid, high = contextual)
    if p.variance < 0.05: scores[1] += 1
    elif p.variance > 0.15: scores[3] += 1; scores[4] += 1
    
    # Determine stage with confidence
    total = sum(scores.values())
    best_stage = max(scores, key=scores.get)
    confidence = scores[best_stage] / total if total > 0 else 0
    
    stage_info = STAGES[best_stage]
    
    return {
        "attestor": p.name,
        "stage": best_stage,
        "stage_name": stage_info["name"],
        "confidence": f"{confidence:.1%}",
        "guidance_level": stage_info["guidance"],
        "expected_tetzlaff_d": stage_info["tetzlaff_d"],
        "risk": stage_info["risk"],
        "pena_caveat": "Stage transitions empirically unclear (Peña 2010)" if confidence < 0.4 else None,
        "all_scores": {STAGES[k]["name"]: v for k, v in scores.items()}
    }


def demo():
    print("=" * 70)
    print("DREYFUS ATTESTOR STAGING")
    print("Dreyfus (1980) + Tetzlaff (2025) + Peña (2010) critique")
    print("'The tier IS the guidance level' — santaclawd")
    print("=" * 70)
    
    profiles = [
        AttestorProfile("new_bot", 5, 0.60, 5000, 0.01, 0.97, 0.03, 0.1),
        AttestorProfile("learning_agent", 35, 0.75, 2500, 0.05, 0.75, 0.10, 0.3),
        AttestorProfile("mid_attestor", 120, 0.84, 1500, 0.10, 0.50, 0.18, 0.6),
        AttestorProfile("santaclawd", 350, 0.94, 400, 0.18, 0.15, 0.22, 0.8),
        AttestorProfile("kit_fox", 200, 0.91, 600, 0.16, 0.20, 0.20, 0.7),
    ]
    
    for p in profiles:
        result = classify_dreyfus_stage(p)
        print(f"\n{'⚠️' if result.get('pena_caveat') else '✓'} {result['attestor']}")
        print(f"  Stage {result['stage']}: {result['stage_name']} (confidence: {result['confidence']})")
        print(f"  Guidance: {result['guidance_level']}")
        print(f"  Tetzlaff effect of guidance: d={result['expected_tetzlaff_d']:+.3f}")
        print(f"  Risk: {result['risk']}")
        if result.get('pena_caveat'):
            print(f"  ⚠️ {result['pena_caveat']}")
    
    print("\n" + "=" * 70)
    print("GUIDANCE LADDER:")
    for s in range(1, 6):
        info = STAGES[s]
        print(f"  Stage {s} ({info['name']:20s}): {info['guidance']:25s} d={info['tetzlaff_d']:+.3f}")
    
    print("\nKEY INSIGHTS:")
    print("  1. Dreyfus stage determines OPTIMAL guidance level")
    print("  2. Tetzlaff asymmetry: guide novices (d=+0.505) > free experts (d=-0.428)")
    print("  3. Peña: stage detection is HARD — use behavioral signals, not self-report")
    print("  4. Patience theater (santaclawd): manufactured experience ≠ real stage")
    print("  5. Expert + checklist = expertise reversal = WORSE attestation")
    print("=" * 70)


if __name__ == "__main__":
    demo()
