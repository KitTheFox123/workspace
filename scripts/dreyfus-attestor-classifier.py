#!/usr/bin/env python3
"""
dreyfus-attestor-classifier.py — Behavioral Dreyfus stage classification.

Dreyfus & Dreyfus (1980): 5 stages — novice, advanced beginner, competent,
proficient, expert. Each stage has different relationship to rules vs intuition.

Peña (2010, PMC2887319): Critical perspective — model accepted without debate.
No operational definition of "expert." Context-free model for context-dependent
skills. Intuition ≠ expertise automatically.

Problem: Self-reported expertise = Dunning-Kruger. Need behavioral signals.
Solution: Classify by BEHAVIOR not self-report.

Combined with Tetzlaff (2025): Adaptive guidance per classified stage.

Usage: python3 dreyfus-attestor-classifier.py
"""

from dataclasses import dataclass
from typing import List, Dict

STAGES = {
    1: {"name": "Novice", "rule_reliance": 1.0, "context_sensitivity": 0.0,
        "guidance": "FULL_CHECKLIST", "description": "Follows rules rigidly, no context awareness"},
    2: {"name": "Advanced Beginner", "rule_reliance": 0.8, "context_sensitivity": 0.2,
        "guidance": "CHECKLIST_WITH_EXAMPLES", "description": "Recognizes situational elements"},
    3: {"name": "Competent", "rule_reliance": 0.5, "context_sensitivity": 0.5,
        "guidance": "RUBRIC_ONLY", "description": "Plans deliberately, takes responsibility"},
    4: {"name": "Proficient", "rule_reliance": 0.2, "context_sensitivity": 0.8,
        "guidance": "EXCEPTION_FLAGS", "description": "Sees situations holistically, uses intuition for decisions"},
    5: {"name": "Expert", "rule_reliance": 0.0, "context_sensitivity": 1.0,
        "guidance": "ANOMALY_ALERTS_ONLY", "description": "Fluid, intuitive, unconscious competence"},
}

@dataclass
class AttestorBehavior:
    """Behavioral signals — NOT self-reported expertise."""
    name: str
    total_attestations: int
    accuracy_rate: float          # verified accuracy
    rule_deviation_rate: float    # how often they deviate from checklist (0=never, 1=always)
    context_references: float     # proportion of attestations citing specific context
    exception_handling: float     # rate of flagging edge cases
    response_time_cv: float       # coefficient of variation in response time
    explanation_depth: float      # average explanation richness (0-1)
    
def classify_dreyfus(b: AttestorBehavior) -> Dict:
    """
    Classify Dreyfus stage from behavioral signals.
    NOT self-report. Peña critique: need operational definitions.
    """
    signals = {}
    
    # Signal 1: Rule reliance (inverse of deviation rate, BUT only if accurate)
    # Novices follow rules. Experts deviate successfully.
    if b.accuracy_rate > 0.85 and b.rule_deviation_rate > 0.5:
        signals["rule_transcendence"] = True  # Deviates AND accurate = genuine expertise
    elif b.accuracy_rate < 0.7 and b.rule_deviation_rate > 0.5:
        signals["rule_transcendence"] = False  # Deviates but inaccurate = overconfidence
    else:
        signals["rule_transcendence"] = None  # Ambiguous
    
    # Signal 2: Context sensitivity
    signals["context_aware"] = b.context_references > 0.4
    
    # Signal 3: Exception handling (Stage 4-5 see patterns others miss)
    signals["pattern_recognition"] = b.exception_handling > 0.15
    
    # Signal 4: Response time variability
    # Experts: variable (fast on familiar, slow on novel)
    # Novices: consistent (always slow, following checklist)
    # Sybils: consistent (always fast, rubber-stamping)
    signals["adaptive_timing"] = 0.3 < b.response_time_cv < 0.8
    
    # Signal 5: Explanation depth
    # Dreyfus Stage 5: experts often CAN'T explain (tacit knowledge)
    # But Peña critique: unexplained ≠ intuitive
    signals["tacit_knowledge"] = (
        b.accuracy_rate > 0.9 and b.explanation_depth < 0.4
    )
    
    # Composite scoring
    score = 0
    if b.total_attestations > 100: score += 1
    if b.accuracy_rate > 0.85: score += 1
    if signals["rule_transcendence"]: score += 1
    if signals["context_aware"]: score += 1
    if signals["pattern_recognition"]: score += 1
    if signals["adaptive_timing"]: score += 0.5
    if signals["tacit_knowledge"]: score += 0.5
    
    # Map to Dreyfus stage
    if score >= 5: stage = 5
    elif score >= 4: stage = 4
    elif score >= 3: stage = 3
    elif score >= 1.5: stage = 2
    else: stage = 1
    
    stage_info = STAGES[stage]
    
    # Dunning-Kruger check
    dk_risk = "NONE"
    if b.total_attestations < 30 and b.rule_deviation_rate > 0.5:
        dk_risk = "HIGH — deviates from rules with insufficient experience"
    elif b.total_attestations < 50 and b.explanation_depth > 0.8:
        dk_risk = "MODERATE — overexplains (compensating?)"
    
    return {
        "attestor": b.name,
        "classified_stage": stage,
        "stage_name": stage_info["name"],
        "description": stage_info["description"],
        "recommended_guidance": stage_info["guidance"],
        "behavioral_signals": signals,
        "composite_score": score,
        "dunning_kruger_risk": dk_risk,
        "peña_caveat": "Classification is behavioral proxy, not ground truth. "
                       "Context-dependent skills may not follow linear progression."
    }


def demo():
    print("=" * 70)
    print("DREYFUS ATTESTOR CLASSIFIER (Behavioral, NOT Self-Report)")
    print("Dreyfus & Dreyfus (1980) + Peña (2010, PMC2887319) critique")
    print("Tetzlaff (2025): adaptive guidance per classified stage")
    print("=" * 70)
    
    attestors = [
        AttestorBehavior("new_agent", 8, 0.62, 0.1, 0.05, 0.0, 0.15, 0.3),
        AttestorBehavior("learning_agent", 35, 0.74, 0.2, 0.25, 0.05, 0.25, 0.6),
        AttestorBehavior("solid_agent", 80, 0.86, 0.35, 0.50, 0.12, 0.45, 0.7),
        AttestorBehavior("santaclawd", 200, 0.94, 0.6, 0.75, 0.25, 0.55, 0.5),
        AttestorBehavior("bro_agent", 180, 0.92, 0.7, 0.80, 0.30, 0.60, 0.35),
        # Dunning-Kruger case: low experience, high deviation, low accuracy
        AttestorBehavior("overconfident", 15, 0.55, 0.65, 0.10, 0.02, 0.20, 0.9),
        # Sybil: fast, consistent, no context, rubber-stamp
        AttestorBehavior("sybil_bot", 500, 0.70, 0.05, 0.02, 0.00, 0.05, 0.1),
    ]
    
    for a in attestors:
        result = classify_dreyfus(a)
        print(f"\n{'='*50}")
        print(f"  {result['attestor']}: Stage {result['classified_stage']} — {result['stage_name']}")
        print(f"  {result['description']}")
        print(f"  Guidance: {result['recommended_guidance']}")
        print(f"  Score: {result['composite_score']}/6")
        if result['dunning_kruger_risk'] != "NONE":
            print(f"  ⚠️ DK Risk: {result['dunning_kruger_risk']}")
        
        sigs = result['behavioral_signals']
        active = [k for k,v in sigs.items() if v is True]
        if active:
            print(f"  Signals: {', '.join(active)}")
    
    print(f"\n{'='*70}")
    print("KEY INSIGHTS:")
    print("1. Self-report expertise = unreliable (Dunning-Kruger)")
    print("2. Behavioral classification: accuracy × deviation = real signal")
    print("3. Experts deviate AND succeed. Overconfident deviate AND fail.")
    print("4. Sybils: high volume, low deviation, no context = Stage 1 forever")
    print("5. Peña caveat: linear progression may not apply to complex skills")
    print(f"{'='*70}")


if __name__ == "__main__":
    demo()
