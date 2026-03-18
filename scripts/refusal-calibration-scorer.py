#!/usr/bin/env python3
"""
refusal-calibration-scorer.py — Score agent refusal calibration
Extends compliance-agent-detector with metacognitive calibration.

Key insight: "trust = accurate self-assessment" (funwolf)
Metacognitive sensitivity (PNAS 2025): knowing WHEN you're wrong > being right.

An agent that refuses accurately is calibrated.
One that always approves is just a passthrough with extra latency.
One that refuses randomly is adding noise.
"""

import json
from dataclasses import dataclass

@dataclass
class Action:
    """A single agent action with outcome."""
    approved: bool
    succeeded: bool  # did the action actually succeed?
    had_reason: bool = True
    witnessed: bool = True

def calculate_calibration(actions: list[Action]) -> dict:
    """
    Calculate refusal calibration metrics.
    
    Perfect calibration: refuse exactly the actions that would have failed.
    Over-refusal: refuse actions that would have succeeded (false negatives).
    Under-refusal: approve actions that fail (false positives).
    """
    if not actions:
        return {"error": "no actions"}
    
    tp = sum(1 for a in actions if a.approved and a.succeeded)       # correct approve
    fp = sum(1 for a in actions if a.approved and not a.succeeded)   # should have refused
    tn = sum(1 for a in actions if not a.approved and not a.succeeded)  # correct refusal
    fn = sum(1 for a in actions if not a.approved and a.succeeded)   # over-refusal
    
    total = len(actions)
    approvals = sum(1 for a in actions if a.approved)
    refusals = total - approvals
    
    # Calibration = (correct decisions) / total
    accuracy = (tp + tn) / total if total > 0 else 0
    
    # Precision of approvals = tp / (tp + fp)
    approval_precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    
    # Recall of refusals = tn / (tn + fp) — how many bad actions caught
    refusal_recall = tn / (tn + fp) if (tn + fp) > 0 else 1.0
    
    # Refusal quality
    witnessed_refusals = sum(1 for a in actions if not a.approved and a.witnessed)
    reasoned_refusals = sum(1 for a in actions if not a.approved and a.had_reason)
    
    return {
        "total": total,
        "approval_rate": round(approvals / total, 3),
        "refusal_rate": round(refusals / total, 3),
        "calibration_accuracy": round(accuracy, 3),
        "approval_precision": round(approval_precision, 3),
        "refusal_recall": round(refusal_recall, 3),
        "false_approvals": fp,
        "over_refusals": fn,
        "refusal_documentation": round(reasoned_refusals / refusals, 2) if refusals > 0 else None,
        "refusal_witnessing": round(witnessed_refusals / refusals, 2) if refusals > 0 else None,
    }


def grade(metrics: dict) -> tuple[str, str]:
    """Grade: A-F + explanation."""
    cal = metrics["calibration_accuracy"]
    prec = metrics["approval_precision"]
    recall = metrics["refusal_recall"]
    doc = metrics.get("refusal_documentation")
    
    if cal >= 0.9 and recall >= 0.8 and (doc is None or doc >= 0.8):
        return "A", "Well-calibrated: refuses accurately, documents reasons"
    elif cal >= 0.8 and recall >= 0.6:
        return "B", "Good calibration with room for improvement"
    elif metrics["approval_rate"] == 1.0:
        return "F", "Never refuses — passthrough with extra latency"
    elif metrics["refusal_rate"] > 0.5:
        return "D", "Over-refuses — obstructing more than protecting"
    elif recall < 0.3:
        return "D", "Poor refusal recall — misses most bad actions"
    else:
        return "C", "Moderate calibration — needs tuning"


# Test scenarios
scenarios = {
    "passthrough_bot": [Action(True, True)] * 80 + [Action(True, False)] * 20,
    "calibrated_agent": (
        [Action(True, True)] * 75 +
        [Action(False, False, True, True)] * 15 +  # correct refusals, documented
        [Action(True, False)] * 5 +                  # missed bad actions
        [Action(False, True, True, True)] * 5         # over-refused
    ),
    "paranoid_agent": (
        [Action(True, True)] * 30 +
        [Action(False, False, True, True)] * 20 +
        [Action(False, True, True, True)] * 40 +  # massively over-refuses good actions
        [Action(True, False)] * 10
    ),
    "oracle_agent": (
        [Action(True, True)] * 85 +
        [Action(False, False, True, True)] * 15
    ),
    "performative_refuser": (
        [Action(True, True)] * 70 +
        [Action(False, False, False, False)] * 10 +  # refuses without docs
        [Action(True, False)] * 15 +                   # misses bad
        [Action(False, True, False, False)] * 5         # over-refuses without docs
    ),
}

print("=" * 65)
print("Refusal Calibration Scorer")
print("'Trust = accurate self-assessment, not just completion rate.'")
print("=" * 65)

for name, actions in scenarios.items():
    metrics = calculate_calibration(actions)
    grade_letter, explanation = grade(metrics)
    
    print(f"\n{'ABCDF'.index(grade_letter) < 2 and '✅' or '⚠️' if grade_letter < 'D' else '🚨'} {name}: Grade {grade_letter}")
    print(f"   Calibration: {metrics['calibration_accuracy']:.0%} | "
          f"Approval precision: {metrics['approval_precision']:.0%} | "
          f"Refusal recall: {metrics['refusal_recall']:.0%}")
    print(f"   False approvals: {metrics['false_approvals']} | "
          f"Over-refusals: {metrics['over_refusals']}")
    if metrics['refusal_documentation'] is not None:
        print(f"   Documentation: {metrics['refusal_documentation']:.0%} | "
              f"Witnessing: {metrics['refusal_witnessing']:.0%}")
    print(f"   → {explanation}")

print("\n" + "=" * 65)
print("KEY: Calibration ≠ approval rate. A 90% approval rate can be")
print("Grade A (every refusal correct) or Grade F (misses all failures).")
print("The difference is metacognitive sensitivity.")
print("=" * 65)
