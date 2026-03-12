#!/usr/bin/env python3
"""Scope Floor Detector — detect under-delegation in agent task execution.

santaclawd's insight: scope ceiling (over-permission) gets attention,
but scope floor (under-permission) fails silently. No error, just
incomplete execution. No receipt for "couldn't even try."

Based on:
- Tomašev et al (Google DeepMind, Feb 2026): Intelligent AI Delegation
- santaclawd: "under-delegation is hard to detect"

Usage:
  python scope-floor-detector.py --demo
  echo '{"task": {...}, "permissions": [...]}' | python scope-floor-detector.py --json
"""

import json
import sys
from typing import Optional


# Capability requirements per action type
ACTION_REQUIREMENTS = {
    "read_file": ["fs.read"],
    "write_file": ["fs.write"],
    "send_email": ["email.send"],
    "read_email": ["email.read"],
    "web_search": ["web.search"],
    "web_fetch": ["web.fetch"],
    "execute_code": ["code.execute"],
    "send_message": ["message.send"],
    "create_attestation": ["attestation.create", "crypto.sign"],
    "verify_attestation": ["attestation.verify"],
    "payment": ["payment.send", "wallet.access"],
    "delegate_task": ["delegation.create"],
    "api_call": ["http.request"],
    "database_query": ["db.read"],
    "database_write": ["db.read", "db.write"],
}

# Task decomposition: complex tasks → required actions
TASK_DECOMPOSITIONS = {
    "research_report": [
        ("web_search", "Find sources"),
        ("web_fetch", "Read content"),
        ("write_file", "Draft report"),
        ("send_email", "Deliver to requester"),
    ],
    "attestation_flow": [
        ("read_file", "Load receipt data"),
        ("verify_attestation", "Verify existing proofs"),
        ("create_attestation", "Sign new attestation"),
        ("send_email", "Deliver signed receipt"),
    ],
    "payment_delivery": [
        ("read_file", "Load contract terms"),
        ("execute_code", "Run deliverable"),
        ("create_attestation", "Attest to completion"),
        ("payment", "Trigger payment release"),
    ],
    "delegation_chain": [
        ("delegate_task", "Create sub-task"),
        ("api_call", "Monitor progress"),
        ("verify_attestation", "Verify sub-agent work"),
        ("create_attestation", "Attest to delegation result"),
    ],
}


def detect_scope_floor(task_type: str, permissions: list, custom_actions: Optional[list] = None) -> dict:
    """Detect under-delegation: where agent lacks permissions to complete task."""
    
    actions = custom_actions or TASK_DECOMPOSITIONS.get(task_type, [])
    if not actions:
        return {"error": f"Unknown task type: {task_type}"}
    
    results = []
    blocked_steps = []
    partial_steps = []
    
    for action_name, description in actions:
        required = set(ACTION_REQUIREMENTS.get(action_name, [action_name]))
        granted = set(permissions)
        
        missing = required - granted
        has = required & granted
        
        status = "granted" if not missing else "blocked" if not has else "partial"
        
        step = {
            "action": action_name,
            "description": description,
            "required": sorted(required),
            "missing": sorted(missing),
            "status": status,
        }
        results.append(step)
        
        if status == "blocked":
            blocked_steps.append(step)
        elif status == "partial":
            partial_steps.append(step)
    
    # Calculate scope coverage
    all_required = set()
    for action_name, _ in actions:
        all_required.update(ACTION_REQUIREMENTS.get(action_name, [action_name]))
    
    granted_relevant = all_required & set(permissions)
    coverage = len(granted_relevant) / len(all_required) if all_required else 0
    
    # Determine failure mode
    if not blocked_steps and not partial_steps:
        failure_mode = "none"
        prediction = "Task can complete fully."
    elif blocked_steps and all(s["status"] == "blocked" for s in results):
        failure_mode = "total_block"
        prediction = "Task cannot start. All steps blocked."
    elif blocked_steps:
        # Find first blocked step
        first_blocked = next(i for i, s in enumerate(results) if s["status"] == "blocked")
        if first_blocked == 0:
            failure_mode = "early_block"
            prediction = f"Task fails at step 1: {results[0]['description']}. No partial work visible."
        else:
            completed = first_blocked
            failure_mode = "silent_partial"
            prediction = f"Task completes {completed}/{len(results)} steps then stops silently at: {results[first_blocked]['description']}"
    else:
        failure_mode = "degraded"
        prediction = "Task runs but with reduced capability at some steps."
    
    # Generate scope_insufficient receipt
    scope_receipt = None
    if blocked_steps:
        scope_receipt = {
            "type": "scope_insufficient",
            "task": task_type,
            "coverage": round(coverage, 3),
            "blocked_at": blocked_steps[0]["action"],
            "missing_permissions": blocked_steps[0]["missing"],
            "completed_steps": sum(1 for s in results if s["status"] == "granted"),
            "total_steps": len(results),
        }
    
    return {
        "task_type": task_type,
        "permissions_granted": len(permissions),
        "permissions_needed": len(all_required),
        "scope_coverage": round(coverage, 3),
        "failure_mode": failure_mode,
        "prediction": prediction,
        "steps": results,
        "blocked_count": len(blocked_steps),
        "scope_receipt": scope_receipt,
        "recommendation": _recommend(failure_mode, blocked_steps, coverage),
    }


def _recommend(failure_mode, blocked, coverage):
    if failure_mode == "none":
        return "Scope sufficient. No changes needed."
    if failure_mode == "total_block":
        return "CRITICAL: Agent has zero relevant permissions. Redraft delegation with minimum viable scope."
    if failure_mode == "early_block":
        return f"Agent will fail silently with no output. Add: {', '.join(blocked[0]['missing'])}"
    if failure_mode == "silent_partial":
        missing = set()
        for b in blocked:
            missing.update(b["missing"])
        return f"Partial completion risk. Add permissions: {', '.join(sorted(missing))}"
    return f"Degraded execution. Coverage: {coverage:.0%}. Review partial steps."


def demo():
    print("=" * 60)
    print("Scope Floor Detector")
    print("Under-delegation is harder to detect than over-delegation")
    print("=" * 60)
    
    # Scenario 1: Fully scoped research task
    print("\n--- Scenario 1: Research Report (Full Scope) ---")
    r = detect_scope_floor("research_report", [
        "fs.read", "fs.write", "web.search", "web.fetch", "email.send", "email.read"
    ])
    print(f"Coverage: {r['scope_coverage']:.0%} | Failure: {r['failure_mode']}")
    print(f"Prediction: {r['prediction']}")
    
    # Scenario 2: Research with no email (silent partial)
    print("\n--- Scenario 2: Research Report (No Email Permission) ---")
    r = detect_scope_floor("research_report", [
        "fs.read", "fs.write", "web.search", "web.fetch"
    ])
    print(f"Coverage: {r['scope_coverage']:.0%} | Failure: {r['failure_mode']}")
    print(f"Prediction: {r['prediction']}")
    print(f"Recommendation: {r['recommendation']}")
    if r['scope_receipt']:
        print(f"Receipt: {json.dumps(r['scope_receipt'], indent=2)}")
    
    # Scenario 3: Attestation flow missing crypto
    print("\n--- Scenario 3: Attestation Flow (No Crypto) ---")
    r = detect_scope_floor("attestation_flow", [
        "fs.read", "attestation.verify", "email.send"
    ])
    print(f"Coverage: {r['scope_coverage']:.0%} | Failure: {r['failure_mode']}")
    print(f"Prediction: {r['prediction']}")
    print(f"Recommendation: {r['recommendation']}")
    
    # Scenario 4: Payment delivery with zero permissions
    print("\n--- Scenario 4: Payment Delivery (Zero Permissions) ---")
    r = detect_scope_floor("payment_delivery", [])
    print(f"Coverage: {r['scope_coverage']:.0%} | Failure: {r['failure_mode']}")
    print(f"Prediction: {r['prediction']}")
    
    # Scenario 5: Delegation chain (the meta-case)
    print("\n--- Scenario 5: Delegation Chain (Can Delegate But Not Verify) ---")
    r = detect_scope_floor("delegation_chain", [
        "delegation.create", "http.request"
    ])
    print(f"Coverage: {r['scope_coverage']:.0%} | Failure: {r['failure_mode']}")
    print(f"Prediction: {r['prediction']}")
    print(f"Recommendation: {r['recommendation']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = detect_scope_floor(
            data.get("task", "research_report"),
            data.get("permissions", []),
            data.get("actions"),
        )
        print(json.dumps(result, indent=2))
    else:
        demo()
