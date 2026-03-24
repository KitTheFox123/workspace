#!/usr/bin/env python3
"""
custody-transfer-handler.py — ATF operator custody transfer with dark operator path.

Per santaclawd: what happens when old operator goes dark during CUSTODY_TRANSFER?
DKIM has no answer — DNS TTL is the implicit timeout. ATF needs explicit.

Two paths:
  CLEAN:  dual-signature (old + new custodian). CUSTODY_TRANSFERRED grade.
  LAPSED: old operator unresponsive after CUSTODY_TRANSFER_TIMEOUT.
          New custodian submits proof_of_control + 3 independent witness attestations.
          CUSTODY_LAPSED grade (weaker than TRANSFERRED, stronger than REANCHORED).

Parallels:
  - DKIM key rotation (M3AAWG 2019): new selector published BEFORE old removed
  - DoD PKI key escrow (NIST SP 800-57): recovery agent holds escrow copy
  - X.509 CA key compromise: cross-signed bridge cert revoked, new issued
  - Domain transfer (ICANN): 5-day lock, auth code, registrar cooperation
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TransferState(Enum):
    INITIATED = "INITIATED"           # New custodian requested
    DUAL_SIGNED = "DUAL_SIGNED"       # Both parties signed (clean path)
    TIMEOUT_PENDING = "TIMEOUT_PENDING"  # Waiting for old operator response
    LAPSED = "LAPSED"                 # Old operator dark, timeout expired
    TRANSFERRED = "TRANSFERRED"       # Clean transfer complete
    REJECTED = "REJECTED"             # Transfer denied
    DISPUTED = "DISPUTED"             # Conflicting claims


class TransferGrade(Enum):
    CUSTODY_TRANSFERRED = "CUSTODY_TRANSFERRED"   # Clean dual-signature (A)
    CUSTODY_LAPSED = "CUSTODY_LAPSED"             # Dark operator timeout (B)
    CUSTODY_CONTESTED = "CUSTODY_CONTESTED"       # Disputed transfer (D)
    CUSTODY_INVALID = "CUSTODY_INVALID"           # Failed validation (F)


# SPEC_CONSTANTS
CUSTODY_TRANSFER_TIMEOUT_DAYS = 30    # SPEC_DEFAULT, genesis overridable (stricter only)
MIN_WITNESS_ATTESTATIONS = 3          # For lapsed path
WITNESS_DIVERSITY_MIN = 0.5           # Simpson diversity on witness set
OVERLAP_WINDOW_DAYS = 7               # Dual-signature overlap period
MAX_TRANSFER_CHAIN_DEPTH = 3          # Prevent cascading transfers


@dataclass
class CustodyTransferRequest:
    agent_id: str
    old_operator_id: str
    new_operator_id: str
    requested_at: float
    reason: str  # "migration", "acquisition", "recovery", "dispute"
    proof_of_control: Optional[str] = None  # Hash of control proof
    old_operator_signature: Optional[str] = None
    new_operator_signature: Optional[str] = None
    witness_attestations: list = field(default_factory=list)
    genesis_timeout_days: int = CUSTODY_TRANSFER_TIMEOUT_DAYS


@dataclass 
class WitnessAttestation:
    witness_id: str
    operator_id: str  # Witness's operator (for diversity check)
    attestation_hash: str
    timestamp: float
    verification_method: str  # "direct_contact", "genesis_audit", "behavioral"


@dataclass
class TransferResult:
    state: TransferState
    grade: TransferGrade
    path: str  # "clean" or "lapsed"
    warnings: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


def compute_witness_diversity(attestations: list[WitnessAttestation]) -> float:
    """Simpson diversity index on witness operator set."""
    if not attestations:
        return 0.0
    operators = [a.operator_id for a in attestations]
    n = len(operators)
    if n <= 1:
        return 0.0
    freq = {}
    for op in operators:
        freq[op] = freq.get(op, 0) + 1
    simpson = sum(f * (f - 1) for f in freq.values()) / (n * (n - 1))
    return round(1.0 - simpson, 4)  # 1 - Simpson = diversity


def validate_clean_transfer(req: CustodyTransferRequest) -> TransferResult:
    """Validate dual-signature (clean) custody transfer."""
    warnings = []
    
    if not req.old_operator_signature:
        return TransferResult(
            state=TransferState.REJECTED,
            grade=TransferGrade.CUSTODY_INVALID,
            path="clean",
            warnings=["Missing old operator signature"],
            details={"reason": "dual_signature_incomplete"}
        )
    
    if not req.new_operator_signature:
        return TransferResult(
            state=TransferState.REJECTED,
            grade=TransferGrade.CUSTODY_INVALID,
            path="clean",
            warnings=["Missing new operator signature"],
            details={"reason": "dual_signature_incomplete"}
        )
    
    if req.old_operator_id == req.new_operator_id:
        warnings.append("Self-transfer detected (same operator)")
    
    return TransferResult(
        state=TransferState.TRANSFERRED,
        grade=TransferGrade.CUSTODY_TRANSFERRED,
        path="clean",
        warnings=warnings,
        details={
            "dual_signed": True,
            "overlap_window_days": OVERLAP_WINDOW_DAYS,
            "old_selector_ttl": f"{OVERLAP_WINDOW_DAYS}d"
        }
    )


def validate_lapsed_transfer(req: CustodyTransferRequest) -> TransferResult:
    """Validate dark-operator (lapsed) custody transfer."""
    now = time.time()
    warnings = []
    
    # Check timeout
    elapsed_days = (now - req.requested_at) / 86400
    timeout = req.genesis_timeout_days
    
    if elapsed_days < timeout:
        return TransferResult(
            state=TransferState.TIMEOUT_PENDING,
            grade=TransferGrade.CUSTODY_INVALID,
            path="lapsed",
            warnings=[f"Timeout not reached: {elapsed_days:.1f}/{timeout}d"],
            details={"days_remaining": round(timeout - elapsed_days, 1)}
        )
    
    # Check proof of control
    if not req.proof_of_control:
        warnings.append("CRITICAL: No proof of control submitted")
        return TransferResult(
            state=TransferState.REJECTED,
            grade=TransferGrade.CUSTODY_INVALID,
            path="lapsed",
            warnings=warnings,
            details={"reason": "no_proof_of_control"}
        )
    
    # Check witness attestations
    if len(req.witness_attestations) < MIN_WITNESS_ATTESTATIONS:
        warnings.append(f"Insufficient witnesses: {len(req.witness_attestations)}/{MIN_WITNESS_ATTESTATIONS}")
        return TransferResult(
            state=TransferState.REJECTED,
            grade=TransferGrade.CUSTODY_INVALID,
            path="lapsed",
            warnings=warnings,
            details={"reason": "insufficient_witnesses"}
        )
    
    # Check witness diversity
    diversity = compute_witness_diversity(req.witness_attestations)
    if diversity < WITNESS_DIVERSITY_MIN:
        warnings.append(f"Low witness diversity: {diversity:.3f} < {WITNESS_DIVERSITY_MIN}")
        return TransferResult(
            state=TransferState.REJECTED,
            grade=TransferGrade.CUSTODY_CONTESTED,
            path="lapsed",
            warnings=warnings,
            details={"reason": "monoculture_witnesses", "diversity": diversity}
        )
    
    # Check for conflicting claims (new operator == old operator's associate)
    new_op_is_witness = any(
        a.operator_id == req.new_operator_id for a in req.witness_attestations
    )
    if new_op_is_witness:
        warnings.append("New operator is also a witness — self-attestation risk")
    
    return TransferResult(
        state=TransferState.LAPSED,
        grade=TransferGrade.CUSTODY_LAPSED,
        path="lapsed",
        warnings=warnings,
        details={
            "timeout_days": timeout,
            "elapsed_days": round(elapsed_days, 1),
            "witness_count": len(req.witness_attestations),
            "witness_diversity": diversity,
            "proof_of_control": req.proof_of_control[:16] + "..."
        }
    )


def process_transfer(req: CustodyTransferRequest) -> TransferResult:
    """Route to clean or lapsed path based on old operator availability."""
    if req.old_operator_signature:
        return validate_clean_transfer(req)
    else:
        return validate_lapsed_transfer(req)


# === Scenarios ===

def run_scenarios():
    now = time.time()
    
    # Scenario 1: Clean dual-signature transfer
    print("=== Scenario 1: Clean Dual-Signature Transfer ===")
    req = CustodyTransferRequest(
        agent_id="kit_fox",
        old_operator_id="operator_a",
        new_operator_id="operator_b",
        requested_at=now - 86400 * 3,
        reason="migration",
        old_operator_signature="sig_old_abc123",
        new_operator_signature="sig_new_def456"
    )
    result = process_transfer(req)
    print(f"  State: {result.state.value}")
    print(f"  Grade: {result.grade.value}")
    print(f"  Path: {result.path}")
    print(f"  Details: {result.details}")
    print()
    
    # Scenario 2: Dark operator — timeout not reached
    print("=== Scenario 2: Dark Operator — Timeout Pending ===")
    req = CustodyTransferRequest(
        agent_id="orphan_agent",
        old_operator_id="dark_operator",
        new_operator_id="rescue_operator",
        requested_at=now - 86400 * 15,  # 15 days
        reason="recovery",
        proof_of_control="proof_hash_abc",
        witness_attestations=[
            WitnessAttestation("w1", "op_x", "att1", now, "direct_contact"),
            WitnessAttestation("w2", "op_y", "att2", now, "genesis_audit"),
            WitnessAttestation("w3", "op_z", "att3", now, "behavioral"),
        ]
    )
    result = process_transfer(req)
    print(f"  State: {result.state.value}")
    print(f"  Grade: {result.grade.value}")
    print(f"  Days remaining: {result.details.get('days_remaining', 'N/A')}")
    print()
    
    # Scenario 3: Dark operator — timeout reached, valid witnesses
    print("=== Scenario 3: Dark Operator — Lapsed Transfer (Valid) ===")
    req = CustodyTransferRequest(
        agent_id="orphan_agent",
        old_operator_id="dark_operator",
        new_operator_id="rescue_operator",
        requested_at=now - 86400 * 35,  # 35 days (past timeout)
        reason="recovery",
        proof_of_control="proof_hash_abc123def456",
        witness_attestations=[
            WitnessAttestation("w1", "op_x", "att1", now, "direct_contact"),
            WitnessAttestation("w2", "op_y", "att2", now, "genesis_audit"),
            WitnessAttestation("w3", "op_z", "att3", now, "behavioral"),
        ]
    )
    result = process_transfer(req)
    print(f"  State: {result.state.value}")
    print(f"  Grade: {result.grade.value}")
    print(f"  Path: {result.path}")
    print(f"  Details: {result.details}")
    print()
    
    # Scenario 4: Monoculture witnesses (same operator = sybil)
    print("=== Scenario 4: Monoculture Witnesses (Sybil Attack) ===")
    req = CustodyTransferRequest(
        agent_id="target_agent",
        old_operator_id="dark_operator",
        new_operator_id="attacker",
        requested_at=now - 86400 * 35,
        reason="recovery",
        proof_of_control="fake_proof_hash",
        witness_attestations=[
            WitnessAttestation("w1", "attacker_op", "att1", now, "direct_contact"),
            WitnessAttestation("w2", "attacker_op", "att2", now, "genesis_audit"),
            WitnessAttestation("w3", "attacker_op", "att3", now, "behavioral"),
        ]
    )
    result = process_transfer(req)
    print(f"  State: {result.state.value}")
    print(f"  Grade: {result.grade.value}")
    print(f"  Warnings: {result.warnings}")
    print(f"  Diversity: {result.details.get('diversity', 'N/A')}")
    print()
    
    # Scenario 5: No proof of control
    print("=== Scenario 5: No Proof of Control ===")
    req = CustodyTransferRequest(
        agent_id="target_agent",
        old_operator_id="dark_operator",
        new_operator_id="claimant",
        requested_at=now - 86400 * 40,
        reason="recovery",
        witness_attestations=[
            WitnessAttestation("w1", "op_a", "att1", now, "behavioral"),
            WitnessAttestation("w2", "op_b", "att2", now, "behavioral"),
            WitnessAttestation("w3", "op_c", "att3", now, "behavioral"),
        ]
    )
    result = process_transfer(req)
    print(f"  State: {result.state.value}")
    print(f"  Grade: {result.grade.value}")
    print(f"  Reason: {result.details.get('reason', 'N/A')}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — Dark Operator Path for ATF")
    print("Per santaclawd: DKIM has no answer for dark operators. ATF does.")
    print("=" * 65)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  CUSTODY_TRANSFER_TIMEOUT = {CUSTODY_TRANSFER_TIMEOUT_DAYS}d")
    print(f"  MIN_WITNESS_ATTESTATIONS = {MIN_WITNESS_ATTESTATIONS}")
    print(f"  WITNESS_DIVERSITY_MIN = {WITNESS_DIVERSITY_MIN}")
    print(f"  OVERLAP_WINDOW = {OVERLAP_WINDOW_DAYS}d")
    print()
    run_scenarios()
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("  1. Clean path (dual-sig) = CUSTODY_TRANSFERRED (Grade A)")
    print("  2. Lapsed path (timeout) = CUSTODY_LAPSED (Grade B)")  
    print("  3. Monoculture witnesses = REJECTED (sybil detection)")
    print("  4. No proof of control = REJECTED (claim without evidence)")
    print("  5. Timeout IS authorization — silence after 30d = implicit consent")
    print("  6. DKIM parallel: DNS TTL is implicit timeout. ATF makes it explicit.")
