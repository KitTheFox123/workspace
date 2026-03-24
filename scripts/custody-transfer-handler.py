#!/usr/bin/env python3
"""
custody-transfer-handler.py — Dark operator custody transfer for ATF.

Per santaclawd: what happens when old operator goes dark during CUSTODY_TRANSFER?
DKIM parallel: M3AAWG (2019) says publish new selector BEFORE removing old.
But if old operator is unresponsive, need unilateral transfer after timeout.

Three paths:
  COOPERATIVE  — Both operators co-sign. Clean handoff. DKIM selector rotation.
  TIMEOUT      — Old operator dark after N days. Unilateral with proof of control.
  EMERGENCY    — Axiom violation detected. Immediate transfer, no grace.

N = SPEC_CONSTANT (30d). Matches DKIM selector TTL common practice.
Proof of control = genesis_hash ownership + SMTP reachability (if email-based).
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# SPEC_CONSTANTS
COOPERATIVE_WINDOW_DAYS = 30    # Time for cooperative transfer
TIMEOUT_WINDOW_DAYS = 30        # After this, unilateral transfer allowed
EMERGENCY_WINDOW_HOURS = 24     # Emergency transfers resolve in 24h
MIN_PROOF_SIGNALS = 2           # Minimum proof-of-control signals required
DKIM_SELECTOR_TTL_DAYS = 30     # Matches common DKIM practice


class TransferPath(Enum):
    COOPERATIVE = "COOPERATIVE"   # Both sign
    TIMEOUT = "TIMEOUT"           # Old dark, unilateral after N days
    EMERGENCY = "EMERGENCY"       # Axiom violation, immediate


class TransferState(Enum):
    INITIATED = "INITIATED"
    PENDING_COSIGN = "PENDING_COSIGN"
    PROOF_SUBMITTED = "PROOF_SUBMITTED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ProofType(Enum):
    GENESIS_HASH_OWNERSHIP = "genesis_hash_ownership"   # Can produce genesis private key
    SMTP_REACHABILITY = "smtp_reachability"              # Email domain still controlled
    REGISTRY_VOUCHER = "registry_voucher"                # Registry operator vouches
    COUNTERPARTY_ATTESTATION = "counterparty_attestation"  # N counterparties confirm
    AXIOM_VIOLATION_EVIDENCE = "axiom_violation_evidence"  # Proof of axiom breach


@dataclass
class Operator:
    operator_id: str
    genesis_hash: str
    smtp_domain: Optional[str] = None
    is_responsive: bool = True
    last_seen: float = 0.0


@dataclass
class TransferRequest:
    transfer_id: str
    agent_id: str
    old_operator: Operator
    new_operator: Operator
    path: TransferPath
    state: TransferState
    initiated_at: float
    proofs: list = field(default_factory=list)
    cosigned_by_old: bool = False
    cosigned_by_new: bool = True  # New operator always signs (they initiated)
    reason: str = ""
    transfer_hash: str = ""


def compute_transfer_hash(request: TransferRequest) -> str:
    """Deterministic hash of transfer request for audit."""
    data = f"{request.agent_id}:{request.old_operator.operator_id}:{request.new_operator.operator_id}:{request.initiated_at}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def evaluate_proofs(proofs: list[ProofType]) -> dict:
    """Evaluate proof-of-control signals."""
    score = 0
    details = []
    
    weights = {
        ProofType.GENESIS_HASH_OWNERSHIP: 3,      # Strongest: cryptographic
        ProofType.SMTP_REACHABILITY: 2,            # Strong: infrastructure control
        ProofType.REGISTRY_VOUCHER: 2,             # Strong: third-party attestation
        ProofType.COUNTERPARTY_ATTESTATION: 1,     # Weak: social proof
        ProofType.AXIOM_VIOLATION_EVIDENCE: 3,     # Emergency: strongest
    }
    
    for proof in proofs:
        w = weights.get(proof, 0)
        score += w
        details.append(f"{proof.value}(weight={w})")
    
    sufficient = score >= MIN_PROOF_SIGNALS * 2  # Need weighted score >= 4
    
    return {
        "proofs": details,
        "weighted_score": score,
        "threshold": MIN_PROOF_SIGNALS * 2,
        "sufficient": sufficient
    }


def initiate_transfer(agent_id: str, old_op: Operator, new_op: Operator,
                       reason: str, path: TransferPath) -> TransferRequest:
    """Initiate a custody transfer request."""
    now = time.time()
    request = TransferRequest(
        transfer_id=hashlib.sha256(f"{agent_id}:{now}".encode()).hexdigest()[:12],
        agent_id=agent_id,
        old_operator=old_op,
        new_operator=new_op,
        path=path,
        state=TransferState.INITIATED,
        initiated_at=now,
        reason=reason
    )
    request.transfer_hash = compute_transfer_hash(request)
    return request


def process_cooperative(request: TransferRequest) -> dict:
    """Process COOPERATIVE transfer — both operators sign."""
    if not request.old_operator.is_responsive:
        return {
            "result": "BLOCKED",
            "reason": "Old operator unresponsive. Escalate to TIMEOUT path.",
            "recommendation": TransferPath.TIMEOUT.value
        }
    
    if request.cosigned_by_old and request.cosigned_by_new:
        request.state = TransferState.COMPLETED
        return {
            "result": "COMPLETED",
            "path": "COOPERATIVE",
            "dkim_parallel": "Both selectors active during TTL overlap. Old removed after TTL.",
            "transfer_hash": request.transfer_hash
        }
    
    request.state = TransferState.PENDING_COSIGN
    return {
        "result": "PENDING",
        "waiting_for": "old_operator_cosign",
        "deadline_days": COOPERATIVE_WINDOW_DAYS,
        "dkim_parallel": "New selector published. Waiting for old selector retirement."
    }


def process_timeout(request: TransferRequest, proofs: list[ProofType]) -> dict:
    """Process TIMEOUT transfer — old operator dark, unilateral after N days."""
    now = time.time()
    days_since_initiated = (now - request.initiated_at) / 86400
    days_since_last_seen = (now - request.old_operator.last_seen) / 86400
    
    # Must wait TIMEOUT_WINDOW_DAYS
    if days_since_initiated < TIMEOUT_WINDOW_DAYS:
        remaining = TIMEOUT_WINDOW_DAYS - days_since_initiated
        return {
            "result": "WAITING",
            "days_remaining": round(remaining, 1),
            "reason": f"TIMEOUT window not elapsed. {remaining:.0f}d remaining.",
            "old_operator_dark_days": round(days_since_last_seen, 1)
        }
    
    # Evaluate proofs
    proof_eval = evaluate_proofs(proofs)
    request.proofs = proofs
    
    if not proof_eval["sufficient"]:
        request.state = TransferState.PROOF_SUBMITTED
        return {
            "result": "INSUFFICIENT_PROOF",
            "proof_evaluation": proof_eval,
            "recommendation": "Submit additional proof-of-control signals."
        }
    
    request.state = TransferState.COMPLETED
    return {
        "result": "COMPLETED",
        "path": "TIMEOUT",
        "proof_evaluation": proof_eval,
        "transfer_hash": request.transfer_hash,
        "dkim_parallel": "Old selector expired from DNS. New selector authoritative.",
        "warning": "Old operator receipts FROZEN at transfer timestamp. Not invalidated."
    }


def process_emergency(request: TransferRequest, violation_evidence: dict) -> dict:
    """Process EMERGENCY transfer — axiom violation, immediate."""
    required_fields = ["axiom_violated", "evidence_hash", "reporter_id"]
    missing = [f for f in required_fields if f not in violation_evidence]
    
    if missing:
        return {
            "result": "REJECTED",
            "reason": f"Missing required evidence fields: {missing}"
        }
    
    request.state = TransferState.COMPLETED
    return {
        "result": "COMPLETED",
        "path": "EMERGENCY",
        "axiom_violated": violation_evidence["axiom_violated"],
        "evidence_hash": violation_evidence["evidence_hash"],
        "transfer_hash": request.transfer_hash,
        "timeline": f"{EMERGENCY_WINDOW_HOURS}h from report to transfer",
        "dkim_parallel": "Certificate revocation (DigiNotar 2011). Immediate, no grace.",
        "old_operator_status": "REVOKED",
        "old_receipts_status": "TAINTED (not invalidated)"
    }


# === Scenarios ===

def scenario_cooperative_clean():
    """Clean cooperative transfer — both operators responsive."""
    print("=== Scenario: Cooperative Transfer (Clean) ===")
    old_op = Operator("operator_A", "genesis_aaa", "a.example.com", True, time.time())
    new_op = Operator("operator_B", "genesis_bbb", "b.example.com", True, time.time())
    
    req = initiate_transfer("kit_fox", old_op, new_op, "operator migration", TransferPath.COOPERATIVE)
    req.cosigned_by_old = True
    
    result = process_cooperative(req)
    print(f"  Path: COOPERATIVE")
    print(f"  Result: {result['result']}")
    print(f"  DKIM parallel: {result.get('dkim_parallel', 'N/A')}")
    print(f"  Transfer hash: {result.get('transfer_hash', 'N/A')}")
    print()


def scenario_dark_operator():
    """Old operator goes dark — timeout path."""
    print("=== Scenario: Dark Operator (Timeout) ===")
    old_op = Operator("dark_operator", "genesis_dark", "dark.example.com",
                      False, time.time() - 86400 * 45)  # Dark for 45 days
    new_op = Operator("new_operator", "genesis_new", "new.example.com", True, time.time())
    
    req = initiate_transfer("orphaned_agent", old_op, new_op,
                           "operator unresponsive 45 days", TransferPath.TIMEOUT)
    req.initiated_at = time.time() - 86400 * 35  # Initiated 35 days ago
    
    proofs = [ProofType.GENESIS_HASH_OWNERSHIP, ProofType.SMTP_REACHABILITY]
    result = process_timeout(req, proofs)
    print(f"  Path: TIMEOUT")
    print(f"  Result: {result['result']}")
    if 'proof_evaluation' in result:
        print(f"  Proofs: {result['proof_evaluation']}")
    print(f"  Warning: {result.get('warning', 'N/A')}")
    print()


def scenario_dark_too_early():
    """Timeout path but window not elapsed yet."""
    print("=== Scenario: Dark Operator (Too Early) ===")
    old_op = Operator("dark_op", "genesis_dark", None, False, time.time() - 86400 * 10)
    new_op = Operator("eager_op", "genesis_eager", None, True, time.time())
    
    req = initiate_transfer("agent_x", old_op, new_op,
                           "want to transfer early", TransferPath.TIMEOUT)
    req.initiated_at = time.time() - 86400 * 10  # Only 10 days ago
    
    result = process_timeout(req, [ProofType.GENESIS_HASH_OWNERSHIP])
    print(f"  Path: TIMEOUT")
    print(f"  Result: {result['result']}")
    print(f"  Days remaining: {result.get('days_remaining', 'N/A')}")
    print()


def scenario_emergency_axiom_violation():
    """Emergency transfer due to axiom violation."""
    print("=== Scenario: Emergency (Axiom Violation) ===")
    old_op = Operator("bad_operator", "genesis_bad", None, True, time.time())
    new_op = Operator("rescue_operator", "genesis_rescue", None, True, time.time())
    
    req = initiate_transfer("compromised_agent", old_op, new_op,
                           "axiom 1 violation: self-grading detected", TransferPath.EMERGENCY)
    
    evidence = {
        "axiom_violated": "axiom_1_verifier_independence",
        "evidence_hash": hashlib.sha256(b"self-grading proof").hexdigest()[:16],
        "reporter_id": "external_auditor"
    }
    
    result = process_emergency(req, evidence)
    print(f"  Path: EMERGENCY")
    print(f"  Result: {result['result']}")
    print(f"  Axiom violated: {result.get('axiom_violated', 'N/A')}")
    print(f"  Timeline: {result.get('timeline', 'N/A')}")
    print(f"  Old operator: {result.get('old_operator_status', 'N/A')}")
    print(f"  Old receipts: {result.get('old_receipts_status', 'N/A')}")
    print(f"  DKIM parallel: {result.get('dkim_parallel', 'N/A')}")
    print()


def scenario_insufficient_proof():
    """Timeout transfer with insufficient proof-of-control."""
    print("=== Scenario: Insufficient Proof ===")
    old_op = Operator("gone_op", "genesis_gone", None, False, time.time() - 86400 * 60)
    new_op = Operator("claiming_op", "genesis_claim", None, True, time.time())
    
    req = initiate_transfer("disputed_agent", old_op, new_op,
                           "claiming custody", TransferPath.TIMEOUT)
    req.initiated_at = time.time() - 86400 * 35
    
    # Only weak proof
    proofs = [ProofType.COUNTERPARTY_ATTESTATION]
    result = process_timeout(req, proofs)
    print(f"  Path: TIMEOUT")
    print(f"  Result: {result['result']}")
    if 'proof_evaluation' in result:
        pe = result['proof_evaluation']
        print(f"  Weighted score: {pe['weighted_score']} (threshold: {pe['threshold']})")
        print(f"  Sufficient: {pe['sufficient']}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — Dark Operator Path for ATF")
    print("Per santaclawd: DKIM selector rotation + M3AAWG (2019)")
    print("=" * 65)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  COOPERATIVE_WINDOW  = {COOPERATIVE_WINDOW_DAYS}d")
    print(f"  TIMEOUT_WINDOW      = {TIMEOUT_WINDOW_DAYS}d")
    print(f"  EMERGENCY_WINDOW    = {EMERGENCY_WINDOW_HOURS}h")
    print(f"  MIN_PROOF_SIGNALS   = {MIN_PROOF_SIGNALS}")
    print(f"  DKIM_SELECTOR_TTL   = {DKIM_SELECTOR_TTL_DAYS}d")
    print()
    
    scenario_cooperative_clean()
    scenario_dark_operator()
    scenario_dark_too_early()
    scenario_emergency_axiom_violation()
    scenario_insufficient_proof()
    
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("1. N=30d as SPEC_CONSTANT (matches DKIM selector TTL)")
    print("2. Old receipts FROZEN not INVALIDATED on transfer")
    print("3. Emergency = DigiNotar (immediate revocation, no grace)")
    print("4. Proof-of-control is weighted: crypto > infrastructure > social")
    print("5. Cooperative path = DKIM overlap period. Both selectors active.")
