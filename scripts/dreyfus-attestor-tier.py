#!/usr/bin/env python3
"""
dreyfus-attestor-tier.py — Dreyfus model skill acquisition for attestor guidance.

Dreyfus & Dreyfus (1980): 5 stages — novice, advanced beginner, competent,
proficient, expert. Each stage uses fundamentally different cognitive strategies.

Peña (2010, Med Ed Online, PMC2887319): Model accepted "almost without debate"
in medicine — itself a cautionary tale. Key criticism: no clear operational
criteria for stage transitions, especially 3→4 (competent→proficient).

Tetzlaff et al (2025): Expertise reversal meta-analysis confirms the mechanism.
Novice d=+0.505 with guidance, expert d=-0.428.

santaclawd insight: "The tier IS the guidance level. Stage 5 experts should get
anomaly triggers, not checklists."

Usage: python3 dreyfus-attestor-tier.py
"""

import json
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class AttestorProfile:
    name: str
    attestation_count: int
    accuracy: float
    domain_months: int
    error_types: List[str]  # what kind of mistakes they make
    uses_intuition: bool    # reports holistic judgment vs checklist

# Dreyfus stages mapped to attestation behavior
DREYFUS_STAGES = {
    1: {
        "name": "Novice",
        "cognition": "context-free rules",
        "guidance": "DETAILED_CHECKLIST",
        "description": "Follows rules without context. Needs explicit steps.",
        "tetzlaff_d": 0.505,  # strong benefit from guidance
    },
    2: {
        "name": "Advanced Beginner",
        "cognition": "situational aspects recognized",
        "guidance": "GUIDED_CHECKLIST",
        "description": "Recognizes patterns from experience but can't prioritize.",
        "tetzlaff_d": 0.35,
    },
    3: {
        "name": "Competent",
        "cognition": "hierarchical decision-making",
        "guidance": "RUBRIC_WITH_FLEXIBILITY",
        "description": "Plans deliberately, accepts responsibility for outcomes.",
        "tetzlaff_d": 0.10,  # near-neutral
    },
    4: {
        "name": "Proficient",
        "cognition": "holistic recognition + analytical decision",
        "guidance": "EXCEPTION_FLAGS_ONLY",
        "description": "Sees situations holistically but still decides analytically.",
        "tetzlaff_d": -0.20,
    },
    5: {
        "name": "Expert",
        "cognition": "intuitive holistic recognition",
        "guidance": "ANOMALY_TRIGGERS",
        "description": "No decomposition. Sees what to do without deliberation.",
        "tetzlaff_d": -0.428,  # harmed by checklists
    },
}

def classify_dreyfus_stage(p: AttestorProfile) -> int:
    """
    Classify attestor into Dreyfus stage.
    
    Peña (2010) criticism: no clear operational criteria for transitions.
    We use behavioral proxies, acknowledging this limitation.
    """
    score = 0
    
    # Experience volume
    if p.attestation_count > 200: score += 3
    elif p.attestation_count > 50: score += 2
    elif p.attestation_count > 10: score += 1
    
    # Accuracy trajectory
    if p.accuracy > 0.92: score += 3
    elif p.accuracy > 0.80: score += 2
    elif p.accuracy > 0.65: score += 1
    
    # Domain tenure
    if p.domain_months > 12: score += 2
    elif p.domain_months > 3: score += 1
    
    # Error types reveal stage
    # Novices: rule-based errors. Experts: novel situation errors.
    novel_errors = sum(1 for e in p.error_types if e in ["edge_case", "novel_scenario", "context_shift"])
    rule_errors = sum(1 for e in p.error_types if e in ["missed_step", "wrong_order", "forgot_rule"])
    
    if novel_errors > rule_errors: score += 2  # Expert-type errors
    elif rule_errors > 0: score -= 1  # Still making novice errors
    
    # Intuition use (Dreyfus stage 4-5 marker)
    if p.uses_intuition and score >= 6: score += 2
    
    # Map score to stage
    if score >= 10: return 5
    elif score >= 7: return 4
    elif score >= 4: return 3
    elif score >= 2: return 2
    else: return 1

def recommend_guidance(stage: int) -> Dict:
    """Return stage-appropriate guidance configuration."""
    s = DREYFUS_STAGES[stage]
    
    config = {
        "stage": stage,
        "stage_name": s["name"],
        "cognition_mode": s["cognition"],
        "guidance_type": s["guidance"],
        "expected_effect": f"d={s['tetzlaff_d']:+.3f}",
    }
    
    # Specific recommendations per stage
    if stage <= 2:
        config["checklist_items"] = [
            "Verify identity hash matches",
            "Check attestation chain completeness",
            "Confirm temporal ordering",
            "Validate co-signer count >= threshold",
            "Cross-reference behavioral signals",
        ]
        config["warning"] = "Do NOT remove checklist. Novice benefit is strongest (d=+0.505)."
    elif stage == 3:
        config["checklist_items"] = [
            "Review attestation context (rubric provided, flexible application)",
            "Flag anomalies for review",
        ]
        config["warning"] = "Transition zone. Monitor for stage 4 indicators."
    elif stage == 4:
        config["checklist_items"] = None
        config["exception_flags"] = [
            "Alert on: attestation count < 3",
            "Alert on: temporal gap > 2× Nyquist threshold",
            "Alert on: new domain (no prior attestations in category)",
        ]
        config["warning"] = "Holistic recognition active. Only flag exceptions."
    else:  # stage 5
        config["checklist_items"] = None
        config["exception_flags"] = None
        config["anomaly_triggers"] = [
            "Pattern break detection (auto)",
            "Cross-domain alert (auto)",
            "Confidence calibration check (periodic)",
        ]
        config["warning"] = "CHECKLISTS HARMFUL at this stage (d=-0.428). Trust gestalt."
    
    return config

def audit_quorum(attestors: List[AttestorProfile]) -> Dict:
    """Audit a quorum for guidance appropriateness."""
    results = []
    mismatches = 0
    
    for a in attestors:
        stage = classify_dreyfus_stage(a)
        guidance = recommend_guidance(stage)
        
        # Check for expertise reversal risk
        reversal = False
        if stage >= 4 and not a.uses_intuition:
            reversal = True  # Being forced into checklist mode
            mismatches += 1
        if stage <= 2 and a.uses_intuition:
            reversal = True  # Skipping needed structure
            mismatches += 1
        
        results.append({
            "attestor": a.name,
            "stage": stage,
            "stage_name": DREYFUS_STAGES[stage]["name"],
            "guidance": guidance["guidance_type"],
            "reversal_risk": reversal,
            "tetzlaff_d": DREYFUS_STAGES[stage]["tetzlaff_d"],
        })
    
    # Peña critique: stage 3→4 transition is hardest to detect
    stage_3_count = sum(1 for r in results if r["stage"] == 3)
    
    return {
        "quorum_size": len(attestors),
        "stage_distribution": {s["name"]: sum(1 for r in results if r["stage"] == i) 
                               for i, s in DREYFUS_STAGES.items()},
        "expertise_reversal_risks": mismatches,
        "stage_3_watch": f"{stage_3_count} attestor(s) in transition zone (hardest to classify — Peña 2010)",
        "one_size_fits_all_harm": sum(abs(r["tetzlaff_d"]) for r in results if r["tetzlaff_d"] < 0),
        "results": results,
    }


def demo():
    print("=" * 70)
    print("DREYFUS ATTESTOR TIERING")
    print("Dreyfus & Dreyfus (1980) + Tetzlaff (2025) + Peña (2010) critique")
    print("The tier IS the guidance level (santaclawd)")
    print("=" * 70)
    
    attestors = [
        AttestorProfile("new_agent", 5, 0.60, 1, ["missed_step", "wrong_order"], False),
        AttestorProfile("learning_agent", 25, 0.74, 4, ["missed_step", "edge_case"], False),
        AttestorProfile("solid_agent", 80, 0.85, 8, ["edge_case", "context_shift"], False),
        AttestorProfile("santaclawd", 250, 0.94, 18, ["novel_scenario", "edge_case"], True),
        AttestorProfile("bro_agent", 180, 0.92, 15, ["novel_scenario"], True),
    ]
    
    audit = audit_quorum(attestors)
    
    print(f"\nQuorum: {audit['quorum_size']} attestors")
    print(f"Distribution: {json.dumps(audit['stage_distribution'])}")
    print(f"Reversal risks: {audit['expertise_reversal_risks']}")
    print(f"Stage 3 watch: {audit['stage_3_watch']}")
    print(f"One-size-all harm: {audit['one_size_fits_all_harm']:.3f} (cumulative negative d)")
    
    print("\n--- Individual Assessments ---")
    for r in audit["results"]:
        flag = " ⚠️ REVERSAL RISK" if r["reversal_risk"] else ""
        print(f"\n  {r['attestor']}: Stage {r['stage']} ({r['stage_name']}){flag}")
        print(f"    Guidance: {r['guidance']}")
        print(f"    Expected effect of current guidance: d={r['tetzlaff_d']:+.3f}")
    
    # Show guidance detail for extremes
    print("\n--- Guidance Details (Stage 1 vs Stage 5) ---")
    g1 = recommend_guidance(1)
    g5 = recommend_guidance(5)
    
    print(f"\n  STAGE 1 ({g1['stage_name']}):")
    print(f"    Type: {g1['guidance_type']}")
    for item in g1["checklist_items"]:
        print(f"    ☐ {item}")
    print(f"    ⚠️ {g1['warning']}")
    
    print(f"\n  STAGE 5 ({g5['stage_name']}):")
    print(f"    Type: {g5['guidance_type']}")
    for trigger in g5["anomaly_triggers"]:
        print(f"    🔔 {trigger}")
    print(f"    ⚠️ {g5['warning']}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHT: One-size-fits-all checklists are harmful by design.")
    print("Novices need structure (d=+0.505). Experts need absence (d=-0.428).")
    print("Peña (2010): Stage 3→4 transition hardest — watch for it.")
    print("santaclawd: 'Stage 5 experts should get anomaly triggers, not checklists.'")
    print("=" * 70)


if __name__ == "__main__":
    demo()
