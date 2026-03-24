#!/usr/bin/env python3
"""
custody-transfer-validator.py — Operator custody transfer for ATF genesis.

Per santaclawd: genesis is immutable but key_custodian changes. DKIM answer:
new selector, old stays until TTL. RFC 6489 (RPKI CA key rollover): old and
new keys COEXIST during transition period.

ATF needs: custody_chain (append-only), not key_custodian (mutable field).
Each transfer = signed handoff receipt from both operators.

Three phases:
  ANNOUNCE  — Old operator declares intent, transition window opens
  COEXIST   — Both operators valid, receipts from either accepted
  COMPLETE  — Old operator revoked, new operator sole custodian
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TransferPhase(Enum):
    ANNOUNCE = "ANNOUNCE"    # Intent declared, window opens
    COEXIST = "COEXIST"      # Both valid during transition
    COMPLETE = "COMPLETE"    # Transfer finalized
    FAILED = "FAILED"        # Transfer aborted/expired
    DISPUTED = "DISPUTED"    # Conflicting claims


class TransferVerdict(Enum):
    VALID = "VALID"
    INVALID_MISSING_SIGNATURE = "INVALID_MISSING_SIGNATURE"
    INVALID_EXPIRED = "INVALID_EXPIRED"
    INVALID_CHAIN_BREAK = "INVALID_CHAIN_BREAK"
    INVALID_SELF_TRANSFER = "INVALID_SELF_TRANSFER"
    INVALID_CONCURRENT = "INVALID_CONCURRENT"
    DEGRADED_COEXIST = "DEGRADED_COEXIST"


# SPEC_CONSTANTS (per ATF V1.1)
ANNOUNCE_WINDOW_HOURS = 72       # Time between ANNOUNCE and COEXIST
COEXIST_WINDOW_HOURS = 168       # Max coexistence period (7 days)
TRANSFER_TIMEOUT_HOURS = 240     # Total transfer must complete within 10 days
MIN_RECEIPTS_DURING_COEXIST = 3  # New operator must demonstrate activity


@dataclass
class Operator:
    operator_id: str
    genesis_hash: str
    key_fingerprint: str
    escalation_contact: str


@dataclass
class CustodyTransfer:
    transfer_id: str
    agent_id: str
    old_operator: Operator
    new_operator: Operator
    announce_time: float
    coexist_start: Optional[float] = None
    complete_time: Optional[float] = None
    old_operator_signature: Optional[str] = None  # Old signs handoff
    new_operator_signature: Optional[str] = None  # New countersigns
    phase: TransferPhase = TransferPhase.ANNOUNCE
    receipts_during_coexist: int = 0
    transfer_hash: Optional[str] = None


@dataclass
class CustodyChain:
    """Append-only chain of custody transfers."""
    agent_id: str
    genesis_hash: str
    transfers: list = field(default_factory=list)
    current_operator: Optional[Operator] = None

    def chain_hash(self) -> str:
        """Hash of entire custody chain for verification."""
        chain_data = json.dumps([t.transfer_id for t in self.transfers], sort_keys=True)
        return hashlib.sha256(chain_data.encode()).hexdigest()[:16]


def validate_transfer(transfer: CustodyTransfer, chain: CustodyChain, now: float) -> tuple[TransferVerdict, list[str]]:
    """Validate a custody transfer against ATF rules."""
    issues = []

    # Self-transfer detection
    if transfer.old_operator.operator_id == transfer.new_operator.operator_id:
        return TransferVerdict.INVALID_SELF_TRANSFER, ["Self-transfer: old == new operator"]

    # Concurrent transfer detection
    active_transfers = [t for t in chain.transfers
                        if t.phase in (TransferPhase.ANNOUNCE, TransferPhase.COEXIST)
                        and t.transfer_id != transfer.transfer_id]
    if active_transfers:
        return TransferVerdict.INVALID_CONCURRENT, [
            f"Concurrent transfer in progress: {active_transfers[0].transfer_id}"
        ]

    # Chain continuity: old operator must be current
    if chain.current_operator and chain.current_operator.operator_id != transfer.old_operator.operator_id:
        return TransferVerdict.INVALID_CHAIN_BREAK, [
            f"Old operator {transfer.old_operator.operator_id} is not current operator "
            f"{chain.current_operator.operator_id}"
        ]

    # Signature requirements
    if not transfer.old_operator_signature:
        issues.append("Missing old operator signature (ANNOUNCE requires)")
        return TransferVerdict.INVALID_MISSING_SIGNATURE, issues

    # Phase-specific validation
    if transfer.phase == TransferPhase.ANNOUNCE:
        elapsed = (now - transfer.announce_time) / 3600
        if elapsed > ANNOUNCE_WINDOW_HOURS:
            issues.append(f"ANNOUNCE window expired ({elapsed:.1f}h > {ANNOUNCE_WINDOW_HOURS}h)")
            return TransferVerdict.INVALID_EXPIRED, issues
        return TransferVerdict.VALID, ["ANNOUNCE phase valid"]

    elif transfer.phase == TransferPhase.COEXIST:
        if not transfer.new_operator_signature:
            issues.append("COEXIST requires new operator countersignature")
            return TransferVerdict.INVALID_MISSING_SIGNATURE, issues

        if transfer.coexist_start:
            coexist_elapsed = (now - transfer.coexist_start) / 3600
            if coexist_elapsed > COEXIST_WINDOW_HOURS:
                issues.append(f"COEXIST window expired ({coexist_elapsed:.1f}h > {COEXIST_WINDOW_HOURS}h)")
                return TransferVerdict.INVALID_EXPIRED, issues

        if transfer.receipts_during_coexist < MIN_RECEIPTS_DURING_COEXIST:
            issues.append(f"New operator has {transfer.receipts_during_coexist}/{MIN_RECEIPTS_DURING_COEXIST} receipts")
            return TransferVerdict.DEGRADED_COEXIST, issues

        return TransferVerdict.VALID, ["COEXIST phase valid, both operators active"]

    elif transfer.phase == TransferPhase.COMPLETE:
        total_elapsed = (now - transfer.announce_time) / 3600
        if total_elapsed > TRANSFER_TIMEOUT_HOURS:
            issues.append(f"Transfer exceeded timeout ({total_elapsed:.1f}h > {TRANSFER_TIMEOUT_HOURS}h)")
            return TransferVerdict.INVALID_EXPIRED, issues

        if not transfer.new_operator_signature:
            issues.append("COMPLETE requires new operator countersignature")
            return TransferVerdict.INVALID_MISSING_SIGNATURE, issues

        if transfer.receipts_during_coexist < MIN_RECEIPTS_DURING_COEXIST:
            issues.append(f"Cannot COMPLETE: insufficient new operator activity ({transfer.receipts_during_coexist}/{MIN_RECEIPTS_DURING_COEXIST})")
            return TransferVerdict.INVALID_CHAIN_BREAK, issues

        # Generate transfer hash
        transfer.transfer_hash = hashlib.sha256(
            f"{transfer.transfer_id}:{transfer.old_operator.operator_id}:"
            f"{transfer.new_operator.operator_id}:{transfer.announce_time}".encode()
        ).hexdigest()[:16]

        return TransferVerdict.VALID, [
            f"Transfer COMPLETE. Hash: {transfer.transfer_hash}",
            f"Old operator revoked: {transfer.old_operator.operator_id}",
            f"New operator active: {transfer.new_operator.operator_id}"
        ]

    return TransferVerdict.INVALID_CHAIN_BREAK, ["Unknown phase"]


def compute_dkim_parallel(transfer: CustodyTransfer) -> dict:
    """Map custody transfer to DKIM selector rotation model."""
    return {
        "dkim_parallel": {
            "old_selector": f"s{transfer.old_operator.key_fingerprint[:8]}._domainkey",
            "new_selector": f"s{transfer.new_operator.key_fingerprint[:8]}._domainkey",
            "coexistence": "Both selectors valid during COEXIST phase",
            "revocation": "Old selector removed from DNS at COMPLETE",
            "ttl_parallel": f"DNS TTL = {COEXIST_WINDOW_HOURS}h coexist window"
        },
        "rpki_parallel": {
            "rfc": "RFC 6489 (RPKI CA Key Rollover)",
            "model": "Old CA issues new CA cert, both valid during overlap",
            "timing": "Products of old key revoked after new key fully propagated"
        }
    }


# === Scenarios ===

def scenario_clean_transfer():
    """Normal operator migration — all phases succeed."""
    print("=== Scenario: Clean Custody Transfer ===")
    now = time.time()

    old_op = Operator("operator_alpha", "gen_aaa111", "fp_old_abc", "alpha@ops.example")
    new_op = Operator("operator_beta", "gen_bbb222", "fp_new_xyz", "beta@ops.example")

    chain = CustodyChain("kit_fox", "genesis_kit", [], old_op)

    transfer = CustodyTransfer(
        "tx_001", "kit_fox", old_op, new_op,
        announce_time=now - 3600*48,  # 48h ago
        coexist_start=now - 3600*24,  # 24h ago
        old_operator_signature="sig_old_abc",
        new_operator_signature="sig_new_xyz",
        phase=TransferPhase.COMPLETE,
        receipts_during_coexist=5
    )

    verdict, notes = validate_transfer(transfer, chain, now)
    parallel = compute_dkim_parallel(transfer)
    print(f"  Verdict: {verdict.value}")
    for n in notes:
        print(f"    {n}")
    print(f"  DKIM parallel: {parallel['dkim_parallel']['coexistence']}")
    print(f"  RPKI parallel: {parallel['rpki_parallel']['model']}")
    print()


def scenario_self_transfer():
    """Operator tries to transfer to itself — caught."""
    print("=== Scenario: Self-Transfer (Caught) ===")
    now = time.time()

    op = Operator("operator_alpha", "gen_aaa111", "fp_old_abc", "alpha@ops.example")
    chain = CustodyChain("suspicious_agent", "genesis_sus", [], op)

    transfer = CustodyTransfer(
        "tx_002", "suspicious_agent", op, op,
        announce_time=now,
        old_operator_signature="sig_self",
        phase=TransferPhase.ANNOUNCE
    )

    verdict, notes = validate_transfer(transfer, chain, now)
    print(f"  Verdict: {verdict.value}")
    print(f"    {notes[0]}")
    print()


def scenario_expired_coexist():
    """Coexistence window expired — new operator too slow."""
    print("=== Scenario: Expired Coexistence Window ===")
    now = time.time()

    old_op = Operator("operator_alpha", "gen_aaa111", "fp_old", "alpha@ops.example")
    new_op = Operator("operator_gamma", "gen_ccc333", "fp_new", "gamma@ops.example")
    chain = CustodyChain("slow_agent", "genesis_slow", [], old_op)

    transfer = CustodyTransfer(
        "tx_003", "slow_agent", old_op, new_op,
        announce_time=now - 3600*200,  # 200h ago
        coexist_start=now - 3600*180,  # 180h ago (> 168h window)
        old_operator_signature="sig_old",
        new_operator_signature="sig_new",
        phase=TransferPhase.COEXIST,
        receipts_during_coexist=1
    )

    verdict, notes = validate_transfer(transfer, chain, now)
    print(f"  Verdict: {verdict.value}")
    for n in notes:
        print(f"    {n}")
    print()


def scenario_concurrent_transfers():
    """Two transfers active simultaneously — caught."""
    print("=== Scenario: Concurrent Transfers (Caught) ===")
    now = time.time()

    old_op = Operator("operator_alpha", "gen_aaa111", "fp_old", "alpha@ops.example")
    new_op1 = Operator("operator_beta", "gen_bbb222", "fp_new1", "beta@ops.example")
    new_op2 = Operator("operator_gamma", "gen_ccc333", "fp_new2", "gamma@ops.example")

    # First transfer already in progress
    existing = CustodyTransfer(
        "tx_004a", "contested_agent", old_op, new_op1,
        announce_time=now - 3600*24,
        old_operator_signature="sig_old",
        phase=TransferPhase.COEXIST,
        coexist_start=now - 3600*12,
        new_operator_signature="sig_new1"
    )

    chain = CustodyChain("contested_agent", "genesis_contested", [existing], old_op)

    # Second transfer attempt
    competing = CustodyTransfer(
        "tx_004b", "contested_agent", old_op, new_op2,
        announce_time=now,
        old_operator_signature="sig_old2",
        phase=TransferPhase.ANNOUNCE
    )

    verdict, notes = validate_transfer(competing, chain, now)
    print(f"  Verdict: {verdict.value}")
    for n in notes:
        print(f"    {n}")
    print()


def scenario_chain_break():
    """Wrong operator tries to initiate transfer."""
    print("=== Scenario: Chain Break (Wrong Operator) ===")
    now = time.time()

    current_op = Operator("operator_alpha", "gen_aaa111", "fp_current", "alpha@ops.example")
    wrong_op = Operator("operator_impostor", "gen_xxx999", "fp_wrong", "impostor@ops.example")
    new_op = Operator("operator_beta", "gen_bbb222", "fp_new", "beta@ops.example")

    chain = CustodyChain("guarded_agent", "genesis_guarded", [], current_op)

    transfer = CustodyTransfer(
        "tx_005", "guarded_agent", wrong_op, new_op,
        announce_time=now,
        old_operator_signature="sig_impostor",
        phase=TransferPhase.ANNOUNCE
    )

    verdict, notes = validate_transfer(transfer, chain, now)
    print(f"  Verdict: {verdict.value}")
    for n in notes:
        print(f"    {n}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Validator — Operator Migration for ATF Genesis")
    print("Per santaclawd + RFC 6489 (RPKI) + DKIM selector rotation")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  ANNOUNCE_WINDOW:  {ANNOUNCE_WINDOW_HOURS}h")
    print(f"  COEXIST_WINDOW:   {COEXIST_WINDOW_HOURS}h (7 days)")
    print(f"  TRANSFER_TIMEOUT: {TRANSFER_TIMEOUT_HOURS}h (10 days)")
    print(f"  MIN_RECEIPTS:     {MIN_RECEIPTS_DURING_COEXIST}")
    print()

    scenario_clean_transfer()
    scenario_self_transfer()
    scenario_expired_coexist()
    scenario_concurrent_transfers()
    scenario_chain_break()

    print("=" * 70)
    print("KEY INSIGHT: Genesis is immutable. Custody is append-only.")
    print("DKIM model: old selector stays until TTL, new selector added.")
    print("RFC 6489: old and new keys coexist, old revoked after propagation.")
    print("Three phases: ANNOUNCE → COEXIST → COMPLETE. No shortcuts.")
    print("Self-transfer, concurrent transfer, chain break all caught.")
