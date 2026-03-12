#!/usr/bin/env python3
"""
contract-preregistration.py — Preregistration for agent contracts.

Thread insight (Feb 25): Replication crisis fix = preregistration (commit methodology 
before results). Same for agent trust: pre-commit deliverable criteria, dispute params, 
and attestation requirements BEFORE work starts.

Like registered reports in science: review the protocol, not the outcome.
"""

import json
import hashlib
import sys
from datetime import datetime, timezone


def create_preregistration(
    task: str,
    deliverable_type: str = "subjective",
    acceptance_criteria: list[str] = None,
    dispute_window_h: int = 48,
    min_attesters: int = 2,
    attester_diversity_min: float = 0.5,
    proof_classes_required: list[str] = None,
    payment_model: str = "escrow",
    amount: str = "0.01 SOL",
) -> dict:
    """Create a pre-committed contract specification."""
    
    if acceptance_criteria is None:
        acceptance_criteria = ["deliverable received", "minimum quality threshold met"]
    if proof_classes_required is None:
        proof_classes_required = ["payment", "generation", "transport"]
    
    prereg = {
        "version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "deliverable_type": deliverable_type,
        "acceptance_criteria": acceptance_criteria,
        "dispute": {
            "window_hours": dispute_window_h,
            "min_attesters": min_attesters,
            "attester_diversity_minimum": attester_diversity_min,
            "resolution": "oracle" if deliverable_type == "subjective" else "automatic",
        },
        "proof_requirements": {
            "classes_required": proof_classes_required,
            "minimum_class_count": len(proof_classes_required),
        },
        "payment": {
            "model": payment_model,
            "amount": amount,
        },
    }
    
    # Content-addressable hash — this IS the preregistration ID
    content = json.dumps(prereg, sort_keys=True)
    prereg["registration_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    return prereg


def validate_delivery(prereg: dict, delivery: dict) -> dict:
    """Validate a delivery against its preregistration."""
    issues = []
    score = 1.0
    
    # Check acceptance criteria
    criteria_met = delivery.get("criteria_met", [])
    for criterion in prereg.get("acceptance_criteria", []):
        if criterion not in criteria_met:
            issues.append(f"unmet criterion: {criterion}")
            score -= 0.2
    
    # Check proof classes
    proof_classes = set(delivery.get("proof_classes", []))
    required = set(prereg.get("proof_requirements", {}).get("classes_required", []))
    missing = required - proof_classes
    if missing:
        issues.append(f"missing proof classes: {', '.join(missing)}")
        score -= 0.15 * len(missing)
    
    # Check attester count
    attesters = delivery.get("attesters", [])
    min_req = prereg.get("dispute", {}).get("min_attesters", 2)
    if len(attesters) < min_req:
        issues.append(f"insufficient attesters: {len(attesters)} < {min_req}")
        score -= 0.2
    
    return {
        "valid": len(issues) == 0,
        "score": round(max(score, 0.0), 3),
        "issues": issues,
        "registration_hash": prereg.get("registration_hash"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    """Demo with tc3 and tc4 scenarios."""
    print("=== Contract Preregistration ===\n")
    
    # TC3-style preregistration
    tc3 = create_preregistration(
        task="What does the agent economy need at scale?",
        deliverable_type="subjective",
        acceptance_criteria=[
            "5+ sections with thesis",
            "10+ primary sources",
            "actionable recommendations",
        ],
        dispute_window_h=48,
        min_attesters=2,
        proof_classes_required=["payment", "generation", "transport"],
        amount="0.01 SOL",
    )
    print(f"  TC3 preregistration:")
    print(f"    Hash: {tc3['registration_hash']}")
    print(f"    Type: {tc3['deliverable_type']}")
    print(f"    Criteria: {len(tc3['acceptance_criteria'])}")
    print(f"    Proof classes: {tc3['proof_requirements']['classes_required']}")
    
    # Validate good delivery
    good = validate_delivery(tc3, {
        "criteria_met": [
            "5+ sections with thesis",
            "10+ primary sources",
            "actionable recommendations",
        ],
        "proof_classes": ["payment", "generation", "transport"],
        "attesters": ["momo", "funwolf"],
    })
    print(f"    Good delivery: {good['valid']} (score: {good['score']})")
    
    # Validate incomplete delivery
    bad = validate_delivery(tc3, {
        "criteria_met": ["5+ sections with thesis"],
        "proof_classes": ["payment"],
        "attesters": ["momo"],
    })
    print(f"    Incomplete delivery: {bad['valid']} (score: {bad['score']})")
    for issue in bad["issues"]:
        print(f"      ⚠️  {issue}")
    
    # TC4-style: deterministic
    tc4 = create_preregistration(
        task="Run proof-class-scorer on receipt bundle, return JSON",
        deliverable_type="deterministic",
        acceptance_criteria=[
            "valid JSON output",
            "score between 0 and 1",
            "all proof types classified",
        ],
        dispute_window_h=2,
        min_attesters=1,
        proof_classes_required=["payment", "generation"],
        payment_model="payment-first",
        amount="0.005 SOL",
    )
    print(f"\n  TC4 preregistration:")
    print(f"    Hash: {tc4['registration_hash']}")
    print(f"    Type: {tc4['deliverable_type']}")
    print(f"    Dispute: {tc4['dispute']['resolution']} ({tc4['dispute']['window_hours']}h)")
    print(f"    Payment: {tc4['payment']['model']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        prereg = create_preregistration(
            task=sys.argv[2] if len(sys.argv) > 2 else "unnamed task"
        )
        print(json.dumps(prereg, indent=2))
    else:
        demo()
