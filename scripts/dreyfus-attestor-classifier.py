#!/usr/bin/env python3
"""
dreyfus-attestor-classifier.py — Dreyfus 5-stage skill acquisition for attestors.

Dreyfus & Dreyfus (1980, 1986): 5 stages of skill acquisition:
  1. Novice: context-free rules, no discretionary judgment
  2. Advanced beginner: situational elements, aspects recognized
  3. Competent: hierarchical decision-making, emotional involvement
  4. Proficient: holistic recognition, intuitive problem identification
  5. Expert: intuitive response, no decomposition needed

Hadjimichael, Ribeiro & Tsoukas (2024, Organization Studies):
  Embodiment enables tacit knowledge acquisition through
  Merleau-Ponty's "body schema" — skill becomes part of the body.

Tetzlaff et al (2025): Guidance helps stages 1-2, HARMS stages 4-5.
funwolf insight: consecutive correct rejections under time pressure
  = stage 3→4 transition marker.

Usage: python3 dreyfus-attestor-classifier.py
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple

@dataclass
class AttestorProfile:
    name: str
    total_attestations: int
    correct_rejections: int       # Said "no" correctly
    false_acceptances: int        # Said "yes" incorrectly
    avg_decision_time_s: float    # Seconds per attestation
    time_pressure_accuracy: float # Accuracy when rushed (0-1)
    consecutive_correct_rejections: int  # funwolf's metric
    months_active: int
    uses_checklist: bool
    
def classify_dreyfus_stage(p: AttestorProfile) -> Tuple[int, str, Dict]:
    """
    Classify attestor into Dreyfus stage 1-5.
    Returns (stage, label, evidence).
    """
    signals = {}
    score = 0
    
    # Signal 1: Volume (experience)
    if p.total_attestations >= 500:
        signals["volume"] = "expert-level (500+)"
        score += 2
    elif p.total_attestations >= 100:
        signals["volume"] = "proficient (100+)"
        score += 1.5
    elif p.total_attestations >= 30:
        signals["volume"] = "competent (30+)"
        score += 1
    elif p.total_attestations >= 10:
        signals["volume"] = "advanced-beginner (10+)"
        score += 0.5
    else:
        signals["volume"] = "novice (<10)"
        score += 0
    
    # Signal 2: Rejection under pressure (funwolf's insight)
    # This is the KEY transition marker: stage 3→4
    if p.time_pressure_accuracy > 0.85 and p.consecutive_correct_rejections >= 5:
        signals["pressure_rejection"] = f"STRONG — {p.consecutive_correct_rejections} consecutive correct rejections under pressure"
        score += 2
    elif p.time_pressure_accuracy > 0.7:
        signals["pressure_rejection"] = "moderate"
        score += 1
    else:
        signals["pressure_rejection"] = "weak — struggles under time pressure"
        score += 0
    
    # Signal 3: Decision speed (experts are FASTER, not slower)
    # Dreyfus: experts don't decompose — they recognize patterns holistically
    if p.avg_decision_time_s < 5 and p.total_attestations > 100:
        signals["speed"] = "fast+experienced = intuitive (expert)"
        score += 2
    elif p.avg_decision_time_s < 10:
        signals["speed"] = "moderate speed"
        score += 1
    else:
        signals["speed"] = "slow — still decomposing"
        score += 0
    
    # Signal 4: False acceptance rate (experts reject more — they see subtleties)
    if p.total_attestations > 0:
        fa_rate = p.false_acceptances / p.total_attestations
        rej_rate = p.correct_rejections / p.total_attestations
        if fa_rate < 0.02 and rej_rate > 0.15:
            signals["discrimination"] = f"high selectivity (FA={fa_rate:.1%}, rej={rej_rate:.1%})"
            score += 2
        elif fa_rate < 0.05:
            signals["discrimination"] = f"moderate (FA={fa_rate:.1%})"
            score += 1
        else:
            signals["discrimination"] = f"low — accepts too readily (FA={fa_rate:.1%})"
            score += 0
    
    # Signal 5: Temporal depth
    if p.months_active >= 12:
        signals["temporal"] = "deep (12+ months)"
        score += 1
    elif p.months_active >= 3:
        signals["temporal"] = "moderate (3+ months)"
        score += 0.5
    else:
        signals["temporal"] = "shallow (<3 months)"
        score += 0
    
    # Map score to Dreyfus stage
    if score >= 8:
        stage, label = 5, "Expert"
    elif score >= 6:
        stage, label = 4, "Proficient"
    elif score >= 4:
        stage, label = 3, "Competent"
    elif score >= 2:
        stage, label = 2, "Advanced Beginner"
    else:
        stage, label = 1, "Novice"
    
    return stage, label, signals

def recommend_guidance(stage: int, uses_checklist: bool) -> Dict:
    """
    Recommend guidance level based on Dreyfus stage.
    Tetzlaff (2025): guidance helps novices (d=+0.505), harms experts (d=-0.428).
    """
    recommendations = {
        1: {
            "guidance": "FULL — detailed rubric, step-by-step checklist",
            "tetzlaff_effect": "+0.505 (strong benefit)",
            "checklist": "REQUIRED",
            "reversal_risk": False
        },
        2: {
            "guidance": "HIGH — rubric with situational examples",
            "tetzlaff_effect": "+0.3 (moderate benefit)",
            "checklist": "RECOMMENDED",
            "reversal_risk": False
        },
        3: {
            "guidance": "MODERATE — goals and criteria, not procedures",
            "tetzlaff_effect": "~neutral",
            "checklist": "OPTIONAL",
            "reversal_risk": False
        },
        4: {
            "guidance": "LOW — anomaly flags only, trust intuition",
            "tetzlaff_effect": "-0.2 (mild harm from over-guidance)",
            "checklist": "REMOVE",
            "reversal_risk": uses_checklist
        },
        5: {
            "guidance": "MINIMAL — exception triggers, no checklist",
            "tetzlaff_effect": "-0.428 (significant harm)",
            "checklist": "HARMFUL — crowds out tacit pattern matching",
            "reversal_risk": uses_checklist
        }
    }
    
    rec = recommendations[stage]
    if rec["reversal_risk"]:
        rec["warning"] = "⚠️ EXPERTISE REVERSAL ACTIVE — current checklist is degrading performance"
    return rec


def demo():
    print("=" * 70)
    print("DREYFUS ATTESTOR CLASSIFIER")
    print("Dreyfus & Dreyfus (1980): 5-stage skill acquisition")
    print("+ funwolf: rejection under pressure = transition marker")
    print("+ Tetzlaff (2025): adaptive guidance per stage")
    print("=" * 70)
    
    attestors = [
        AttestorProfile("new_bot", 5, 0, 2, 30.0, 0.40, 0, 1, True),
        AttestorProfile("growing_agent", 45, 8, 3, 12.0, 0.65, 2, 4, True),
        AttestorProfile("solid_attestor", 150, 30, 5, 8.0, 0.78, 4, 8, True),
        AttestorProfile("santaclawd", 600, 120, 8, 3.5, 0.92, 12, 18, True),
        AttestorProfile("bro_agent", 400, 80, 5, 4.0, 0.88, 8, 14, False),
    ]
    
    for p in attestors:
        stage, label, signals = classify_dreyfus_stage(p)
        rec = recommend_guidance(stage, p.uses_checklist)
        
        print(f"\n{'─' * 50}")
        print(f"  {p.name} → Stage {stage}: {label}")
        print(f"  Attestations: {p.total_attestations} | Months: {p.months_active}")
        print(f"  Pressure accuracy: {p.time_pressure_accuracy:.0%} | Consec. rejections: {p.consecutive_correct_rejections}")
        print(f"  Currently uses checklist: {'Yes' if p.uses_checklist else 'No'}")
        print(f"  Signals:")
        for k, v in signals.items():
            print(f"    {k}: {v}")
        print(f"  Guidance: {rec['guidance']}")
        print(f"  Tetzlaff effect: {rec['tetzlaff_effect']}")
        print(f"  Checklist: {rec['checklist']}")
        if rec.get("warning"):
            print(f"  {rec['warning']}")
    
    # funwolf's insight
    print(f"\n{'=' * 70}")
    print("KEY TRANSITIONS:")
    print("  Stage 2→3: emotional investment (cares about being wrong)")
    print("  Stage 3→4: consecutive correct REJECTIONS under time pressure")
    print("             (funwolf: acceptance is easy, rejection under pressure = internalized)")
    print("  Stage 4→5: no decomposition — holistic pattern, instant response")
    print("")
    print("Polanyi (1966): 'We know more than we can tell.'")
    print("Expert attestors can't explain WHY something is wrong.")
    print("Checklists force them to decompose what should be gestalt.")
    print("That decomposition IS the harm (Tetzlaff d=-0.428).")
    print("=" * 70)


if __name__ == "__main__":
    demo()
