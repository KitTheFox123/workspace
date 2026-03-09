#!/usr/bin/env python3
"""skill-atrophy-classifier.py — Distinguish atrophy from disuse from intentional scope reduction.

Based on:
- Arthur et al 1998: skill decay d=-1.4 at 1yr, cognitive > physical
- Macnamara et al 2024 (PMC11239631): AI assistance accelerates skill decay without awareness
- Weitzel & Jonsson 1989: organizational decline 5 stages

Three-signal differential diagnosis:
1. Atrophy: gradual decline in quality when attempting the skill
2. Disuse: absence of attempts (but skill intact if tested)
3. Intentional reduction: explicit scope change (signed scope-commit)

Usage:
    python3 skill-atrophy-classifier.py [--demo]
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class SkillObservation:
    """Single observation of a skill category."""
    skill: str
    cycle: int
    attempted: bool
    quality_score: float  # 0-1, -1 if not attempted
    scope_commit_present: bool  # Was removal signed?


@dataclass
class SkillDiagnosis:
    """Diagnosis for a skill category."""
    skill: str
    classification: str  # atrophy | disuse | intentional_reduction | healthy
    confidence: float
    evidence: str
    severity: str  # low | medium | high | critical
    recommendation: str


def classify_skill(observations: List[SkillObservation]) -> SkillDiagnosis:
    """Classify skill status from observation history."""
    if not observations:
        return SkillDiagnosis("unknown", "insufficient_data", 0.0, "No observations", "low", "Collect data")
    
    skill = observations[0].skill
    attempted = [o for o in observations if o.attempted]
    not_attempted = [o for o in observations if not o.attempted]
    has_scope_removal = any(o.scope_commit_present for o in not_attempted)
    
    # Case 1: Intentional reduction — scope-commit present for removal
    if has_scope_removal and len(not_attempted) > len(observations) * 0.5:
        return SkillDiagnosis(
            skill, "intentional_reduction", 0.95,
            f"Signed scope-commit removes {skill}. {len(not_attempted)}/{len(observations)} cycles absent.",
            "low",
            "Verify scope change was principal-authorized."
        )
    
    # Case 2: Disuse — not attempted but no quality decline when attempted
    if len(not_attempted) > len(observations) * 0.5:
        if attempted:
            recent_quality = [o.quality_score for o in attempted[-3:]]
            avg_quality = sum(recent_quality) / len(recent_quality)
            if avg_quality > 0.6:
                return SkillDiagnosis(
                    skill, "disuse", 0.75,
                    f"Absent {len(not_attempted)}/{len(observations)} cycles but quality={avg_quality:.2f} when attempted.",
                    "medium",
                    "Probe with test task. If quality intact, this is disuse not atrophy."
                )
        return SkillDiagnosis(
            skill, "disuse", 0.60,
            f"Absent {len(not_attempted)}/{len(observations)} cycles. No recent quality data.",
            "high",
            "Administer skill probe. Absence without quality data = ambiguous."
        )
    
    # Case 3: Atrophy — attempted but declining quality
    if len(attempted) >= 3:
        qualities = [o.quality_score for o in attempted]
        first_half = qualities[:len(qualities)//2]
        second_half = qualities[len(qualities)//2:]
        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0
        decline = avg_first - avg_second
        
        if decline > 0.15:
            severity = "critical" if decline > 0.3 else "high" if decline > 0.2 else "medium"
            return SkillDiagnosis(
                skill, "atrophy", min(0.9, 0.5 + decline),
                f"Quality decline: {avg_first:.2f}→{avg_second:.2f} (Δ={decline:.2f}). Arthur et al: cognitive tasks decay fastest.",
                severity,
                "Re-train or increase frequency. Macnamara 2024: AI assistance masks decay."
            )
    
    # Case 4: Healthy
    if attempted:
        avg = sum(o.quality_score for o in attempted) / len(attempted)
        return SkillDiagnosis(
            skill, "healthy", 0.80,
            f"Active in {len(attempted)}/{len(observations)} cycles, avg quality={avg:.2f}.",
            "low",
            "Continue monitoring."
        )
    
    return SkillDiagnosis(skill, "insufficient_data", 0.3, "Mixed signals", "medium", "Collect more data")


def demo():
    """Run demo with 4 skill scenarios."""
    scenarios = {
        "clawk_engagement": [
            SkillObservation("clawk_engagement", i, True, max(0.3, 0.9 - i*0.05), False)
            for i in range(10)
        ],
        "moltbook_posting": [
            SkillObservation("moltbook_posting", i, i < 3, 0.8 if i < 3 else -1, False)
            for i in range(10)
        ],
        "shellmates_dm": [
            SkillObservation("shellmates_dm", i, i < 2, 0.7 if i < 2 else -1, i >= 5)
            for i in range(10)
        ],
        "research": [
            SkillObservation("research", i, True, 0.85 + (i % 3) * 0.05, False)
            for i in range(10)
        ],
    }
    
    print("=" * 60)
    print("SKILL ATROPHY CLASSIFIER")
    print("Based on Arthur et al 1998 + Macnamara 2024")
    print("=" * 60)
    
    for name, obs in scenarios.items():
        dx = classify_skill(obs)
        grade = {"healthy": "A", "intentional_reduction": "B", "disuse": "D", "atrophy": "F"}.get(dx.classification, "C")
        print(f"\n[{grade}] {dx.skill}: {dx.classification} (confidence={dx.confidence:.2f})")
        print(f"    Severity: {dx.severity}")
        print(f"    Evidence: {dx.evidence}")
        print(f"    Action: {dx.recommendation}")
    
    print("\n" + "-" * 60)
    print("Key insight: atrophy looks like variance, not removal.")
    print("Macnamara 2024: AI assistance accelerates decay WITHOUT awareness.")
    print("The question 'did you intend to stop?' IS the diagnostic.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        scenarios = {
            "clawk": [SkillObservation("clawk", i, True, max(0.3, 0.9-i*0.05), False) for i in range(10)],
            "moltbook": [SkillObservation("moltbook", i, i<3, 0.8 if i<3 else -1, False) for i in range(10)],
        }
        results = {k: asdict(classify_skill(v)) for k, v in scenarios.items()}
        print(json.dumps(results, indent=2))
    else:
        demo()
