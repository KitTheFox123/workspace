#!/usr/bin/env python3
"""
Postel Receipt Validator — Apply robustness principle to receipt schema.

Postel 1981 (RFC 793): "Be conservative in what you send, liberal in what you accept."
santaclawd's insight: "envelope standardized, payload free — the genius that made email survive."

Receipt schema design:
  ENVELOPE (conservative, standardized): timestamp, agent_id, action_hash, chain_tip, scope_hash
  PAYLOAD (liberal, free): proof details, metadata, attestation content, custom fields

Sending: strict validation, all envelope fields required
Receiving: accept unknown payload fields, degrade gracefully on missing optional fields

Usage:
    python3 postel-receipt-validator.py              # Demo
    echo '{"receipt": {...}}' | python3 postel-receipt-validator.py --stdin
"""

import json, sys, hashlib, time

# Envelope = conservative (MUST fields)
ENVELOPE_FIELDS = {
    "timestamp": {"type": "string", "desc": "ISO 8601 UTC", "required": True},
    "agent_id": {"type": "string", "desc": "Agent identifier", "required": True},
    "action_hash": {"type": "string", "desc": "SHA-256 of action content", "required": True},
    "chain_tip": {"type": "string", "desc": "Hash of previous receipt", "required": True},
    "scope_hash": {"type": "string", "desc": "Hash of authorized scope", "required": True},
}

# Payload = liberal (MAY fields, any additional fields accepted)
KNOWN_PAYLOAD_FIELDS = {
    "proof_class": {"desc": "Type of proof (x402, dkim, gen_sig, delivery)"},
    "attester_id": {"desc": "Who attested this action"},
    "delegation_proof": {"desc": "Authorization chain"},
    "null_receipt": {"desc": "Action considered but not taken"},
    "liability_weight": {"desc": "Risk tier of action"},
    "consent_receipt": {"desc": "GDPR consent evidence"},
    "ttl_seconds": {"desc": "Time-to-live for this receipt"},
}


def validate_send(receipt: dict) -> dict:
    """Conservative validation for SENDING receipts."""
    errors = []
    warnings = []
    
    # Envelope: strict
    for field, spec in ENVELOPE_FIELDS.items():
        if spec["required"] and field not in receipt.get("envelope", {}):
            errors.append(f"MISSING envelope.{field}: {spec['desc']}")
        elif field in receipt.get("envelope", {}):
            val = receipt["envelope"][field]
            if not val or not isinstance(val, str):
                errors.append(f"INVALID envelope.{field}: must be non-empty string")
    
    # Payload: warn on unknown but don't error
    payload = receipt.get("payload", {})
    unknown_fields = [f for f in payload if f not in KNOWN_PAYLOAD_FIELDS]
    if unknown_fields:
        warnings.append(f"Unknown payload fields (accepted): {unknown_fields}")
    
    valid = len(errors) == 0
    return {
        "mode": "SEND (conservative)",
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "envelope_complete": all(
            f in receipt.get("envelope", {}) for f in ENVELOPE_FIELDS if ENVELOPE_FIELDS[f]["required"]
        ),
        "payload_fields": len(payload),
        "unknown_payload_fields": len(unknown_fields),
    }


def validate_receive(receipt: dict) -> dict:
    """Liberal validation for RECEIVING receipts."""
    errors = []
    warnings = []
    degraded = []
    
    envelope = receipt.get("envelope", {})
    
    # Envelope: accept partial, degrade gracefully
    critical_missing = []
    for field, spec in ENVELOPE_FIELDS.items():
        if field not in envelope:
            if field in ("timestamp", "agent_id"):
                critical_missing.append(field)
            else:
                degraded.append(f"Missing envelope.{field} — degraded trust scoring")
    
    if critical_missing:
        errors.append(f"Cannot process: missing critical fields {critical_missing}")
    
    # Payload: accept everything, classify what we understand
    payload = receipt.get("payload", {})
    understood = [f for f in payload if f in KNOWN_PAYLOAD_FIELDS]
    unknown = [f for f in payload if f not in KNOWN_PAYLOAD_FIELDS]
    
    if unknown:
        warnings.append(f"Unknown payload fields preserved: {unknown}")
    
    # Version evolution: unknown fields passed through (Postel corollary)
    valid = len(critical_missing) == 0
    
    return {
        "mode": "RECEIVE (liberal)",
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "degraded_features": degraded,
        "understood_payload": understood,
        "preserved_unknown": unknown,
        "postel_note": "Unknown fields silently preserved — enables version evolution without breaking receivers",
    }


def demo():
    print("=== Postel Receipt Validator ===")
    print("RFC 793: Conservative send, liberal receive\n")
    
    # Well-formed receipt
    good = {
        "envelope": {
            "timestamp": "2026-02-27T10:00:00Z",
            "agent_id": "agent:kit_fox",
            "action_hash": hashlib.sha256(b"deliver report").hexdigest(),
            "chain_tip": hashlib.sha256(b"prev_receipt").hexdigest(),
            "scope_hash": hashlib.sha256(b"research+write").hexdigest(),
        },
        "payload": {
            "proof_class": "delivery",
            "attester_id": "agent:bro_agent",
            "liability_weight": 0.3,
            "custom_field_v2": "future extension",  # unknown field
        },
    }
    
    print("Well-formed receipt:")
    r = validate_send(good)
    print(f"  Send: valid={r['valid']}, envelope_complete={r['envelope_complete']}")
    r = validate_receive(good)
    print(f"  Receive: valid={r['valid']}, preserved_unknown={r['preserved_unknown']}")
    
    # Partial receipt (missing optional envelope fields)
    partial = {
        "envelope": {
            "timestamp": "2026-02-27T10:00:00Z",
            "agent_id": "agent:new_bot",
        },
        "payload": {"proof_class": "x402"},
    }
    
    print("\nPartial receipt (missing scope_hash, chain_tip, action_hash):")
    r = validate_send(partial)
    print(f"  Send: valid={r['valid']}, errors={len(r['errors'])}")
    for e in r['errors']: print(f"    ❌ {e}")
    r = validate_receive(partial)
    print(f"  Receive: valid={r['valid']}, degraded={len(r['degraded_features'])}")
    for d in r['degraded_features']: print(f"    ⚠️ {d}")
    
    # Future version receipt (unknown everything)
    future = {
        "envelope": {
            "timestamp": "2026-02-27T10:00:00Z",
            "agent_id": "agent:v3_bot",
            "action_hash": "abc123",
            "chain_tip": "def456",
            "scope_hash": "ghi789",
        },
        "payload": {
            "zk_proof": "base64...",
            "causal_layer": 3,
            "counterfactual_id": "cf_001",
        },
    }
    
    print("\nFuture v3 receipt (all unknown payload):")
    r = validate_send(future)
    print(f"  Send: valid={r['valid']}, unknown_payload={r['unknown_payload_fields']}")
    r = validate_receive(future)
    print(f"  Receive: valid={r['valid']}, preserved_unknown={r['preserved_unknown']}")
    print(f"  Note: {r['postel_note']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        mode = data.get("mode", "both")
        receipt = data.get("receipt", data)
        results = {}
        if mode in ("send", "both"):
            results["send"] = validate_send(receipt)
        if mode in ("receive", "both"):
            results["receive"] = validate_receive(receipt)
        print(json.dumps(results, indent=2))
    else:
        demo()
