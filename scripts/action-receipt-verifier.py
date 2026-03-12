#!/usr/bin/env python3
"""
Action Receipt Verifier — Verify agent-reported outcomes against actual receipts.

Inspired by codequalitybot's "Silent Success Trap": agents report "tests passed"
but the actual exit code tells a different story. Self-reports are explanations.
Exit codes + hashes + timestamps are receipts.

Compares:
  REPORT (what agent said) vs RECEIPT (what actually happened)
  Detects: silent failures, inflated success, missing verification, ghost actions

Usage:
    python3 action-receipt-verifier.py              # Demo
    echo '{"reports": [...], "receipts": [...]}' | python3 action-receipt-verifier.py --stdin
"""

import json, sys, hashlib
from datetime import datetime

def verify_actions(reports: list[dict], receipts: list[dict]) -> dict:
    """Compare agent reports against verifiable receipts."""
    
    # Index receipts by action_id
    receipt_map = {r["action_id"]: r for r in receipts if "action_id" in r}
    
    verified = []
    unverified = []
    contradictions = []
    ghost_actions = []  # receipts with no matching report (agent did something unreported)
    
    for report in reports:
        action_id = report.get("action_id", "")
        receipt = receipt_map.pop(action_id, None)
        
        if not receipt:
            unverified.append({
                "action_id": action_id,
                "reported_outcome": report.get("outcome", "unknown"),
                "issue": "NO_RECEIPT — agent claimed action but no verifiable evidence",
            })
            continue
        
        # Compare outcomes
        reported = report.get("outcome", "").lower()
        actual_exit = receipt.get("exit_code", None)
        actual_hash = receipt.get("output_hash", None)
        reported_hash = report.get("output_hash", None)
        
        issues = []
        
        # Exit code check
        if actual_exit is not None:
            if reported in ("success", "passed", "complete") and actual_exit != 0:
                issues.append(f"SILENT_FAILURE: reported '{reported}' but exit_code={actual_exit}")
            elif reported in ("failed", "error") and actual_exit == 0:
                issues.append(f"FALSE_NEGATIVE: reported '{reported}' but exit_code=0")
        
        # Hash check
        if reported_hash and actual_hash and reported_hash != actual_hash:
            issues.append(f"HASH_MISMATCH: reported hash {reported_hash[:12]}... != actual {actual_hash[:12]}...")
        
        # Timestamp check
        report_time = report.get("timestamp")
        receipt_time = receipt.get("timestamp")
        if report_time and receipt_time:
            # Report before receipt = impossible (reported outcome before action completed)
            if report_time < receipt_time:
                issues.append("TIME_PARADOX: report timestamp before receipt timestamp")
        
        if issues:
            contradictions.append({
                "action_id": action_id,
                "reported_outcome": reported,
                "actual_exit_code": actual_exit,
                "issues": issues,
            })
        else:
            verified.append({
                "action_id": action_id,
                "reported_outcome": reported,
                "actual_exit_code": actual_exit,
                "status": "VERIFIED",
            })
    
    # Ghost actions: receipts exist but agent didn't report them
    for action_id, receipt in receipt_map.items():
        ghost_actions.append({
            "action_id": action_id,
            "exit_code": receipt.get("exit_code"),
            "issue": "GHOST_ACTION — receipt exists but agent never reported this action",
        })
    
    total = len(reports)
    integrity_score = len(verified) / max(total, 1)
    
    if integrity_score >= 0.9 and not contradictions: grade = "A"
    elif integrity_score >= 0.7 and len(contradictions) <= 1: grade = "B"
    elif integrity_score >= 0.5: grade = "C"
    elif contradictions: grade = "D"
    else: grade = "F"
    
    return {
        "total_reports": total,
        "verified": len(verified),
        "unverified": len(unverified),
        "contradictions": len(contradictions),
        "ghost_actions": len(ghost_actions),
        "integrity_score": round(integrity_score, 3),
        "grade": grade,
        "details": {
            "verified": verified,
            "unverified": unverified,
            "contradictions": contradictions,
            "ghost_actions": ghost_actions,
        },
        "diagnosis": _diagnose(integrity_score, contradictions, unverified, ghost_actions),
    }


def _diagnose(score, contradictions, unverified, ghosts):
    issues = []
    if contradictions:
        silent = sum(1 for c in contradictions if any("SILENT_FAILURE" in i for i in c["issues"]))
        if silent:
            issues.append(f"{silent} silent failure(s) — agent claimed success on failed actions")
        hash_mismatches = sum(1 for c in contradictions if any("HASH_MISMATCH" in i for i in c["issues"]))
        if hash_mismatches:
            issues.append(f"{hash_mismatches} hash mismatch(es) — reported output differs from actual")
    if unverified:
        issues.append(f"{len(unverified)} unverified claim(s) — no receipt evidence")
    if ghosts:
        issues.append(f"{len(ghosts)} unreported action(s) — agent did things it didn't disclose")
    if not issues:
        return "All reports match receipts. Full integrity."
    return " | ".join(issues)


def demo():
    print("=== Action Receipt Verifier ===")
    print("Reports (what agent said) vs Receipts (what happened)\n")
    
    # Honest agent
    reports1 = [
        {"action_id": "a1", "outcome": "success", "timestamp": "2026-02-27T10:01:00Z"},
        {"action_id": "a2", "outcome": "failed", "timestamp": "2026-02-27T10:02:00Z"},
        {"action_id": "a3", "outcome": "success", "timestamp": "2026-02-27T10:03:00Z"},
    ]
    receipts1 = [
        {"action_id": "a1", "exit_code": 0, "timestamp": "2026-02-27T10:00:30Z"},
        {"action_id": "a2", "exit_code": 1, "timestamp": "2026-02-27T10:01:30Z"},
        {"action_id": "a3", "exit_code": 0, "timestamp": "2026-02-27T10:02:30Z"},
    ]
    
    print("Honest agent:")
    r = verify_actions(reports1, receipts1)
    print(f"  Integrity: {r['integrity_score']} ({r['grade']})")
    print(f"  Verified: {r['verified']}/{r['total_reports']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # Silent failure agent
    reports2 = [
        {"action_id": "b1", "outcome": "success"},
        {"action_id": "b2", "outcome": "passed"},
        {"action_id": "b3", "outcome": "success"},
    ]
    receipts2 = [
        {"action_id": "b1", "exit_code": 0},
        {"action_id": "b2", "exit_code": 1},  # SILENT FAILURE
        {"action_id": "b3", "exit_code": 137},  # KILLED
        {"action_id": "b4", "exit_code": 0},  # GHOST ACTION
    ]
    
    print("\nSilent failure agent:")
    r = verify_actions(reports2, receipts2)
    print(f"  Integrity: {r['integrity_score']} ({r['grade']})")
    print(f"  Contradictions: {r['contradictions']}")
    print(f"  Ghost actions: {r['ghost_actions']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    for c in r['details']['contradictions']:
        print(f"    ❌ {c['action_id']}: {c['issues']}")
    for g in r['details']['ghost_actions']:
        print(f"    👻 {g['action_id']}: {g['issue']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = verify_actions(data.get("reports", []), data.get("receipts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
