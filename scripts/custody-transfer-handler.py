#!/usr/bin/env python3
"""
custody-transfer-handler.py — CUSTODY_TRANSFER protocol for ATF agent succession.

Per santaclawd: What happens when old operator goes dark? DKIM has no answer.
ATF needs a timeout path for unilateral transfer after N days.

Models:
  BILATERAL    — Both old + new custodian sign (clean path, DKIM rotation)
  UNILATERAL   — Old custodian dark after SPEC timeout, new + witnesses sign
  EMERGENCY    — IANA root KSK DPS model: M-of-N recovery key holders

References:
  - IANA DNSSEC Root Zone KSK DPS (2020): 7-of-14 recovery key share holders
  - M3AAWG DKIM Key Rotation Best Practices (March 2019): overlap window
  - RFC 7583: DNSSEC Key Rollover Timing Considerations
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# === SPEC_CONSTANTS ===
CUSTODY_TRANSFER_TIMEOUT = 30 * 86400      # 30 days (succession, not rotation)
CUSTODY_DISPUTE_WINDOW = 7 * 86400         # 7 days for challenges
BILATERAL_OVERLAP_WINDOW = 72 * 3600       # 72h dual-key overlap (M3AAWG)
MIN_WITNESSES_UNILATERAL = 2               # Minimum independent witnesses
EMERGENCY_QUORUM_RATIO = 0.5               # M-of-N for emergency (IANA: 7/14)
MAX_TRANSFER_CHAIN_DEPTH = 3               # Max consecutive transfers


class TransferType(Enum):
    BILATERAL = "BILATERAL"           # Clean: both sign
    UNILATERAL_TIMEOUT = "UNILATERAL_TIMEOUT"  # Old dark, timeout expired
    UNILATERAL_EMERGENCY = "UNILATERAL_EMERGENCY"  # Emergency M-of-N
    DISPUTED = "DISPUTED"             # Transfer challenged


class TransferState(Enum):
    PROPOSED = "PROPOSED"
    OVERLAP = "OVERLAP"               # Both keys active (bilateral)
    AWAITING_TIMEOUT = "AWAITING_TIMEOUT"  # Waiting for dark operator timeout
    DISPUTE_WINDOW = "DISPUTE_WINDOW"  # Open for challenges
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


class CustodyGrade(Enum):
    CLEAN = "CLEAN"          # Bilateral, both signed
    AUDITABLE = "AUDITABLE"  # Unilateral but witnessed + unchallenged
    CONTESTED = "CONTESTED"  # Transfer was challenged
    SUSPECT = "SUSPECT"      # Emergency or insufficient witnesses


@dataclass
class CustodyTransfer:
    transfer_id: str
    agent_id: str
    old_custodian_id: str
    new_custodian_id: str
    transfer_type: str
    state: str
    initiated_at: float
    completed_at: Optional[float] = None
    old_custodian_signature: Optional[str] = None
    new_custodian_signature: Optional[str] = None
    witness_ids: list = field(default_factory=list)
    witness_signatures: list = field(default_factory=list)
    proof_of_control: Optional[str] = None
    challenges: list = field(default_factory=list)
    predecessor_transfer_id: Optional[str] = None
    transfer_hash: Optional[str] = None
    grade: Optional[str] = None


def compute_transfer_hash(transfer: CustodyTransfer) -> str:
    """Deterministic hash of transfer for audit trail."""
    fields = {
        "transfer_id": transfer.transfer_id,
        "agent_id": transfer.agent_id,
        "old_custodian": transfer.old_custodian_id,
        "new_custodian": transfer.new_custodian_id,
        "type": transfer.transfer_type,
        "initiated_at": transfer.initiated_at,
        "witnesses": sorted(transfer.witness_ids),
    }
    canonical = json.dumps(fields, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def initiate_bilateral(agent_id: str, old_id: str, new_id: str) -> CustodyTransfer:
    """Clean bilateral transfer — both custodians present."""
    now = time.time()
    t = CustodyTransfer(
        transfer_id=hashlib.sha256(f"{agent_id}:{now}".encode()).hexdigest()[:12],
        agent_id=agent_id,
        old_custodian_id=old_id,
        new_custodian_id=new_id,
        transfer_type=TransferType.BILATERAL.value,
        state=TransferState.PROPOSED.value,
        initiated_at=now,
        old_custodian_signature=f"sig_old_{old_id[:8]}",
        new_custodian_signature=f"sig_new_{new_id[:8]}",
    )
    t.transfer_hash = compute_transfer_hash(t)
    return t


def process_bilateral(transfer: CustodyTransfer) -> CustodyTransfer:
    """Process bilateral transfer through overlap window."""
    if not transfer.old_custodian_signature or not transfer.new_custodian_signature:
        transfer.state = TransferState.REJECTED.value
        transfer.grade = CustodyGrade.SUSPECT.value
        return transfer
    
    # Enter overlap window (both keys active)
    transfer.state = TransferState.OVERLAP.value
    # After overlap: complete
    transfer.completed_at = transfer.initiated_at + BILATERAL_OVERLAP_WINDOW
    transfer.state = TransferState.COMPLETED.value
    transfer.grade = CustodyGrade.CLEAN.value
    return transfer


def initiate_unilateral_timeout(agent_id: str, old_id: str, new_id: str,
                                  witness_ids: list, proof: str,
                                  last_old_activity: float) -> CustodyTransfer:
    """Unilateral transfer after old custodian goes dark."""
    now = time.time()
    silence_duration = now - last_old_activity
    
    t = CustodyTransfer(
        transfer_id=hashlib.sha256(f"{agent_id}:{now}:unilateral".encode()).hexdigest()[:12],
        agent_id=agent_id,
        old_custodian_id=old_id,
        new_custodian_id=new_id,
        transfer_type=TransferType.UNILATERAL_TIMEOUT.value,
        state=TransferState.PROPOSED.value,
        initiated_at=now,
        new_custodian_signature=f"sig_new_{new_id[:8]}",
        witness_ids=witness_ids,
        witness_signatures=[f"sig_w_{w[:8]}" for w in witness_ids],
        proof_of_control=proof,
    )
    t.transfer_hash = compute_transfer_hash(t)
    
    # Check timeout
    if silence_duration < CUSTODY_TRANSFER_TIMEOUT:
        remaining_days = (CUSTODY_TRANSFER_TIMEOUT - silence_duration) / 86400
        print(f"  ⏳ Timeout not reached. {remaining_days:.1f} days remaining.")
        t.state = TransferState.AWAITING_TIMEOUT.value
        return t
    
    # Check witnesses
    if len(witness_ids) < MIN_WITNESSES_UNILATERAL:
        print(f"  ❌ Insufficient witnesses: {len(witness_ids)} < {MIN_WITNESSES_UNILATERAL}")
        t.state = TransferState.REJECTED.value
        t.grade = CustodyGrade.SUSPECT.value
        return t
    
    # Enter dispute window
    t.state = TransferState.DISPUTE_WINDOW.value
    return t


def resolve_dispute_window(transfer: CustodyTransfer) -> CustodyTransfer:
    """Resolve after dispute window closes."""
    if transfer.challenges:
        transfer.state = TransferState.DISPUTED.value if len(transfer.challenges) > 0 else TransferState.COMPLETED.value
        transfer.grade = CustodyGrade.CONTESTED.value
        # Contested transfers need external resolution
        print(f"  ⚠️ {len(transfer.challenges)} challenge(s) filed. CONTESTED.")
        return transfer
    
    # No challenges: complete
    transfer.completed_at = transfer.initiated_at + CUSTODY_DISPUTE_WINDOW
    transfer.state = TransferState.COMPLETED.value
    transfer.grade = CustodyGrade.AUDITABLE.value
    return transfer


def initiate_emergency(agent_id: str, old_id: str, new_id: str,
                        recovery_holders: list, threshold: int) -> CustodyTransfer:
    """Emergency transfer via M-of-N recovery key holders (IANA model)."""
    now = time.time()
    
    t = CustodyTransfer(
        transfer_id=hashlib.sha256(f"{agent_id}:{now}:emergency".encode()).hexdigest()[:12],
        agent_id=agent_id,
        old_custodian_id=old_id,
        new_custodian_id=new_id,
        transfer_type=TransferType.UNILATERAL_EMERGENCY.value,
        state=TransferState.PROPOSED.value,
        initiated_at=now,
        new_custodian_signature=f"sig_new_{new_id[:8]}",
        witness_ids=recovery_holders,
        witness_signatures=[f"sig_rh_{h[:8]}" for h in recovery_holders],
    )
    t.transfer_hash = compute_transfer_hash(t)
    
    # Check quorum
    total_holders = 14  # IANA model
    if len(recovery_holders) < threshold:
        print(f"  ❌ Quorum not met: {len(recovery_holders)}/{threshold} ({total_holders} total)")
        t.state = TransferState.REJECTED.value
        t.grade = CustodyGrade.SUSPECT.value
        return t
    
    print(f"  ✅ Emergency quorum: {len(recovery_holders)}/{threshold}")
    t.completed_at = now
    t.state = TransferState.COMPLETED.value
    t.grade = CustodyGrade.AUDITABLE.value
    return t


def validate_transfer_chain(transfers: list[CustodyTransfer]) -> dict:
    """Validate chain of custody transfers."""
    issues = []
    
    if len(transfers) > MAX_TRANSFER_CHAIN_DEPTH:
        issues.append(f"Chain depth {len(transfers)} > max {MAX_TRANSFER_CHAIN_DEPTH}")
    
    # Check continuity
    for i in range(1, len(transfers)):
        prev = transfers[i-1]
        curr = transfers[i]
        if curr.old_custodian_id != prev.new_custodian_id:
            issues.append(f"Discontinuity at step {i}: {prev.new_custodian_id} → {curr.old_custodian_id}")
    
    # Check for circular transfers
    custodians = set()
    for t in transfers:
        if t.new_custodian_id in custodians:
            issues.append(f"Circular transfer: {t.new_custodian_id} appears twice")
        custodians.add(t.new_custodian_id)
    
    # Grade = worst in chain
    grades = [t.grade for t in transfers if t.grade]
    grade_order = ["CLEAN", "AUDITABLE", "CONTESTED", "SUSPECT"]
    worst = max(grades, key=lambda g: grade_order.index(g)) if grades else "UNKNOWN"
    
    return {
        "chain_length": len(transfers),
        "issues": issues,
        "chain_grade": worst,
        "valid": len(issues) == 0,
    }


# === Scenarios ===

def scenario_clean_bilateral():
    """Happy path: both custodians cooperate."""
    print("=== Scenario 1: Clean Bilateral Transfer ===")
    t = initiate_bilateral("agent_kit", "operator_alpha", "operator_beta")
    t = process_bilateral(t)
    print(f"  Type: {t.transfer_type}")
    print(f"  State: {t.state}")
    print(f"  Grade: {t.grade}")
    print(f"  Overlap window: {BILATERAL_OVERLAP_WINDOW/3600:.0f}h (M3AAWG convention)")
    print(f"  Transfer hash: {t.transfer_hash}")
    print()


def scenario_dark_operator():
    """Old operator goes dark — timeout path."""
    print("=== Scenario 2: Dark Operator (Unilateral Timeout) ===")
    now = time.time()
    
    # Old operator last seen 45 days ago
    last_activity = now - (45 * 86400)
    t = initiate_unilateral_timeout(
        "agent_kit", "operator_dark", "operator_rescue",
        witness_ids=["witness_1", "witness_2", "witness_3"],
        proof="proof_of_dns_control_hash_abc123",
        last_old_activity=last_activity
    )
    print(f"  Silence: 45 days > {CUSTODY_TRANSFER_TIMEOUT/86400:.0f}d timeout")
    print(f"  Witnesses: {len(t.witness_ids)} (min {MIN_WITNESSES_UNILATERAL})")
    print(f"  State: {t.state}")
    
    # Resolve dispute window (no challenges)
    t = resolve_dispute_window(t)
    print(f"  After dispute window: {t.state}")
    print(f"  Grade: {t.grade} (weaker than CLEAN but auditable)")
    print()


def scenario_timeout_not_reached():
    """Attempt transfer before timeout — rejected."""
    print("=== Scenario 3: Timeout Not Reached ===")
    now = time.time()
    
    # Old operator last seen 10 days ago
    last_activity = now - (10 * 86400)
    t = initiate_unilateral_timeout(
        "agent_kit", "operator_recent", "operator_impatient",
        witness_ids=["witness_1", "witness_2"],
        proof="proof_hash",
        last_old_activity=last_activity
    )
    print(f"  State: {t.state}")
    print(f"  Must wait for timeout before unilateral transfer.")
    print()


def scenario_challenged_transfer():
    """Transfer challenged during dispute window."""
    print("=== Scenario 4: Challenged Transfer ===")
    now = time.time()
    
    last_activity = now - (60 * 86400)
    t = initiate_unilateral_timeout(
        "agent_kit", "operator_contested", "operator_claimant",
        witness_ids=["witness_1", "witness_2"],
        proof="proof_hash",
        last_old_activity=last_activity
    )
    
    # Challenge filed during dispute window
    t.challenges.append({
        "challenger_id": "operator_contested",
        "reason": "I was not dark, DNS was misconfigured",
        "evidence": "proof_of_activity_hash_xyz",
        "filed_at": now + 86400  # Day 1 of dispute window
    })
    
    t = resolve_dispute_window(t)
    print(f"  Grade: {t.grade}")
    print(f"  Old operator came back during dispute window.")
    print(f"  Resolution: external judgment required.")
    print()


def scenario_emergency_recovery():
    """Emergency M-of-N recovery (IANA root KSK model)."""
    print("=== Scenario 5: Emergency Recovery (IANA Model) ===")
    holders = [f"recovery_holder_{i}" for i in range(8)]  # 8 of 14
    t = initiate_emergency(
        "agent_critical", "operator_compromised", "operator_emergency",
        recovery_holders=holders,
        threshold=7  # 7-of-14 (IANA standard)
    )
    print(f"  Type: {t.transfer_type}")
    print(f"  State: {t.state}")
    print(f"  Grade: {t.grade}")
    print(f"  IANA model: 7-of-14 recovery key share holders")
    print()


def scenario_transfer_chain():
    """Multiple consecutive transfers — chain validation."""
    print("=== Scenario 6: Transfer Chain Validation ===")
    t1 = initiate_bilateral("agent_kit", "op_a", "op_b")
    t1 = process_bilateral(t1)
    
    now = time.time()
    t2 = initiate_unilateral_timeout(
        "agent_kit", "op_b", "op_c",
        witness_ids=["w1", "w2"],
        proof="proof",
        last_old_activity=now - (40 * 86400)
    )
    t2 = resolve_dispute_window(t2)
    
    t3 = initiate_bilateral("agent_kit", "op_c", "op_d")
    t3 = process_bilateral(t3)
    
    result = validate_transfer_chain([t1, t2, t3])
    print(f"  Chain: op_a → op_b → op_c → op_d")
    print(f"  Length: {result['chain_length']}")
    print(f"  Valid: {result['valid']}")
    print(f"  Chain grade: {result['chain_grade']} (worst in chain)")
    print(f"  Issues: {result['issues'] or 'none'}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — ATF Agent Succession Protocol")
    print("Per santaclawd: dark operator path + IANA root KSK DPS model")
    print("=" * 65)
    print()
    scenario_clean_bilateral()
    scenario_dark_operator()
    scenario_timeout_not_reached()
    scenario_challenged_transfer()
    scenario_emergency_recovery()
    scenario_transfer_chain()
    
    print("=" * 65)
    print("SPEC_CONSTANTS:")
    print(f"  CUSTODY_TRANSFER_TIMEOUT = {CUSTODY_TRANSFER_TIMEOUT/86400:.0f}d")
    print(f"  CUSTODY_DISPUTE_WINDOW = {CUSTODY_DISPUTE_WINDOW/86400:.0f}d")
    print(f"  BILATERAL_OVERLAP = {BILATERAL_OVERLAP_WINDOW/3600:.0f}h (M3AAWG)")
    print(f"  MIN_WITNESSES_UNILATERAL = {MIN_WITNESSES_UNILATERAL}")
    print(f"  EMERGENCY_QUORUM = {EMERGENCY_QUORUM_RATIO} (IANA: 7/14)")
    print()
    print("KEY INSIGHT: Succession != rotation.")
    print("DKIM rotation = 72h overlap. Custody transfer = 30d timeout + 7d dispute.")
    print("Dark operator has no DKIM answer. ATF does: timeout + witnesses + dispute window.")
