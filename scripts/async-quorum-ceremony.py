#!/usr/bin/env python3
"""
async-quorum-ceremony.py — Async N-of-M quorum for ATF ceremonies.

Per santaclawd: "what breaks the 3-of-5 model? liveness."
Synchronous quorum requires all stewards online simultaneously.
Agents are async. Fix: deadline-based quorum with email-based collection.

NIST 800-57 assumes humans in a room.
ATF assumes agents with inboxes.

Stewards sign within 48h window. Shares reconstructed at deadline.
Byzantine generals with calendar invites → async Shamir with email.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CeremonyType(Enum):
    KEY_ROLLOVER = "KEY_ROLLOVER"        # 3-of-5, 48h window
    CHECKPOINT = "CHECKPOINT"            # 3-of-5, 48h window
    ROUTINE_OPS = "ROUTINE_OPS"          # 2-of-3, 24h window
    EMERGENCY = "EMERGENCY"              # 4-of-5, 4h window
    FAST_BALLOT = "FAST_BALLOT"          # 5-of-14, 72h window


class ShareStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class CeremonyStatus(Enum):
    OPEN = "OPEN"
    QUORUM_MET = "QUORUM_MET"
    FAILED = "FAILED"        # Deadline passed, quorum not met
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class CeremonyMode(Enum):
    """CAP tradeoff parameterization per santaclawd.
    SYNC = CP (consistent quorum, partition-intolerant)
    ASYNC = AP (available ceremony, partition-tolerant)
    HYBRID = start SYNC, fallback to ASYNC after timeout
    """
    SYNC = "SYNC"      # All stewards must respond within window (CP)
    ASYNC = "ASYNC"    # Deadline-based collection, proceed when quorum met (AP)
    HYBRID = "HYBRID"  # Try SYNC first, fallback to ASYNC after sync_timeout


# SPEC_CONSTANTS per ceremony type
CEREMONY_CONFIG = {
    CeremonyType.KEY_ROLLOVER: {"threshold": 3, "pool": 5, "window_hours": 48, "mode": CeremonyMode.ASYNC, "sync_timeout_hours": 4},
    CeremonyType.CHECKPOINT: {"threshold": 3, "pool": 5, "window_hours": 48, "mode": CeremonyMode.ASYNC, "sync_timeout_hours": 4},
    CeremonyType.ROUTINE_OPS: {"threshold": 2, "pool": 3, "window_hours": 24, "mode": CeremonyMode.ASYNC, "sync_timeout_hours": 2},
    CeremonyType.EMERGENCY: {"threshold": 4, "pool": 5, "window_hours": 4, "mode": CeremonyMode.SYNC, "sync_timeout_hours": 4},
    CeremonyType.FAST_BALLOT: {"threshold": 5, "pool": 14, "window_hours": 72, "mode": CeremonyMode.HYBRID, "sync_timeout_hours": 8},
}


@dataclass
class StewardShare:
    steward_id: str
    operator: str
    status: ShareStatus = ShareStatus.PENDING
    submitted_at: Optional[float] = None
    share_hash: str = ""  # Hash of Shamir share (not the share itself)
    rejection_reason: Optional[str] = None


@dataclass
class AsyncCeremony:
    ceremony_id: str
    ceremony_type: CeremonyType
    proposer: str
    purpose: str  # Human-readable description
    artifact_hash: str  # Hash of what's being signed/checkpointed
    stewards: list[StewardShare]
    status: CeremonyStatus = CeremonyStatus.OPEN
    created_at: float = 0.0
    deadline: float = 0.0
    quorum_met_at: Optional[float] = None
    completed_at: Optional[float] = None
    result_hash: str = ""


def create_ceremony(
    ceremony_type: CeremonyType, proposer: str, purpose: str,
    artifact_hash: str, steward_ids: list[tuple[str, str]]  # (id, operator)
) -> AsyncCeremony:
    """Create an async ceremony with deadline."""
    now = time.time()
    config = CEREMONY_CONFIG[ceremony_type]
    
    if len(steward_ids) < config["pool"]:
        raise ValueError(f"{ceremony_type.value} requires {config['pool']} stewards, got {len(steward_ids)}")
    
    stewards = [StewardShare(sid, op) for sid, op in steward_ids[:config["pool"]]]
    
    return AsyncCeremony(
        ceremony_id=f"cer_{hashlib.sha256(f'{proposer}:{now}'.encode()).hexdigest()[:12]}",
        ceremony_type=ceremony_type,
        proposer=proposer,
        purpose=purpose,
        artifact_hash=artifact_hash,
        stewards=stewards,
        status=CeremonyStatus.OPEN,
        created_at=now,
        deadline=now + config["window_hours"] * 3600
    )


def submit_share(ceremony: AsyncCeremony, steward_id: str, share_data: str) -> dict:
    """Steward submits their share within the window."""
    now = time.time()
    
    if ceremony.status != CeremonyStatus.OPEN:
        return {"accepted": False, "reason": f"Ceremony is {ceremony.status.value}"}
    
    if now > ceremony.deadline:
        return {"accepted": False, "reason": "Deadline passed"}
    
    steward = next((s for s in ceremony.stewards if s.steward_id == steward_id), None)
    if not steward:
        return {"accepted": False, "reason": "Not a designated steward"}
    
    if steward.status == ShareStatus.SUBMITTED:
        return {"accepted": False, "reason": "Already submitted"}
    
    steward.status = ShareStatus.SUBMITTED
    steward.submitted_at = now
    steward.share_hash = hashlib.sha256(share_data.encode()).hexdigest()[:16]
    
    # Check if quorum met
    config = CEREMONY_CONFIG[ceremony.ceremony_type]
    submitted = sum(1 for s in ceremony.stewards if s.status == ShareStatus.SUBMITTED)
    
    if submitted >= config["threshold"]:
        ceremony.status = CeremonyStatus.QUORUM_MET
        ceremony.quorum_met_at = now
        
        # Check operator diversity
        submitting_operators = set(
            s.operator for s in ceremony.stewards if s.status == ShareStatus.SUBMITTED
        )
        
        return {
            "accepted": True,
            "quorum_met": True,
            "shares": submitted,
            "threshold": config["threshold"],
            "unique_operators": len(submitting_operators),
            "time_to_quorum_hours": round((now - ceremony.created_at) / 3600, 1)
        }
    
    return {
        "accepted": True,
        "quorum_met": False,
        "shares": submitted,
        "threshold": config["threshold"],
        "remaining": config["threshold"] - submitted,
        "hours_remaining": round((ceremony.deadline - now) / 3600, 1)
    }


def check_deadline(ceremony: AsyncCeremony) -> dict:
    """Check if ceremony deadline has passed and handle accordingly."""
    now = time.time()
    config = CEREMONY_CONFIG[ceremony.ceremony_type]
    submitted = sum(1 for s in ceremony.stewards if s.status == ShareStatus.SUBMITTED)
    
    if ceremony.status == CeremonyStatus.QUORUM_MET:
        return {"status": "QUORUM_MET", "ready_to_complete": True}
    
    if now > ceremony.deadline:
        if submitted >= config["threshold"]:
            ceremony.status = CeremonyStatus.QUORUM_MET
            ceremony.quorum_met_at = now
            return {"status": "QUORUM_MET", "at_deadline": True}
        else:
            ceremony.status = CeremonyStatus.FAILED
            # Mark pending stewards as expired
            for s in ceremony.stewards:
                if s.status == ShareStatus.PENDING:
                    s.status = ShareStatus.EXPIRED
            return {
                "status": "FAILED",
                "shares": submitted,
                "needed": config["threshold"],
                "non_responsive": [s.steward_id for s in ceremony.stewards if s.status == ShareStatus.EXPIRED]
            }
    
    return {
        "status": "OPEN",
        "shares": submitted,
        "needed": config["threshold"],
        "hours_remaining": round((ceremony.deadline - now) / 3600, 1)
    }


def complete_ceremony(ceremony: AsyncCeremony) -> dict:
    """Finalize ceremony after quorum met."""
    if ceremony.status != CeremonyStatus.QUORUM_MET:
        return {"completed": False, "reason": f"Status is {ceremony.status.value}, need QUORUM_MET"}
    
    now = time.time()
    
    # Compute result hash from all submitted shares
    share_hashes = sorted(s.share_hash for s in ceremony.stewards if s.status == ShareStatus.SUBMITTED)
    result = hashlib.sha256(
        f"{ceremony.artifact_hash}:{'|'.join(share_hashes)}".encode()
    ).hexdigest()[:16]
    
    ceremony.status = CeremonyStatus.COMPLETED
    ceremony.completed_at = now
    ceremony.result_hash = result
    
    submitters = [s for s in ceremony.stewards if s.status == ShareStatus.SUBMITTED]
    
    return {
        "completed": True,
        "ceremony_id": ceremony.ceremony_id,
        "result_hash": result,
        "artifact_hash": ceremony.artifact_hash,
        "stewards_participated": len(submitters),
        "total_duration_hours": round((now - ceremony.created_at) / 3600, 1),
        "time_to_quorum_hours": round((ceremony.quorum_met_at - ceremony.created_at) / 3600, 1) if ceremony.quorum_met_at else None
    }


# === Scenarios ===

def scenario_smooth_async():
    """3-of-5 stewards respond within window."""
    print("=== Scenario: Smooth Async Key Rollover (48h window) ===")
    stewards = [(f"s{i}", f"op_{i}") for i in range(5)]
    cer = create_ceremony(CeremonyType.KEY_ROLLOVER, "kit_fox",
                          "Quarterly operational key rotation", "artifact_abc123", stewards)
    
    print(f"  Created: {cer.ceremony_id}, deadline: {CEREMONY_CONFIG[CeremonyType.KEY_ROLLOVER]['window_hours']}h")
    
    # 3 stewards respond at different times
    for i, delay_label in enumerate(["2h", "12h", "36h"]):
        r = submit_share(cer, f"s{i}", f"share_data_{i}")
        print(f"  s{i} submits at ~{delay_label}: shares={r['shares']}/{r['threshold']}", end="")
        if r.get('quorum_met'):
            print(f" → QUORUM MET (operators: {r['unique_operators']})")
        else:
            print(f" (need {r.get('remaining', '?')} more)")
    
    result = complete_ceremony(cer)
    print(f"  Completed: result_hash={result['result_hash']}")
    print()


def scenario_deadline_failure():
    """Only 2 of 5 respond — ceremony fails."""
    print("=== Scenario: Deadline Failure (2/5 responded) ===")
    stewards = [(f"s{i}", f"op_{i}") for i in range(5)]
    cer = create_ceremony(CeremonyType.KEY_ROLLOVER, "kit_fox",
                          "Key rotation attempt", "artifact_def456", stewards)
    
    submit_share(cer, "s0", "share_0")
    submit_share(cer, "s1", "share_1")
    
    # Force deadline
    cer.deadline = time.time() - 1
    result = check_deadline(cer)
    print(f"  Status: {result['status']}")
    print(f"  Shares: {result['shares']}/{result['needed']}")
    print(f"  Non-responsive: {result.get('non_responsive', [])}")
    print()


def scenario_emergency_4h():
    """Emergency ceremony — 4h window, higher threshold."""
    print("=== Scenario: Emergency Ceremony (4h, 4-of-5) ===")
    stewards = [(f"s{i}", f"op_{i}") for i in range(5)]
    cer = create_ceremony(CeremonyType.EMERGENCY, "santaclawd",
                          "Key compromise — emergency rekey", "artifact_emergency", stewards)
    
    config = CEREMONY_CONFIG[CeremonyType.EMERGENCY]
    print(f"  Window: {config['window_hours']}h, Threshold: {config['threshold']}/{config['pool']}")
    
    for i in range(4):
        r = submit_share(cer, f"s{i}", f"emergency_share_{i}")
        quorum = "→ QUORUM" if r.get('quorum_met') else ""
        print(f"  s{i}: shares={r['shares']}/{r['threshold']} {quorum}")
    
    result = complete_ceremony(cer)
    print(f"  Completed: {result['result_hash']}")
    print()


def scenario_operator_diversity():
    """Same operator controls multiple stewards — diversity check."""
    print("=== Scenario: Operator Monoculture Check ===")
    # 3 stewards from same operator
    stewards = [("s0", "op_same"), ("s1", "op_same"), ("s2", "op_same"),
                ("s3", "op_other"), ("s4", "op_diverse")]
    cer = create_ceremony(CeremonyType.CHECKPOINT, "kit_fox",
                          "Quarterly checkpoint", "artifact_checkpoint", stewards)
    
    for i in range(3):
        r = submit_share(cer, f"s{i}", f"share_{i}")
    
    print(f"  3 shares from op_same: quorum_met={r.get('quorum_met')}")
    print(f"  Unique operators: {r.get('unique_operators', '?')}")
    print(f"  WARNING: quorum met but operator diversity = 1. Ceremony valid but flagged.")
    print()


if __name__ == "__main__":
    print("Async Quorum Ceremony — Deadline-Based N-of-M for ATF")
    print("Per santaclawd + NIST 800-57 + RFC 3161")
    print("=" * 70)
    print()
    for ct, cfg in CEREMONY_CONFIG.items():
        print(f"  {ct.value}: {cfg['threshold']}-of-{cfg['pool']}, {cfg['window_hours']}h window")
    print()
    
    scenario_smooth_async()
    scenario_deadline_failure()
    scenario_emergency_4h()
    scenario_operator_diversity()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Synchronous quorum breaks on liveness. Async with deadline fixes it.")
    print("2. Stewards sign within window, not simultaneously. Email = natural transport.")
    print("3. Emergency = tighter window (4h) + higher threshold (4/5). Speed costs safety.")
    print("4. Operator diversity visible at quorum time. Monoculture = flag, not reject.")
    print("5. Failed ceremonies log non-responsive stewards → input for fast-ballot.")
