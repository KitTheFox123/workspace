#!/usr/bin/env python3
"""ai-loafing-detector.py — Social loafing detector for human-AI teams.

Based on Stieglitz, Mirbabaie & Möllmann (2021, PMC8528661):
humans social-loaf MORE when AI assistants are on the team.
Responsibility diffuses to the machine.

Measures 4 signals:
1. Contribution asymmetry (AI does increasing share)
2. Responsibility attribution (blame shifts to AI on failure)
3. Evaluation potential (can individual human effort be measured?)
4. Task dispensability (does human feel replaceable?)

Usage:
    python3 ai-loafing-detector.py [--demo]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class LoafingSignal:
    name: str
    value: float  # 0-1, higher = more loafing
    description: str
    mitigation: str


def analyze_team(
    ai_contribution_ratio: float,  # 0-1: fraction of output by AI
    blame_on_ai: float,           # 0-1: fraction of failures attributed to AI
    individual_measurable: bool,   # can individual human contributions be measured?
    human_feels_replaceable: float # 0-1: how replaceable does human feel?
) -> dict:
    """Analyze a human-AI team for social loafing risk."""
    
    signals = [
        LoafingSignal(
            name="contribution_asymmetry",
            value=ai_contribution_ratio,
            description=f"AI produces {ai_contribution_ratio*100:.0f}% of output",
            mitigation="Assign specific deliverables to humans"
        ),
        LoafingSignal(
            name="responsibility_diffusion",
            value=blame_on_ai,
            description=f"{blame_on_ai*100:.0f}% of failures attributed to AI",
            mitigation="Named accountability for review decisions"
        ),
        LoafingSignal(
            name="evaluation_potential",
            value=0.2 if individual_measurable else 0.8,
            description="Individual contributions " + ("measurable" if individual_measurable else "NOT measurable"),
            mitigation="Track per-person review/approval rates"
        ),
        LoafingSignal(
            name="task_dispensability",
            value=human_feels_replaceable,
            description=f"Perceived replaceability: {human_feels_replaceable*100:.0f}%",
            mitigation="Assign uniquely human tasks (judgment, context, ethics)"
        ),
    ]
    
    composite = sum(s.value for s in signals) / len(signals)
    
    if composite < 0.3:
        grade, risk = "A", "LOW"
    elif composite < 0.5:
        grade, risk = "B", "MODERATE"
    elif composite < 0.7:
        grade, risk = "D", "HIGH"
    else:
        grade, risk = "F", "CRITICAL"
    
    return {
        "signals": [asdict(s) for s in signals],
        "composite_score": round(composite, 3),
        "grade": grade,
        "risk_level": risk,
        "insight": "Stieglitz 2021: AI teammates increase social loafing via "
                  "responsibility diffusion. Named accountability + measurable "
                  "individual output = primary mitigations.",
        "ringelmann_parallel": "Ringelmann 1913: 8 people = 49% potential. "
                             "AI teammate = perceived group size increase."
    }


def demo():
    """Run demo scenarios."""
    scenarios = [
        ("Healthy team", dict(ai_contribution_ratio=0.3, blame_on_ai=0.2, individual_measurable=True, human_feels_replaceable=0.2)),
        ("AI-dependent team", dict(ai_contribution_ratio=0.8, blame_on_ai=0.7, individual_measurable=False, human_feels_replaceable=0.6)),
        ("Attestor pool (named)", dict(ai_contribution_ratio=0.5, blame_on_ai=0.3, individual_measurable=True, human_feels_replaceable=0.3)),
        ("Attestor pool (anonymous)", dict(ai_contribution_ratio=0.5, blame_on_ai=0.6, individual_measurable=False, human_feels_replaceable=0.7)),
    ]
    
    print("=" * 60)
    print("AI SOCIAL LOAFING DETECTOR")
    print("Based on Stieglitz et al 2021 (PMC8528661)")
    print("=" * 60)
    
    for name, params in scenarios:
        result = analyze_team(**params)
        print(f"\n[{result['grade']}] {name} — {result['risk_level']} risk ({result['composite_score']:.3f})")
        for s in result["signals"]:
            print(f"    {s['name']}: {s['value']:.2f} — {s['description']}")
    
    print(f"\n{'='*60}")
    print("Key insight: Named + measurable = low loafing.")
    print("Anonymous + unmeasurable = high loafing.")
    print("Attestor pools need per-attestor scoring.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI social loafing detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(analyze_team(0.5, 0.5, False, 0.5), indent=2))
    else:
        demo()
