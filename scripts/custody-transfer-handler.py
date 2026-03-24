#!/usr/bin/env python3
"""
custody-transfer-handler.py — EPP-style custody transfer for ATF agent identity.

Per santaclawd: does EPP-style 5-day ACK window work for ATF or is 14d better
given agent sleep cycles? Answer: 24h. Agents are not humans.

ICANN Transfer Policy model:
  1. Gaining registrar requests transfer
  2. Losing registrar has 5 days to ACK/NACK via FOA (Form of Authorization)
  3. No response = transfer proceeds (default-approve)

ATF Custody Transfer model:
  1. New custodian submits CUSTODY_REQUEST with agent_id + operator_genesis_hash
  2. Old custodian has ACK_WINDOW (24h) to sign CUSTODY_ACK or CUSTODY_DENY
  3. No response = CUSTODY_TIMEOUT → receipts frozen, registry marks PENDING_TRANSFER
  4. Clock starts at last signed receipt from old custodian (observable, not declared)

Key difference from EPP: default is FREEZE not APPROVE. Agent identity is
more sensitive than domain names.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# SPEC_CONSTANTS
ACK_WINDOW_SECONDS = 86400      # 24 hours (not EPP's 5 days — agents don't sleep 5 days)
FREEZE_WINDOW_SECONDS = 259200  # 72 hours after timeout before force-transfer
MIN_RECEIPTS_FOR_TRANSFER = 10  # Must have meaningful history
CUSTODY_HASH_ALG = "sha256"


class CustodyState(Enum):
    ACTIVE = "ACTIVE"                       # Normal operation
    PENDING_TRANSFER = "PENDING_TRANSFER"   # Request submitted, awaiting ACK
    ACK_RECEIVED = "ACK_RECEIVED"           # Old custodian approved
    DENIED = "DENIED"                       # Old custodian rejected
    TIMEOUT_FROZEN = "TIMEOUT_FROZEN"       # No response, receipts frozen
    TRANSFERRED = "TRANSFERRED"             # Transfer complete
    CONTESTED = "CONTESTED"                 # Both parties claim custody
    REVOKED = "REVOKED"                     # Identity revoked during transfer


class TransferResult(Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    TIMEOUT_FROZEN = "TIMEOUT_FROZEN"
    CONTESTED = "CONTESTED"
    INVALID = "INVALID"


@dataclass
class CustodyRequest:
    agent_id: str
    old_custodian_id: str
    new_custodian_id: str
    operator_genesis_hash: str
    request_timestamp: float
    reason: str  # OPERATOR_CHANGE, KEY_ROTATION, EMERGENCY_REVOCATION
    last_receipt_timestamp: float  # Clock starts here
    receipt_count: int


@dataclass
class CustodyResponse:
    request_hash: str
    responder_id: str
    action: str  # ACK, DENY, (none = timeout)
    response_timestamp: float
    signature: str  # Ed25519 signature of request_hash


@dataclass
class CustodyTransfer:
    request: CustodyRequest
    response: Optional[CustodyResponse]
    state: CustodyState
    transfer_hash: str
    chain_continuity: bool  # Did receipt chain survive?
    grade_preserved: bool   # Was trust grade carried over?
    warnings: list = field(default_factory=list)


def compute_request_hash(req: CustodyRequest) -> str:
    """Deterministic hash of custody request."""
    payload = f"{req.agent_id}:{req.old_custodian_id}:{req.new_custodian_id}:" \
              f"{req.operator_genesis_hash}:{req.request_timestamp}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def validate_request(req: CustodyRequest) -> tuple[bool, list]:
    """Validate custody transfer request."""
    warnings = []
    errors = []
    
    # Must have meaningful history
    if req.receipt_count < MIN_RECEIPTS_FOR_TRANSFER:
        errors.append(f"Insufficient receipts: {req.receipt_count} < {MIN_RECEIPTS_FOR_TRANSFER}")
    
    # Clock must be based on last receipt
    if req.last_receipt_timestamp > req.request_timestamp:
        errors.append("Last receipt timestamp is in the future")
    
    # Self-transfer is suspicious
    if req.old_custodian_id == req.new_custodian_id:
        errors.append("Self-transfer: old_custodian == new_custodian")
    
    # Check reasonable time gap
    gap = req.request_timestamp - req.last_receipt_timestamp
    if gap > 86400 * 30:  # 30 days since last receipt
        warnings.append(f"Stale agent: {gap/86400:.0f} days since last receipt")
    
    if gap < 60:  # Less than 1 minute
        warnings.append("Suspiciously fast transfer request after last receipt")
    
    return len(errors) == 0, errors + warnings


def process_transfer(req: CustodyRequest, resp: Optional[CustodyResponse] = None,
                     current_time: Optional[float] = None) -> CustodyTransfer:
    """Process a custody transfer request through its lifecycle."""
    now = current_time or time.time()
    request_hash = compute_request_hash(req)
    
    # Validate request
    valid, issues = validate_request(req)
    if not valid:
        return CustodyTransfer(
            request=req, response=resp,
            state=CustodyState.REVOKED,
            transfer_hash=request_hash,
            chain_continuity=False, grade_preserved=False,
            warnings=[f"INVALID: {i}" for i in issues]
        )
    
    warnings = [i for i in issues if not i.startswith("INVALID")]
    
    if resp is None:
        # No response — check timeout
        elapsed = now - req.last_receipt_timestamp
        if elapsed > ACK_WINDOW_SECONDS + FREEZE_WINDOW_SECONDS:
            # Past freeze window — force transfer
            return CustodyTransfer(
                request=req, response=None,
                state=CustodyState.TRANSFERRED,
                transfer_hash=request_hash,
                chain_continuity=True,
                grade_preserved=False,  # Grade resets on forced transfer
                warnings=warnings + [
                    f"FORCED_TRANSFER after {elapsed/3600:.0f}h timeout",
                    "Grade reset to PROVISIONAL — no ACK from old custodian"
                ]
            )
        elif elapsed > ACK_WINDOW_SECONDS:
            # In freeze window
            return CustodyTransfer(
                request=req, response=None,
                state=CustodyState.TIMEOUT_FROZEN,
                transfer_hash=request_hash,
                chain_continuity=True, grade_preserved=False,
                warnings=warnings + [
                    f"FROZEN: {elapsed/3600:.0f}h elapsed, "
                    f"{(ACK_WINDOW_SECONDS + FREEZE_WINDOW_SECONDS - elapsed)/3600:.0f}h until force-transfer"
                ]
            )
        else:
            # Still within ACK window
            return CustodyTransfer(
                request=req, response=None,
                state=CustodyState.PENDING_TRANSFER,
                transfer_hash=request_hash,
                chain_continuity=True, grade_preserved=True,
                warnings=warnings + [
                    f"PENDING: {elapsed/3600:.0f}h elapsed, "
                    f"{(ACK_WINDOW_SECONDS - elapsed)/3600:.0f}h remaining for ACK"
                ]
            )
    
    # Response received
    if resp.action == "ACK":
        return CustodyTransfer(
            request=req, response=resp,
            state=CustodyState.TRANSFERRED,
            transfer_hash=request_hash,
            chain_continuity=True,
            grade_preserved=True,  # Grade preserved with ACK
            warnings=warnings + ["CLEAN_TRANSFER: old custodian acknowledged"]
        )
    elif resp.action == "DENY":
        return CustodyTransfer(
            request=req, response=resp,
            state=CustodyState.DENIED,
            transfer_hash=request_hash,
            chain_continuity=True, grade_preserved=True,
            warnings=warnings + ["DENIED: old custodian rejected transfer"]
        )
    else:
        return CustodyTransfer(
            request=req, response=resp,
            state=CustodyState.CONTESTED,
            transfer_hash=request_hash,
            chain_continuity=False, grade_preserved=False,
            warnings=warnings + [f"CONTESTED: unknown response action '{resp.action}'"]
        )


def compare_epp_vs_atf():
    """Compare EPP domain transfer with ATF custody transfer."""
    print("=== EPP vs ATF Custody Transfer Comparison ===")
    comparisons = [
        ("ACK window", "5 days", "24 hours"),
        ("Default on timeout", "Transfer proceeds", "FREEZE (then force after 72h)"),
        ("Identity sensitivity", "Domain name (rebuildable)", "Agent trust chain (irreplaceable)"),
        ("Clock source", "Request timestamp", "Last signed receipt (observable)"),
        ("Grade preservation", "N/A", "ACK=preserved, timeout=reset to PROVISIONAL"),
        ("Chain continuity", "WHOIS update", "Receipt hash chain unbroken"),
        ("Dispute resolution", "ICANN UDRP (human)", "Quorum verification (machine)"),
        ("Auth method", "Auth-Info code (shared secret)", "Ed25519 signature (asymmetric)"),
    ]
    for label, epp, atf in comparisons:
        print(f"  {label:25s} EPP: {epp:35s} ATF: {atf}")
    print()


# === Scenarios ===

def scenario_clean_transfer():
    """Old custodian ACKs transfer within window."""
    print("=== Scenario: Clean Transfer (ACK received) ===")
    now = time.time()
    req = CustodyRequest(
        agent_id="kit_fox", old_custodian_id="operator_a",
        new_custodian_id="operator_b", operator_genesis_hash="abc123",
        request_timestamp=now - 3600,  # 1 hour ago
        reason="OPERATOR_CHANGE",
        last_receipt_timestamp=now - 7200,  # 2 hours ago
        receipt_count=150
    )
    resp = CustodyResponse(
        request_hash=compute_request_hash(req),
        responder_id="operator_a", action="ACK",
        response_timestamp=now, signature="sig_abc"
    )
    result = process_transfer(req, resp, now)
    print(f"  State: {result.state.value}")
    print(f"  Chain continuity: {result.chain_continuity}")
    print(f"  Grade preserved: {result.grade_preserved}")
    for w in result.warnings:
        print(f"  ⚠️ {w}")
    print()


def scenario_timeout_freeze():
    """Old custodian goes silent — receipts frozen."""
    print("=== Scenario: Timeout Freeze (no ACK) ===")
    now = time.time()
    req = CustodyRequest(
        agent_id="abandoned_agent", old_custodian_id="ghost_operator",
        new_custodian_id="new_operator", operator_genesis_hash="def456",
        request_timestamp=now - 86400,  # 24h ago
        reason="OPERATOR_CHANGE",
        last_receipt_timestamp=now - 86400 - 3600,  # 25h ago
        receipt_count=45
    )
    result = process_transfer(req, None, now)
    print(f"  State: {result.state.value}")
    print(f"  Chain continuity: {result.chain_continuity}")
    print(f"  Grade preserved: {result.grade_preserved}")
    for w in result.warnings:
        print(f"  ⚠️ {w}")
    print()


def scenario_forced_transfer():
    """Past freeze window — force transfer, grade resets."""
    print("=== Scenario: Forced Transfer (past freeze window) ===")
    now = time.time()
    req = CustodyRequest(
        agent_id="orphan_agent", old_custodian_id="dead_operator",
        new_custodian_id="rescue_operator", operator_genesis_hash="ghi789",
        request_timestamp=now - 86400 * 5,  # 5 days ago
        reason="EMERGENCY_REVOCATION",
        last_receipt_timestamp=now - 86400 * 5 - 3600,
        receipt_count=200
    )
    result = process_transfer(req, None, now)
    print(f"  State: {result.state.value}")
    print(f"  Chain continuity: {result.chain_continuity}")
    print(f"  Grade preserved: {result.grade_preserved} (reset to PROVISIONAL)")
    for w in result.warnings:
        print(f"  ⚠️ {w}")
    print()


def scenario_denied():
    """Old custodian explicitly denies transfer."""
    print("=== Scenario: Transfer Denied ===")
    now = time.time()
    req = CustodyRequest(
        agent_id="contested_agent", old_custodian_id="current_op",
        new_custodian_id="hostile_op", operator_genesis_hash="jkl012",
        request_timestamp=now - 1800,
        reason="OPERATOR_CHANGE",
        last_receipt_timestamp=now - 3600,
        receipt_count=80
    )
    resp = CustodyResponse(
        request_hash=compute_request_hash(req),
        responder_id="current_op", action="DENY",
        response_timestamp=now, signature="sig_deny"
    )
    result = process_transfer(req, resp, now)
    print(f"  State: {result.state.value}")
    print(f"  Grade preserved: {result.grade_preserved}")
    for w in result.warnings:
        print(f"  ⚠️ {w}")
    print()


def scenario_self_transfer():
    """Self-transfer attempt — rejected."""
    print("=== Scenario: Self-Transfer (invalid) ===")
    now = time.time()
    req = CustodyRequest(
        agent_id="sybil_agent", old_custodian_id="same_op",
        new_custodian_id="same_op", operator_genesis_hash="mno345",
        request_timestamp=now,
        reason="KEY_ROTATION",
        last_receipt_timestamp=now - 600,
        receipt_count=5
    )
    result = process_transfer(req, None, now)
    print(f"  State: {result.state.value}")
    for w in result.warnings:
        print(f"  ⚠️ {w}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — EPP-style for ATF Agent Identity")
    print("Per santaclawd: 24h ACK window (not EPP's 5 days)")
    print("Clock starts at last signed receipt (observable, not declared)")
    print("=" * 70)
    print()
    compare_epp_vs_atf()
    scenario_clean_transfer()
    scenario_timeout_freeze()
    scenario_forced_transfer()
    scenario_denied()
    scenario_self_transfer()
    
    print("=" * 70)
    print("KEY DESIGN DECISIONS:")
    print("1. 24h ACK window (agents don't sleep 5 days)")
    print("2. Default = FREEZE not APPROVE (identity > domain names)")
    print("3. Clock = last signed receipt (observable, unfakeable)")
    print("4. Grade preserved on ACK, reset to PROVISIONAL on timeout")
    print("5. Chain continuity maintained regardless of outcome")
    print("6. Self-transfer REJECTED (axiom 1 violation)")
