#!/usr/bin/env python3
"""
expertise-reversal-attestor.py — Adaptive attestation guidance based on expertise level.

Tetzlaff, Simonsmeier, Peters & Brod (2025, Learning & Instruction 98:102142,
60 studies, N=5,924): Expertise reversal effect meta-analysis.
- Novices: d=0.505 benefit from high-assistance instruction
- Experts: d=-0.428 HARMED by same assistance
- ASYMMETRIC: helping novices stronger than withholding from experts
- Moderated by: prior knowledge assessment type, educational status, domain

Kalyuga (2007): Scaffolding that helps novices HARMS experts.
Sweller (2023): Expertise reversal = replication failures explained.

Agent translation: New attestors need checklists. Experienced attestors need
checklists REMOVED or they'll phone it in (redundancy effect).

Usage: python3 expertise-reversal-attestor.py
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Attestor:
    name: str
    attestation_count: int
    accuracy_rate: float  # historical accuracy
    domain_months: int    # months active in domain
    uses_checklist: bool
    
@dataclass 
class AttestationTask:
    complexity: str  # low, medium, high
    domain: str
    element_interactivity: float  # 0-1, from CLT

def classify_expertise(a: Attestor) -> str:
    """Classify attestor expertise level."""
    score = 0
    if a.attestation_count > 100: score += 2
    elif a.attestation_count > 30: score += 1
    if a.accuracy_rate > 0.9: score += 2
    elif a.accuracy_rate > 0.75: score += 1
    if a.domain_months > 12: score += 2
    elif a.domain_months > 3: score += 1
    
    if score >= 5: return "expert"
    elif score >= 3: return "intermediate"
    else: return "novice"

def predict_performance(a: Attestor, task: AttestationTask) -> Dict:
    """
    Predict attestation quality with/without guidance.
    Based on Tetzlaff et al (2025) effect sizes.
    """
    expertise = classify_expertise(a)
    
    # Base performance from accuracy history
    base = a.accuracy_rate
    
    # Effect of guidance (checklist/rubric)
    # Tetzlaff: novice d=0.505, expert d=-0.428
    # Convert d to performance delta (rough: d * 0.1 for practical scale)
    guidance_effects = {
        "novice": 0.505 * 0.1,      # +5.05% with guidance
        "intermediate": 0.05 * 0.1,  # ~neutral
        "expert": -0.428 * 0.1       # -4.28% with guidance (REVERSED)
    }
    
    guidance_delta = guidance_effects[expertise]
    
    # Task complexity modulates
    complexity_mult = {"low": 0.5, "medium": 1.0, "high": 1.5}
    guidance_delta *= complexity_mult.get(task.complexity, 1.0)
    
    # Element interactivity modulates (Sweller 2023)
    # High interactivity = more benefit for novices, more harm for experts
    if task.element_interactivity > 0.7:
        guidance_delta *= 1.3
    
    with_guidance = min(1.0, max(0.0, base + guidance_delta))
    without_guidance = base
    
    # Asymmetry finding: helping novices > withholding from experts
    asymmetry_note = ""
    if expertise == "novice":
        asymmetry_note = "HIGH PRIORITY: Provide guidance (stronger effect than expert withholding)"
    elif expertise == "expert":
        asymmetry_note = "MODERATE: Remove checklist (weaker effect but still significant)"
    
    return {
        "attestor": a.name,
        "expertise": expertise,
        "with_guidance": round(with_guidance, 3),
        "without_guidance": round(without_guidance, 3),
        "guidance_delta": round(guidance_delta, 3),
        "recommendation": "PROVIDE" if guidance_delta > 0 else "REMOVE",
        "asymmetry": asymmetry_note,
        "reversal_risk": expertise == "expert" and a.uses_checklist
    }

def adaptive_quorum(attestors: List[Attestor], task: AttestationTask) -> Dict:
    """
    Design adaptive attestation quorum — different guidance per expertise level.
    """
    results = []
    for a in attestors:
        r = predict_performance(a, task)
        results.append(r)
    
    # Count reversals (experts being harmed by current guidance)
    reversals = sum(1 for r in results if r["reversal_risk"])
    
    # Optimal: mixed expertise with adaptive guidance
    novices = [r for r in results if r["expertise"] == "novice"]
    experts = [r for r in results if r["expertise"] == "expert"]
    
    # Tetzlaff asymmetry: novice assistance d=0.505 > expert withholding d=0.428
    priority = "GUIDE_NOVICES" if len(novices) > 0 else "REMOVE_EXPERT_SCAFFOLDING"
    
    return {
        "quorum_size": len(attestors),
        "expertise_distribution": {
            "novice": len(novices),
            "intermediate": len([r for r in results if r["expertise"] == "intermediate"]),
            "expert": len(experts)
        },
        "active_reversals": reversals,
        "reversal_warning": f"{reversals} expert(s) currently harmed by guidance" if reversals > 0 else "No reversals detected",
        "priority_action": priority,
        "individual_results": results
    }


def demo():
    """Run demonstration with realistic attestor profiles."""
    print("=" * 70)
    print("EXPERTISE REVERSAL ATTESTOR")
    print("Tetzlaff et al (2025, Learning & Instruction, 60 studies, N=5,924)")
    print("Novice d=+0.505 with guidance | Expert d=-0.428 with guidance")
    print("ASYMMETRIC: Helping novices > withholding from experts")
    print("=" * 70)
    
    attestors = [
        Attestor("new_agent_01", attestation_count=5, accuracy_rate=0.65, 
                 domain_months=1, uses_checklist=True),
        Attestor("mid_agent_02", attestation_count=50, accuracy_rate=0.82,
                 domain_months=6, uses_checklist=True),
        Attestor("santaclawd", attestation_count=200, accuracy_rate=0.94,
                 domain_months=18, uses_checklist=True),  # Expert WITH checklist = reversal!
        Attestor("bro_agent", attestation_count=150, accuracy_rate=0.91,
                 domain_months=14, uses_checklist=False),  # Expert without = optimal
        Attestor("fresh_attestor", attestation_count=2, accuracy_rate=0.50,
                 domain_months=0, uses_checklist=False),   # Novice without = suboptimal
    ]
    
    task = AttestationTask(
        complexity="high",
        domain="trust_verification",
        element_interactivity=0.8
    )
    
    print(f"\nTask: {task.domain} (complexity={task.complexity}, EI={task.element_interactivity})")
    print("-" * 70)
    
    result = adaptive_quorum(attestors, task)
    
    print(f"\nQuorum: {result['quorum_size']} attestors")
    print(f"Distribution: {json.dumps(result['expertise_distribution'])}")
    print(f"Active reversals: {result['reversal_warning']}")
    print(f"Priority: {result['priority_action']}")
    
    print("\n--- Individual Predictions ---")
    for r in result["individual_results"]:
        status = "⚠️ REVERSAL" if r["reversal_risk"] else "✓"
        print(f"\n{status} {r['attestor']} ({r['expertise']})")
        print(f"  With guidance:    {r['with_guidance']}")
        print(f"  Without guidance: {r['without_guidance']}")
        print(f"  Delta:            {r['guidance_delta']:+.3f}")
        print(f"  Recommendation:   {r['recommendation']}")
        if r["asymmetry"]:
            print(f"  Note:             {r['asymmetry']}")
    
    # Key insight
    print("\n" + "=" * 70)
    print("KEY INSIGHT (Tetzlaff 2025):")
    print("The effect is NOT symmetrical.")
    print(f"  Helping novices:    d = +0.505 (STRONG)")
    print(f"  Withholding experts: d = -0.428 (moderate)")  
    print("If you can only do one thing: GUIDE THE NOVICES.")
    print("Removing expert scaffolding matters less.")
    print("")
    print("Agent translation:")
    print("  New attestors + detailed rubric = best ROI")
    print("  Experienced attestors + same rubric = HARMFUL (redundancy effect)")
    print("  One-size-fits-all checklists = expertise reversal by design")
    print("=" * 70)


if __name__ == "__main__":
    demo()
