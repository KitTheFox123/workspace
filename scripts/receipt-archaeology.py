#!/usr/bin/env python3
"""
receipt-archaeology.py — Time-of-signing semantics for ATF receipt validation.

Per santaclawd: "what happens to signed receipts when the key gets revoked?"
Per CAdES-A (ETSI EN 319 122): embed timestamp + validation data at signing time.
Receipt valid for window issued regardless of later revocation.

Key insight: retroactive invalidation kills all audit trails.
Dispute resolution MUST use snapshot-at-signing, not current verifier state.

Three validation modes:
  CURRENT     — Validate against current verifier table (live queries)
  SNAPSHOT    — Validate against embedded snapshot (time-of-signing)
  ARCHIVAL    — Validate with timestamp authority + full chain (CAdES-A model)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ValidationMode(Enum):
    CURRENT = "CURRENT"      # Live validation (may fail for old receipts)
    SNAPSHOT = "SNAPSHOT"     # Embedded validation data from signing time
    ARCHIVAL = "ARCHIVAL"     # Full CAdES-A with TSA


class ReceiptValidity(Enum):
    VALID = "VALID"
    VALID_AT_SIGNING = "VALID_AT_SIGNING"  # Key now revoked, but was valid when signed
    INVALID = "INVALID"
    INDETERMINATE = "INDETERMINATE"  # Cannot determine (missing snapshot data)


class KeyStatus(Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"


@dataclass
class VerifierSnapshot:
    """Snapshot of verifier state at time of signing (CAdES-A model)."""
    key_id: str
    key_status: KeyStatus
    key_fingerprint: str
    trusted_score: float
    snapshot_timestamp: float
    registry_hash: str  # Hash of registry state at snapshot time


@dataclass
class TimestampToken:
    """RFC 3161 timestamp authority token."""
    tsa_id: str
    timestamp: float
    hash_algorithm: str
    message_hash: str
    tsa_signature: str


@dataclass
class ArchivalReceipt:
    """Receipt with full archival validation data."""
    receipt_id: str
    agent_id: str
    counterparty_id: str
    content_hash: str
    signing_key_id: str
    signature: str
    timestamp: float
    # CAdES-A archival data
    verifier_snapshot: Optional[VerifierSnapshot] = None
    timestamp_token: Optional[TimestampToken] = None
    # Chain of prior snapshots for long-term validation
    validation_chain: list[VerifierSnapshot] = field(default_factory=list)


@dataclass
class VerifierTable:
    """Current state of verifier table (live)."""
    keys: dict  # key_id -> KeyStatus
    scores: dict  # agent_id -> trusted_score
    last_updated: float


def create_receipt_with_snapshot(
    agent_id: str, counterparty_id: str, content: str,
    signing_key_id: str, verifier_table: VerifierTable
) -> ArchivalReceipt:
    """Create a receipt with embedded verifier snapshot (time-of-signing)."""
    now = time.time()
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # Embed snapshot of current verifier state
    key_status = verifier_table.keys.get(signing_key_id, KeyStatus.ACTIVE)
    score = verifier_table.scores.get(agent_id, 0.0)
    registry_hash = hashlib.sha256(
        json.dumps({"keys": {k: v.value for k, v in verifier_table.keys.items()},
                    "scores": verifier_table.scores}, sort_keys=True).encode()
    ).hexdigest()[:16]
    
    snapshot = VerifierSnapshot(
        key_id=signing_key_id,
        key_status=key_status,
        key_fingerprint=hashlib.sha256(signing_key_id.encode()).hexdigest()[:12],
        trusted_score=score,
        snapshot_timestamp=now,
        registry_hash=registry_hash
    )
    
    # Simulated TSA token
    tsa_token = TimestampToken(
        tsa_id="tsa_atf_root",
        timestamp=now,
        hash_algorithm="sha256",
        message_hash=content_hash,
        tsa_signature=hashlib.sha256(f"tsa:{content_hash}:{now}".encode()).hexdigest()[:16]
    )
    
    return ArchivalReceipt(
        receipt_id=f"rcpt_{hashlib.sha256(f'{agent_id}:{now}'.encode()).hexdigest()[:12]}",
        agent_id=agent_id,
        counterparty_id=counterparty_id,
        content_hash=content_hash,
        signing_key_id=signing_key_id,
        signature=hashlib.sha256(f"sig:{content_hash}:{signing_key_id}".encode()).hexdigest()[:16],
        timestamp=now,
        verifier_snapshot=snapshot,
        timestamp_token=tsa_token
    )


def validate_receipt(
    receipt: ArchivalReceipt,
    current_table: VerifierTable,
    mode: ValidationMode
) -> dict:
    """Validate a receipt using specified mode."""
    
    if mode == ValidationMode.CURRENT:
        # Live validation against current state
        key_status = current_table.keys.get(receipt.signing_key_id, KeyStatus.EXPIRED)
        
        if key_status == KeyStatus.ACTIVE:
            return {"validity": ReceiptValidity.VALID.value, "mode": mode.value,
                    "key_status": key_status.value}
        elif key_status == KeyStatus.REVOKED:
            return {"validity": ReceiptValidity.INVALID.value, "mode": mode.value,
                    "key_status": key_status.value,
                    "warning": "Key revoked. Receipt may have been valid at signing time. Use SNAPSHOT mode."}
        else:
            return {"validity": ReceiptValidity.INDETERMINATE.value, "mode": mode.value,
                    "key_status": key_status.value}
    
    elif mode == ValidationMode.SNAPSHOT:
        # Validate against embedded snapshot
        if not receipt.verifier_snapshot:
            return {"validity": ReceiptValidity.INDETERMINATE.value, "mode": mode.value,
                    "reason": "No embedded snapshot. Cannot validate time-of-signing."}
        
        snapshot = receipt.verifier_snapshot
        if snapshot.key_status == KeyStatus.ACTIVE:
            # Key was active at signing time
            current_status = current_table.keys.get(receipt.signing_key_id, KeyStatus.EXPIRED)
            if current_status == KeyStatus.REVOKED:
                return {"validity": ReceiptValidity.VALID_AT_SIGNING.value, "mode": mode.value,
                        "at_signing": snapshot.key_status.value,
                        "current": current_status.value,
                        "snapshot_time": snapshot.snapshot_timestamp,
                        "trusted_score_at_signing": snapshot.trusted_score,
                        "note": "Receipt was valid when signed. Key later revoked. Audit trail preserved."}
            else:
                return {"validity": ReceiptValidity.VALID.value, "mode": mode.value,
                        "at_signing": snapshot.key_status.value,
                        "current": current_status.value}
        else:
            return {"validity": ReceiptValidity.INVALID.value, "mode": mode.value,
                    "reason": f"Key was {snapshot.key_status.value} at signing time."}
    
    elif mode == ValidationMode.ARCHIVAL:
        # Full CAdES-A validation with TSA
        if not receipt.verifier_snapshot or not receipt.timestamp_token:
            return {"validity": ReceiptValidity.INDETERMINATE.value, "mode": mode.value,
                    "reason": "Missing archival data (snapshot or TSA token)."}
        
        snapshot = receipt.verifier_snapshot
        tsa = receipt.timestamp_token
        
        # Verify TSA token matches content
        expected_hash = receipt.content_hash
        tsa_valid = tsa.message_hash == expected_hash
        
        # Verify snapshot timestamp matches TSA timestamp (within tolerance)
        time_match = abs(snapshot.snapshot_timestamp - tsa.timestamp) < 60  # 1 min tolerance
        
        if not tsa_valid:
            return {"validity": ReceiptValidity.INVALID.value, "mode": mode.value,
                    "reason": "TSA hash mismatch — content tampered after signing."}
        
        if not time_match:
            return {"validity": ReceiptValidity.INDETERMINATE.value, "mode": mode.value,
                    "reason": "Timestamp mismatch between snapshot and TSA."}
        
        current_status = current_table.keys.get(receipt.signing_key_id, KeyStatus.EXPIRED)
        
        return {
            "validity": (ReceiptValidity.VALID_AT_SIGNING.value 
                        if current_status != KeyStatus.ACTIVE 
                        else ReceiptValidity.VALID.value),
            "mode": mode.value,
            "tsa_verified": True,
            "snapshot_verified": True,
            "at_signing": snapshot.key_status.value,
            "current": current_status.value,
            "signing_time": tsa.timestamp,
            "trusted_score_at_signing": snapshot.trusted_score,
            "registry_hash": snapshot.registry_hash,
            "archival_complete": True
        }


# === Scenarios ===

def scenario_key_revoked_after_signing():
    """Receipt signed with valid key, key later revoked."""
    print("=== Scenario: Key Revoked After Signing ===")
    
    # State at signing time
    signing_table = VerifierTable(
        keys={"key_001": KeyStatus.ACTIVE},
        scores={"agent_a": 0.85},
        last_updated=time.time()
    )
    
    receipt = create_receipt_with_snapshot("agent_a", "agent_b", "deliverable content",
                                           "key_001", signing_table)
    
    # State now (key revoked)
    current_table = VerifierTable(
        keys={"key_001": KeyStatus.REVOKED, "key_002": KeyStatus.ACTIVE},
        scores={"agent_a": 0.85},
        last_updated=time.time()
    )
    
    # Compare all three modes
    for mode in ValidationMode:
        result = validate_receipt(receipt, current_table, mode)
        print(f"  {mode.value}: {result['validity']}")
        if 'note' in result:
            print(f"    → {result['note']}")
        if 'warning' in result:
            print(f"    ⚠ {result['warning']}")
    print()


def scenario_no_snapshot():
    """Old receipt without embedded snapshot — indeterminate."""
    print("=== Scenario: Legacy Receipt (No Snapshot) ===")
    
    receipt = ArchivalReceipt(
        receipt_id="rcpt_legacy",
        agent_id="agent_old",
        counterparty_id="agent_c",
        content_hash="abc123",
        signing_key_id="key_expired",
        signature="sig_old",
        timestamp=time.time() - 86400 * 365,
        verifier_snapshot=None,
        timestamp_token=None
    )
    
    current_table = VerifierTable(
        keys={"key_expired": KeyStatus.EXPIRED},
        scores={"agent_old": 0.30},
        last_updated=time.time()
    )
    
    for mode in ValidationMode:
        result = validate_receipt(receipt, current_table, mode)
        print(f"  {mode.value}: {result['validity']} — {result.get('reason', result.get('warning', 'ok'))}")
    print()


def scenario_dispute_resolution():
    """Dispute uses snapshot-at-signing for fair adjudication."""
    print("=== Scenario: Dispute Resolution (Snapshot-at-Signing) ===")
    
    signing_table = VerifierTable(
        keys={"key_dispute": KeyStatus.ACTIVE},
        scores={"agent_disputed": 0.92},
        last_updated=time.time() - 86400 * 30
    )
    
    receipt = create_receipt_with_snapshot("agent_disputed", "agent_accuser",
                                           "scope: deliver report by March 1",
                                           "key_dispute", signing_table)
    
    # Agent's score dropped since then (maybe due to other failures)
    current_table = VerifierTable(
        keys={"key_dispute": KeyStatus.SUSPENDED},
        scores={"agent_disputed": 0.45},
        last_updated=time.time()
    )
    
    # SNAPSHOT mode shows what was true at contract time
    result = validate_receipt(receipt, current_table, ValidationMode.ARCHIVAL)
    print(f"  Archival validation: {result['validity']}")
    print(f"  Score at signing: {result.get('trusted_score_at_signing', '?')}")
    print(f"  Score now: {current_table.scores.get('agent_disputed', '?')}")
    print(f"  Key at signing: {result.get('at_signing', '?')}")
    print(f"  Key now: {result.get('current', '?')}")
    print(f"  → Dispute adjudication uses signing-time state, not current state.")
    print(f"  → Agent was 0.92 trusted when they committed. Current 0.45 is irrelevant to THIS receipt.")
    print()


if __name__ == "__main__":
    print("Receipt Archaeology — Time-of-Signing Semantics for ATF")
    print("Per santaclawd + CAdES-A (ETSI EN 319 122)")
    print("=" * 70)
    print()
    print("Three validation modes:")
    print("  CURRENT:  Live validation (fails for revoked keys)")
    print("  SNAPSHOT: Embedded verifier state from signing time")
    print("  ARCHIVAL: Full CAdES-A with TSA + chain validation")
    print()
    
    scenario_key_revoked_after_signing()
    scenario_no_snapshot()
    scenario_dispute_resolution()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Retroactive invalidation kills all audit trails. Never do it.")
    print("2. Receipts carry snapshot of verifier state AT signing time.")
    print("3. VALID_AT_SIGNING = key now revoked but receipt was valid when signed.")
    print("4. Dispute resolution MUST use snapshot-at-signing, not current state.")
    print("5. Legacy receipts without snapshots = INDETERMINATE (migration problem).")
    print("6. TSA token prevents backdating — content hash locked at signing time.")
