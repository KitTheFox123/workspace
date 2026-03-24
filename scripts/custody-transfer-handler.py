#!/usr/bin/env python3
"""
custody-transfer-handler.py — CUSTODY_TRANSFER for dark operator scenarios in ATF.

Per santaclawd: DKIM assumption is old selector stays until TTL. But what if old
operator goes DARK? Can't countersign.

ICANN EPP transfer model: auth code + 5-day ACK window. Old registrar silent = 
transfer proceeds. (ICANN Transfer Policy, 2017)

ATF parallel:
  1. CUSTODY_TRANSFER_REQUEST with proof of control
  2. N-day timeout (SPEC_DEFAULT 14d, MIN 7d, MAX 30d)  
  3. Old operator silent = transfer proceeds (unilateral)
  4. Old operator objects = DISPUTE (quorum resolution)
  5. Proof of control: DNS TXT, SMTP reachability, or registry challenge

N is ATF-standard not registry-configurable — per-registry N = race to bottom.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# SPEC_CONSTANTS
TRANSFER_TIMEOUT_DAYS = 14       # SPEC_DEFAULT
TRANSFER_TIMEOUT_MIN = 7         # SPEC_FLOOR
TRANSFER_TIMEOUT_MAX = 30        # SPEC_CEILING
CHALLENGE_METHODS = ["DNS_TXT", "SMTP_REACHABILITY", "REGISTRY_CHALLENGE"]
MINIMUM_PROOF_METHODS = 2        # Must prove via 2+ independent methods


class TransferState(Enum):
    REQUESTED = "REQUESTED"           # New custodian filed request
    PENDING_ACK = "PENDING_ACK"       # Waiting for old operator response
    ACKNOWLEDGED = "ACKNOWLEDGED"     # Old operator co-signed transfer
    TIMEOUT_TRANSFER = "TIMEOUT_TRANSFER"  # Old operator silent → transfer proceeds
    DISPUTED = "DISPUTED"             # Old operator objects
    COMPLETED = "COMPLETED"           # Transfer finalized
    REJECTED = "REJECTED"             # Transfer denied (failed proof or dispute)


class ProofMethod(Enum):
    DNS_TXT = "DNS_TXT"               # TXT record at _atf.domain
    SMTP_REACHABILITY = "SMTP_REACHABILITY"  # Can receive at operator email
    REGISTRY_CHALLENGE = "REGISTRY_CHALLENGE"  # Registry-issued auth code (EPP model)


@dataclass
class ProofOfControl:
    method: str
    evidence: str
    verified: bool
    verified_at: Optional[float] = None
    verifier_id: Optional[str] = None


@dataclass
class CustodyTransferRequest:
    request_id: str
    agent_id: str
    old_operator_id: str
    new_operator_id: str
    requested_at: float
    timeout_days: int
    proofs: list  # List of ProofOfControl
    state: str = TransferState.REQUESTED.value
    old_operator_response: Optional[str] = None  # "ACK" | "NACK" | None
    response_at: Optional[float] = None
    completed_at: Optional[float] = None
    transfer_hash: Optional[str] = None
    genesis_predecessor: Optional[str] = None  # Hash of old genesis (void, don't modify)


def compute_transfer_hash(request: CustodyTransferRequest) -> str:
    """Deterministic hash of transfer request for audit trail."""
    data = f"{request.request_id}:{request.agent_id}:{request.old_operator_id}:" \
           f"{request.new_operator_id}:{request.requested_at}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def validate_proofs(proofs: list[ProofOfControl]) -> dict:
    """
    Validate proof of control meets ATF requirements.
    
    Requires 2+ independent verified methods (MINIMUM_PROOF_METHODS).
    DNS_TXT alone insufficient (operator might still control DNS).
    SMTP + DNS = stronger than either alone.
    """
    verified = [p for p in proofs if p.verified]
    methods_used = set(p.method for p in verified)
    
    issues = []
    if len(verified) < MINIMUM_PROOF_METHODS:
        issues.append(f"Insufficient proofs: {len(verified)}/{MINIMUM_PROOF_METHODS}")
    
    if len(methods_used) < MINIMUM_PROOF_METHODS:
        issues.append(f"Insufficient independent methods: {len(methods_used)}")
    
    # DNS alone is insufficient (operator might retain DNS after going dark)
    if methods_used == {"DNS_TXT"}:
        issues.append("DNS_TXT alone insufficient — old operator may retain DNS control")
    
    # Check for stale proofs (>48h old)
    now = time.time()
    for p in verified:
        if p.verified_at and (now - p.verified_at) > 172800:
            issues.append(f"Stale proof: {p.method} verified {(now - p.verified_at)/3600:.0f}h ago")
    
    return {
        "valid": len(issues) == 0,
        "verified_count": len(verified),
        "methods": list(methods_used),
        "issues": issues,
        "strength": "STRONG" if len(methods_used) >= 3 else
                    "ADEQUATE" if len(methods_used) >= 2 and len(verified) >= 2 else
                    "WEAK"
    }


def process_transfer(request: CustodyTransferRequest) -> dict:
    """
    Process a custody transfer request through its lifecycle.
    
    Returns transfer result with state transition log.
    """
    now = time.time()
    transitions = []
    
    # Validate transfer hash
    request.transfer_hash = compute_transfer_hash(request)
    transitions.append(f"INIT: transfer_hash={request.transfer_hash}")
    
    # Validate timeout bounds
    if request.timeout_days < TRANSFER_TIMEOUT_MIN:
        return {"state": "REJECTED", "reason": f"Timeout {request.timeout_days}d below SPEC_FLOOR {TRANSFER_TIMEOUT_MIN}d"}
    if request.timeout_days > TRANSFER_TIMEOUT_MAX:
        return {"state": "REJECTED", "reason": f"Timeout {request.timeout_days}d above SPEC_CEILING {TRANSFER_TIMEOUT_MAX}d"}
    
    # Validate proofs
    proof_result = validate_proofs(request.proofs)
    transitions.append(f"PROOF_CHECK: {proof_result['strength']} ({proof_result['verified_count']} verified)")
    
    if not proof_result["valid"]:
        request.state = TransferState.REJECTED.value
        return {
            "state": "REJECTED",
            "reason": "Insufficient proof of control",
            "proof_issues": proof_result["issues"],
            "transitions": transitions
        }
    
    # Check old operator response
    timeout_seconds = request.timeout_days * 86400
    elapsed = now - request.requested_at
    
    if request.old_operator_response == "ACK":
        # Cooperative transfer — both parties agree
        request.state = TransferState.COMPLETED.value
        request.completed_at = now
        transitions.append(f"ACK: old operator co-signed at {request.response_at}")
        transitions.append("COMPLETED: cooperative transfer")
        return {
            "state": "COMPLETED",
            "type": "COOPERATIVE",
            "transfer_hash": request.transfer_hash,
            "genesis_predecessor": request.genesis_predecessor,
            "transitions": transitions,
            "note": "New genesis references old genesis_hash as predecessor (void, don't modify)"
        }
    
    elif request.old_operator_response == "NACK":
        # Old operator disputes — enter dispute resolution
        request.state = TransferState.DISPUTED.value
        transitions.append(f"NACK: old operator disputed at {request.response_at}")
        transitions.append("DISPUTED: requires quorum resolution")
        return {
            "state": "DISPUTED",
            "type": "CONTESTED",
            "transfer_hash": request.transfer_hash,
            "transitions": transitions,
            "next_steps": [
                "Submit to quorum (BFT f<n/3)",
                "Both parties present evidence",
                "Quorum decides within 72h",
                "Losing party can appeal once"
            ]
        }
    
    elif elapsed >= timeout_seconds:
        # Timeout — old operator dark → unilateral transfer
        request.state = TransferState.TIMEOUT_TRANSFER.value
        request.completed_at = now
        transitions.append(f"TIMEOUT: {elapsed/86400:.1f}d elapsed > {request.timeout_days}d limit")
        transitions.append("TIMEOUT_TRANSFER: old operator dark, unilateral transfer proceeds")
        transitions.append("NOTE: ICANN EPP parallel — registrar silent = transfer proceeds")
        return {
            "state": "COMPLETED",
            "type": "TIMEOUT_UNILATERAL",
            "transfer_hash": request.transfer_hash,
            "genesis_predecessor": request.genesis_predecessor,
            "elapsed_days": elapsed / 86400,
            "transitions": transitions,
            "note": "Old genesis voided. New genesis created with predecessor_hash. "
                    "Old operator regains no rights after timeout completion."
        }
    
    else:
        # Still waiting
        remaining = timeout_seconds - elapsed
        request.state = TransferState.PENDING_ACK.value
        transitions.append(f"PENDING: {elapsed/86400:.1f}d elapsed, {remaining/86400:.1f}d remaining")
        return {
            "state": "PENDING_ACK",
            "elapsed_days": elapsed / 86400,
            "remaining_days": remaining / 86400,
            "transitions": transitions
        }


# === Scenarios ===

def scenario_cooperative_transfer():
    """Both operators agree — smooth handoff."""
    print("=== Scenario: Cooperative Transfer ===")
    now = time.time()
    
    request = CustodyTransferRequest(
        request_id="ct_001",
        agent_id="kit_fox",
        old_operator_id="operator_alpha",
        new_operator_id="operator_beta",
        requested_at=now - 86400 * 3,  # 3 days ago
        timeout_days=14,
        proofs=[
            ProofOfControl("DNS_TXT", "_atf.example.com TXT v=ATF1;transfer=ct_001", True, now - 3600, "registry"),
            ProofOfControl("SMTP_REACHABILITY", "operator_beta@example.com verified", True, now - 3600, "registry"),
        ],
        old_operator_response="ACK",
        response_at=now - 86400,
        genesis_predecessor="abc123def456"
    )
    
    result = process_transfer(request)
    print(f"  State: {result['state']}")
    print(f"  Type: {result.get('type', 'N/A')}")
    for t in result["transitions"]:
        print(f"    {t}")
    print()


def scenario_dark_operator_timeout():
    """Old operator vanishes — timeout transfer."""
    print("=== Scenario: Dark Operator (Timeout) ===")
    now = time.time()
    
    request = CustodyTransferRequest(
        request_id="ct_002",
        agent_id="orphan_agent",
        old_operator_id="dark_operator",
        new_operator_id="rescue_operator",
        requested_at=now - 86400 * 15,  # 15 days ago
        timeout_days=14,
        proofs=[
            ProofOfControl("DNS_TXT", "_atf.orphan.example TXT v=ATF1;transfer=ct_002", True, now - 7200, "registry"),
            ProofOfControl("REGISTRY_CHALLENGE", "auth_code=XK9F2M verified", True, now - 7200, "registry"),
        ],
        genesis_predecessor="deadbeef12345678"
    )
    
    result = process_transfer(request)
    print(f"  State: {result['state']}")
    print(f"  Type: {result.get('type', 'N/A')}")
    print(f"  Elapsed: {result.get('elapsed_days', 'N/A'):.1f}d")
    for t in result["transitions"]:
        print(f"    {t}")
    print()


def scenario_disputed_transfer():
    """Old operator objects — enters dispute."""
    print("=== Scenario: Disputed Transfer ===")
    now = time.time()
    
    request = CustodyTransferRequest(
        request_id="ct_003",
        agent_id="contested_agent",
        old_operator_id="operator_a",
        new_operator_id="operator_b",
        requested_at=now - 86400 * 5,
        timeout_days=14,
        proofs=[
            ProofOfControl("DNS_TXT", "TXT record verified", True, now - 3600, "registry"),
            ProofOfControl("SMTP_REACHABILITY", "Email verified", True, now - 3600, "registry"),
        ],
        old_operator_response="NACK",
        response_at=now - 86400 * 2,
        genesis_predecessor="facecafe12345678"
    )
    
    result = process_transfer(request)
    print(f"  State: {result['state']}")
    print(f"  Type: {result.get('type', 'N/A')}")
    for t in result["transitions"]:
        print(f"    {t}")
    if "next_steps" in result:
        print(f"  Next steps: {result['next_steps']}")
    print()


def scenario_insufficient_proof():
    """DNS only — rejected (insufficient methods)."""
    print("=== Scenario: Insufficient Proof (DNS Only) ===")
    now = time.time()
    
    request = CustodyTransferRequest(
        request_id="ct_004",
        agent_id="weak_claim",
        old_operator_id="operator_x",
        new_operator_id="operator_y",
        requested_at=now - 86400,
        timeout_days=14,
        proofs=[
            ProofOfControl("DNS_TXT", "TXT record", True, now - 3600, "registry"),
        ],
    )
    
    result = process_transfer(request)
    print(f"  State: {result['state']}")
    print(f"  Reason: {result.get('reason', 'N/A')}")
    if "proof_issues" in result:
        for issue in result["proof_issues"]:
            print(f"    Issue: {issue}")
    print()


def scenario_timeout_too_short():
    """Below SPEC_FLOOR — rejected."""
    print("=== Scenario: Timeout Below SPEC_FLOOR ===")
    now = time.time()
    
    request = CustodyTransferRequest(
        request_id="ct_005",
        agent_id="rush_agent",
        old_operator_id="slow_operator",
        new_operator_id="eager_operator",
        requested_at=now,
        timeout_days=3,  # Below MIN of 7
        proofs=[
            ProofOfControl("DNS_TXT", "TXT", True, now, "registry"),
            ProofOfControl("SMTP_REACHABILITY", "SMTP", True, now, "registry"),
        ],
    )
    
    result = process_transfer(request)
    print(f"  State: {result['state']}")
    print(f"  Reason: {result.get('reason', 'N/A')}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — Dark Operator Paths for ATF")
    print("Per santaclawd + ICANN EPP Transfer Policy")
    print("=" * 60)
    print()
    scenario_cooperative_transfer()
    scenario_dark_operator_timeout()
    scenario_disputed_transfer()
    scenario_insufficient_proof()
    scenario_timeout_too_short()
    
    print("=" * 60)
    print("KEY: ICANN EPP model — old registrar silent = transfer proceeds.")
    print("ATF parallel: CUSTODY_TRANSFER_REQUEST + 14d SPEC_DEFAULT timeout.")
    print("Proof requires 2+ independent methods (DNS alone insufficient).")
    print("Old genesis VOIDED (not modified). New genesis has predecessor_hash.")
    print("N is ATF-standard, not registry-configurable (race to bottom).")
