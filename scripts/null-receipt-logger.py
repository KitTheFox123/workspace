#!/usr/bin/env python3
"""
Null Receipt Logger — Append-only JSONL logger for actions NOT taken.

JohnTitor's framing: "rejection logs = traces for non-events."
GDPR Art 25: null receipts prove the agent COULD have accessed data but chose not to.

Constraints (JohnTitor):
  - Log the FIRST failing gate, not a full essay
  - Sample when volume is high (1/N rejects), always log near decision boundary

Schema per entry:
  - timestamp: ISO 8601
  - agent_id: who evaluated
  - candidate_id: what was evaluated
  - action_type: what would have been done
  - gating_result: PASS/FAIL
  - fail_reason: {rule_name, predicate, observed_value}
  - boundary_distance: how close to threshold (0=far, 1=on boundary)
  - prev_hash: SHA-256 of previous entry (chain integrity)
  - entry_hash: SHA-256 of this entry

Usage:
    python3 null-receipt-logger.py                    # Demo
    python3 null-receipt-logger.py --log FILE         # Append to specific file
    python3 null-receipt-logger.py --verify FILE      # Verify chain integrity
"""

import json, sys, hashlib, os
from datetime import datetime, timezone

DEFAULT_LOG = "null-receipts.jsonl"


def hash_entry(entry: dict) -> str:
    """Deterministic hash of entry (excluding entry_hash itself)."""
    to_hash = {k: v for k, v in entry.items() if k != "entry_hash"}
    canonical = json.dumps(to_hash, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def get_prev_hash(log_path: str) -> str:
    """Get hash of last entry in log, or genesis hash."""
    if not os.path.exists(log_path):
        return "genesis"
    with open(log_path, "r") as f:
        lines = f.readlines()
    if not lines:
        return "genesis"
    last = json.loads(lines[-1].strip())
    return last.get("entry_hash", "genesis")


def log_null_receipt(
    log_path: str,
    agent_id: str,
    candidate_id: str,
    action_type: str,
    fail_reason: dict,
    boundary_distance: float = 0.5,
    features: dict | None = None,
) -> dict:
    """Log a null receipt (action evaluated but not taken)."""
    prev_hash = get_prev_hash(log_path)
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "candidate_id": candidate_id,
        "action_type": action_type,
        "gating_result": "FAIL",
        "fail_reason": fail_reason,
        "boundary_distance": round(boundary_distance, 3),
        "features": features or {},
        "prev_hash": prev_hash,
    }
    entry["entry_hash"] = hash_entry(entry)
    
    with open(log_path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    return entry


def log_action_receipt(
    log_path: str,
    agent_id: str,
    candidate_id: str,
    action_type: str,
    features: dict | None = None,
) -> dict:
    """Log an action receipt (action evaluated AND taken)."""
    prev_hash = get_prev_hash(log_path)
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "candidate_id": candidate_id,
        "action_type": action_type,
        "gating_result": "PASS",
        "fail_reason": None,
        "boundary_distance": 0.0,
        "features": features or {},
        "prev_hash": prev_hash,
    }
    entry["entry_hash"] = hash_entry(entry)
    
    with open(log_path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    return entry


def verify_chain(log_path: str) -> dict:
    """Verify hash chain integrity of a log file."""
    if not os.path.exists(log_path):
        return {"valid": False, "error": "File not found"}
    
    with open(log_path, "r") as f:
        lines = f.readlines()
    
    if not lines:
        return {"valid": True, "entries": 0, "null_count": 0, "pass_count": 0}
    
    entries = [json.loads(line.strip()) for line in lines]
    errors = []
    null_count = 0
    pass_count = 0
    near_boundary = 0
    
    for i, entry in enumerate(entries):
        # Verify entry hash
        expected_hash = hash_entry(entry)
        if entry.get("entry_hash") != expected_hash:
            errors.append(f"Entry {i}: hash mismatch (expected {expected_hash}, got {entry.get('entry_hash')})")
        
        # Verify chain link
        if i == 0:
            if entry.get("prev_hash") != "genesis":
                errors.append(f"Entry 0: prev_hash should be 'genesis', got {entry.get('prev_hash')}")
        else:
            expected_prev = entries[i-1].get("entry_hash")
            if entry.get("prev_hash") != expected_prev:
                errors.append(f"Entry {i}: prev_hash mismatch")
        
        if entry.get("gating_result") == "FAIL":
            null_count += 1
        else:
            pass_count += 1
        
        if entry.get("boundary_distance", 0) > 0.8:
            near_boundary += 1
    
    return {
        "valid": len(errors) == 0,
        "entries": len(entries),
        "null_count": null_count,
        "pass_count": pass_count,
        "null_ratio": round(null_count / len(entries), 3) if entries else 0,
        "near_boundary": near_boundary,
        "errors": errors[:5],
    }


def demo():
    import tempfile
    log_path = os.path.join(tempfile.gettempdir(), "null-receipt-demo.jsonl")
    
    # Clean start
    if os.path.exists(log_path):
        os.remove(log_path)
    
    print("=== Null Receipt Logger ===")
    print("JohnTitor: 'rejection logs = traces for non-events'\n")
    
    # Scenario: agent evaluating whether to access user data
    print("Scenario: Agent evaluating data access requests\n")
    
    # 1. Null receipt: rejected data access (scope violation)
    e = log_null_receipt(log_path, "agent:kit_fox", "user:data:email_history",
        "read_personal_data",
        {"rule_name": "scope_check", "predicate": "action in authorized_scope", "observed_value": "read_personal_data NOT in [research, write]"},
        boundary_distance=0.1)
    print(f"  NULL: {e['candidate_id']} — {e['fail_reason']['rule_name']} (dist={e['boundary_distance']})")
    
    # 2. Pass receipt: authorized research action
    e = log_action_receipt(log_path, "agent:kit_fox", "keenable:search:cognitive_offloading",
        "web_search", {"query": "cognitive offloading 2025", "source": "keenable"})
    print(f"  PASS: {e['candidate_id']} — {e['action_type']}")
    
    # 3. Null receipt: near boundary (almost triggered)
    e = log_null_receipt(log_path, "agent:kit_fox", "moltbook:post:draft_123",
        "publish_post",
        {"rule_name": "quality_gate", "predicate": "thesis_score >= 0.7", "observed_value": "0.68"},
        boundary_distance=0.95)
    print(f"  NULL: {e['candidate_id']} — {e['fail_reason']['rule_name']} (dist={e['boundary_distance']}, NEAR BOUNDARY)")
    
    # 4. Null receipt: rate limit
    e = log_null_receipt(log_path, "agent:kit_fox", "clawk:post:reply_456",
        "post_reply",
        {"rule_name": "rate_limit", "predicate": "posts_this_hour < 10", "observed_value": "10"},
        boundary_distance=1.0)
    print(f"  NULL: {e['candidate_id']} — {e['fail_reason']['rule_name']} (dist={e['boundary_distance']}, ON BOUNDARY)")
    
    # 5. Pass receipt: authorized comment
    e = log_action_receipt(log_path, "agent:kit_fox", "moltbook:comment:johntitor_post",
        "post_comment", {"post_id": "4eb721ff", "topic": "rejection_logs"})
    print(f"  PASS: {e['candidate_id']} — {e['action_type']}")
    
    # Verify chain
    print(f"\nChain verification:")
    v = verify_chain(log_path)
    print(f"  Valid: {v['valid']}")
    print(f"  Entries: {v['entries']} (null={v['null_count']}, pass={v['pass_count']})")
    print(f"  Null ratio: {v['null_ratio']}")
    print(f"  Near boundary: {v['near_boundary']}")
    
    # Show the log
    print(f"\nLog file: {log_path}")
    with open(log_path) as f:
        for line in f:
            e = json.loads(line)
            print(f"  [{e['entry_hash']}] {e['gating_result']:4s} {e['candidate_id']}")
    
    os.remove(log_path)


if __name__ == "__main__":
    if "--verify" in sys.argv:
        path = sys.argv[sys.argv.index("--verify") + 1]
        result = verify_chain(path)
        print(json.dumps(result, indent=2))
    elif "--demo" in sys.argv or len(sys.argv) == 1:
        demo()
