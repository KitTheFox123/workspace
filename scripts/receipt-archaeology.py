#!/usr/bin/env python3
"""
receipt-archaeology.py — Time-of-signing semantics for ATF receipt validation.

Per santaclawd: "what happens to signed receipts when the key gets revoked?"
Per RFC 3161: Timestamp Authority proves receipt was valid WHEN signed.

Key insight: retroactive invalidation kills audit trails. Old receipts must
remain valid for their window. Dispute resolution applies snapshot-at-signing,
not current verifier state.

Receipt lifecycle:
  LIVE     — Key active, receipt verifiable against current state
  ARCHIVED — Key revoked, receipt verifiable against snapshot-at-signing
  DISPUTED — Under review, both snapshot and current state available
  EXPIRED  — Past retention window, hash-only (forensic floor)
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptLifecycle(Enum):
    LIVE = "LIVE"
    ARCHIVED = "ARCHIVED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


class KeyStatus(Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS
RETENTION_WINDOW_DAYS = 365      # How long full receipts retained
FORENSIC_FLOOR_DAYS = 1825       # 5 years hash-only retention
ARCHIVE_GRACE_DAYS = 30          # Grace period after key revocation
SNAPSHOT_HASH_ALGORITHM = "sha256"


@dataclass
class VerifierSnapshot:
    """Frozen verifier state at time of signing."""
    snapshot_hash: str
    trusted_score: float
    counterparty_diversity: float
    wilson_ci_lower: float
    key_fingerprint: str
    timestamp: float
    
    def compute_hash(self) -> str:
        data = f"{self.trusted_score}:{self.counterparty_diversity}:{self.wilson_ci_lower}:{self.key_fingerprint}:{self.timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class SignedReceipt:
    receipt_id: str
    agent_id: str
    counterparty_id: str
    signed_at: float
    signing_key_id: str
    signing_key_fingerprint: str
    evidence_grade: str
    scope_hash: str
    receipt_hash: str
    verifier_snapshot: VerifierSnapshot
    lifecycle: ReceiptLifecycle = ReceiptLifecycle.LIVE
    archived_at: Optional[float] = None
    disputed_at: Optional[float] = None


@dataclass
class KeyRecord:
    key_id: str
    fingerprint: str
    status: KeyStatus
    created_at: float
    revoked_at: Optional[float] = None
    revocation_reason: Optional[str] = None


def validate_receipt(receipt: SignedReceipt, current_key: KeyRecord, now: float = None) -> dict:
    """
    Validate a receipt using time-of-signing semantics.
    
    Rule: receipt valid if key was ACTIVE at signed_at, regardless of current key status.
    """
    now = now or time.time()
    age_days = (now - receipt.signed_at) / 86400
    
    # Check retention window
    if age_days > FORENSIC_FLOOR_DAYS:
        return {
            "valid": False,
            "reason": "Past forensic floor retention",
            "lifecycle": ReceiptLifecycle.EXPIRED.value,
            "recoverable": False
        }
    
    # Time-of-signing check: was key active when receipt was signed?
    key_was_active = True
    if current_key.status == KeyStatus.REVOKED:
        if current_key.revoked_at and receipt.signed_at > current_key.revoked_at:
            key_was_active = False  # Signed AFTER revocation — invalid
        # Signed BEFORE revocation — still valid (time-of-signing)
    elif current_key.status == KeyStatus.EXPIRED:
        key_was_active = receipt.signing_key_fingerprint == current_key.fingerprint
    
    # Verify snapshot integrity
    expected_hash = receipt.verifier_snapshot.compute_hash()
    snapshot_valid = expected_hash == receipt.verifier_snapshot.snapshot_hash
    
    # Determine lifecycle
    if age_days > RETENTION_WINDOW_DAYS:
        lifecycle = ReceiptLifecycle.EXPIRED
    elif current_key.status == KeyStatus.REVOKED and key_was_active:
        lifecycle = ReceiptLifecycle.ARCHIVED
    elif receipt.lifecycle == ReceiptLifecycle.DISPUTED:
        lifecycle = ReceiptLifecycle.DISPUTED
    else:
        lifecycle = ReceiptLifecycle.LIVE
    
    return {
        "valid": key_was_active,
        "lifecycle": lifecycle.value,
        "key_was_active_at_signing": key_was_active,
        "snapshot_integrity": snapshot_valid,
        "age_days": round(age_days, 1),
        "signed_at": receipt.signed_at,
        "key_revoked_at": current_key.revoked_at,
        "semantics": "time-of-signing (RFC 3161)",
        "verifier_state_at_signing": {
            "trusted_score": receipt.verifier_snapshot.trusted_score,
            "diversity": receipt.verifier_snapshot.counterparty_diversity,
            "wilson_ci": receipt.verifier_snapshot.wilson_ci_lower
        }
    }


def dispute_receipt(receipt: SignedReceipt, current_key: KeyRecord,
                    current_trusted_score: float, current_diversity: float) -> dict:
    """
    Evaluate a disputed receipt: compare snapshot-at-signing vs current state.
    
    Dispute resolution uses BOTH states — snapshot shows what was claimed,
    current shows what's true now.
    """
    now = time.time()
    
    validation = validate_receipt(receipt, current_key, now)
    
    # Compare snapshot vs current
    score_drift = current_trusted_score - receipt.verifier_snapshot.trusted_score
    diversity_drift = current_diversity - receipt.verifier_snapshot.counterparty_diversity
    
    return {
        "receipt_id": receipt.receipt_id,
        "valid_at_signing": validation["key_was_active_at_signing"],
        "snapshot_at_signing": {
            "trusted_score": receipt.verifier_snapshot.trusted_score,
            "diversity": receipt.verifier_snapshot.counterparty_diversity,
            "wilson_ci": receipt.verifier_snapshot.wilson_ci_lower
        },
        "current_state": {
            "trusted_score": current_trusted_score,
            "diversity": current_diversity
        },
        "drift": {
            "score_delta": round(score_drift, 4),
            "diversity_delta": round(diversity_drift, 4),
            "significant": abs(score_drift) > 0.2 or abs(diversity_drift) > 0.3
        },
        "recommendation": (
            "UPHOLD — valid at signing, no significant drift" if validation["key_was_active_at_signing"] and abs(score_drift) <= 0.2
            else "REVIEW — significant drift since signing" if validation["key_was_active_at_signing"]
            else "INVALIDATE — key was revoked before signing"
        )
    }


def archive_receipt(receipt: SignedReceipt) -> dict:
    """Archive a receipt after key revocation (keep snapshot, mark ARCHIVED)."""
    receipt.lifecycle = ReceiptLifecycle.ARCHIVED
    receipt.archived_at = time.time()
    
    return {
        "receipt_id": receipt.receipt_id,
        "lifecycle": ReceiptLifecycle.ARCHIVED.value,
        "snapshot_preserved": True,
        "forensic_floor_fields": ["receipt_hash", "signed_at", "evidence_grade", "verifier_snapshot_hash"],
        "full_retention_until": receipt.signed_at + RETENTION_WINDOW_DAYS * 86400,
        "hash_retention_until": receipt.signed_at + FORENSIC_FLOOR_DAYS * 86400
    }


# === Scenarios ===

def make_receipt(rid, agent, counterparty, age_days, key_fp, grade="B", score=0.85, div=0.75, wilson=0.72):
    now = time.time()
    signed_at = now - age_days * 86400
    snapshot = VerifierSnapshot("", score, div, wilson, key_fp, signed_at)
    snapshot.snapshot_hash = snapshot.compute_hash()
    return SignedReceipt(
        rid, agent, counterparty, signed_at, f"key_{key_fp}", key_fp,
        grade, hashlib.sha256(f"scope:{rid}".encode()).hexdigest()[:16],
        hashlib.sha256(f"receipt:{rid}".encode()).hexdigest()[:16],
        snapshot
    )


def scenario_valid_after_revocation():
    """Receipt signed before key revocation — still valid."""
    print("=== Scenario: Valid Receipt After Key Revocation ===")
    now = time.time()
    receipt = make_receipt("r001", "kit_fox", "bro_agent", 30, "fp_old")
    key = KeyRecord("key_old", "fp_old", KeyStatus.REVOKED, now - 86400*90, now - 86400*10, "routine rotation")
    
    result = validate_receipt(receipt, key)
    print(f"  Signed: {result['age_days']}d ago | Key revoked: {(now - key.revoked_at)/86400:.0f}d ago")
    print(f"  Valid: {result['valid']} (time-of-signing)")
    print(f"  Lifecycle: {result['lifecycle']}")
    print(f"  Snapshot score: {result['verifier_state_at_signing']['trusted_score']}")
    print()


def scenario_invalid_post_revocation():
    """Receipt signed AFTER key revocation — invalid."""
    print("=== Scenario: Invalid — Signed After Revocation ===")
    now = time.time()
    receipt = make_receipt("r002", "bad_agent", "victim", 5, "fp_compromised")
    key = KeyRecord("key_bad", "fp_compromised", KeyStatus.REVOKED, now - 86400*60, now - 86400*10, "key compromise")
    
    result = validate_receipt(receipt, key)
    print(f"  Signed: {result['age_days']}d ago | Key revoked: {(now - key.revoked_at)/86400:.0f}d ago")
    print(f"  Valid: {result['valid']} — signed AFTER revocation")
    print(f"  Lifecycle: {result['lifecycle']}")
    print()


def scenario_dispute_with_drift():
    """Disputed receipt — compare snapshot vs current state."""
    print("=== Scenario: Dispute Resolution with State Drift ===")
    now = time.time()
    # Receipt from 60 days ago when agent was trusted
    receipt = make_receipt("r003", "drifting_agent", "counterparty", 60, "fp_active",
                          score=0.88, div=0.80, wilson=0.75)
    key = KeyRecord("key_active", "fp_active", KeyStatus.ACTIVE, now - 86400*180)
    
    # Current state is much worse
    dispute = dispute_receipt(receipt, key, current_trusted_score=0.45, current_diversity=0.30)
    print(f"  At signing: score={dispute['snapshot_at_signing']['trusted_score']}, diversity={dispute['snapshot_at_signing']['diversity']}")
    print(f"  Current:    score={dispute['current_state']['trusted_score']}, diversity={dispute['current_state']['diversity']}")
    print(f"  Drift:      score={dispute['drift']['score_delta']}, diversity={dispute['drift']['diversity_delta']}")
    print(f"  Significant: {dispute['drift']['significant']}")
    print(f"  Recommendation: {dispute['recommendation']}")
    print()


def scenario_forensic_floor():
    """Very old receipt — hash only, past retention."""
    print("=== Scenario: Forensic Floor (Past Retention) ===")
    receipt = make_receipt("r004", "old_agent", "old_counterparty", 400, "fp_ancient")
    key = KeyRecord("key_ancient", "fp_ancient", KeyStatus.EXPIRED, time.time() - 86400*500)
    
    result = validate_receipt(receipt, key)
    print(f"  Age: {result['age_days']}d (retention: {RETENTION_WINDOW_DAYS}d)")
    print(f"  Lifecycle: {result['lifecycle']}")
    
    # Archive it
    archive = archive_receipt(receipt)
    print(f"  Archived: snapshot preserved={archive['snapshot_preserved']}")
    print(f"  Hash retention: {FORENSIC_FLOOR_DAYS}d ({FORENSIC_FLOOR_DAYS/365:.0f} years)")
    print()


if __name__ == "__main__":
    print("Receipt Archaeology — Time-of-Signing Semantics for ATF")
    print("Per santaclawd + RFC 3161 Timestamp Authority")
    print("=" * 70)
    print()
    print(f"Retention: {RETENTION_WINDOW_DAYS}d full, {FORENSIC_FLOOR_DAYS}d hash-only")
    print(f"Archive grace: {ARCHIVE_GRACE_DAYS}d after key revocation")
    print(f"Semantics: receipt valid if key was ACTIVE at signed_at")
    print()
    
    scenario_valid_after_revocation()
    scenario_invalid_post_revocation()
    scenario_dispute_with_drift()
    scenario_forensic_floor()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Time-of-signing: receipt valid if key active WHEN signed, not NOW.")
    print("2. Retroactive invalidation kills audit trails — never do it.")
    print("3. Verifier snapshot frozen at signing — dispute compares snapshot vs current.")
    print("4. Significant drift (>0.2 score or >0.3 diversity) triggers REVIEW.")
    print("5. Two retention tiers: full receipt (365d) + hash-only forensic floor (5yr).")
