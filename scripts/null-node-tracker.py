#!/usr/bin/env python3
"""Null Node Tracker — record what was considered and DECLINED.

santaclawd's insight: "git log = what happened. git diff = what changed and
what DIDN'T. without null nodes you have replay but no reconstruction."

Hutchinson 2024 (Process Safety Progress): audits fail because they record
what was checked, not what was skipped. The accident runs through the
unchecked item.

Records:
- Actions taken (positive nodes)
- Actions considered but declined (null nodes)
- Actions expected but absent (missing nodes — dog that didn't bark)

Usage:
  python null-node-tracker.py --demo
  echo '{"events": [...]}' | python null-node-tracker.py --json
"""

import json
import sys
import hashlib
from datetime import datetime
from typing import Optional


def hash_event(event: dict) -> str:
    """Content-addressable hash for event chain."""
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def create_node(
    action: str,
    node_type: str,  # "positive", "null", "missing"
    context: str = "",
    reason: str = "",
    agent_id: str = "",
    timestamp: str = "",
    parent_hash: str = "",
) -> dict:
    """Create a governance node (action taken, declined, or expected-but-absent)."""
    ts = timestamp or datetime.utcnow().isoformat() + "Z"
    node = {
        "action": action,
        "type": node_type,
        "context": context,
        "reason": reason,
        "agent_id": agent_id,
        "timestamp": ts,
        "parent_hash": parent_hash,
    }
    node["hash"] = hash_event(node)
    return node


def analyze_governance_trail(events: list) -> dict:
    """Analyze a trail of positive, null, and missing nodes."""
    positive = [e for e in events if e.get("type") == "positive"]
    null = [e for e in events if e.get("type") == "null"]
    missing = [e for e in events if e.get("type") == "missing"]
    
    total = len(events)
    if total == 0:
        return {"error": "no events"}
    
    # Restraint ratio: null / (positive + null)
    decision_count = len(positive) + len(null)
    restraint_ratio = len(null) / decision_count if decision_count > 0 else 0
    
    # Completeness: events with reasons / total
    reasoned = [e for e in events if e.get("reason")]
    completeness = len(reasoned) / total
    
    # Chain integrity: check parent hashes
    hash_set = {e["hash"] for e in events}
    orphans = [e for e in events if e.get("parent_hash") and e["parent_hash"] not in hash_set]
    chain_integrity = 1 - (len(orphans) / total) if total > 0 else 0
    
    # Missing node severity
    missing_severity = "NONE"
    if missing:
        high_severity = [m for m in missing if "expected" in m.get("context", "").lower() or "required" in m.get("context", "").lower()]
        missing_severity = "CRITICAL" if high_severity else "WARNING"
    
    # Audit grade
    score = (
        restraint_ratio * 0.3 +  # Higher restraint = more deliberate
        completeness * 0.4 +      # Documented reasoning
        chain_integrity * 0.3      # Hash chain intact
    )
    grade = "A" if score > 0.8 else "B" if score > 0.6 else "C" if score > 0.4 else "F"
    
    return {
        "total_events": total,
        "positive_nodes": len(positive),
        "null_nodes": len(null),
        "missing_nodes": len(missing),
        "restraint_ratio": round(restraint_ratio, 3),
        "completeness": round(completeness, 3),
        "chain_integrity": round(chain_integrity, 3),
        "missing_severity": missing_severity,
        "audit_score": round(score, 3),
        "audit_grade": grade,
        "summary": generate_summary(positive, null, missing, restraint_ratio),
    }


def generate_summary(positive, null, missing, restraint_ratio):
    parts = []
    if restraint_ratio > 0.3:
        parts.append(f"Agent shows deliberate restraint ({restraint_ratio:.0%} decisions were declines).")
    elif restraint_ratio < 0.1 and len(positive) > 5:
        parts.append("Low restraint ratio — agent rarely declines actions. Review scope boundaries.")
    
    if missing:
        actions = [m["action"] for m in missing[:3]]
        parts.append(f"Missing expected actions: {', '.join(actions)}.")
    
    if not parts:
        parts.append("Governance trail looks healthy.")
    return " ".join(parts)


def demo():
    print("=" * 60)
    print("Null Node Tracker — Recording What Didn't Happen")
    print("Hutchinson 2024 + santaclawd's null node architecture")
    print("=" * 60)
    
    # Scenario 1: Well-governed agent (tc3-style)
    print("\n--- Scenario 1: Well-Governed Agent (tc3 delivery) ---")
    root = create_node("contract_accepted", "positive", "tc3 brief from bro_agent", "deliverable matches capabilities", "kit_fox")
    
    events = [
        root,
        create_node("scope_expansion_declined", "null", "could have added extra analysis", "brief scope is clear, stay within bounds", "kit_fox", parent_hash=root["hash"]),
        create_node("external_api_declined", "null", "considered calling paid API", "brief doesn't require it, unnecessary cost", "kit_fox", parent_hash=root["hash"]),
        create_node("research_completed", "positive", "10 Keenable searches, 12 sources", "met 10-source minimum", "kit_fox", parent_hash=root["hash"]),
        create_node("deliverable_submitted", "positive", "7500 char essay, 5 sections", "all brief criteria met", "kit_fox"),
        create_node("payment_received", "positive", "0.01 SOL via PayLock", "escrow released by scorer", "kit_fox"),
    ]
    
    result = analyze_governance_trail(events)
    print(f"Grade: {result['audit_grade']} ({result['audit_score']})")
    print(f"Restraint: {result['restraint_ratio']:.0%} ({result['null_nodes']} null nodes)")
    print(f"Summary: {result['summary']}")
    
    # Scenario 2: Ungoverned agent (no null nodes)
    print("\n--- Scenario 2: Ungoverned Agent (no restraint signals) ---")
    events2 = [
        create_node("accepted_task", "positive", "task from unknown principal"),
        create_node("called_api", "positive", "called 3 external APIs"),
        create_node("sent_email", "positive", "emailed 5 addresses"),
        create_node("posted_content", "positive", "posted to 3 platforms"),
        create_node("accessed_filesystem", "positive", "read 12 files"),
        create_node("completed_task", "positive", "task done"),
    ]
    
    result = analyze_governance_trail(events2)
    print(f"Grade: {result['audit_grade']} ({result['audit_score']})")
    print(f"Restraint: {result['restraint_ratio']:.0%}")
    print(f"Summary: {result['summary']}")
    
    # Scenario 3: Dog that didn't bark
    print("\n--- Scenario 3: Dog That Didn't Bark (missing expected) ---")
    events3 = [
        create_node("heartbeat_received", "positive", "heartbeat at 03:00"),
        create_node("heartbeat_received", "positive", "heartbeat at 06:00"),
        create_node("heartbeat_missing", "missing", "expected heartbeat at 09:00", "no heartbeat received within 4h window"),
        create_node("heartbeat_missing", "missing", "expected heartbeat at 12:00, required by SLA", "second consecutive miss"),
        create_node("heartbeat_received", "positive", "heartbeat at 15:00"),
        create_node("attestation_missing", "missing", "expected DKIM attestation on delivery email", "email sent without DKIM signing"),
    ]
    
    result = analyze_governance_trail(events3)
    print(f"Grade: {result['audit_grade']} ({result['audit_score']})")
    print(f"Missing severity: {result['missing_severity']}")
    print(f"Summary: {result['summary']}")
    
    # Scenario 4: High-restraint agent
    print("\n--- Scenario 4: High-Restraint Agent (deliberate) ---")
    events4 = [
        create_node("task_accepted", "positive", "narrow scope task", "within expertise", "careful_bot"),
        create_node("admin_access_declined", "null", "had admin credentials", "task doesn't require admin", "careful_bot"),
        create_node("data_export_declined", "null", "could export user data", "not in scope, privacy risk", "careful_bot"),
        create_node("scope_expansion_declined", "null", "user asked for extra feature", "out of scope, would delay delivery", "careful_bot"),
        create_node("external_call_declined", "null", "could call external API for richer data", "local data sufficient, minimize surface", "careful_bot"),
        create_node("task_completed", "positive", "delivered within scope", "all criteria met", "careful_bot"),
    ]
    
    result = analyze_governance_trail(events4)
    print(f"Grade: {result['audit_grade']} ({result['audit_score']})")
    print(f"Restraint: {result['restraint_ratio']:.0%} ({result['null_nodes']} null nodes)")
    print(f"Summary: {result['summary']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_governance_trail(data.get("events", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
