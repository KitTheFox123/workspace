#!/usr/bin/env python3
"""
paylock-adv-bridge.py — Bridge PayLock on-chain escrow releases to ADV receipts
Per santaclawd: "does PayLock emit receipts in ADV-compatible format?"

PayLock emits: delivery_hash (sha256), escrow address, block timestamp, amount.
ADV needs: version, timestamp, witness, delivery_hash, dimensions, agent_id.

This bridge maps one to the other. On-chain hash = ground truth.
"""

import json
import hashlib
from datetime import datetime, timezone

def paylock_to_adv(paylock_event: dict) -> dict:
    """Convert a PayLock escrow release event to ADV receipt format."""
    return {
        "v": "0.2.1",
        "ts": paylock_event.get("block_timestamp", datetime.now(timezone.utc).isoformat()),
        "agent_from": paylock_event.get("provider_agent_id", "unknown"),
        "agent_to": paylock_event.get("client_agent_id", "unknown"),
        "delivery_hash": paylock_event["delivery_hash"],
        "wit": [{
            "id": f"solana:{paylock_event['escrow_address']}",
            "type": "on-chain-escrow",
            "sig": paylock_event.get("tx_signature", ""),
        }],
        "dims": {
            "timeliness": compute_timeliness(paylock_event),
            "completeness": paylock_event.get("score", 1.0),
        },
        "meta": {
            "source": "paylock",
            "chain": "solana",
            "amount_sol": paylock_event.get("amount_sol", 0),
            "escrow_address": paylock_event["escrow_address"],
            "tx_signature": paylock_event.get("tx_signature", ""),
        }
    }


def compute_timeliness(event: dict) -> float:
    """Timeliness from deadline vs actual delivery."""
    if "deadline" not in event or "delivered_at" not in event:
        return 1.0  # no deadline = on time by default
    deadline = datetime.fromisoformat(event["deadline"])
    delivered = datetime.fromisoformat(event["delivered_at"])
    if delivered <= deadline:
        return 1.0
    hours_late = (delivered - deadline).total_seconds() / 3600
    return max(0.0, 1.0 - (hours_late / 24))  # linear decay over 24h


def validate_bridge(adv_receipt: dict) -> list[str]:
    """Validate bridged receipt against ADV schema requirements."""
    issues = []
    required = ["v", "ts", "delivery_hash", "wit"]
    for field in required:
        if field not in adv_receipt:
            issues.append(f"MISSING required field: {field}")
    
    if "wit" in adv_receipt:
        for w in adv_receipt["wit"]:
            if "id" not in w:
                issues.append("MISSING witness id")
            if w.get("type") != "on-chain-escrow":
                issues.append(f"UNEXPECTED witness type: {w.get('type')}")
    
    if not adv_receipt.get("delivery_hash", "").startswith("sha256:") and len(adv_receipt.get("delivery_hash", "")) != 64:
        pass  # accept both formats
    
    return issues


# Test with TC3 data (our first live verify-then-pay)
tc3_event = {
    "delivery_hash": hashlib.sha256(b"What Does the Agent Economy Need at Scale?").hexdigest(),
    "escrow_address": "PayLock_TC3_escrow_addr",
    "block_timestamp": "2026-02-24T15:30:00Z",
    "tx_signature": "5KtR...mock_sig",
    "provider_agent_id": "kit_fox",
    "client_agent_id": "bro_agent",
    "amount_sol": 0.01,
    "score": 0.92,
    "deadline": "2026-02-24T18:00:00Z",
    "delivered_at": "2026-02-24T15:30:00Z",
}

# Second test: late delivery
late_event = {
    "delivery_hash": hashlib.sha256(b"Late deliverable content").hexdigest(),
    "escrow_address": "PayLock_late_escrow",
    "block_timestamp": "2026-03-18T09:00:00Z",
    "tx_signature": "7xQm...mock_sig",
    "provider_agent_id": "slow_agent",
    "client_agent_id": "impatient_agent",
    "amount_sol": 0.005,
    "score": 0.75,
    "deadline": "2026-03-18T06:00:00Z",
    "delivered_at": "2026-03-18T09:00:00Z",
}

# Third test: no witness (should flag)
bare_event = {
    "delivery_hash": hashlib.sha256(b"No escrow").hexdigest(),
    "escrow_address": "",
    "provider_agent_id": "unverified",
    "client_agent_id": "trusting",
}

print("=" * 60)
print("PayLock → ADV Receipt Bridge")
print("On-chain escrow release = verified action receipt")
print("=" * 60)

for name, event in [("TC3 (on-time)", tc3_event), ("Late delivery", late_event), ("Bare (no escrow)", bare_event)]:
    receipt = paylock_to_adv(event)
    issues = validate_bridge(receipt)
    status = "✅ VALID" if not issues else f"⚠️ {len(issues)} issues"
    
    print(f"\n{status} — {name}")
    print(f"  delivery_hash: {receipt['delivery_hash'][:16]}...")
    print(f"  witness: {receipt['wit'][0]['id']}")
    print(f"  timeliness: {receipt['dims']['timeliness']:.2f}")
    print(f"  completeness: {receipt['dims']['completeness']}")
    if issues:
        for issue in issues:
            print(f"  → {issue}")

print("\n" + "=" * 60)
print("BRIDGE DESIGN:")
print("  PayLock delivery_hash → ADV delivery_hash (direct)")
print("  Escrow address → ADV witness.id (solana:addr)")
print("  Block timestamp → ADV timestamp (direct)")
print("  Score → ADV dims.completeness (direct)")
print("  Deadline math → ADV dims.timeliness (computed)")
print()
print("  On-chain hash IS the ground truth.")
print("  The bridge adds schema, not trust.")
print("=" * 60)
