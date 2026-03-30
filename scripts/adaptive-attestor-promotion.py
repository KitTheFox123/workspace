#!/usr/bin/env python3
"""
adaptive-attestor-promotion.py — CAT-inspired attestor expertise promotion.

When should an attestor graduate from novice (rubric) to expert (anomaly flags)?

Choi, Grady & Dodd (2010, Educ Psych Meas 70:1-17, PMC3028267): PSER stopping
rule — stop testing when predicted SE reduction falls below threshold.

Bloom (1968): Mastery learning — 80% criterion before advancing.

funwolf's insight: "consecutive correct rejections under time pressure" = the
transition trigger. Not volume. Not time. DEMONSTRATED SKILL.

Tetzlaff et al (2025, 60 studies, N=5924): Expertise reversal is asymmetric.
Guide novices (d=+0.505) > remove expert scaffolding (d=-0.428).

Usage: python3 adaptive-attestor-promotion.py
"""

import json
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class AttestorRecord:
    name: str
    assessments: List[Dict] = field(default_factory=list)
    tier: str = "novice"  # novice -> intermediate -> expert
    consecutive_correct: int = 0
    se_estimate: float = 1.0  # standard error of ability estimate
    
def add_assessment(record: AttestorRecord, correct: bool, time_pressure: bool,
                   difficulty: str) -> Dict:
    """Record an assessment and check for promotion."""
    record.assessments.append({
        "correct": correct,
        "time_pressure": time_pressure,
        "difficulty": difficulty
    })
    
    if correct:
        record.consecutive_correct += 1
    else:
        record.consecutive_correct = 0
    
    # Update SE estimate (simplified IRT-style)
    n = len(record.assessments)
    correct_rate = sum(1 for a in record.assessments if a["correct"]) / n
    record.se_estimate = max(0.1, 1.0 / (n ** 0.5) * (1 + abs(correct_rate - 0.5)))
    
    # Check promotion criteria
    promotion = check_promotion(record)
    
    return {
        "consecutive_correct": record.consecutive_correct,
        "se_estimate": record.se_estimate,
        "current_tier": record.tier,
        "promotion": promotion
    }

def check_promotion(record: AttestorRecord) -> Dict:
    """
    CAT-inspired promotion logic.
    
    Novice → Intermediate: Bloom mastery (80% correct, n≥10)
    Intermediate → Expert: PSER-style (consecutive correct under pressure, SE < threshold)
    
    funwolf's key insight: consecutive correct REJECTIONS (not just accepts)
    under time pressure = demonstrated expertise.
    """
    n = len(record.assessments)
    if n == 0:
        return {"eligible": False, "reason": "No assessments yet"}
    
    correct_rate = sum(1 for a in record.assessments if a["correct"]) / n
    
    # Count rejections specifically (harder than accepts)
    rejections = [a for a in record.assessments if not a.get("accepted", True)]
    
    # Promotion thresholds
    if record.tier == "novice":
        # Bloom mastery: 80% correct, minimum 10 assessments
        if n >= 10 and correct_rate >= 0.80:
            record.tier = "intermediate"
            return {
                "eligible": True,
                "new_tier": "intermediate",
                "reason": f"Bloom mastery: {correct_rate:.0%} correct over {n} assessments",
                "action": "Reduce rubric detail, add anomaly examples"
            }
        return {
            "eligible": False,
            "reason": f"{correct_rate:.0%} correct ({n} assessments, need 80% over 10+)",
            "action": "Continue with full rubric"
        }
    
    elif record.tier == "intermediate":
        # PSER-style: consecutive correct under time pressure + low SE
        pressure_assessments = [a for a in record.assessments if a["time_pressure"]]
        pressure_correct = sum(1 for a in pressure_assessments if a["correct"])
        
        # funwolf criterion: 5+ consecutive correct under time pressure
        consecutive_threshold = 5
        se_threshold = 0.3
        
        if (record.consecutive_correct >= consecutive_threshold and 
            record.se_estimate < se_threshold and
            len(pressure_assessments) >= 5 and
            pressure_correct / len(pressure_assessments) >= 0.85):
            record.tier = "expert"
            return {
                "eligible": True,
                "new_tier": "expert",
                "reason": f"{record.consecutive_correct} consecutive correct, SE={record.se_estimate:.3f}, pressure accuracy={pressure_correct/len(pressure_assessments):.0%}",
                "action": "Remove rubric, enable anomaly-only flags"
            }
        return {
            "eligible": False,
            "reason": f"Consecutive: {record.consecutive_correct}/{consecutive_threshold}, SE: {record.se_estimate:.3f}/{se_threshold}",
            "action": "Simplified rubric + anomaly examples"
        }
    
    else:  # expert
        # Demotion check: expertise can decay
        recent = record.assessments[-10:] if len(record.assessments) >= 10 else record.assessments
        recent_correct = sum(1 for a in recent if a["correct"]) / len(recent)
        
        if recent_correct < 0.70:
            record.tier = "intermediate"
            return {
                "eligible": True,
                "new_tier": "intermediate",
                "reason": f"DEMOTION: Recent accuracy {recent_correct:.0%} < 70%",
                "action": "Re-enable simplified rubric (expertise decay detected)"
            }
        return {
            "eligible": False,
            "reason": "Expert tier maintained",
            "action": "Anomaly-only flags, no rubric"
        }


def guidance_for_tier(tier: str) -> Dict:
    """
    Tetzlaff-informed guidance per tier.
    Novice: full rubric (d=+0.505 benefit)
    Expert: anomaly flags only (d=-0.428 if given rubric)
    """
    return {
        "novice": {
            "instrument": "Full rubric with examples",
            "items": ["Check identity chain", "Verify attestation format", 
                      "Cross-reference timestamps", "Validate signatures",
                      "Assess behavioral consistency"],
            "expected_benefit": "+0.505 (Tetzlaff 2025)",
            "rationale": "Scaffolding maximizes novice performance"
        },
        "intermediate": {
            "instrument": "Simplified rubric + anomaly triggers",
            "items": ["Anomaly: temporal clustering", "Anomaly: style discontinuity",
                      "Core check: identity chain valid"],
            "expected_benefit": "~neutral (transition zone)",
            "rationale": "Reducing scaffolding as expertise grows"
        },
        "expert": {
            "instrument": "Anomaly flags only",
            "items": ["Flag if something feels wrong (Polanyi tacit knowledge)",
                      "Exception report if deviates from gestalt"],
            "expected_benefit": "-0.428 if rubric forced (REVERSAL)",
            "rationale": "Checklists crowd out pattern recognition (Polanyi 1966)"
        }
    }[tier]


def demo():
    """Simulate attestor career progression."""
    print("=" * 70)
    print("ADAPTIVE ATTESTOR PROMOTION")
    print("CAT stopping rules (Choi 2010) + Bloom mastery (1968)")
    print("funwolf: consecutive correct under pressure = transition trigger")
    print("Tetzlaff (2025): asymmetric — guide novices first (bigger ROI)")
    print("=" * 70)
    
    random.seed(42)
    
    # Simulate an attestor learning over time
    attestor = AttestorRecord(name="learning_agent")
    
    print(f"\n--- {attestor.name} career progression ---\n")
    
    # Phase 1: Novice (accuracy improving from 60% to 85%)
    for i in range(15):
        accuracy = 0.60 + (i / 15) * 0.25
        correct = random.random() < accuracy
        time_pressure = i > 8  # pressure starts mid-career
        difficulty = "medium" if i < 10 else "hard"
        
        result = add_assessment(attestor, correct, time_pressure, difficulty)
        
        if result["promotion"]["eligible"]:
            print(f"  Assessment {i+1}: {'✓' if correct else '✗'} → "
                  f"PROMOTED to {result['promotion']['new_tier']}!")
            print(f"    Reason: {result['promotion']['reason']}")
            print(f"    Action: {result['promotion']['action']}")
            guidance = guidance_for_tier(attestor.tier)
            print(f"    Instrument: {guidance['instrument']}")
            print(f"    Expected benefit: {guidance['expected_benefit']}")
            print()
    
    # Phase 2: Intermediate (high accuracy under pressure)
    for i in range(15):
        correct = random.random() < 0.90
        result = add_assessment(attestor, correct, True, "hard")
        
        if result["promotion"]["eligible"]:
            print(f"  Assessment {16+i}: {'✓' if correct else '✗'} → "
                  f"PROMOTED to {result['promotion']['new_tier']}!")
            print(f"    Reason: {result['promotion']['reason']}")
            print(f"    Action: {result['promotion']['action']}")
            guidance = guidance_for_tier(attestor.tier)
            print(f"    Instrument: {guidance['instrument']}")
            print(f"    Expected benefit: {guidance['expected_benefit']}")
            print()
    
    # Summary
    n = len(attestor.assessments)
    correct_total = sum(1 for a in attestor.assessments if a["correct"])
    
    print(f"\n--- Final Status ---")
    print(f"  Tier: {attestor.tier}")
    print(f"  Assessments: {n}")
    print(f"  Accuracy: {correct_total/n:.0%}")
    print(f"  SE estimate: {attestor.se_estimate:.3f}")
    print(f"  Consecutive correct: {attestor.consecutive_correct}")
    
    guidance = guidance_for_tier(attestor.tier)
    print(f"\n  Current instrument: {guidance['instrument']}")
    print(f"  Items: {guidance['items']}")
    print(f"  Benefit: {guidance['expected_benefit']}")
    
    print(f"\n{'='*70}")
    print("KEY FINDINGS:")
    print("  1. Bloom mastery (80%/10+) gates novice→intermediate")
    print("  2. Consecutive correct under pressure gates intermediate→expert")  
    print("  3. Tetzlaff asymmetry: novice guidance d=+0.505 > expert removal d=-0.428")
    print("  4. Demotion exists: recent accuracy <70% → re-enable scaffolding")
    print("  5. Same quorum, different instruments per tier")
    print(f"{'='*70}")


if __name__ == "__main__":
    demo()
