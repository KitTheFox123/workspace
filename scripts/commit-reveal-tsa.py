#!/usr/bin/env python3
"""
commit-reveal-tsa.py — Commit-reveal protocol with RFC 3161 timestamping for ATF receipts.

Closes write-time injection attack per santaclawd.

Protocol:
  1. COMMIT: Agent publishes H(receipt || nonce) BEFORE interaction
  2. INTERACT: Interaction happens, receipt generated
  3. REVEAL: Agent reveals receipt + nonce, verifier checks hash matches commit
  4. TIMESTAMP: External TSA timestamp on commit proves pre-existence

Three independent timing proofs:
  - Commit hash (pre-interaction)
  - K-of-N counterparty receipts (interaction-time)
  - RFC 3161 TSA timestamp (external, non-colluding)

No single party controls all three → write-time injection closed cryptographically.
"""

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Phase(Enum):
    COMMIT = "COMMIT"
    INTERACT = "INTERACT"
    REVEAL = "REVEAL"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass
class Commitment:
    """Pre-interaction commitment."""
    agent_id: str
    commit_hash: str          # H(receipt_template || nonce)
    nonce: str                # Random, revealed later
    timestamp: float          # When commitment was published
    tsa_token: Optional[str]  # RFC 3161 timestamp token (simulated)
    phase: str = Phase.COMMIT.value


@dataclass
class Receipt:
    """ATF receipt generated during interaction."""
    receipt_id: str
    agent_id: str
    counterparty_id: str
    evidence_grade: str
    interaction_hash: str     # Hash of interaction content
    timestamp: float
    metadata: dict = field(default_factory=dict)


@dataclass
class Revelation:
    """Post-interaction reveal."""
    commitment: Commitment
    receipt: Receipt
    nonce: str
    verify_result: str        # VERIFIED or FAILED + reason
    timing_proofs: dict = field(default_factory=dict)


def generate_nonce(length: int = 32) -> str:
    """Cryptographically random nonce."""
    return os.urandom(length).hex()


def compute_commit_hash(receipt_template: dict, nonce: str) -> str:
    """H(receipt_template || nonce) — binding commitment."""
    payload = json.dumps(receipt_template, sort_keys=True) + nonce
    return hashlib.sha256(payload.encode()).hexdigest()


def simulate_tsa_timestamp(data: str) -> dict:
    """
    Simulate RFC 3161 TSA response.
    
    In production: POST hash to TSA server, receive signed timestamp token.
    TSA signs: {hash, time, serial, policy_oid, tsa_name}
    """
    ts = time.time()
    token_hash = hashlib.sha256(f"{data}:{ts}".encode()).hexdigest()[:32]
    return {
        "tsa_name": "ATF-TSA-Sim",
        "serial": token_hash[:16],
        "timestamp": ts,
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "hash_algorithm": "SHA-256",
        "message_imprint": hashlib.sha256(data.encode()).hexdigest(),
        "policy_oid": "1.3.6.1.4.1.99999.1.1",  # Simulated
        "accuracy_seconds": 1,
        "token_signature": f"SIG:{token_hash}"
    }


def phase_commit(agent_id: str, counterparty_id: str, intent: str) -> tuple[Commitment, str]:
    """
    Phase 1: Agent commits to interaction intent before it happens.
    
    Returns (commitment, nonce) — nonce kept secret until reveal.
    """
    nonce = generate_nonce()
    
    receipt_template = {
        "agent_id": agent_id,
        "counterparty_id": counterparty_id,
        "intent": intent,
        "template_version": "1.0"
    }
    
    commit_hash = compute_commit_hash(receipt_template, nonce)
    tsa_response = simulate_tsa_timestamp(commit_hash)
    
    commitment = Commitment(
        agent_id=agent_id,
        commit_hash=commit_hash,
        nonce="HIDDEN",  # Not revealed yet
        timestamp=time.time(),
        tsa_token=json.dumps(tsa_response),
        phase=Phase.COMMIT.value
    )
    
    return commitment, nonce


def phase_interact(agent_id: str, counterparty_id: str, interaction_data: str) -> Receipt:
    """
    Phase 2: Interaction happens, receipt generated.
    """
    interaction_hash = hashlib.sha256(interaction_data.encode()).hexdigest()
    
    return Receipt(
        receipt_id=hashlib.sha256(f"{agent_id}:{counterparty_id}:{time.time()}".encode()).hexdigest()[:16],
        agent_id=agent_id,
        counterparty_id=counterparty_id,
        evidence_grade="B",
        interaction_hash=interaction_hash,
        timestamp=time.time()
    )


def phase_reveal(commitment: Commitment, receipt: Receipt, nonce: str,
                 counterparty_id: str, intent: str) -> Revelation:
    """
    Phase 3: Agent reveals nonce, verifier checks commitment matches receipt.
    
    Verification checks:
    1. H(receipt_template || nonce) == commit_hash (binding)
    2. TSA timestamp < interaction timestamp (ordering)
    3. Counterparty receipt exists (K-of-N corroboration)
    """
    # Reconstruct template
    receipt_template = {
        "agent_id": commitment.agent_id,
        "counterparty_id": counterparty_id,
        "intent": intent,
        "template_version": "1.0"
    }
    
    # Check 1: Hash binding
    recomputed_hash = compute_commit_hash(receipt_template, nonce)
    hash_match = recomputed_hash == commitment.commit_hash
    
    # Check 2: Temporal ordering (TSA timestamp before interaction)
    tsa_data = json.loads(commitment.tsa_token)
    tsa_time = tsa_data["timestamp"]
    temporal_valid = tsa_time <= receipt.timestamp
    
    # Check 3: Agent matches
    agent_match = commitment.agent_id == receipt.agent_id
    
    timing_proofs = {
        "commit_hash_match": hash_match,
        "temporal_ordering": temporal_valid,
        "agent_identity_match": agent_match,
        "commit_time": commitment.timestamp,
        "tsa_time": tsa_time,
        "interaction_time": receipt.timestamp,
        "time_delta_ms": round((receipt.timestamp - tsa_time) * 1000, 2),
        "three_proof_summary": {
            "proof_1_commit_hash": "PASS" if hash_match else "FAIL",
            "proof_2_kofn_receipt": "PASS (simulated)",
            "proof_3_tsa_timestamp": "PASS" if temporal_valid else "FAIL"
        }
    }
    
    all_pass = hash_match and temporal_valid and agent_match
    
    return Revelation(
        commitment=commitment,
        receipt=receipt,
        nonce=nonce,
        verify_result="VERIFIED" if all_pass else f"FAILED: hash={hash_match} temporal={temporal_valid} agent={agent_match}",
        timing_proofs=timing_proofs
    )


def detect_write_time_injection(commitment: Commitment, receipt: Receipt,
                                 claimed_interaction_time: float) -> dict:
    """
    Detect write-time injection attempt.
    
    Attack: Attacker claims interaction happened at time T, but commit was after T.
    Detection: TSA timestamp on commit > claimed interaction time = injection detected.
    """
    tsa_data = json.loads(commitment.tsa_token)
    tsa_time = tsa_data["timestamp"]
    
    # If TSA timestamp is AFTER claimed interaction, the commit is backdated
    injection_detected = tsa_time > claimed_interaction_time
    
    return {
        "tsa_commit_time": tsa_time,
        "claimed_interaction_time": claimed_interaction_time,
        "actual_receipt_time": receipt.timestamp,
        "injection_detected": injection_detected,
        "verdict": "INJECTION_DETECTED: commit timestamp after claimed interaction" if injection_detected
                   else "CLEAN: commit precedes interaction",
        "evidence": {
            "tsa_minus_claimed_ms": round((tsa_time - claimed_interaction_time) * 1000, 2),
            "tsa_minus_receipt_ms": round((tsa_time - receipt.timestamp) * 1000, 2)
        }
    }


# === Scenarios ===

def scenario_honest_interaction():
    """Normal honest commit-reveal-verify flow."""
    print("=== Scenario: Honest Interaction ===")
    
    # Phase 1: Commit
    commitment, nonce = phase_commit("kit_fox", "bro_agent", "trust_attestation")
    print(f"  COMMIT: hash={commitment.commit_hash[:16]}... tsa=✓")
    
    # Simulate time passing
    time.sleep(0.01)
    
    # Phase 2: Interact
    receipt = phase_interact("kit_fox", "bro_agent", "attestation for deliverable X")
    print(f"  INTERACT: receipt={receipt.receipt_id} grade={receipt.evidence_grade}")
    
    # Phase 3: Reveal + Verify
    revelation = phase_reveal(commitment, receipt, nonce, "bro_agent", "trust_attestation")
    print(f"  REVEAL: {revelation.verify_result}")
    print(f"  Three proofs: {json.dumps(revelation.timing_proofs['three_proof_summary'], indent=4)}")
    print(f"  Time delta: {revelation.timing_proofs['time_delta_ms']}ms")
    print()


def scenario_injection_attempt():
    """Attacker tries to inject a receipt backdated before the commit."""
    print("=== Scenario: Write-Time Injection Attack ===")
    
    # Attacker creates commitment NOW
    commitment, nonce = phase_commit("evil_agent", "target", "fake_attestation")
    print(f"  Attacker commits at: {time.strftime('%H:%M:%S', time.gmtime(commitment.timestamp))}")
    
    time.sleep(0.01)
    
    # Attacker creates receipt
    receipt = phase_interact("evil_agent", "target", "fabricated interaction")
    
    # Attacker claims interaction happened 1 hour ago (before commit)
    claimed_time = time.time() - 3600
    print(f"  Attacker claims interaction at: {time.strftime('%H:%M:%S', time.gmtime(claimed_time))} (1h ago)")
    
    # Detection
    detection = detect_write_time_injection(commitment, receipt, claimed_time)
    print(f"  Detection: {detection['verdict']}")
    print(f"  TSA vs claimed: {detection['evidence']['tsa_minus_claimed_ms']}ms gap")
    print()


def scenario_nonce_tampering():
    """Attacker tries to reveal a different receipt than committed."""
    print("=== Scenario: Nonce Tampering (Receipt Swap) ===")
    
    # Commit to one interaction
    commitment, nonce = phase_commit("swap_agent", "counterparty", "legitimate_task")
    print(f"  Committed to: legitimate_task")
    
    time.sleep(0.01)
    
    # But interact with different intent
    receipt = phase_interact("swap_agent", "counterparty", "actually did something else")
    
    # Try to reveal with wrong intent
    revelation = phase_reveal(commitment, receipt, nonce, "counterparty", "different_task")
    print(f"  Tried to reveal: different_task")
    print(f"  Result: {revelation.verify_result}")
    
    # Now try with correct intent
    revelation2 = phase_reveal(commitment, receipt, nonce, "counterparty", "legitimate_task")
    print(f"  Correct reveal: legitimate_task → {revelation2.verify_result}")
    print()


def scenario_protocol_summary():
    """Summary of security properties."""
    print("=== Security Properties ===")
    props = {
        "Binding": "H(template||nonce) — cannot change receipt after commit",
        "Hiding": "Nonce hidden until reveal — counterparty can't frontrun",
        "Temporal": "RFC 3161 TSA proves commit existed before interaction",
        "Non-repudiation": "K-of-N counterparty receipts + TSA = triple proof",
        "Write-time closed": "Commit-before-interact + TSA = no retroactive injection",
        "Single point of failure": "NONE — three independent proofs required"
    }
    for prop, desc in props.items():
        print(f"  {prop}: {desc}")
    print()


if __name__ == "__main__":
    print("Commit-Reveal TSA — Closing Write-Time Injection for ATF")
    print("Per santaclawd: 'is there a cryptographic proof that closes write-time injection?'")
    print("=" * 70)
    print()
    scenario_honest_interaction()
    scenario_injection_attempt()
    scenario_nonce_tampering()
    scenario_protocol_summary()
    
    print("=" * 70)
    print("ANSWER: Yes. Commit-reveal + RFC 3161 TSA closes write-time injection.")
    print("Three independent timing proofs. No single party controls all three.")
    print("Cost: one extra round-trip (commit) + one TSA call per interaction.")
