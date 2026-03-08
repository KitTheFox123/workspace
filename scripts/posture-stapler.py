#!/usr/bin/env python3
"""posture-stapler.py — OCSP-stapling-inspired trust posture binding for agent actions.

Every action receipt carries a stapled trust posture: cert_id + warn_state + 
posture_timestamp + scope_hash. No separate lookup needed. Stale posture = stale action.

Based on RFC 6960 (OCSP) and RFC 6066 §8 (TLS Certificate Status Request).

Usage:
    python3 posture-stapler.py --demo
    python3 posture-stapler.py --staple --cert-id CERT --action ACTION [--warn-state clean|warn|critical]
    python3 posture-stapler.py --verify --receipt RECEIPT_JSON
"""

import argparse
import json
import hashlib
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TrustPosture:
    """Trust state at a specific moment."""
    cert_id: str
    warn_state: str  # clean, warn, critical, expired, unknown
    posture_timestamp: str
    scope_hash: str
    ttl_seconds: int = 300  # 5 min default posture validity


@dataclass
class ActionReceipt:
    """Action bound to trust posture via stapling."""
    action_hash: str
    action_description: str
    posture: TrustPosture
    staple_timestamp: str
    receipt_hash: str  # H(action_hash || posture)

    def is_posture_fresh(self) -> bool:
        """Check if stapled posture was fresh at staple time."""
        posture_ts = datetime.fromisoformat(self.posture.posture_timestamp)
        staple_ts = datetime.fromisoformat(self.staple_timestamp)
        delta = (staple_ts - posture_ts).total_seconds()
        return delta <= self.posture.ttl_seconds

    def grade(self) -> str:
        """Grade the receipt."""
        if not self.is_posture_fresh():
            return "F"  # Stale posture
        state_grades = {"clean": "A", "warn": "C", "critical": "D", "expired": "F", "unknown": "D"}
        return state_grades.get(self.posture.warn_state, "F")


def compute_hash(*parts: str) -> str:
    """SHA-256 of concatenated parts."""
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode())
    return h.hexdigest()[:16]


def staple_action(cert_id: str, action: str, warn_state: str = "clean",
                  scope_hash: str = "", ttl: int = 300) -> ActionReceipt:
    """Create a stapled action receipt."""
    now = datetime.now(timezone.utc).isoformat()
    
    posture = TrustPosture(
        cert_id=cert_id,
        warn_state=warn_state,
        posture_timestamp=now,
        scope_hash=scope_hash or compute_hash(cert_id, "scope"),
        ttl_seconds=ttl
    )
    
    action_hash = compute_hash(action, now)
    receipt_hash = compute_hash(action_hash, json.dumps(asdict(posture), sort_keys=True))
    
    return ActionReceipt(
        action_hash=action_hash,
        action_description=action,
        posture=posture,
        staple_timestamp=now,
        receipt_hash=receipt_hash
    )


def verify_receipt(receipt_json: str) -> dict:
    """Verify a receipt's integrity and freshness."""
    data = json.loads(receipt_json)
    
    # Reconstruct receipt hash
    posture_json = json.dumps(data["posture"], sort_keys=True)
    expected_hash = compute_hash(data["action_hash"], posture_json)
    
    integrity = expected_hash == data["receipt_hash"]
    
    receipt = ActionReceipt(
        action_hash=data["action_hash"],
        action_description=data["action_description"],
        posture=TrustPosture(**data["posture"]),
        staple_timestamp=data["staple_timestamp"],
        receipt_hash=data["receipt_hash"]
    )
    
    return {
        "integrity": "PASS" if integrity else "FAIL",
        "posture_fresh": receipt.is_posture_fresh(),
        "grade": receipt.grade(),
        "warn_state": receipt.posture.warn_state,
        "cert_id": receipt.posture.cert_id,
    }


def demo():
    """Demo: staple actions with different trust postures."""
    print("=" * 55)
    print("POSTURE STAPLER — OCSP-style trust binding")
    print("=" * 55)
    print()
    
    scenarios = [
        ("cert-001", "read user data", "clean"),
        ("cert-002", "write external API", "warn"),
        ("cert-003", "execute shell command", "critical"),
        ("cert-expired", "delete database", "expired"),
    ]
    
    for cert_id, action, state in scenarios:
        receipt = staple_action(cert_id, action, state)
        print(f"Action: {action}")
        print(f"  Cert: {cert_id} | State: {state} | Grade: {receipt.grade()}")
        print(f"  Receipt: {receipt.receipt_hash}")
        print(f"  Posture fresh: {receipt.is_posture_fresh()}")
        print()
    
    # Verify round-trip
    receipt = staple_action("cert-roundtrip", "test action", "clean")
    receipt_json = json.dumps(asdict(receipt))
    verification = verify_receipt(receipt_json)
    print(f"Round-trip verification: {verification}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCSP-stapling-inspired trust posture binding")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--staple", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--cert-id", type=str)
    parser.add_argument("--action", type=str)
    parser.add_argument("--warn-state", type=str, default="clean")
    parser.add_argument("--receipt", type=str)
    args = parser.parse_args()
    
    if args.staple and args.cert_id and args.action:
        receipt = staple_action(args.cert_id, args.action, args.warn_state)
        print(json.dumps(asdict(receipt), indent=2))
    elif args.verify and args.receipt:
        print(json.dumps(verify_receipt(args.receipt), indent=2))
    else:
        demo()
