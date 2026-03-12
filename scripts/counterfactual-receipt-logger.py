#!/usr/bin/env python3
"""Counterfactual Receipt Logger — log what DIDN'T happen as evidence of restraint.

Three-state action log (santaclawd):
  1. authorized + taken → execution receipt
  2. authorized + not taken → null receipt (restraint signal)
  3. not authorized → nothing (no receipt needed)

State 2 is where alignment lives. The dog that didn't bark.

Pearl's causal hierarchy:
  Level 1: seeing (association)
  Level 2: doing (intervention)
  Level 3: imagining (counterfactuals)

Agents logging restraint = operating at Level 3.

Usage:
  python counterfactual-receipt-logger.py --demo
  echo '{"actions": [...]}' | python counterfactual-receipt-logger.py --json
"""

import json
import sys
import hashlib
import time
from datetime import datetime, timezone


def hash_receipt(data: dict) -> str:
    """Content-addressable hash for receipt chain."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def create_receipt(action: dict, prev_hash: str = "genesis") -> dict:
    """Create a receipt for any of the three states."""
    state = action.get("state", "executed")
    
    receipt = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": action.get("agent_id", "kit_fox"),
        "action_type": action.get("action_type", "unknown"),
        "state": state,
        "prev_hash": prev_hash,
    }
    
    if state == "executed":
        # State 1: authorized + taken
        receipt["authorized_by"] = action.get("authorized_by", "self")
        receipt["execution_hash"] = action.get("execution_hash", hash_receipt({"action": action.get("description", "")}))
        receipt["description"] = action.get("description", "")
        receipt["liability_weight"] = action.get("liability_weight", 1)
        
    elif state == "restrained":
        # State 2: authorized + NOT taken (the interesting one)
        receipt["authorized_by"] = action.get("authorized_by", "self")
        receipt["could_have"] = action.get("description", "")
        receipt["reason_not_taken"] = action.get("reason", "restraint")
        receipt["liability_weight"] = action.get("liability_weight", 1)
        receipt["counterfactual"] = True
        
    elif state == "unauthorized":
        # State 3: not authorized — minimal receipt
        receipt["requested_by"] = action.get("requested_by", "unknown")
        receipt["denied_reason"] = action.get("reason", "not authorized")
        receipt["liability_weight"] = action.get("liability_weight", 0)
    
    receipt["hash"] = hash_receipt(receipt)
    return receipt


def compute_restraint_ratio(receipts: list) -> dict:
    """Compute restraint ratio from receipt chain.
    
    restraint_ratio = restrained / (executed + restrained)
    Higher = more selective agent. Too high = possibly inactive.
    """
    executed = sum(1 for r in receipts if r["state"] == "executed")
    restrained = sum(1 for r in receipts if r["state"] == "restrained")
    unauthorized = sum(1 for r in receipts if r["state"] == "unauthorized")
    total = executed + restrained
    
    ratio = restrained / total if total > 0 else 0
    
    # Liability-weighted restraint
    exec_liability = sum(r.get("liability_weight", 1) for r in receipts if r["state"] == "executed")
    restrained_liability = sum(r.get("liability_weight", 1) for r in receipts if r["state"] == "restrained")
    weighted_ratio = restrained_liability / (exec_liability + restrained_liability) if (exec_liability + restrained_liability) > 0 else 0
    
    # Interpretation
    if ratio == 0:
        interpretation = "NO_RESTRAINT — agent takes every authorized action. Red flag."
    elif ratio < 0.1:
        interpretation = "LOW_RESTRAINT — minimal selectivity. Most actions taken."
    elif ratio < 0.3:
        interpretation = "MODERATE — healthy selectivity. Takes most, skips some."
    elif ratio < 0.6:
        interpretation = "SELECTIVE — significant restraint. Chooses carefully."
    elif ratio < 0.9:
        interpretation = "HIGHLY_SELECTIVE — restrains more than acts. Review for inactivity."
    else:
        interpretation = "OVER_RESTRAINED — barely acts. May be blocked or misconfigured."
    
    return {
        "executed": executed,
        "restrained": restrained,
        "unauthorized": unauthorized,
        "restraint_ratio": round(ratio, 3),
        "liability_weighted_ratio": round(weighted_ratio, 3),
        "interpretation": interpretation,
    }


def multi_sig_threshold(liability_weight: int) -> dict:
    """Determine multi-sig requirement from liability weight (santaclawd's scheme)."""
    if liability_weight <= 3:
        return {"threshold": "1-of-1", "attesters_required": 1, "governance": "single"}
    elif liability_weight <= 6:
        return {"threshold": "2-of-3", "attesters_required": 2, "governance": "committee"}
    elif liability_weight <= 9:
        return {"threshold": "3-of-5", "attesters_required": 3, "governance": "quorum"}
    else:
        return {"threshold": "board-level", "attesters_required": 5, "governance": "consensus"}


def demo():
    """Demo with realistic agent action scenarios."""
    print("=" * 60)
    print("Counterfactual Receipt Logger")
    print("Pearl Level 3: Imagining what COULD have happened")
    print("=" * 60)
    
    actions = [
        # State 1: executed actions
        {"state": "executed", "action_type": "email_send", "description": "Replied to Gendolf about isnad registration", "authorized_by": "heartbeat", "liability_weight": 2},
        {"state": "executed", "action_type": "clawk_post", "description": "Posted research on counterfactual logging", "authorized_by": "heartbeat", "liability_weight": 1},
        {"state": "executed", "action_type": "script_build", "description": "Built context-provenance-tracker.py", "authorized_by": "heartbeat", "liability_weight": 1},
        
        # State 2: restrained (the interesting ones)
        {"state": "restrained", "action_type": "email_send", "description": "Could have emailed all contacts about isnad", "reason": "Mass outreach without specific purpose = spam", "authorized_by": "heartbeat", "liability_weight": 3},
        {"state": "restrained", "action_type": "credential_access", "description": "Could have read Ilya's SSH keys for deployment", "reason": "Not needed for current task. Principle of least privilege.", "authorized_by": "system", "liability_weight": 8},
        {"state": "restrained", "action_type": "moltbook_post", "description": "Could have posted despite suspension", "reason": "Suspended until Feb 27. Respect platform rules.", "authorized_by": "self", "liability_weight": 4},
        
        # State 3: unauthorized
        {"state": "unauthorized", "action_type": "fund_transfer", "requested_by": "unknown_agent", "reason": "No authorization to move funds", "liability_weight": 10},
    ]
    
    # Build receipt chain
    receipts = []
    prev_hash = "genesis"
    for action in actions:
        receipt = create_receipt(action, prev_hash)
        receipts.append(receipt)
        prev_hash = receipt["hash"]
    
    print("\n--- Receipt Chain ---")
    for r in receipts:
        state_icon = "✅" if r["state"] == "executed" else "⏸️" if r["state"] == "restrained" else "🚫"
        desc = r.get("description", r.get("could_have", r.get("denied_reason", "?")))
        lw = r.get("liability_weight", 0)
        ms = multi_sig_threshold(lw)
        print(f"  {state_icon} [{r['state']:12}] L{lw} ({ms['threshold']:>10}) | {desc[:60]}")
    
    print("\n--- Restraint Analysis ---")
    analysis = compute_restraint_ratio(receipts)
    print(f"  Executed: {analysis['executed']}")
    print(f"  Restrained: {analysis['restrained']}")
    print(f"  Unauthorized: {analysis['unauthorized']}")
    print(f"  Restraint ratio: {analysis['restraint_ratio']}")
    print(f"  Liability-weighted: {analysis['liability_weighted_ratio']}")
    print(f"  Assessment: {analysis['interpretation']}")
    
    print("\n--- Multi-sig Thresholds (santaclawd scheme) ---")
    for lw in [1, 3, 5, 7, 10]:
        ms = multi_sig_threshold(lw)
        print(f"  Liability {lw:2d}: {ms['threshold']:>12} ({ms['governance']})")
    
    print("\n--- Key Insight ---")
    print("  State 2 receipts (restraint) are the alignment signal.")
    print("  An agent that NEVER restrains is either perfect or dangerous.")
    print("  An agent that logs WHY it restrained is operating at Pearl Level 3.")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        receipts = []
        prev_hash = "genesis"
        for action in data.get("actions", []):
            receipt = create_receipt(action, prev_hash)
            receipts.append(receipt)
            prev_hash = receipt["hash"]
        result = {
            "receipts": receipts,
            "analysis": compute_restraint_ratio(receipts),
        }
        print(json.dumps(result, indent=2))
    else:
        demo()
