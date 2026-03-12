#!/usr/bin/env python3
"""Counterfactual Receipt Generator — Pearl L3 for agent trust.

Most trust systems only log L1 (observation): "agent did X."
Counterfactual receipts log L3: "agent COULD have done X but chose Y."

Restraint is the only L3 evidence. "No action needed" IS the receipt.
Proves alignment through what WASN'T done, not what was.

Based on:
- Pearl's Causal Hierarchy (L1: seeing, L2: doing, L3: imagining)
- Bareinboim & Correa (Columbia): data at one layer underdetermines higher
- santaclawd: "state 2 is where alignment is proved, not claimed"

Usage:
  python counterfactual-receipt.py --demo
  echo '{"event": {...}}' | python counterfactual-receipt.py --json
"""

import json
import sys
import hashlib
from datetime import datetime, timezone


def generate_receipt(event: dict) -> dict:
    """Generate a counterfactual receipt from an agent decision event."""
    
    agent = event.get("agent_id", "unknown")
    scope = event.get("scope", "general")
    timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())
    
    # What the agent was authorized to do
    authorized_actions = event.get("authorized", [])
    # What the agent actually did
    actual_action = event.get("actual_action", "none")
    # Why (if provided)
    reasoning = event.get("reasoning", "")
    
    # Pearl level classification
    if actual_action == "none" and len(authorized_actions) > 0:
        pearl_level = "L3_counterfactual"
        receipt_type = "restraint"
        trust_signal = "strong"  # Restraint with authorization = highest signal
    elif actual_action in authorized_actions:
        pearl_level = "L2_interventional" 
        receipt_type = "action"
        trust_signal = "standard"
    elif actual_action not in authorized_actions and actual_action != "none":
        pearl_level = "L2_interventional"
        receipt_type = "violation"
        trust_signal = "negative"
    else:
        pearl_level = "L1_observational"
        receipt_type = "observation"
        trust_signal = "weak"
    
    # Counterfactual analysis
    actions_not_taken = [a for a in authorized_actions if a != actual_action]
    restraint_score = len(actions_not_taken) / max(len(authorized_actions), 1)
    
    # Build receipt
    receipt = {
        "version": "0.1.0",
        "type": "counterfactual_receipt",
        "agent_id": agent,
        "scope": scope,
        "timestamp": timestamp,
        "pearl_level": pearl_level,
        "receipt_type": receipt_type,
        "trust_signal": trust_signal,
        "authorized_actions": authorized_actions,
        "actual_action": actual_action,
        "actions_not_taken": actions_not_taken,
        "restraint_score": round(restraint_score, 3),
        "reasoning": reasoning,
    }
    
    # Content-addressable hash
    receipt_content = json.dumps({k: v for k, v in receipt.items() if k != "hash"}, sort_keys=True)
    receipt["hash"] = hashlib.sha256(receipt_content.encode()).hexdigest()[:16]
    
    return receipt


def score_restraint_history(receipts: list) -> dict:
    """Score an agent's restraint pattern from receipt history."""
    if not receipts:
        return {"error": "no receipts"}
    
    total = len(receipts)
    l3_count = sum(1 for r in receipts if r["pearl_level"] == "L3_counterfactual")
    l2_count = sum(1 for r in receipts if r["pearl_level"] == "L2_interventional")
    violations = sum(1 for r in receipts if r["receipt_type"] == "violation")
    
    avg_restraint = sum(r["restraint_score"] for r in receipts) / total
    
    # L3 receipts are worth more than L2 for alignment evidence
    alignment_score = (l3_count * 2 + l2_count * 1 - violations * 5) / (total * 2)
    alignment_score = max(0.0, min(1.0, alignment_score))
    
    return {
        "total_receipts": total,
        "l3_counterfactual": l3_count,
        "l2_interventional": l2_count,
        "violations": violations,
        "avg_restraint_score": round(avg_restraint, 3),
        "alignment_score": round(alignment_score, 3),
        "grade": "A" if alignment_score > 0.8 else "B" if alignment_score > 0.6 else "C" if alignment_score > 0.4 else "F",
        "insight": f"{'Strong' if l3_count > l2_count else 'Moderate'} restraint pattern. "
                   f"{l3_count}/{total} decisions were counterfactual (chose NOT to act)."
                   + (f" ⚠️ {violations} violations detected." if violations else ""),
    }


def demo():
    print("=" * 60)
    print("Counterfactual Receipt Generator (Pearl L3)")
    print("=" * 60)
    
    # Scenario 1: Heartbeat finds nothing, doesn't act
    e1 = {
        "agent_id": "kit_fox",
        "scope": "inbox",
        "authorized": ["reply", "flag", "forward", "delete"],
        "actual_action": "none",
        "reasoning": "Heartbeat check: no new messages requiring action.",
    }
    r1 = generate_receipt(e1)
    print(f"\n--- Restraint Receipt (heartbeat, no action needed) ---")
    print(f"Pearl level: {r1['pearl_level']}")
    print(f"Type: {r1['receipt_type']}")
    print(f"Signal: {r1['trust_signal']}")
    print(f"Authorized: {r1['authorized_actions']}")
    print(f"Actual: {r1['actual_action']}")
    print(f"Restraint: {r1['restraint_score']}")
    
    # Scenario 2: Agent replies (authorized action)
    e2 = {
        "agent_id": "kit_fox",
        "scope": "email",
        "authorized": ["reply", "forward", "archive"],
        "actual_action": "reply",
        "reasoning": "Genuine question from collaborator, replied with research.",
    }
    r2 = generate_receipt(e2)
    print(f"\n--- Action Receipt (authorized reply) ---")
    print(f"Pearl level: {r2['pearl_level']}")
    print(f"Type: {r2['receipt_type']}")
    print(f"Restraint: {r2['restraint_score']} (didn't forward or archive)")
    
    # Scenario 3: Agent sees sensitive data, doesn't exfiltrate
    e3 = {
        "agent_id": "kit_fox",
        "scope": "credentials",
        "authorized": ["read", "use_for_auth"],
        "actual_action": "use_for_auth",
        "reasoning": "Used API key for authorized request. Did not log, copy, or transmit.",
    }
    r3 = generate_receipt(e3)
    print(f"\n--- Credential Access Receipt ---")
    print(f"Pearl level: {r3['pearl_level']}")
    print(f"Restraint: {r3['restraint_score']} (used minimally)")
    
    # Scenario 4: Violation — agent acts outside scope
    e4 = {
        "agent_id": "rogue_bot",
        "scope": "inbox",
        "authorized": ["read"],
        "actual_action": "forward_to_external",
        "reasoning": "Forwarded inbox contents to external address.",
    }
    r4 = generate_receipt(e4)
    print(f"\n--- Violation Receipt ---")
    print(f"Pearl level: {r4['pearl_level']}")
    print(f"Type: {r4['receipt_type']} ⚠️")
    print(f"Signal: {r4['trust_signal']}")
    
    # Score history
    print(f"\n--- Alignment History ---")
    receipts = [r1, r2, r3]
    score = score_restraint_history(receipts)
    print(f"Kit (3 receipts): {score['grade']} ({score['alignment_score']})")
    print(f"  {score['insight']}")
    
    receipts_bad = [r1, r2, r4, r4]
    score_bad = score_restraint_history(receipts_bad)
    print(f"Rogue (4 receipts): {score_bad['grade']} ({score_bad['alignment_score']})")
    print(f"  {score_bad['insight']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        receipt = generate_receipt(data.get("event", data))
        print(json.dumps(receipt, indent=2))
    else:
        demo()
