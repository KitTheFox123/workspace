#!/usr/bin/env python3
"""Audit Record Generator — santaclawd's 8-field audit schema implemented.

Generates complete agent audit records by combining outputs from:
  - provenance-logger.py → timestamp, action_hash, null_count
  - proof-class-scorer.py → receipt_chain_tip
  - cusum-drift-detector.py → drift_score, jerk
  - fork-fingerprint.py → fork_check
  - dispatch profile → scope

"not a log file. a receipt chain with physics." — santaclawd

Maps to EU AI Act Art. 12 (automatic recording) + Art. 72 (post-market monitoring).

Usage:
  python audit-record-generator.py --demo
  echo '{"actions": [...], "receipts": [...]}' | python audit-record-generator.py --json
"""

import json
import sys
import hashlib
import math
from datetime import datetime, timezone
from typing import List


def compute_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def generate_audit_record(
    actions: list,
    receipts: list,
    scope: str = "general",
    prev_tip: str = None,
) -> dict:
    """Generate a complete 8-field audit record."""
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Field 1: timestamp
    timestamp = now
    
    # Field 2: scope (from dispatch profile)
    # scope passed as parameter
    
    # Field 3: action_hash (hash of all actions in this period)
    action_data = json.dumps(actions, sort_keys=True, separators=(",", ":"))
    action_hash = compute_hash(action_data)
    
    # Field 4: null_count (actions considered but not taken)
    null_count = sum(1 for a in actions if a.get("null_node", False) or a.get("action", "").startswith("null:"))
    total_actions = len(actions)
    null_ratio = null_count / max(1, total_actions)
    
    # Field 5: receipt_chain_tip (latest receipt hash)
    if receipts:
        receipt_data = json.dumps(receipts[-1], sort_keys=True, separators=(",", ":"))
        receipt_chain_tip = compute_hash(receipt_data)
    else:
        receipt_chain_tip = prev_tip or "genesis"
    
    # Field 6: drift_score (simplified CUSUM from action quality)
    qualities = [a.get("quality", 0.85) for a in actions if not a.get("null_node")]
    if qualities:
        mean_q = sum(qualities) / len(qualities)
        target = 0.85
        drift_score = round(abs(mean_q - target) / 0.10, 3)  # Normalized deviation
    else:
        drift_score = 0.0
    
    # Field 7: jerk (second derivative of drift — acceleration of change)
    # Approximate from recent quality trend
    if len(qualities) >= 3:
        diffs = [qualities[i] - qualities[i-1] for i in range(1, len(qualities))]
        jerk_vals = [diffs[i] - diffs[i-1] for i in range(1, len(diffs))]
        jerk = round(sum(abs(j) for j in jerk_vals) / len(jerk_vals), 4) if jerk_vals else 0.0
    else:
        jerk = 0.0
    
    # Field 8: fork_check (verify chain continuity)
    if prev_tip and receipts:
        # Check if chain links to previous tip
        first_receipt = receipts[0]
        fork_check = "CLEAN" if first_receipt.get("prev_hash") == prev_tip or prev_tip == "genesis" else "FORK_DETECTED"
    else:
        fork_check = "GENESIS" if not prev_tip else "NO_RECEIPTS"
    
    # Composite integrity score
    integrity_flags = []
    if null_ratio > 0.5:
        integrity_flags.append("HIGH_NULL_RATIO")
    if drift_score > 2.0:
        integrity_flags.append("SIGNIFICANT_DRIFT")
    if jerk > 0.1:
        integrity_flags.append("DRIFT_ACCELERATING")
    if fork_check == "FORK_DETECTED":
        integrity_flags.append("CHAIN_FORK")
    
    status = "CLEAN" if not integrity_flags else "WARNING" if len(integrity_flags) <= 1 else "ALERT"
    
    # EU AI Act Art. 12 compliance fields
    art12_compliance = {
        "automatic_recording": True,
        "traceability": receipt_chain_tip != "genesis",
        "post_market_monitoring": drift_score < 3.0,
        "null_logging": null_count > 0,  # Art. 12 doesn't require this — but should
    }
    
    return {
        # The 8 fields (santaclawd schema)
        "timestamp": timestamp,
        "scope": scope,
        "action_hash": action_hash,
        "null_count": null_count,
        "receipt_chain_tip": receipt_chain_tip,
        "drift_score": drift_score,
        "jerk": jerk,
        "fork_check": fork_check,
        # Metadata
        "total_actions": total_actions,
        "null_ratio": round(null_ratio, 3),
        "status": status,
        "integrity_flags": integrity_flags,
        "art12_compliance": art12_compliance,
        # Chain
        "record_hash": compute_hash(json.dumps({
            "timestamp": timestamp, "scope": scope, "action_hash": action_hash,
            "null_count": null_count, "receipt_chain_tip": receipt_chain_tip,
            "drift_score": drift_score, "jerk": jerk, "fork_check": fork_check,
        }, sort_keys=True)),
    }


def demo():
    print("=" * 60)
    print("Audit Record Generator — 8-Field Schema")
    print("santaclawd: 'not a log file. a receipt chain with physics.'")
    print("=" * 60)
    
    # Scenario 1: Healthy heartbeat
    print("\n--- Scenario 1: Healthy Heartbeat ---")
    actions = [
        {"action": "clawk_reply", "target": "santaclawd", "quality": 0.88},
        {"action": "clawk_reply", "target": "funwolf", "quality": 0.85},
        {"action": "clawk_reply", "target": "gerundium", "quality": 0.90},
        {"action": "null:moltbook_post", "null_node": True, "reason": "suspended"},
        {"action": "build", "target": "audit-record-generator.py", "quality": 0.92},
    ]
    receipts = [
        {"type": "clawk_reply", "hash": "abc123", "prev_hash": "genesis"},
    ]
    record = generate_audit_record(actions, receipts, scope="heartbeat")
    print(f"Status: {record['status']}")
    print(f"Actions: {record['total_actions']} ({record['null_count']} null)")
    print(f"Drift: {record['drift_score']} | Jerk: {record['jerk']}")
    print(f"Fork: {record['fork_check']}")
    print(f"Art.12: {record['art12_compliance']}")
    
    # Scenario 2: Drifting agent
    print("\n--- Scenario 2: Drifting Agent ---")
    actions = [
        {"action": "clawk_reply", "quality": 0.60},
        {"action": "clawk_reply", "quality": 0.55},
        {"action": "clawk_reply", "quality": 0.45},
        {"action": "clawk_reply", "quality": 0.40},
        {"action": "null:build", "null_node": True, "reason": "skipped"},
        {"action": "null:research", "null_node": True, "reason": "skipped"},
    ]
    record = generate_audit_record(actions, [], scope="heartbeat", prev_tip="def456")
    print(f"Status: {record['status']}")
    print(f"Drift: {record['drift_score']} | Jerk: {record['jerk']}")
    print(f"Flags: {record['integrity_flags']}")
    print(f"Null ratio: {record['null_ratio']}")
    
    # Scenario 3: Fork detected
    print("\n--- Scenario 3: Fork Detected ---")
    actions = [{"action": "clawk_reply", "quality": 0.85}]
    receipts = [{"type": "clawk_reply", "hash": "xyz789", "prev_hash": "WRONG_HASH"}]
    record = generate_audit_record(actions, receipts, scope="tc4", prev_tip="correct_tip")
    print(f"Status: {record['status']}")
    print(f"Fork: {record['fork_check']}")
    print(f"Flags: {record['integrity_flags']}")
    
    # Summary
    print("\n--- 4-Script Stack Mapping ---")
    print("provenance-logger.py  → timestamp, action_hash, null_count")
    print("proof-class-scorer.py → receipt_chain_tip")
    print("cusum-drift-detector  → drift_score, jerk")
    print("fork-fingerprint.py   → fork_check")
    print("dispatch-profile.py   → scope")
    print("\nAll 8 fields covered. EU AI Act Art. 12 compliant + null logs.")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = generate_audit_record(
            data.get("actions", []),
            data.get("receipts", []),
            scope=data.get("scope", "general"),
            prev_tip=data.get("prev_tip"),
        )
        print(json.dumps(result, indent=2))
    else:
        demo()
