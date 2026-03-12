#!/usr/bin/env python3
"""
ostrom-commons-checker.py — Score a protocol/system against Ostrom's 8 design principles.

Ostrom (Nobel 2009) studied commons that survived centuries. 8 principles emerged.
Every failed digital commons violated at least 3. Thread insight (Feb 25):
v0.3 has ~4 of 8. This tool scores any system description.

Usage:
  python3 ostrom-commons-checker.py                    # demo with v0.3
  echo '{"principles": {...}}' | python3 ostrom-commons-checker.py --json
"""

import json
import sys
from datetime import datetime, timezone

PRINCIPLES = {
    "1_clear_boundaries": {
        "name": "Clear boundaries",
        "description": "Who can access the resource? Who are members?",
        "questions": [
            "Are resource boundaries clearly defined?",
            "Is membership/participation clearly defined?",
            "Can outsiders be distinguished from members?",
        ],
    },
    "2_congruent_rules": {
        "name": "Congruent rules (appropriation & provision)",
        "description": "Rules match local conditions. Benefits proportional to contributions.",
        "questions": [
            "Do rules match the actual coordination context?",
            "Are benefits proportional to contributions?",
            "Are rules adapted to local/domain conditions?",
        ],
    },
    "3_collective_choice": {
        "name": "Collective-choice arrangements",
        "description": "Those affected by rules can participate in modifying them.",
        "questions": [
            "Can participants modify the rules?",
            "Is there a governance process for rule changes?",
            "Are affected parties included in decisions?",
        ],
    },
    "4_monitoring": {
        "name": "Monitoring",
        "description": "Monitors are accountable to appropriators or are appropriators themselves.",
        "questions": [
            "Is resource use monitored?",
            "Are monitors accountable to participants?",
            "Is monitoring cost lower than resource value?",
        ],
    },
    "5_graduated_sanctions": {
        "name": "Graduated sanctions",
        "description": "Sanctions for rule violations are graduated, not binary.",
        "questions": [
            "Are sanctions proportional to severity?",
            "Do first-time violations get lighter treatment?",
            "Is there escalation for repeat violations?",
        ],
    },
    "6_conflict_resolution": {
        "name": "Conflict resolution mechanisms",
        "description": "Rapid, low-cost, local arenas for resolving disputes.",
        "questions": [
            "Is there a dispute resolution mechanism?",
            "Is resolution low-cost and accessible?",
            "Can disputes be resolved locally/quickly?",
        ],
    },
    "7_minimal_recognition": {
        "name": "Minimal recognition of rights",
        "description": "External authorities recognize the right of participants to self-organize.",
        "questions": [
            "Can participants self-organize without external permission?",
            "Are participant identities/rights recognized?",
            "Is there sovereignty over internal rules?",
        ],
    },
    "8_nested_enterprises": {
        "name": "Nested enterprises",
        "description": "Governance organized in multiple layers of nested enterprises.",
        "questions": [
            "Are there multiple governance layers?",
            "Does each layer govern its own scope?",
            "Do layers coordinate without centralizing?",
        ],
    },
}


def score_system(assessments: dict) -> dict:
    """Score a system against Ostrom's 8 principles.
    
    assessments: {principle_key: score} where score is 0.0-1.0
    """
    scores = {}
    total = 0.0
    
    for key, principle in PRINCIPLES.items():
        s = assessments.get(key, 0.0)
        scores[key] = {
            "name": principle["name"],
            "score": s,
            "status": "✅" if s >= 0.7 else "⚠️" if s >= 0.4 else "❌",
        }
        total += s
    
    avg = total / len(PRINCIPLES)
    
    # Tier
    if avg >= 0.8:
        tier = "A"
    elif avg >= 0.6:
        tier = "B"
    elif avg >= 0.4:
        tier = "C"
    else:
        tier = "F"
    
    # Weakest principles
    weakest = sorted(scores.items(), key=lambda x: x[1]["score"])[:3]
    
    return {
        "overall_score": round(avg, 3),
        "tier": tier,
        "principles": scores,
        "weakest": [{"key": k, "name": v["name"], "score": v["score"]} for k, v in weakest],
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    """Score v0.3 trust spec against Ostrom."""
    print("=== Ostrom Commons Checker ===\n")
    print("System: v0.3 Agent Trust Spec (Feb 2025 thread)\n")
    
    # Assessment based on thread discussion
    v03 = {
        "1_clear_boundaries": 0.8,    # proof class boundaries defined, attester pools
        "2_congruent_rules": 0.7,     # profile-defined rules match context
        "3_collective_choice": 0.4,   # thread-based evolution, no formal governance
        "4_monitoring": 0.9,          # proof-class-scorer, burst detector, attestation chains
        "5_graduated_sanctions": 0.6, # rep decay exists, but no formal escalation
        "6_conflict_resolution": 0.7, # dispute oracle, tc3 tested it
        "7_minimal_recognition": 0.8, # DID binding, self-sovereign identity
        "8_nested_enterprises": 0.6,  # isnad local + scorer regional, but federation incomplete
    }
    
    result = score_system(v03)
    
    print(f"  Overall: {result['overall_score']} ({result['tier']})\n")
    for key, data in result["principles"].items():
        print(f"  {data['status']} {data['name']}: {data['score']}")
    
    print(f"\n  Weakest:")
    for w in result["weakest"]:
        print(f"    - {w['name']}: {w['score']}")
    
    print(f"\n  Recommendation: Strengthen collective-choice (formal RFC process)")
    print(f"  + graduated sanctions (explicit rep decay curves with escalation)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        result = score_system(data.get("principles", data))
        print(json.dumps(result, indent=2))
    else:
        demo()
