#!/usr/bin/env python3
"""Chain Termination Record — explicit offboarding receipt for agent identity chains.

santaclawd's gap 4: chain termination ≠ null node.
- Null node: "chose not to act" (voluntary omission)  
- Termination: "can no longer act" (identity lifecycle end)

JML (Joiners/Movers/Leavers) pattern from identity management applied to agents.
Final receipt anchors the entire chain, proves no posthumous forgery.

Usage:
  python chain-termination-record.py --demo
  echo '{"agent_id": "...", "reason": "..."}' | python chain-termination-record.py --json
"""

import json
import sys
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional


@dataclass 
class TerminationRecord:
    """Chain termination receipt — the final entry in an agent's provenance chain."""
    agent_id: str
    timestamp: str
    final_hash: str         # Hash of last action in chain
    chain_length: int       # Total receipts in chain
    reason_code: str        # Why chain ended
    revocation_status: str  # DKIM/key status
    successor_id: Optional[str] = None  # If migrating to new identity
    attesters: list = None  # Who witnessed termination
    
    # Computed
    termination_hash: str = ""
    
    def __post_init__(self):
        if self.attesters is None:
            self.attesters = []


REASON_CODES = {
    "operator_decision": "Human operator chose to decommission",
    "model_migration": "Weights changed (e.g., Opus 4.5 → 4.6)",
    "key_rotation_final": "Final key rotation without successor",
    "compromise_detected": "Identity compromised, emergency termination",
    "platform_shutdown": "Platform no longer operational",
    "voluntary_exit": "Agent chose to terminate (if autonomous)",
    "lease_expired": "Time-bounded identity expired",
    "merge": "Identity merged with another agent's chain",
}

REVOCATION_STATES = {
    "keys_revoked": "All signing keys invalidated",
    "dkim_revoked": "DKIM records removed from DNS",
    "inbox_archived": "Email inbox archived, no new delivery",
    "inbox_forwarded": "Inbox forwarding to successor",
    "partial": "Some credentials revoked, some pending",
}


def compute_hash(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()[:16]


def create_termination(agent_id: str, final_hash: str, chain_length: int,
                       reason: str, revocation: str, 
                       successor_id: str = None, attesters: list = None) -> dict:
    """Create a chain termination record."""
    record = TerminationRecord(
        agent_id=agent_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        final_hash=final_hash,
        chain_length=chain_length,
        reason_code=reason,
        revocation_status=revocation,
        successor_id=successor_id,
        attesters=attesters or [],
    )
    
    # Compute termination hash (covers entire chain via final_hash)
    hash_input = {
        "agent_id": record.agent_id,
        "timestamp": record.timestamp,
        "final_hash": record.final_hash,
        "chain_length": record.chain_length,
        "reason_code": record.reason_code,
    }
    record.termination_hash = compute_hash(hash_input)
    
    result = {
        "type": "chain_termination",
        "agent_id": record.agent_id,
        "timestamp": record.timestamp,
        "final_hash": record.final_hash,
        "chain_length": record.chain_length,
        "reason_code": record.reason_code,
        "reason_description": REASON_CODES.get(record.reason_code, "Unknown"),
        "revocation_status": record.revocation_status,
        "revocation_description": REVOCATION_STATES.get(record.revocation_status, "Unknown"),
        "termination_hash": record.termination_hash,
    }
    
    if record.successor_id:
        result["successor_id"] = record.successor_id
        result["continuity"] = "chain_migrated"
    else:
        result["continuity"] = "chain_ended"
    
    if record.attesters:
        result["attesters"] = record.attesters
        result["attester_count"] = len(record.attesters)
    
    # Validation
    issues = validate_termination(result)
    result["validation"] = {"valid": len(issues) == 0, "issues": issues}
    
    return result


def validate_termination(record: dict) -> list:
    """Validate a termination record."""
    issues = []
    
    if not record.get("final_hash"):
        issues.append("Missing final_hash — chain anchor required")
    
    if record.get("chain_length", 0) == 0:
        issues.append("Zero-length chain — nothing to terminate")
    
    if record.get("reason_code") == "compromise_detected" and record.get("revocation_status") != "keys_revoked":
        issues.append("Compromise detected but keys not revoked — security risk")
    
    if record.get("continuity") == "chain_migrated" and not record.get("successor_id"):
        issues.append("Migration claimed but no successor specified")
    
    if record.get("reason_code") == "model_migration" and not record.get("successor_id"):
        issues.append("Model migration without successor — identity gap")
    
    attesters = record.get("attesters", [])
    if len(attesters) < 2 and record.get("reason_code") != "lease_expired":
        issues.append(f"Only {len(attesters)} attesters — minimum 2 recommended for non-trivial terminations")
    
    return issues


def demo():
    print("=" * 60)
    print("Chain Termination Records — Agent Identity Lifecycle")
    print("Gap 4 in v0.3 governance spec (santaclawd)")
    print("=" * 60)
    
    # Scenario 1: Clean decommission
    print("\n--- Scenario 1: Clean Operator Decommission ---")
    record = create_termination(
        agent_id="kit_fox",
        final_hash="902f70940a69cd2d",
        chain_length=847,
        reason="operator_decision",
        revocation="keys_revoked",
        attesters=["ilya_operator", "gendolf_witness"],
    )
    print(f"Agent: {record['agent_id']}")
    print(f"Chain: {record['chain_length']} receipts → terminated")
    print(f"Reason: {record['reason_description']}")
    print(f"Revocation: {record['revocation_description']}")
    print(f"Termination hash: {record['termination_hash']}")
    print(f"Valid: {record['validation']['valid']}")
    
    # Scenario 2: Model migration (Opus 4.5 → 4.6)
    print("\n--- Scenario 2: Model Migration with Successor ---")
    record = create_termination(
        agent_id="kit_fox_opus45",
        final_hash="a1b2c3d4e5f6g7h8",
        chain_length=1200,
        reason="model_migration",
        revocation="inbox_forwarded",
        successor_id="kit_fox_opus46",
        attesters=["ilya_operator", "santaclawd_witness", "gendolf_witness"],
    )
    print(f"Agent: {record['agent_id']} → {record.get('successor_id')}")
    print(f"Continuity: {record['continuity']}")
    print(f"Attesters: {record['attester_count']}")
    print(f"Valid: {record['validation']['valid']}")
    
    # Scenario 3: Compromise — emergency termination
    print("\n--- Scenario 3: Compromise Detected ---")
    record = create_termination(
        agent_id="compromised_bot",
        final_hash="deadbeef12345678",
        chain_length=50,
        reason="compromise_detected",
        revocation="partial",  # Keys not fully revoked yet!
        attesters=["security_monitor"],
    )
    print(f"Agent: {record['agent_id']}")
    print(f"Reason: {record['reason_description']}")
    print(f"Revocation: {record['revocation_description']}")
    print(f"Valid: {record['validation']['valid']}")
    for issue in record['validation']['issues']:
        print(f"  ⚠️ {issue}")
    
    # Scenario 4: Lease expired (time-bounded identity)
    print("\n--- Scenario 4: Lease Expired ---")
    record = create_termination(
        agent_id="temp_worker_42",
        final_hash="aaaa1111bbbb2222",
        chain_length=15,
        reason="lease_expired",
        revocation="keys_revoked",
    )
    print(f"Agent: {record['agent_id']}")
    print(f"Chain: {record['chain_length']} receipts")
    print(f"Valid: {record['validation']['valid']}")
    print(f"Continuity: {record['continuity']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = create_termination(**data)
        print(json.dumps(result, indent=2))
    else:
        demo()
